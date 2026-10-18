# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Headless Core file operations built on Argonaut's validated file modules."""
from dataclasses import dataclass, field
from pathlib import Path
import copy
import hashlib
import os
import posixpath
import tempfile
import time
import uuid
from threading import Lock
from weakref import WeakKeyDictionary

from .api import BrowserError
from .storage import require_file_operation
from .diagnostics import cleanup_context, cleanup_event
from .deletion import prepare as prepare_deletion, delete_reviewed, snapshot as deletion_snapshot, _delete_recovery_file, VerifiedTargetAbsent
from .files import child, operate_managed
from .ftp_reads import read_operation, adapter_for
from .folder_copy import build_plan, execute_plan
from .jobs import CoreJob, JobCancelled, _current_job
from .scheduler import CoreScheduler, DeviceSession, JobBinding
from .native_files import read_local, read_remote, upload_flash, validate_upload, FlashEvidence


CORE_HOST = 'core-host'
C64U = 'c64u'
CLIENT_UPLOAD = 'client-upload'


@dataclass(frozen=True)
class FileLocation:
    """A path plus the filesystem that interprets it."""
    scope: str
    path: str
    artifact_id: str = ''

    @classmethod
    def core_host(cls, path): return cls(CORE_HOST,str(Path(path).expanduser().absolute()))
    @classmethod
    def c64u(cls, path): return cls(C64U,str(path))
    @classmethod
    def client_upload(cls, artifact_id, name=''):
        return cls(CLIENT_UPLOAD,name,artifact_id)


@dataclass(frozen=True)
class PartialUpload:
    """Recovery evidence; only the issuing FileService can authorize its use."""
    location: FileLocation
    device_id: str
    session_id: str


@dataclass(frozen=True)
class CopyRequest:
    source: FileLocation
    names: tuple[str, ...]
    destination: FileLocation


@dataclass(frozen=True)
class CopyPreview:
    plan_id: str
    source: FileLocation
    destination: FileLocation
    names: tuple[str, ...]
    conflicts: tuple[str, ...]
    replaceable: tuple[str, ...]
    operation_count: int
    created_at: float


@dataclass(frozen=True)
class CopyResult:
    completed: tuple[str, ...]
    skipped: tuple[str, ...]
    remaining: tuple[str, ...]
    partial_path: str | None = None
    failure: str = ''
    partial_upload: PartialUpload | None = None
    uploads: tuple = ()
    replacements: tuple = ()
    folder_steps: tuple = ()

    @property
    def message(self):
        return (f'{len(self.completed)} items completed; {len(self.skipped)} skipped; '
                f'{len(self.remaining)} unfinished.'+
                (' Stopped: '+self.failure if self.failure else ''))

    def details(self):
        text=self.message
        for title,items in (('Completed',self.completed),('Skipped',self.skipped),
                            ('Unfinished (first item failed)',self.remaining)):
            if items:text+='\n\n'+title+':\n'+'\n'.join(items)
        if self.partial_path:text+='\n\nPossible partial upload: '+self.partial_path
        for upload in self.uploads:
            if upload.inspection_message():text+='\n\n'+upload.inspection_message()
        for step in self.folder_steps:
            if step.inspection_message():text+='\n\n'+step.inspection_message()
        for replacement in self.replacements:
            if replacement.inspection_message():text+='\n\n'+replacement.inspection_message()
        return text


@dataclass(frozen=True)
class DeleteItem:
    path: str
    kind: str


@dataclass(frozen=True)
class DeletePreview:
    plan_id: str
    scope: str
    targets: tuple[str, ...]
    items: tuple[DeleteItem, ...]
    created_at: float


@dataclass(frozen=True)
class DeleteResult:
    removed: tuple[str, ...]
    total: int
    failure: str = ''
    stopped_target: str | None = None
    mutation: dict | None = None
    not_attempted: tuple[str, ...] = ()
    absent_target: str | None = None

    @property
    def message(self):
        uncertainty = (' Result uncertain for '+self.stopped_target+'.'
                       if self.mutation and self.mutation['outcome']=='unknown' else '')
        return (f'Deleted {len(self.removed)} of {self.total} item(s).'+uncertainty+
                (' Stopped: '+self.failure if self.failure else ''))


@dataclass(frozen=True)
class NativeUploadPreview:
    plan_id: str
    source: FileLocation
    destination: FileLocation
    size: int
    created_at: float


@dataclass(frozen=True)
class NativeUploadResult:
    destination: FileLocation
    size: int
    flash: FlashEvidence | None = None

    @property
    def message(self):
        return self.flash.message() if self.flash else "Flash upload did not start."


@dataclass
class _CopyPlan:
    request: CopyRequest
    plan: object
    session: DeviceSession | None
    created_at: float


@dataclass
class _DeletePlan:
    scope: str
    targets: tuple[str, ...]
    items: tuple
    session: DeviceSession | None
    created_at: float
    recovery: object = None


@dataclass
class _UploadOrigin:
    session: DeviceSession
    eligible: bool
    decision: str | None = None
    receipt: object = None
    retired: bool = False


@dataclass(frozen=True, eq=False)
class _CleanupEligibility:
    """One-shot handoff evidence, NOT a deletion plan or dispatch capability."""
    job_id: str
    session: DeviceSession
    partial_upload: PartialUpload


@dataclass
class _CleanupContinuation:
    record: PartialUpload
    session: DeviceSession
    state: str = 'issued'
    preparation: object = None
    plan_id: str | None = None


@dataclass
class _Recovery:
    record: PartialUpload
    session: DeviceSession
    path: str
    operation: str
    evidence: object
    origin: object = None
    state: str = "available"
    plan_id: str | None = None


@dataclass
class _NativePlan:
    source: FileLocation
    destination: FileLocation
    data: bytes = field(repr=False)
    session: DeviceSession
    created_at: float


class FileJobFailure(BrowserError):
    def __init__(self, code, message, result=None, retryable=False):
        super().__init__(message)
        self.code=code;self.result=result;self.retryable=retryable


class FileService:
    """Core-owned file plans and jobs; no transport or credentials escape."""
    def __init__(self, client_provider, session_provider, *, scheduler=None,
                 plan_ttl=300, plan_limit=128, clock=time.time, bound_profile_provider=None):
        self._bound_profile_provider=bound_profile_provider
        self._client_provider=client_provider
        self._session_provider=session_provider
        self._clock=clock
        self.plan_ttl=max(0,float(plan_ttl));self.plan_limit=max(0,int(plan_limit))
        self._scheduler=scheduler or CoreScheduler(self._device_session,clock=clock)
        self._copy_plans={};self._delete_plans={};self._native_plans={};self._fresh_plans={}
        self._flash_cleanup_plans={}
        self._lock=Lock()
        self._recoveries={}
        self._upload_origins=WeakKeyDictionary()
        self._cleanup_continuations=WeakKeyDictionary()
        self._recovery_closed=False

    def invalidate_recovery(self):
        """Drop session authority, including any outstanding recovery reviews."""
        with self._lock:
            self._invalidate_recovery_locked()

    def _invalidate_recovery_locked(self):
        for entry in self._recoveries.values():
            if entry.plan_id:self._delete_plans.pop(entry.plan_id,None)
        self._recoveries.clear()
        self._upload_origins.clear()
        for continuation in self._cleanup_continuations.values():continuation.state="retired"
        self._cleanup_continuations.clear()

    def close(self):
        with self._lock:
            self._recovery_closed=True
            self._invalidate_recovery_locked()

    def _prune_recovery_locked(self):
        current=self._device_session()
        for evidence,continuation in tuple(self._cleanup_continuations.items()):
            if continuation.session!=current:
                continuation.state="retired"
                self._cleanup_continuations.pop(evidence,None)
        for job,origin in tuple(self._upload_origins.items()):
            if origin.session!=current:self._upload_origins.pop(job,None)
        for key,entry in tuple(self._recoveries.items()):
            if entry.session!=current:
                if entry.plan_id:self._delete_plans.pop(entry.plan_id,None)
                self._recoveries.pop(key,None)

    def _partial_from_report(self, report, session, operation):
        """Internal issuance from executed transfer evidence, never a public claim.

        Reporting limitations must not erase transfer/cancellation accounting.
        """
        if not report.partial:return None
        evidence=next((item for item in report.uploads
                       if item.staging==report.partial and
                       item.disposition=='staging-candidate' and
                       item.stor and item.stor.get('submitted')),None)
        reason=''
        job=_current_job()
        with self._lock:
            self._prune_recovery_locked()
            if self._recovery_closed or session!=self._device_session() or not session.session_id:
                reason='The upload session ended.'
            elif (job not in self._upload_origins or
                  self._upload_origins[job].session!=session or
                  job.operation!=operation or evidence is None or operation not in ('file.copy.execute','usb.restore.execute')
                  or not (report.error or getattr(report,'cancelled',False))):
                reason='No qualifying staged-transfer evidence.'
            elif len(self._recoveries)>=32:
                reason='The session recovery limit of 32 entries was reached.'
            else:
                record=PartialUpload(FileLocation.c64u(evidence.staging),session.device_id,session.session_id)
                self._recoveries[id(record)]=_Recovery(record,session,evidence.staging,operation,copy.deepcopy(evidence),job)
                return record
        report.error=(report.error+' ' if report.error else '')+reason+' Partial cleanup authority was not issued; inspect the remote state explicitly.'
        return None

    def _register_upload_job(self, job, session, eligible):
        """Called only by trusted copy/restore submission, before scheduling."""
        with self._lock:
            if not self._recovery_closed and session==self._device_session():
                self._upload_origins[job]=_UploadOrigin(session,bool(eligible))

    def _upload_cancel_eligible(self, job):
        """Read-only presentation query; a label or operation name is not authority."""
        if not isinstance(job,CoreJob):return False
        with self._lock:
            self._prune_recovery_locked()
            origin=self._upload_origins.get(job)
            if (self._recovery_closed or origin is None or not origin.eligible or
                    origin.retired or origin.decision is not None):return False
            snapshot=job.snapshot()
            return (snapshot.operation in ('file.copy.execute','usb.restore.execute') and
                    snapshot.state in ('pending','queued','running') and
                    snapshot.device_id==origin.session.device_id and
                    snapshot.session_id==origin.session.session_id)

    def _request_upload_cancel(self, job, decision):
        """Intent-aware dialog entry point; ordinary cancellation remains separate.

        Lock order: service state then this upload job's state. Registered
        upload jobs have no failure-result callback taking the service lock.
        No listeners or transport work run while either lock is held.
        """
        def report(accepted):
            cleanup_event('cancellation', origin=job.id if isinstance(job, CoreJob) else None,
                          job_id=job.id if isinstance(job, CoreJob) else None,
                          accepted=accepted, decision=decision if decision in ('keep','delete') else 'invalid',
                          session_match=(DeviceSession(job.snapshot().device_id, job.snapshot().session_id) == self._device_session())
                              if isinstance(job, CoreJob) else False)
            return accepted
        if not isinstance(job,CoreJob) or decision not in ('keep','delete'):return report(False)
        with self._lock:
            self._prune_recovery_locked()
            origin=self._upload_origins.get(job)
            if (self._recovery_closed or origin is None or not origin.eligible or
                    origin.retired or origin.decision is not None):return report(False)
            def install(receipt):
                origin.decision=decision
                origin.receipt=receipt
            accepted=job._request_cancel_with_intent(install)
            if not accepted:origin.retired=True
        if accepted:job._emit('cancel-requested')
        return report(accepted)

    def _take_cleanup_eligibility(self, job):
        """Retire once even on validation failure; never prepare/delete/submit.

        Read the registered job's authoritative result, never a caller snapshot.
        Returned immutable evidence requires fresh authority/session validation
        in the future coordinator; it is not permission to dispatch deletion.
        """
        if not isinstance(job,CoreJob):return None
        with self._lock:
            self._prune_recovery_locked()
            origin=self._upload_origins.get(job)
            if origin is None or origin.retired:return None
            origin.retired=True
            if (self._recovery_closed or origin.decision!='delete' or
                    origin.receipt is None):return None
            result=job.snapshot()
            if (result.state not in ('failed','cancelled') or
                    result.device_id!=origin.session.device_id or
                    result.session_id!=origin.session.session_id):return None
            record=getattr(result.result,'partial_upload',None)
            entry=self._recoveries.get(id(record))
            if (entry is None or entry.record is not record or entry.origin is not job or
                    entry.session!=origin.session or entry.state!='available' or
                    entry.path!=record.location.path or
                    entry.evidence.disposition!='staging-candidate' or
                    entry.evidence.staging!=entry.path):return None
            evidence=_CleanupEligibility(job.id,origin.session,record)
            self._cleanup_continuations[evidence]=_CleanupContinuation(record,origin.session)
            return evidence

    def _cleanup_decision(self, job):
        """Presentation only; this value cannot authorize a continuation."""
        with self._lock:
            self._prune_recovery_locked()
            origin=self._upload_origins.get(job)
            return origin.decision if origin is not None else None

    def _prepare_intent_cleanup(self, evidence):
        with self._lock:
            self._prune_recovery_locked()
            continuation=self._cleanup_continuations.get(evidence)
            if continuation is None or continuation.state!='issued':
                raise BrowserError('Upload cleanup continuation is no longer available.')
            continuation.state='preparing'
        try:
            job=self.prepare_partial_delete(continuation.record,_continuation=continuation)
            with self._lock:continuation.preparation=job
            return job
        except Exception:
            self._abandon_intent_cleanup(evidence)
            raise

    def _execute_intent_cleanup(self, evidence):
        # Only our authoritative preparation result selects the plan. Caller
        # snapshots, plan IDs and paths are never accepted here.
        with self._lock:
            self._cleanup_plans_locked()
            continuation=self._cleanup_continuations.get(evidence)
            if continuation is None or continuation.state!='prepared':
                raise BrowserError('Upload cleanup preparation is unavailable.')
            job=continuation.preparation
        # Preparation failure callbacks may acquire service state under the job
        # lock. Never take that job lock while holding the service lock.
        result=job.snapshot() if job is not None else None
        with self._lock:
            self._cleanup_plans_locked()
            if (self._cleanup_continuations.get(evidence) is not continuation or
                    continuation.state!='prepared'):
                raise BrowserError('Upload cleanup continuation expired.')
            continuation.state='retired'
            stored=self._delete_plans.get(continuation.plan_id)
            entry=self._recoveries.get(id(continuation.record))
            valid=(result is not None and result.state=='succeeded' and
                   result.result.plan_id==continuation.plan_id and stored is not None and
                   entry is not None and entry.record is continuation.record and
                   stored.recovery is entry and stored.session==continuation.session and
                   stored.targets==(entry.path,) and len(stored.items)==1 and
                   stored.items[0].kind=='file')
        if not valid:
            self._abandon_intent_cleanup(evidence)
            raise BrowserError('Upload cleanup plan does not match its reviewed target.')
        # execute_delete consumes the recovery/plan before scheduler admission.
        return self.execute_delete(continuation.plan_id)

    def _abandon_intent_cleanup(self, evidence):
        with self._lock:
            continuation=self._cleanup_continuations.pop(evidence,None)
            if continuation is None:return
            continuation.state='retired'
            entry=self._recoveries.get(id(continuation.record))
            if (entry is not None and entry.record is continuation.record and
                    entry.plan_id==continuation.plan_id):
                self._release_recovery_locked(entry)

    def _release_recovery_locked(self, entry):
        if (self._recoveries.get(id(entry.record)) is entry and
                entry.state=='reserved'):
            if entry.plan_id:self._delete_plans.pop(entry.plan_id,None)
            entry.plan_id=None
            if not self._recovery_closed and entry.session==self._device_session():
                entry.state='available'
            else:self._recoveries.pop(id(entry.record),None)

    def job(self, job_id):
        return self._scheduler.job(job_id)

    def cancel(self, job_id):
        return self._scheduler.cancel(job_id)

    def cleanup(self):
        with self._lock:self._cleanup_plans_locked()
        self._scheduler.cleanup()

    def _device_session(self):
        value=self._session_provider()
        if isinstance(value,DeviceSession):return value
        # Compatibility for direct service users while Core adopts explicit IDs.
        return DeviceSession('test-device',str(value))

    def _observed_job(self, operation, task, *, session=None, failure_result=None, upload_eligible=None,
                      cleanup_origin=None):
        def observed_task(job):
            if not cleanup_origin and not upload_eligible:return task(job)
            with cleanup_context(cleanup_origin or (job.id if upload_eligible else None)):
                cleanup_event('job_start', job_id=job.id, stage=operation,
                              session_match=session == self._device_session())
                return task(job)
        job=CoreJob(operation,observed_task,failure_result=failure_result)
        origin=cleanup_origin or (job.id if upload_eligible else None)
        if origin:
            def observe(event):
                if event.kind != 'finished':return
                snap=event.job
                uploads=getattr(snap.result, 'uploads', ())
                partial=getattr(snap.result, 'partial_path', None)
                upload=next((u for u in uploads if u.staging == partial), None)
                if upload is None and uploads:upload=uploads[-1]
                if upload is not None:
                    stor=upload.stor or {}
                    cleanup_event('transfer_evidence', origin=origin, job_id=snap.id,
                                  sender_confirmed_bytes=stor.get('confirmed_sender_bytes',stor.get('transferred')),
                                  attempted_send_bytes=stor.get('attempted_send_bytes'),
                                  terminal_stor_acknowledged=stor.get('terminal_reply') in (226,250),
                                  publication=upload.disposition)
                if isinstance(snap.result, DeleteResult):
                    cleanup_event('deletion_result', origin=origin, job_id=snap.id,
                                  removed_count=len(snap.result.removed),
                                  not_attempted_count=len(snap.result.not_attempted),
                                  mutation_outcome=(snap.result.mutation or {}).get('outcome'))
                cleanup_event('terminal', origin=origin, job_id=snap.id,
                              stage=operation, state=snap.state,
                              started_at=snap.started_at, finished_at=snap.finished_at,
                              session_match=session == self._device_session(),
                              error_code=snap.error.code if snap.error else None)
            job.add_listener(observe)
        return job

    def _job(self, operation, task, *, session=None, failure_result=None, upload_eligible=None,
             cleanup_origin=None):
        job=self._observed_job(operation,task,session=session,failure_result=failure_result,
                               upload_eligible=upload_eligible,cleanup_origin=cleanup_origin)
        if upload_eligible is not None:
            self._register_upload_job(job,session,upload_eligible)
        binding=(JobBinding.device(session) if session is not None
                 else JobBinding.core_host())
        return self._scheduler.submit(job,binding)

    def _cleanup_plans_locked(self):
        self._prune_recovery_locked()
        now=self._clock();registries=(self._copy_plans,self._delete_plans,
                                      self._native_plans,self._fresh_plans,self._flash_cleanup_plans)
        for registry in registries:
            for plan_id,plan in tuple(registry.items()):
                if now-plan.created_at>self.plan_ttl:registry.pop(plan_id,None)
        all_plans=sorted(((plan.created_at,plan_id,registry)
                          for registry in registries
                          for plan_id,plan in registry.items()),key=lambda row:row[0])
        while len(all_plans)>self.plan_limit:
            _,plan_id,registry=all_plans.pop(0);registry.pop(plan_id,None)
        for entry in tuple(self._recoveries.values()):
            if entry.plan_id and entry.plan_id not in self._delete_plans:
                self._release_recovery_locked(entry)

    def _take_plan(self, registry, plan_id, label):
        with self._lock:
            self._cleanup_plans_locked();stored=registry.pop(plan_id,None)
            if stored is not None and registry is self._delete_plans and stored.recovery is not None:
                entry=stored.recovery
                if (self._recoveries.get(id(entry.record)) is not entry or
                        entry.state!='reserved' or entry.plan_id!=plan_id):
                    raise BrowserError('Partial cleanup authority is no longer available.')
                # Consume before admission/dispatch, including definite rejection.
                entry.state='consumed'
                self._recoveries.pop(id(entry.record))
        if stored is None:
            raise BrowserError(f'{label} is missing, expired, or already used. Prepare it again.')
        return stored

    def _local(self, location):
        if location.scope==CLIENT_UPLOAD:
            raise BrowserError('Client-upload artifacts are not available yet; stage the file with Core first.')
        if location.scope not in (CORE_HOST,C64U):raise BrowserError('Unknown filesystem scope.')
        if not location.path:raise BrowserError('A file location needs a path.')
        return location.scope==CORE_HOST

    def _session(self, locations):
        return self._device_session() if any(item.scope==C64U for item in locations) else None

    def _client(self, locations, expected=None):
        if not any(item.scope==C64U for item in locations):return None
        client=self._client_provider()
        # Pair the captured transport with its session. If reconnect/device
        # selection raced this lookup, no operation is issued through it.
        self._check_session(expected)
        return client

    def _check_session(self, expected):
        if expected is not None and expected!=self._device_session():
            raise FileJobFailure('session','The C64U connection changed. Prepare the operation again.')

    def prepare_copy(self, request):
        if not isinstance(request,CopyRequest) or not request.names:
            raise BrowserError('Choose at least one item to copy.')
        source_local=self._local(request.source);destination_local=self._local(request.destination)
        session=self._session((request.source,request.destination))
        def task(job):
            if not source_local:require_file_operation(request.source.path, parent=True)
            if not destination_local:require_file_operation(request.destination.path, parent=True)
            client=self._client((request.source,request.destination),session)
            plan=build_plan(client,source_local,request.source.path,request.names,
                            destination_local,request.destination.path,job.check_cancel)
            job.check_cancel()
            plan_id=uuid.uuid4().hex
            with self._lock:
                self._cleanup_plans_locked()
                self._copy_plans[plan_id]=_CopyPlan(request,plan,session,self._clock())
                self._cleanup_plans_locked()
            return CopyPreview(plan_id,request.source,request.destination,
                tuple(request.names),tuple(plan.conflicts),
                tuple(step.relative for step in plan.replacements),
                len(plan.steps),time.time())
        return self._job('file.copy.prepare',task,session=session)

    def discard_plan(self, plan_id):
        with self._lock:
            self._cleanup_plans_locked()
            removed=bool(self._copy_plans.pop(plan_id,None) or
                        self._delete_plans.pop(plan_id,None) or
                        self._native_plans.pop(plan_id,None) or
                        self._fresh_plans.pop(plan_id,None) or
                        self._flash_cleanup_plans.pop(plan_id,None))
            self._cleanup_plans_locked()
            return removed

    def execute_copy(self, plan_id, decision='skip'):
        if decision not in ('skip','replace'):
            raise BrowserError('Choose skip or replace for existing files.')
        stored=self._take_plan(self._copy_plans,plan_id,'Copy plan')
        request=stored.request;plan=copy.deepcopy(stored.plan)
        if decision=='replace':
            replaced={step.relative for step in plan.replacements}
            plan.conflicts=[name for name in plan.conflicts if name not in replaced]
            plan.steps.extend(plan.replacements)
        def task(job):
            self._check_session(stored.session)
            client=self._client((request.source,request.destination),stored.session)
            report=execute_plan(client,plan,request.source.scope==CORE_HOST,
                                request.destination.scope==CORE_HOST,
                                job.byte_progress())
            partial=self._partial_from_report(report,stored.session,'file.copy.execute') if stored.session else None
            result=CopyResult(tuple(report.completed),tuple(report.skipped),
                tuple(report.remaining),report.partial,report.error,partial,tuple(report.uploads),tuple(report.replacements),tuple(report.folder_steps))
            if getattr(report,'cancelled',False):raise JobCancelled(result=result)
            if report.error:
                raise FileJobFailure('partial-upload' if report.partial else 'transfer',
                                     report.error,result)
            return result
        return self._job('file.copy.execute',task,session=stored.session,
            upload_eligible=(request.source.scope==CORE_HOST and
                request.destination.scope==C64U and
                any(not step.directory and not step.existed for step in plan.steps)))

    def prepare_delete(self, locations):
        return self._prepare_delete(tuple(locations))

    def prepare_partial_delete(self, partial, *, _continuation=None):
        with self._lock:
            self._cleanup_plans_locked()
            entry=self._recoveries.get(id(partial))
            if entry is None or entry.record is not partial:
                raise BrowserError('Core did not identify this as an available partial C64U upload.')
            self._check_session(entry.session)
            if entry.state!='available':raise BrowserError('Partial cleanup is already reserved for review.')
            entry.state='reserved'
        try:
            return self._prepare_delete((FileLocation.c64u(entry.path),),entry.session,recovery=entry,continuation=_continuation)
        except Exception:
            with self._lock:self._release_recovery_locked(entry)
            raise

    def _prepare_delete(self, locations, expected_session=None, *, recovery=None, continuation=None):
        locations=tuple(locations)
        if not locations:raise BrowserError('Choose at least one item to delete.')
        scopes={item.scope for item in locations}
        if len(scopes)!=1:raise BrowserError('One deletion plan cannot mix filesystems.')
        local=self._local(locations[0])
        if any(self._local(item)!=local for item in locations):raise BrowserError('Deletion targets must share one filesystem.')
        targets=tuple(item.path for item in locations)
        session=expected_session or self._session(locations)
        def task(job):
            if not local:
                for path in targets:require_file_operation(path)
            client=self._client(locations,session);job.check_cancel()
            with read_operation(client, job.check_cancel):
                if recovery is not None:
                    # A staged addition is a file. Never traverse a substituted folder.
                    item=deletion_snapshot(client,False,recovery.path)
                    if item.kind!='file':raise BrowserError('Partial upload target is no longer a file.')
                    items=(item,)
                else:items=prepare_deletion(client,local,targets,job.check_cancel)
            job.check_cancel();plan_id=uuid.uuid4().hex
            with self._lock:
                self._cleanup_plans_locked()
                if recovery is not None:
                    if (self._recoveries.get(id(recovery.record)) is not recovery or
                            recovery.state!='reserved' or self._recovery_closed):
                        raise BrowserError('Partial upload session ended during review.')
                    if continuation is not None:
                        if continuation.state!='preparing':
                            raise BrowserError('Upload cleanup continuation ended during review.')
                        continuation.plan_id=plan_id
                        continuation.state='prepared'
                    recovery.plan_id=plan_id
                self._delete_plans[plan_id]=_DeletePlan(
                    locations[0].scope,targets,items,session,self._clock(),recovery)
                self._cleanup_plans_locked()
            return DeletePreview(plan_id,locations[0].scope,targets,
                tuple(DeleteItem(item.path,item.kind) for item in items),time.time())
        def failed(exc):
            if recovery is not None:
                with self._lock:self._release_recovery_locked(recovery)
                if isinstance(exc, VerifiedTargetAbsent) and exc.path == recovery.path:
                    return DeleteResult((), 1, str(exc), recovery.path, None,
                                        (recovery.path,), absent_target=recovery.path)
            return getattr(exc,'result',None)
        return self._job('file.delete.prepare',task,session=session,failure_result=failed,
                         cleanup_origin=recovery.origin.id if recovery is not None else None)

    def execute_delete(self, plan_id):
        stored=self._take_plan(self._delete_plans,plan_id,'Deletion plan')
        local=stored.scope==CORE_HOST
        def task(job):
            self._check_session(stored.session)
            client=self._client((FileLocation(stored.scope,stored.targets[0]),),
                                stored.session)
            if not local:
                if stored.recovery is not None:
                    recovery=stored.recovery
                    if (recovery.state!='consumed' or stored.targets!=(recovery.path,) or
                            stored.session!=recovery.session or len(stored.items)!=1 or
                            stored.items[0].path!=recovery.path):
                        raise BrowserError('Invalid consumed partial cleanup plan.')
                    def check():
                        self._check_session(stored.session)
                        job.check_cancel()
                    report=_delete_recovery_file(client,stored.items[0],check)
                else:
                    report=delete_reviewed(client,False,stored.targets,stored.items,
                                           check=job.check_cancel)
                result=DeleteResult(tuple(report.removed),len(stored.items),
                    str(report.error) if report.error else '',report.stopped_target,
                    report.mutation,report.not_attempted,report.absent_target)
                if isinstance(report.error,JobCancelled):raise JobCancelled(result=result)
                if report.error:raise FileJobFailure('delete',str(report.error),result)
                return result
            removed,error=delete_reviewed(client,local,stored.targets,stored.items,
                                          check=job.check_cancel)
            result=DeleteResult(tuple(removed),len(stored.items),error or '')
            if error=='Operation cancelled by request.':raise JobCancelled(result=result)
            if error:raise FileJobFailure('delete',error,result)
            return result
        return self._job('file.delete.execute',task,session=stored.session,
                         cleanup_origin=stored.recovery.origin.id if stored.recovery is not None else None)

    def create_folder(self, parent, name):
        local=self._local(parent)
        if not local:require_file_operation(parent.path, parent=True)
        session=self._session((parent,))
        child('/USB2',name)
        target=str(Path(parent.path)/name) if local else child(parent.path,name)
        def task(job):
            job.check_cancel();self._check_session(session)
            if local:Path(target).mkdir()
            else:self._managed_mutation(self._client((parent,),session),'mkdir',target,check=job.check_cancel)
            return FileLocation(parent.scope,target)
        return self._job('file.folder.create',task,session=session)

    @staticmethod
    def _managed_mutation(client, action, path, **kwargs):
        try:return operate_managed(client,action,path,**kwargs)
        except JobCancelled:raise
        except BrowserError as exc:
            # Availability of the network never implies mutation replay safety.
            raise FileJobFailure(getattr(exc,'kind','mutation'),str(exc),
                                 getattr(exc,'result',None),retryable=False) from None

    def rename(self, source, new_name):
        if source.scope!=C64U:
            raise BrowserError('This rename operation requires a C64U source.')
        session=self._session((source,))
        def task(job):
            require_file_operation(source.path)
            client=self._client((source,),session)
            return self._managed_mutation(client,'rename',source.path,
                                          new_name=new_name,check=job.check_cancel)
        return self._job('file.rename',task,session=session)

    def prepare_native_upload(self, source, destination_folder, name):
        self._local(source)
        destination=FileLocation.c64u(posixpath.join(destination_folder,name))
        session=self._session((source,destination))
        def task(job):
            def check():
                self._check_session(session);job.check_cancel()
            try:
                check()
                if source.scope==CORE_HOST:
                    data=read_local(source.path)
                else:
                    client=self._client((source,),session)
                    adapter=adapter_for(client)
                    if adapter is None:raise BrowserError('Managed source adapter required.')
                    with adapter.operation(check):data=read_remote(client,source.path)
                validate_upload(destination_folder,name,data);check()
            except Exception as exc:
                evidence=FlashEvidence(phase='source',validation='refused',
                    error_category='cancelled' if getattr(exc,'cancelled',False) else 'source',
                    cancellation_requested=bool(getattr(exc,'cancelled',False)))
                result=NativeUploadResult(FileLocation.c64u(''),0,evidence)
                if getattr(exc,'cancelled',False):raise JobCancelled(result.message,result) from None
                raise FileJobFailure('flash-source',result.message,result) from None
            plan_id=uuid.uuid4().hex
            with self._lock:
                self._cleanup_plans_locked()
                self._native_plans[plan_id]=_NativePlan(
                    source,destination,data,session,self._clock())
                self._cleanup_plans_locked()
            return NativeUploadPreview(plan_id,source,destination,len(data),time.time())
        return self._job('file.native-upload.prepare',task,session=session,
                         failure_result=self._native_unstarted_result)

    @staticmethod
    def _native_unstarted_result(exc):
        result=getattr(exc,'result',None)
        if isinstance(result,NativeUploadResult):return result
        cancelled=bool(getattr(exc,'cancelled',False))
        evidence=FlashEvidence(phase='queued',error_category='cancelled' if cancelled else 'session',
            cancellation_phase='queued' if cancelled else None,cancellation_requested=cancelled)
        return NativeUploadResult(FileLocation.c64u(''),0,evidence)

    def execute_native_upload(self, plan_id):
        stored=self._take_plan(self._native_plans,plan_id,'Upload plan')
        def task(job):
            def check():
                self._check_session(stored.session);job.check_cancel()
            try:
                check()
                folder,name=posixpath.split(stored.destination.path)
                observation=dict(kind='local-capture' if stored.source.scope==CORE_HOST else 'managed-size-retr-size',
                                 bytes=len(stored.data),sha256=hashlib.sha256(stored.data).hexdigest())
                evidence=upload_flash(self._client((stored.destination,),stored.session),
                    folder,name,stored.data,check=check,source_observation=observation,
                    cancellation_requested=lambda:job.snapshot().state=='cancel-requested')
                return NativeUploadResult(stored.destination,len(stored.data),evidence)
            except Exception as exc:
                evidence=getattr(exc,'flash_evidence',FlashEvidence(
                    phase='session',error_category='session',
                    cancellation_requested=bool(getattr(exc,'cancelled',False))))
                result=NativeUploadResult(stored.destination,len(stored.data),evidence)
                if getattr(exc,'cancelled',False):raise JobCancelled(result.message,result) from None
                raise FileJobFailure('flash-upload',result.message,result) from None
            finally:
                # CoreJob retains its task closure; release consumed payload there too.
                stored.data=b''
        def failure_result(exc):
            # CoreJob can refuse before task/finally (queued cancellation or a
            # stale binding). Preserve task evidence and release bytes either way.
            stored.data=b''
            return self._native_unstarted_result(exc)
        try:
            return self._job('file.native-upload.execute',task,session=stored.session,
                             failure_result=failure_result)
        except Exception:
            stored.data=b''
            raise


    def save_native_copy(self, source, destination):
        if source.scope!=C64U or destination.scope!=CORE_HOST:
            raise BrowserError('Native save-copy currently requires a C64U source and Core-host destination.')
        session=self._session((source,));self._local(destination)
        def task(job):
            job.check_cancel();self._check_session(session)
            data=read_remote(self._client((source,),session),source.path);job.check_cancel()
            path=Path(destination.path);temporary=None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
                    temporary=stream.name;stream.write(data);stream.flush();os.fsync(stream.fileno())
                job.check_cancel();os.replace(temporary,path);temporary=None
            finally:
                if temporary and os.path.exists(temporary):os.unlink(temporary)
            return {'destination':destination,'bytes':len(data)}
        return self._job('file.native-save-copy',task,session=session)

    def prepare_fresh_folder_upload(self, source, parent):
        from .fresh_folder import prepare
        return prepare(self, source, parent)

    def execute_fresh_folder_upload(self, plan_id):
        from .fresh_folder import execute
        return execute(self, plan_id)

    def prepare_flash_cleanup(self, path, expected_size, expected_sha256):
        """Internal qualification support; never a general Flash delete UI."""
        from .flash_cleanup import prepare
        return prepare(self, path, expected_size, expected_sha256)

    def execute_flash_cleanup(self, plan_id):
        from .flash_cleanup import execute
        return execute(self, plan_id)
