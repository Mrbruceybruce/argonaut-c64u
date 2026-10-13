# SPDX-License-Identifier: GPL-3.0-or-later
"""Core-owned one-use managed staging. No publication, recovery or remote cleanup."""
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import io
import os
import stat
from uuid import uuid4

from .ftp_reads import adapter_for
from .import_admission import ExecutionAdmission
from .import_capacity import reserve_capacity
from .import_transaction import TransactionError
from .import_execution import ExecutionTransaction, ExecutionAccounting as Accounting
from .import_execution_policy4 import encode_record
from .import_execution_store import ExecutionJournalStore, _definite_creation_refusal
from .import_snapshots import (ReadAllowance, refuse, check_snapshot_identity,
    validate_owned_snapshots, file_identity)
from .managed_library import ManagedLibraryReader
from .scheduler import DeviceSession, JobBinding


@dataclass(frozen=True)
class StagingConfirmation:
    token: str
    transaction: ExecutionTransaction
    expires_at: float

    @property
    def message(self):
        tx = self.transaction
        return (f'Stage and independently verify transaction {tx.id} on device {tx.library.device_id}, '
                f'library {tx.library.library_id} at {tx.library.path} on root {tx.library.root}. Create {tx.directory}, '
                'upload transaction.json and these approved payloads: ' +
                ', '.join(f'{i.final_path} ({i.size} bytes, SHA-256 {i.sha256})' for i in tx.items) +
                '. Remote leftovers will be retained on failure. This does not import or publish games. '
                'You must explicitly acknowledge that no other FTP client, Argonaut instance or '
                'C64U-side operation will modify the selected managed-library storage during staging. '
                'This is an exclusive-writer operating requirement, not a technical lock. Ordinary '
                'FTP STOR may overwrite a file created by an external writer after our absence check.')


@dataclass(frozen=True)
class StagingAuthorization:
    token: str


@dataclass(frozen=True)
class StagingReceipt:
    transaction: ExecutionTransaction
    state: str
    accounting: Accounting
    verified_artifacts: tuple[tuple[str, int, str], ...]
    # Historical readback observations, not immutable/current remote-content proof.
    # Later publication must independently rehash the record and payloads and
    # revalidate manifest identity, destination collisions and device/library bindings.
    # Receipt data never reconstructs execution, cleanup or publication authority.

    @property
    def evidence_scope(self):
        return 'point-in-time'

    @property
    def requires_publication_revalidation(self):
        return True


@dataclass(frozen=True)
class StagingFailure:
    transaction_id: str
    journal_state: str
    accounting: Accounting
    remote_effects_possible: bool
    inspection_required: bool
    unsaved_context: object = None
    unsaved_mkd_proof: object = None


class StagingAdmission(ExecutionAdmission):
    confirmation_type = StagingConfirmation
    authorization_type = StagingAuthorization
    execution_policy_version = 4

    def confirm(self, target, *, confirmed, exclusive_writer_acknowledged=False):
        # Only this staging-specific confirmation path mints a registered capability.
        # The acknowledgment applies to the exact reviewed object and its bindings;
        # it is not another transferable token or serialized journal permission.
        if confirmed is not False:
            refuse(exclusive_writer_acknowledged is True, 'staging-exclusive-writer',
                   'Explicit exclusive-writer acknowledgment is required for staging.')
        return super().confirm(target, confirmed=confirmed)

    def stage(self, authorization, *, journal_directory, check_cancel=lambda: None):
        refuse(type(authorization) is StagingAuthorization, 'staging-authorization',
               'Fresh staging-only confirmation required.')
        with self._lock:registered = self._authorized.pop(authorization.token, None)
        refuse(registered is not None and registered[0] is authorization, 'staging-authorization',
               'Staging authorization is copied, cross-Core, stale or already used.')
        # Registration proves staging confirmation included the exclusive-writer
        # acknowledgment. Consumption precedes scheduler/FTP admission.
        entry = registered[1]
        target, client, generation, owner, snapshots = entry
        execution = _Staging(self, entry, journal_directory, check_cancel)
        claimed = running = False
        try:
            with self.core._session_admission():
                execution.check()
                with self._lock:
                    refuse(not self._running, 'admission_busy', 'Staging is already active.')
                    self._running = running = True
                self.core._import_preparation.claim_execution(snapshots, owner); claimed = True
            reserve_capacity(target.transaction)
            execution.check()
            with self.core.scheduler.inline(JobBinding.device(DeviceSession(
                    target.transaction.library.device_id, target.transaction.session_id)), reject_busy=True) as scheduler_check:
                execution.scheduler_check = scheduler_check
                execution.check()
                execution.adapter = adapter_for(client)
                refuse(execution.adapter is not None, 'staging-transport', 'Managed FTP transport required.')
                execution.creating = True
                execution.writer = ExecutionJournalStore(journal_directory).create_reserved(target.transaction)
                execution.writer.transition('awaiting-confirmation', previous=execution.writer.current)
                execution.writer.transition('staging', previous=execution.writer.current)
                # Handle durable terminal evidence before releasing the FTP lease
                # and scheduler. Ownership lasts through persistence uncertainty.
                try:
                    with execution.adapter.operation(execution.check, reject_busy=True):
                        try:return execution.run()
                        except BaseException as exc:
                            execution.fail(exc)
                            raise
                except BaseException as exc:
                    execution.fail(exc)
                    raise
        except BaseException as exc:
            execution.fail(exc)
            exc.staging_evidence = execution.failure()
            raise
        finally:
            try:
                if claimed:self.core._import_preparation.release_execution(snapshots, uncertain=execution.block_cleanup)
            finally:
                if running:
                    with self._lock:self._running = False


@contextmanager
def _snapshot_stream(owner, ordinal, check):
    """Open a sealed member by held directory; never reopen its original source."""
    check_snapshot_identity(owner, owner.transaction)
    name = f'item-{ordinal:04d}.snapshot'
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=owner.directory)
    try:
        def verify():
            held = os.fstat(fd); named = os.stat(name, dir_fd=owner.directory, follow_symlinks=False)
            refuse(stat.S_ISREG(held.st_mode) and held.st_nlink == named.st_nlink == 1 and
                   file_identity(held) == file_identity(named) == owner.sealed[name],
                   'execution-snapshot', 'Pinned snapshot identity changed.')
        verify()
        class Stream:
            def read(self, amount):
                check(); verify()
                data = os.read(fd, min(amount, 8192))
                verify()
                return data
        yield Stream()
    finally:os.close(fd)


class _Staging:
    def __init__(self, admission, entry, directory, cancel):
        self.admission = admission; self.entry = entry; self.tx = entry[0].transaction
        self.owner = entry[3]; self.directory = directory; self.cancel = cancel
        self.writer = self.adapter = None; self.scheduler_check = lambda: None
        self.admitted = self.creating = self.remote_possible = self.block_cleanup = False
        self.handled = False
        self.unsaved_context = None
        tx = self.tx
        self.snapshot_reads = ReadAllowance(tx.limits.snapshot_validation_reads)
        self.control_reads = ReadAllowance(tx.limits.control_read_bytes)
        self.control_writes = ReadAllowance(tx.limits.control_upload_bytes)
        self.uploads = ReadAllowance(tx.budgets.upload_allowance)
        self.readbacks = ReadAllowance(tx.budgets.readback_allowance)
        self.confirmed = 0
        self.members = {}
        self.observed_size = 0; self.observed_hash = ''
        self.op_unknown = False; self.collision = False; self.mkd_proof = None

    def check(self):
        self.scheduler_check(); self.cancel()
        self.admission._check(self.entry, expiry=not self.admitted)
        refuse(self.adapter is None or adapter_for(self.entry[1]) is self.adapter,
               'staging-transport', 'Managed adapter ownership changed.')

    def accounting(self):
        return Accounting(self.snapshot_reads.consumed, self.uploads.consumed, self.confirmed,
            self.uploads.consumed-self.confirmed, self.readbacks.consumed,
            self.control_writes.consumed, self.control_reads.consumed)

    def failure(self):
        state = ('persistence-uncertain' if self.writer and self.writer.blocked else
                 self.writer.current.state if self.writer else 'creation-uncertain' if self.creating else 'not-created')
        return StagingFailure(self.tx.id, state, self.accounting(), self.remote_possible, self.block_cleanup, self.unsaved_context, self.mkd_proof if self.unsaved_context is not None else None)

    def fail(self, exc):
        if self.handled:return
        self.handled = True
        definite_refusal = self.writer is None and _definite_creation_refusal(exc)
        if definite_refusal:self.creating = False
        self.block_cleanup = (self.block_cleanup or self.remote_possible or bool(self.writer and self.writer.blocked) or
            self.creating and self.writer is None or getattr(exc, 'code', '') == 'execution-snapshot' or
            isinstance(exc, OSError) and not definite_refusal)
        w = self.writer
        if w and not w.blocked and w.current.state not in ('failed','canceled','uncertain','verified-staged'):
            try:
                # A pending intent here means outcome persistence was not safely
                # possible. Never erase it or invent a definite non-submission.
                pending = w.current.operations and w.current.operations[-1].outcome == 'intent'
                state = 'uncertain' if pending else 'canceled' if getattr(exc,'cancelled',False) else 'failed'
                w.transition(state, previous=w.current, reason='staging-stopped')
            except BaseException:
                self.block_cleanup = True
                exc.add_note('Terminal staging evidence could not be persisted; inspection required.')

    def listing(self, path):
        self.check()
        actual, rows = self.adapter.list_directory(path, budget=self.control_reads, allow_fallback=False)
        names = [r.name.casefold() for r in rows]
        refuse(actual == path and len(names) == len(set(names)) and all(
            r.name not in ('','.','..') and '/' not in r.name and '\\' not in r.name and
            r.kind in ('file','dir') for r in rows), 'staging-listing', 'Ambiguous directory identity or members.')
        self.check()
        return actual, rows

    def library(self, *, created):
        captured = []
        def read(path, maximum):
            data = self.adapter.read(path, maximum, check=self.check, budget=self.control_reads)
            captured.append(data); return data
        tx = self.tx; self.check()
        lib = ManagedLibraryReader(self.listing, read, DeviceSession(tx.library.device_id,tx.session_id),self.check).load(
            tx.library.path, tx.library.library_id)
        refuse(lib.identity == tx.library and lib.revision == tx.manifest_revision and len(captured)==1 and
               hashlib.sha256(captured[0]).hexdigest()==tx.manifest_digest,
               'staging-manifest', 'Approved manifest identity changed.')
        rows = self.listing(tx.library.path)[1]
        matches = [r for r in rows if r.name.casefold()==tx.directory.casefold()]
        if not created and matches:self.collision = True
        refuse((len(matches)==1 and matches[0].name==tx.directory and matches[0].kind=='dir') if created else not matches,
               'staging-collision', 'Transaction directory identity or absence changed.')
        names = {r.name.casefold() for r in self.listing(tx.library.path+'/games')[1]}
        refuse(not any(i.final_path.split('/')[-1].casefold() in names for i in tx.items),
               'staging-collision', 'Final destination name is occupied.')

    def membership(self, target=None):
        rows = self.listing(self.tx.library.path+'/'+self.tx.directory)[1]
        if target is not None and any(r.name.casefold()==target.casefold() for r in rows):
            self.collision = True
        refuse({r.name:r.size for r in rows if r.kind=='file'} == self.members and
               len(rows)==len(self.members), 'staging-membership', 'Unexpected transaction-directory contents.')

    def operation(self, kind, path, body):
        self.check(); w = self.writer
        oid = str(uuid4()); before = self.accounting()
        self.observed_size = 0; self.observed_hash = ''; self.op_unknown = False; self.collision = False; self.mkd_proof = None
        w.intent(oid,kind,path,previous=w.current,
                 collision='absent' if kind in ('mkdir','record-upload','upload') else 'not-applicable')
        def values():
            after = self.accounting()
            delta = Accounting(**{name:getattr(after,name)-getattr(before,name) for name in before.__dataclass_fields__})
            size = (delta.snapshot_validation_reads if kind=='snapshot-validation' else
                    delta.readback_bytes if kind=='readback' else self.observed_size)
            return dict(size=size,sha256=self.observed_hash,accounting=delta,mkd_proof=self.mkd_proof)
        try:
            body()
            # No cooperative check here: accepted mutations must be durable first.
            w.outcome(oid,'completed',previous=w.current,**values())
        except BaseException as exc:
            wire = getattr(exc,'ftp_error',None)
            unknown = self.op_unknown or bool(wire and wire.outcome == 'unknown')
            invalid_proof = kind == 'mkdir' and isinstance(exc, TransactionError)
            if invalid_proof:
                # Reject the observation rather than silently dropping its fields
                # into a different, valid outcome. fail() retains unresolved intent.
                self.block_cleanup = True
                exc.add_note('Invalid MKD proof rejected; durable intent retained without an outcome.')
            if not invalid_proof and not w.blocked and w.current.operations[-1].outcome=='intent':
                try:
                    status = ('unknown' if unknown else 'not-started' if self.mkd_proof is not None and
                              not self.mkd_proof.consequential_submitted else 'rejected')
                    w.outcome(oid,status,previous=w.current,
                        terminal_state='uncertain' if unknown else 'canceled' if getattr(exc,'cancelled',False) else 'failed',
                        collision='present' if self.collision and kind in ('mkdir','record-upload','upload') and not unknown else None,
                        reason=getattr(exc,'code','') if getattr(exc,'code','') in (
                            'staging-collision','staging-membership','staging-manifest','staging-readback',
                            'execution-snapshot','staging-upload','snapshot-read-budget','mkd-unobserved') else 'staging-stopped',**values())
                except BaseException:
                    self.block_cleanup = True
                    exc.add_note('Staging outcome persistence failed; retained intent requires inspection.')
            raise

    def binding_valid(self):
        # No cooperative cancellation here: accepted observations go to disk first.
        try:
            self.admission._check(self.entry, expiry=False)
            return adapter_for(self.entry[1]) is self.adapter
        except Exception: return False

    def mkdir(self):
        self.check(); w = self.writer; oid = str(uuid4()); before = self.accounting()
        self.collision = False; self.mkd_proof = None; self.op_unknown = False
        context = self.adapter.staging_context_binding(self.tx, oid)
        self.unsaved_context = context
        w.intent(oid, 'mkdir', self.tx.directory, previous=w.current, collision='absent', context=context)
        def accounting():
            now = self.accounting()
            return Accounting(**{name:getattr(now,name)-getattr(before,name) for name in before.__dataclass_fields__})
        def persist(phase, **kw):
            self.unsaved_context = context
            w.context_checkpoint(context, phase, previous=w.current, accounting=accounting(), **kw)
            self.unsaved_context = None
        def stopped(exc):
            if w.blocked or w.current.operations[-1].outcome != 'intent': return
            if isinstance(exc, TransactionError):
                self.block_cleanup = True
                exc.add_note('Invalid context/MKD proof rejected; durable intent retained without an outcome.')
                return  # Invalid projection must not be laundered into an outcome.
            status = ('unknown' if self.op_unknown else 'rejected' if self.collision else 'not-started')
            if self.mkd_proof is not None:
                status = ('not-started' if not self.mkd_proof.consequential_submitted else
                          'rejected' if self.mkd_proof.acknowledgment == 'rejected' else 'unknown')
            try:
                persist('stopped', status=status, mkd_proof=self.mkd_proof,
                    terminal_state='uncertain' if status == 'unknown' else 'canceled' if getattr(exc,'cancelled',False) else 'failed',
                    reason='staging-stopped', collision='present' if self.collision else None)
            except BaseException:
                self.block_cleanup = True
                exc.add_note('Context outcome persistence failed; retained intent requires inspection.')
        try:
            self.library(created=False)
            check_snapshot_identity(self.owner, self.owner.transaction)
            self.check(); self.admitted = True
            refuse(context.provenance == 'live-rest', 'staging-context', 'Live identity required for context.')
            with self.adapter.staging_context(context) as guard:
                try:
                    for verb, phase in (('CWD', 'cwd-observed'), ('PWD', 'pwd-observed')):
                        self.check()
                        observed, error = guard.observe(verb)
                        if not self.binding_valid():
                            from .import_context_evidence import classification
                            observed = replace(observed, binding_after=False)
                            observed = replace(observed, completion=classification(observed, verb)).validate(verb)
                        context = replace(context, **{verb.lower(): observed})
                        self.unsaved_context = context
                        if observed.completion != 'accepted':
                            if error is not None: raise error
                            refuse(False, 'staging-context', 'FTP root context is unqualified.')
                        persist(phase)
                    self.check()
                    refuse(guard.valid() and self.binding_valid(), 'staging-context', 'Context ownership changed.')
                    persist('mkd-intent')
                    self.check()
                    refuse(guard.valid() and self.binding_valid(), 'staging-context', 'Context ownership changed before MKD dispatch.')
                    evidence = error = None
                    try:
                        evidence = guard.mkdir()
                        self.remote_possible = self.op_unknown = True
                    except BaseException as exc:
                        error = exc
                        wire = getattr(exc, 'ftp_error', exc)
                        mutation = getattr(wire, 'mutation', None)
                        if mutation is not None and mutation.consequential_submitted:
                            self.remote_possible = True
                            self.op_unknown = mutation.acknowledgment != 'rejected'
                    owner_valid = guard.valid() and self.binding_valid()
                    context = replace(context, mkd_lease_id=guard.client.identity.ftp_session_id, mkd_owner_valid=owner_valid)
                    self.unsaved_context = context
                    self.mkd_proof = self.adapter.classify_staging_mkdir(self.tx, oid, result=evidence,
                        error=error, context_valid=owner_valid)
                    if self.mkd_proof is None:
                        self.remote_possible = self.op_unknown = True
                        raise TransactionError('MKD observation unavailable; retain durable intent.')
                    if error is not None: raise error
                    refuse(self.mkd_proof.decision in ('strict', 'firmware-compatible'),
                           'staging-mkdir', 'MKD lacks qualified path evidence.')
                    persist('mkd-observed', status='completed', mkd_proof=self.mkd_proof)
                    self.op_unknown = False
                except BaseException as exc:
                    stopped(exc)
                    raise
        except BaseException as exc:
            stopped(exc)
            raise

    def upload(self, path, source, expected, digest, *, control=False):
        # Refuse observed targets. STOR is not atomic create-if-absent: another
        # writer violating the acknowledged operating restriction can still race it.
        self.library(created=True); self.membership(path.split('/')[-1]); self.check()
        budget = self.control_writes if control else self.uploads
        evidence = None
        try:
            result = self.adapter.write_from(self.tx.library.path+'/'+path,source,expected,budget=budget)
            evidence = result.transfer
        except BaseException as exc:
            wire = getattr(exc,'ftp_error',None)
            evidence = wire.transfer if wire else None
            raise
        finally:
            if evidence is not None:
                self.observed_size = evidence.confirmed_sender_bytes
                self.observed_hash = evidence.sha256 or ''
                if not control:self.confirmed += evidence.confirmed_sender_bytes
                self.remote_possible |= evidence.submitted
                self.op_unknown = evidence.submitted and evidence.acknowledgment != 'rejected'
        refuse(evidence.acknowledgment=='completed' and
               (self.observed_size,self.observed_hash)==(expected,digest),
               'staging-upload', 'Upload acknowledgment or approved sender content differs.')
        self.op_unknown = False
        self.members[path.split('/')[-1]] = expected

    def readback(self, path, expected, digest, *, control=False):
        self.check(); budget=self.control_reads if control else self.readbacks
        before=budget.consumed; hashed=0; hasher=hashlib.sha256()
        class Sink:
            def write(_, block):
                nonlocal hashed
                hashed += len(block);hasher.update(block);return len(block)
        try:
            self.adapter.read_into(self.tx.library.path+'/'+path,Sink(),expected_bytes=expected,budget=budget)
            self.check()
            refuse(hashed==expected and hasher.hexdigest()==digest,
                   'staging-readback', 'Independent readback length or SHA-256 differs.')
        finally:
            self.observed_size=budget.consumed-before
            self.observed_hash=hasher.hexdigest() if hashed==self.observed_size else ''

    def run(self):
        tx=self.tx; record=encode_record(tx); record_hash=hashlib.sha256(record).hexdigest()
        def snapshot():
            self.library(created=False)
            validate_owned_snapshots(self.owner,self.owner.transaction,self.snapshot_reads,self.check)
            self.library(created=False)
            check_snapshot_identity(self.owner,self.owner.transaction)
        self.operation('snapshot-validation','',snapshot)
        self.mkdir()
        # This first membership observation proves visibility/emptiness after the
        # acknowledged MKD outcome was persisted, charged to record-upload intent.
        self.operation('record-upload',tx.record_path,
                       lambda:self.upload(tx.record_path,io.BytesIO(record),len(record),record_hash,control=True))
        for n,item in enumerate(tx.items,1):
            def send(n=n,item=item):
                with _snapshot_stream(self.owner,n,self.check) as source:
                    self.upload(item.staged_path,source,item.size,item.sha256)
            self.operation('upload',item.staged_path,send)
        self.check(); self.writer.transition('verifying',previous=self.writer.current)
        self.operation('record-readback',tx.record_path,
                       lambda:self.readback(tx.record_path,len(record),record_hash,control=True))
        for item in tx.items:
            self.operation('readback',item.staged_path,
                           lambda item=item:self.readback(item.staged_path,item.size,item.sha256))
        # Membership/size checks do not detect equal-length edits after readback.
        # The receipt records observations; a later publisher must verify afresh.
        def final():
            self.library(created=True);self.membership()
            check_snapshot_identity(self.owner,self.owner.transaction);self.check()
        self.operation('final-validation',tx.directory,final)
        self.check(); self.writer.transition('verified-staged',previous=self.writer.current)
        return StagingReceipt(tx,'verified-staged',self.accounting(),
            ((tx.record_path,len(record),record_hash),)+tuple((i.staged_path,i.size,i.sha256) for i in tx.items))
