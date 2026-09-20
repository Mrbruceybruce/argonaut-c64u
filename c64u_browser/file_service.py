# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Headless Core file operations built on Argonaut's validated file modules."""
from dataclasses import dataclass
from pathlib import Path
import copy
import os
import posixpath
import tempfile
import time
import uuid
from threading import Lock

from .api import BrowserError
from .deletion import prepare as prepare_deletion, delete_reviewed
from .files import child, operate
from .folder_copy import build_plan, execute_plan
from .jobs import CoreJob, JobCancelled
from .scheduler import CoreScheduler, DeviceSession, JobBinding
from .native_files import read_local, read_remote, upload_flash, validate_upload


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
    """A Core-observed staged upload bound to its originating session."""
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
        if self.partial_path:text+='\n\nPartial upload: '+self.partial_path
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

    @property
    def message(self):
        return (f'Deleted {len(self.removed)} of {self.total} item(s).'+
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


@dataclass
class _NativePlan:
    source: FileLocation
    destination: FileLocation
    data: bytes
    session: DeviceSession
    created_at: float


class FileJobFailure(BrowserError):
    def __init__(self, code, message, result=None, retryable=False):
        super().__init__(message)
        self.code=code;self.result=result;self.retryable=retryable


class FileService:
    """Core-owned file plans and jobs; no transport or credentials escape."""
    def __init__(self, client_provider, session_provider, *, scheduler=None,
                 plan_ttl=300, plan_limit=128, clock=time.time):
        self._client_provider=client_provider
        self._session_provider=session_provider
        self._clock=clock
        self.plan_ttl=max(0,float(plan_ttl));self.plan_limit=max(0,int(plan_limit))
        self._scheduler=scheduler or CoreScheduler(self._device_session,clock=clock)
        self._copy_plans={};self._delete_plans={};self._native_plans={}
        self._lock=Lock()

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

    def _job(self, operation, task, *, session=None):
        job=CoreJob(operation,task)
        binding=(JobBinding.device(session) if session is not None
                 else JobBinding.core_host())
        return self._scheduler.submit(job,binding)

    def _cleanup_plans_locked(self):
        now=self._clock();registries=(self._copy_plans,self._delete_plans,
                                      self._native_plans)
        for registry in registries:
            for plan_id,plan in tuple(registry.items()):
                if now-plan.created_at>self.plan_ttl:registry.pop(plan_id,None)
        all_plans=sorted(((plan.created_at,plan_id,registry)
                          for registry in registries
                          for plan_id,plan in registry.items()),key=lambda row:row[0])
        while len(all_plans)>self.plan_limit:
            _,plan_id,registry=all_plans.pop(0);registry.pop(plan_id,None)

    def _take_plan(self, registry, plan_id, label):
        with self._lock:
            self._cleanup_plans_locked();stored=registry.pop(plan_id,None)
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
            return bool(self._copy_plans.pop(plan_id,None) or
                        self._delete_plans.pop(plan_id,None) or
                        self._native_plans.pop(plan_id,None))

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
            partial=(PartialUpload(FileLocation.c64u(report.partial),
                        stored.session.device_id,stored.session.session_id)
                     if report.partial and stored.session else None)
            result=CopyResult(tuple(report.completed),tuple(report.skipped),
                tuple(report.remaining),report.partial,report.error,partial)
            if getattr(report,'cancelled',False):raise JobCancelled(result=result)
            if report.error:
                raise FileJobFailure('partial-upload' if report.partial else 'transfer',
                                     report.error,result)
            return result
        return self._job('file.copy.execute',task,session=stored.session)

    def prepare_delete(self, locations):
        return self._prepare_delete(tuple(locations))

    def prepare_partial_delete(self, partial):
        if not isinstance(partial,PartialUpload) or partial.location.scope!=C64U:
            raise BrowserError('Core did not identify this as a partial C64U upload.')
        expected=DeviceSession(partial.device_id,partial.session_id)
        self._check_session(expected)
        return self._prepare_delete((partial.location,),expected)

    def _prepare_delete(self, locations, expected_session=None):
        locations=tuple(locations)
        if not locations:raise BrowserError('Choose at least one item to delete.')
        scopes={item.scope for item in locations}
        if len(scopes)!=1:raise BrowserError('One deletion plan cannot mix filesystems.')
        local=self._local(locations[0])
        if any(self._local(item)!=local for item in locations):raise BrowserError('Deletion targets must share one filesystem.')
        targets=tuple(item.path for item in locations)
        session=expected_session or self._session(locations)
        def task(job):
            client=self._client(locations,session);job.check_cancel()
            items=prepare_deletion(client,local,targets,job.check_cancel)
            job.check_cancel();plan_id=uuid.uuid4().hex
            with self._lock:
                self._cleanup_plans_locked()
                self._delete_plans[plan_id]=_DeletePlan(
                    locations[0].scope,targets,items,session,self._clock())
                self._cleanup_plans_locked()
            return DeletePreview(plan_id,locations[0].scope,targets,
                tuple(DeleteItem(item.path,item.kind) for item in items),time.time())
        return self._job('file.delete.prepare',task,session=session)

    def execute_delete(self, plan_id):
        stored=self._take_plan(self._delete_plans,plan_id,'Deletion plan')
        local=stored.scope==CORE_HOST
        def task(job):
            self._check_session(stored.session)
            client=self._client((FileLocation(stored.scope,stored.targets[0]),),
                                stored.session)
            removed,error=delete_reviewed(client,local,stored.targets,stored.items,
                                          check=job.check_cancel)
            result=DeleteResult(tuple(removed),len(stored.items),error or '')
            if error=='Operation cancelled by request.':raise JobCancelled(result=result)
            if error:raise FileJobFailure('delete',error,result)
            return result
        return self._job('file.delete.execute',task,session=stored.session)

    def create_folder(self, parent, name):
        local=self._local(parent);session=self._session((parent,))
        child('/USB2',name)
        target=str(Path(parent.path)/name) if local else child(parent.path,name)
        def task(job):
            job.check_cancel();self._check_session(session)
            if local:Path(target).mkdir()
            else:operate(self._client((parent,),session),'mkdir',target)
            return FileLocation(parent.scope,target)
        return self._job('file.folder.create',task,session=session)

    def prepare_native_upload(self, source, destination_folder, name):
        self._local(source)
        destination=FileLocation.c64u(posixpath.join(destination_folder,name))
        session=self._session((source,destination))
        def task(job):
            client=self._client((source,),session) if source.scope==C64U else None
            job.check_cancel()
            data=read_local(source.path) if source.scope==CORE_HOST else read_remote(client,source.path)
            validate_upload(destination_folder,name,data);job.check_cancel()
            plan_id=uuid.uuid4().hex
            with self._lock:
                self._cleanup_plans_locked()
                self._native_plans[plan_id]=_NativePlan(
                    source,destination,data,session,self._clock())
                self._cleanup_plans_locked()
            return NativeUploadPreview(plan_id,source,destination,len(data),time.time())
        return self._job('file.native-upload.prepare',task,session=session)

    def execute_native_upload(self, plan_id):
        stored=self._take_plan(self._native_plans,plan_id,'Upload plan')
        def task(job):
            job.check_cancel();self._check_session(stored.session)
            folder,name=posixpath.split(stored.destination.path)
            result=upload_flash(self._client((stored.destination,),stored.session),
                                folder,name,stored.data)
            return NativeUploadResult(FileLocation.c64u(result),len(stored.data))
        return self._job('file.native-upload.execute',task,session=stored.session)

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
