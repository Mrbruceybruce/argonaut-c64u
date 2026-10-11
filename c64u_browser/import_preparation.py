# SPDX-License-Identifier: GPL-3.0-or-later
"""Core-owned, volatile one-use snapshot admission. No remote execution APIs."""
from dataclasses import dataclass, replace
from threading import Lock
import hashlib
import time
from uuid import uuid4

from .app_preferences import validate
from .ftp_reads import adapter_for, read_operation
from .import_policy import TransactionV2, ResourceAccounting
from .import_snapshots import SnapshotError, SnapshotEvidence, prepare_snapshots, refuse
from .jobs import CoreJob
from .scheduler import DeviceSession, JobBinding

CONFIRMATION_TEXT = 'Stage and Verify prepares files but does not import them into the Game Library.'
AUTHORIZATION_SECONDS = 120


@dataclass(frozen=True)
class SnapshotConfirmation:
    token: str
    transaction: TransactionV2
    expires_at: float
    message: str = CONFIRMATION_TEXT


@dataclass(frozen=True)
class SnapshotAuthorization:
    token: str


class SnapshotPreparation:
    """Bounded in-memory registry; serialized IDs never reconstruct authority."""
    def __init__(self, core):
        self.core = core
        self._lock = Lock()
        self._pending = {}
        self._authorized = {}
        self._ready = {}
        self._running = False
        self._closed = False
        self._cleanup_blocked = False
        self._cleaning = set()
        self.cleanup_evidence = None
        self._uncertain_owner = None
        self._generation = 0

    def invalidate(self):
        with self._lock:
            self._pending.clear();self._authorized.clear();self._generation += 1

    def _check(self, target, client, generation):
        tx = target.transaction
        with self._lock:
            refuse(not self._closed and self._generation == generation,
                   'snapshot-stale', 'Snapshot confirmation is no longer current.')
        refuse(time.monotonic() < target.expires_at, 'snapshot-expired', 'Snapshot authorization expired.')
        refuse(self.core._client is client and self.core.device_session() == DeviceSession(tx.library.device_id,tx.session_id),
               'snapshot-session', 'Device session changed. Confirm a new attempt.')
        refuse(self.core.preferences.game_library_location == tx.library.preference(),
               'snapshot-library', 'Selected library changed. Confirm a new attempt.')
        options = validate(self.core.preferences.app_options)
        refuse((options['import_batch_mib']*1048576,options['import_temp_mib']*1048576) ==
               (tx.budgets.batch_payload_limit,tx.budgets.temporary_disk_limit),
               'snapshot-policy', 'Import resource preferences changed. Prepare a new transaction.')
        tx.validate()

    def review(self, transaction, expected_session):
        refuse(type(transaction) is TransactionV2,'snapshot-policy','A new schema-2 transaction is required.')
        transaction.validate()
        with self.core._session_admission():
            client = self.core._require_client()
            refuse(expected_session == self.core.device_session(),'snapshot-session','Connection changed.')
            target = SnapshotConfirmation(uuid4().hex,transaction,time.monotonic()+AUTHORIZATION_SECONDS)
            with self._lock:generation = self._generation
            self._check(target,client,generation)
            with self._lock:
                refuse(not self._running and not self._ready and not self._cleanup_blocked,'admission_busy','Discard existing snapshots before a new attempt.')
                if len(self._pending) >= 32:self._pending.pop(next(iter(self._pending)))
                self._pending[target.token] = (target,client,generation)
            return target

    def confirm(self, target, *, confirmed):
        refuse(type(target) is SnapshotConfirmation,'snapshot-authorization','Unknown confirmation.')
        with self.core._session_admission():
            with self._lock:entry = self._pending.pop(target.token,None)
            refuse(entry is not None and entry[0] is target,'snapshot-authorization','Confirmation is stale or already used.')
            if confirmed is False:return None
            refuse(confirmed is True,'snapshot-authorization','Explicit confirmation is required.')
            self._check(*entry)
            authorization = SnapshotAuthorization(uuid4().hex)
            with self._lock:
                if len(self._authorized) >= 32:self._authorized.pop(next(iter(self._authorized)))
                self._authorized[authorization.token] = (authorization,entry)
            return authorization

    def _manifest(self, target, client, check):
        from .managed_library import ManagedLibraryReader
        from .native_files import read_remote_game
        tx = target.transaction;captured = []
        def read(path, limit):
            data = read_remote_game(client,path,limit,check=check);captured.append(data);return data
        check()
        library = ManagedLibraryReader(client.list_directory,read,
            DeviceSession(tx.library.device_id,tx.session_id),check).load(tx.library.path,tx.library.library_id)
        refuse(library.identity == tx.library and library.revision == tx.manifest_revision and
               captured and hashlib.sha256(captured[0]).hexdigest() == tx.manifest_digest,
               'snapshot-manifest','Library manifest changed. Prepare a new transaction.')
        check()

    def prepare(self, authorization, *, temporary_parent):
        refuse(type(authorization) is SnapshotAuthorization,'snapshot-authorization','Explicit snapshot authorization required.')
        # Even a busy/session admission failure consumes this one-use capability.
        with self._lock:entry = self._authorized.pop(authorization.token,None)
        refuse(entry is not None and entry[0] is authorization,'snapshot-authorization','Authorization is unknown or already used.')
        target,client,generation = entry[1]
        with self.core._session_admission():
            self._check(target,client,generation)
            with self._lock:
                refuse(not self._running and not self._ready and not self._cleanup_blocked,'admission_busy','Snapshot preparation is already owned.')
                self._running = True
            def task(job):
                owned = None;evidence = None
                def check():
                    job.check_cancel();self._check(target,client,generation)
                def remote(item,sink,budget,check):
                    adapter = adapter_for(client)
                    refuse(adapter is not None,'snapshot-session','Managed source reader unavailable.')
                    return adapter.read_into(item.source.path,sink,expected_bytes=item.size,budget=budget,check=check)
                try:
                    with read_operation(client,check):
                        self._manifest(target,client,check)
                        owned,evidence = prepare_snapshots(target.transaction,temporary_parent,remote,check,job.report)
                        self._manifest(target,client,check)
                    # Serialize the final identity check with reconnect/selection changes.
                    with self.core._session_admission():
                        check()
                        with self._lock:
                            refuse(not self._closed,'snapshot-stale','Core is shutting down.')
                            key = uuid4().hex
                            result = replace(evidence,snapshot_id=key)
                            self._ready[key] = (owned,result)
                            owned = None
                        return result
                except BaseException as exc:
                    if owned:
                        try:cleaned = owned.cleanup()
                        except BaseException:cleaned = False
                        exc.snapshot_evidence = replace(evidence,status='canceled' if getattr(exc,'cancelled',False) else 'failed',
                                                       cleanup_complete=cleaned)
                    raise
            def failure(exc):
                result = getattr(exc,'snapshot_evidence',SnapshotEvidence(target.transaction.id,
                    'canceled' if getattr(exc,'cancelled',False) else 'failed',0,len(target.transaction.items),ResourceAccounting(),True))
                if not result.cleanup_complete:
                    with self._lock:
                        self._cleanup_blocked = True
                        self.cleanup_evidence = result
                        self._uncertain_owner = getattr(exc,'snapshot_owner',None)
                return result
            job = CoreJob('game-library.import-snapshots',task,failure_result=failure)
            def finished(event):
                if event.kind == 'finished':
                    with self._lock:self._running = False
            job.add_listener(finished)
            try:return self.core.scheduler.submit(job,JobBinding.device(self.core.device_session()),reject_busy=True)
            except BaseException:
                with self._lock:self._running = False
                raise

    def discard(self, result):
        with self._lock:
            entry = self._ready.get(getattr(result,'snapshot_id',''))
            refuse(entry is not None and entry[1] is result,'snapshot-ownership','Unknown snapshot ownership.')
            refuse(not self._cleanup_blocked and result.snapshot_id not in self._cleaning,
                   'admission_busy','Snapshot cleanup is active or requires recovery review.')
            # Retain _ready throughout cleanup: it owns admission and disk usage.
            self._cleaning.add(result.snapshot_id)
        cleaned = False
        try:
            cleaned = entry[0].cleanup()
            return cleaned
        finally:
            # Cancellation/exception is uncertain, never an implicit release.
            with self._lock:
                self._cleaning.discard(result.snapshot_id)
                self.cleanup_evidence = replace(result,
                    status='discarded' if cleaned else 'cleanup-uncertain',
                    cleanup_complete=cleaned)
                if cleaned:self._ready.pop(result.snapshot_id)
                else:self._cleanup_blocked = True

    def close(self):
        with self._lock:
            self._closed = True;self._generation += 1
            self._pending.clear();self._authorized.clear()
            # Do not race an active discard or retry unresolved cleanup.
            ready = tuple(result for key,(owned,result) in self._ready.items()
                          if key not in self._cleaning and not self._cleanup_blocked)
        for result in ready:
            try:self.discard(result)
            except Exception:pass  # discard retained ownership and uncertainty evidence.
