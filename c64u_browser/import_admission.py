# SPDX-License-Identifier: GPL-3.0-or-later
"""Core-owned read-only execution admission. No remote mutation dispatcher."""
from dataclasses import dataclass, replace
import hashlib
import json
from threading import Lock
import time
from uuid import uuid4

from .app_preferences import validate
from .ftp_reads import adapter_for
from .import_capacity import reserve_capacity
from .import_execution import ExecutionLimits, ExecutionAccounting, ExecutionTransaction, execution_transaction
from .import_execution_store import ExecutionJournalStore, _definite_creation_refusal
from .import_preparation import AUTHORIZATION_SECONDS
from .import_snapshots import ReadAllowance, refuse, validate_owned_snapshots, check_snapshot_identity
from .import_transaction import canonical, MiB
from .managed_library import ManagedLibraryReader
from .scheduler import DeviceSession, JobBinding


@dataclass(frozen=True)
class ExecutionConfirmation:
    token: str
    transaction: ExecutionTransaction
    expires_at: float
    message: str = ('Confirm this device, selected library and listed payloads for staging and verification only. '
                    'This checkpoint performs read-only admission; it does not upload or import games.')


@dataclass(frozen=True)
class ExecutionAuthorization:
    token: str


@dataclass(frozen=True)
class AdmissionEvidence:
    transaction_id: str
    status: str
    snapshot_validation_reads: int
    control_read_bytes: int
    capacity_bytes: int
    capacity_revisions: int
    journal_state: str
    # Returning evidence never extends authority beyond the resource lifetime.
    mutation_enabled: bool = False


class ExecutionAdmission:
    confirmation_type = ExecutionConfirmation
    authorization_type = ExecutionAuthorization
    execution_policy_version = 1

    def __init__(self, core):
        self.core = core
        self._lock = Lock()
        self._pending = {}
        self._authorized = {}
        self._running = False

    def invalidate(self):
        with self._lock:
            self._pending.clear(); self._authorized.clear()

    def _check(self, entry, *, expiry=True):
        target, client, generation, owner, snapshots = entry
        tx = target.transaction; preparation = self.core._import_preparation
        with preparation._lock:
            ready = preparation._ready.get(snapshots.snapshot_id)
            refuse(not preparation._closed and preparation._generation == generation and
                   not preparation._cleanup_blocked and ready is not None and
                   ready[0] is owner and ready[1] is snapshots and not owner.closed,
                   'execution-stale', 'Execution confirmation or snapshot ownership is stale.')
        refuse(not expiry or time.monotonic() < target.expires_at,
               'execution-expired', 'Execution confirmation expired.')
        refuse(self.core._client is client and self.core.device_session() ==
               DeviceSession(tx.library.device_id, tx.session_id),
               'execution-session', 'Device session or client changed.')
        refuse(self.core.preferences.game_library_location == tx.library.preference(),
               'execution-library', 'Selected library changed.')
        options = validate(self.core.preferences.app_options)
        refuse((options['import_batch_mib']*MiB, options['import_temp_mib']*MiB) ==
               (tx.budgets.batch_payload_limit, tx.budgets.temporary_disk_limit),
               'execution-policy', 'Import resource policy changed.')
        tx.validate(); snapshots.accounting.validate()
        refuse(snapshots.transaction_id == tx.id and snapshots.status == 'snapshots-ready' and
               snapshots.files_completed == snapshots.files_total == len(tx.items) and
               snapshots.accounting.snapshot_read_bytes <= tx.budgets.snapshot_read_allowance and
               snapshots.accounting.temporary_disk_peak_bytes <= tx.budgets.temporary_disk_limit and
               snapshots.accounting.upload_bytes == snapshots.accounting.readback_bytes == 0,
               'execution-snapshot', 'Incomplete or over-budget snapshot evidence.')

    def review(self, snapshots, expected_session):
        with self.core._session_admission():
            refuse(expected_session == self.core.device_session(), 'execution-session', 'Device session changed.')
            preparation = self.core._import_preparation
            owner = preparation.execution_owner(snapshots)
            original = owner.transaction
            digest = hashlib.sha256(json.dumps(canonical(snapshots), sort_keys=True,
                separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
            tx = execution_transaction(original, snapshot_evidence_sha256=digest,
                limits=ExecutionLimits(original.budgets.planned_upload_bytes, MiB, 16*MiB))
            if self.execution_policy_version == 3:
                from .import_execution_v4 import new_transaction
                tx = new_transaction(tx)
            else:
                tx = replace(tx, execution_policy_version=self.execution_policy_version).validate()
            target = self.confirmation_type(uuid4().hex, tx, time.monotonic()+AUTHORIZATION_SECONDS)
            with preparation._lock:generation = preparation._generation
            entry = (target, self.core._require_client(), generation, owner, snapshots)
            self._check(entry)
            with self._lock:
                refuse(not self._running, 'admission_busy', 'Execution admission is active.')
                if len(self._pending) >= 32:self._pending.pop(next(iter(self._pending)))
                self._pending[target.token] = entry
            return target

    def confirm(self, target, *, confirmed):
        refuse(type(target) is self.confirmation_type, 'execution-authorization', 'Unknown execution confirmation.')
        with self._lock:entry = self._pending.pop(target.token, None)
        refuse(entry is not None and entry[0] is target, 'execution-authorization', 'Confirmation is copied, stale or used.')
        if confirmed is False:return None
        refuse(confirmed is True, 'execution-authorization', 'Explicit execution confirmation required.')
        with self.core._session_admission():
            self._check(entry)
            authorization = self.authorization_type(uuid4().hex)
            with self._lock:
                if len(self._authorized) >= 32:self._authorized.pop(next(iter(self._authorized)))
                self._authorized[authorization.token] = (authorization, entry)
            return authorization

    def admit(self, authorization, *, journal_directory, check_cancel=lambda: None):
        refuse(type(authorization) is ExecutionAuthorization, 'execution-authorization', 'Execution confirmation required.')
        # Pop before session, scheduler, ownership, capacity or FTP admission.
        with self._lock:registered = self._authorized.pop(authorization.token, None)
        refuse(registered is not None and registered[0] is authorization,
               'execution-authorization', 'Authorization is copied, cross-Core, stale or used.')
        entry = registered[1]; target, client, generation, owner, snapshots = entry
        tx = target.transaction; claimed = running = False; writer = None; uncertain = False
        reads = ReadAllowance(tx.limits.snapshot_validation_reads)
        control = ReadAllowance(tx.limits.control_read_bytes)
        persistence_started = False
        definite_refusal = False
        capacity = None; operation_id = str(uuid4())
        def evidence(status):
            return AdmissionEvidence(tx.id, status, reads.consumed, control.consumed,
                capacity.aggregate_bytes if capacity else 0, capacity.revisions if capacity else 0,
                ('persistence-uncertain' if writer and writer.blocked else writer.current.state if writer else
                 'not-created' if definite_refusal or not persistence_started else 'creation-uncertain'))
        def check():
            check_cancel(); self._check(entry)
        try:
            with self.core._session_admission():
                check()
                with self._lock:
                    refuse(not self._running, 'admission_busy', 'Execution admission already owned.')
                    self._running = running = True
                self.core._import_preparation.claim_execution(snapshots, owner); claimed = True
            capacity = reserve_capacity(tx); check()
            # Snapshot ownership encloses the scheduler and FTP lifetimes. Their
            # contexts drain in reverse order before ownership can be released.
            with self.core.scheduler.inline(JobBinding.device(DeviceSession(tx.library.device_id, tx.session_id)),
                                            reject_busy=True) as scheduler_check:
                def current():
                    scheduler_check(); check()
                current()
                adapter = adapter_for(client)
                refuse(adapter is not None, 'execution-transport', 'Managed read-only FTP transport required.')
                persistence_started = True
                writer = ExecutionJournalStore(journal_directory).create_reserved(tx)
                writer.transition('awaiting-confirmation', previous=writer.current)
                writer.transition('staging', previous=writer.current)
                writer.intent(operation_id, 'snapshot-validation', '', previous=writer.current)
                with adapter.operation(current, reject_busy=True):
                    def listing(path):
                        current()
                        actual, rows = adapter.list_directory(path, budget=control, allow_fallback=False)
                        names = [row.name.casefold() for row in rows]
                        refuse(actual == path and len(names) == len(set(names)) and all(
                            row.name not in ('', '.', '..') and '/' not in row.name and '\\' not in row.name and
                            row.kind in ('file', 'dir') for row in rows),
                            'execution-listing', 'Directory identity or entries are ambiguous.')
                        current(); return actual, rows
                    def remote_manifest():
                        captured = []
                        def read(path, maximum):
                            data = adapter.read(path, maximum, check=current, budget=control)
                            captured.append(data); return data
                        reader = ManagedLibraryReader(listing, read,
                            DeviceSession(tx.library.device_id, tx.session_id), current)
                        library = reader.load(tx.library.path, tx.library.library_id)
                        refuse(library.identity == tx.library and library.revision == tx.manifest_revision and
                               len(captured) == 1 and hashlib.sha256(captured[0]).hexdigest() == tx.manifest_digest,
                               'execution-manifest', 'Manifest identity, revision or digest changed.')
                        root_rows = listing(tx.library.path)[1]
                        refuse(tx.directory.casefold() not in {r.name.casefold() for r in root_rows},
                               'execution-collision', 'Transaction destination already exists.')
                        game_names = {r.name.casefold() for r in listing(tx.library.path+'/games')[1]}
                        refuse(not any(i.final_path.split('/')[-1].casefold() in game_names for i in tx.items),
                               'execution-collision', 'Intended destination already exists.')
                    current(); remote_manifest(); current()
                    try:
                        validate_owned_snapshots(owner, owner.transaction, reads, current)
                        current(); remote_manifest(); current()
                        check_snapshot_identity(owner, owner.transaction)
                    except OSError:
                        uncertain = True
                        raise
                    writer.outcome(operation_id, 'completed', previous=writer.current,
                        size=reads.consumed, accounting=ExecutionAccounting(
                            snapshot_validation_reads=reads.consumed, control_read_bytes=control.consumed))
                    current()
                    # No executor is installed in this slice. End this attempt
                    # durably; the report cannot be replayed as mutation authority.
                    writer.transition('canceled', previous=writer.current, reason='read-only-admission-complete')
                    current()
            check()
            return evidence('admission-checked')
        except BaseException as exc:
            definite_refusal = writer is None and _definite_creation_refusal(exc)
            uncertain = uncertain or getattr(exc, 'code', '') == 'execution-snapshot' or bool(writer and writer.blocked) or (persistence_started and writer is None and not definite_refusal)
            if writer is not None and not writer.blocked and writer.current.state not in ('failed', 'canceled', 'uncertain'):
                try:
                    if writer.current.operations and writer.current.operations[-1].outcome == 'intent':
                        writer.outcome(operation_id, 'rejected', previous=writer.current,
                            size=reads.consumed, accounting=ExecutionAccounting(
                                snapshot_validation_reads=reads.consumed, control_read_bytes=control.consumed),
                            terminal_state='canceled' if getattr(exc, 'cancelled', False) else 'failed', reason='admission-stopped')
                    else:
                        writer.transition('canceled' if getattr(exc, 'cancelled', False) else 'failed',
                                          previous=writer.current, reason='admission-stopped')
                except BaseException:
                    uncertain = True
                    exc.add_note('Journal persistence failed; retained intent requires inspection.')
            exc.execution_evidence = evidence('canceled' if getattr(exc, 'cancelled', False) else 'failed')
            raise
        finally:
            try:
                if claimed:self.core._import_preparation.release_execution(snapshots, uncertain=uncertain)
            finally:
                if running:
                    with self._lock:self._running = False
