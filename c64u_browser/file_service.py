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
    session: int | None


@dataclass
class _DeletePlan:
    scope: str
    targets: tuple[str, ...]
    items: tuple
    session: int | None


@dataclass
class _NativePlan:
    source: FileLocation
    destination: FileLocation
    data: bytes
    session: int


class FileJobFailure(BrowserError):
    def __init__(self, code, message, result=None, retryable=False):
        super().__init__(message)
        self.code=code;self.result=result;self.retryable=retryable


class FileService:
    """Core-owned file plans and jobs; no transport or credentials escape."""
    def __init__(self, client_provider, session_provider):
        self._client_provider=client_provider
        self._session_provider=session_provider
        self._jobs={};self._copy_plans={};self._delete_plans={};self._native_plans={}
        self._lock=Lock()

    def job(self, job_id):
        with self._lock:job=self._jobs.get(job_id)
        if job is None:raise BrowserError('Unknown file job.')
        return job.snapshot()

    def cancel(self, job_id):
        with self._lock:job=self._jobs.get(job_id)
        return False if job is None else job.request_cancel()

    def _job(self, operation, task):
        job=CoreJob(operation,task)
        with self._lock:self._jobs[job.id]=job
        return job

    def _local(self, location):
        if location.scope==CLIENT_UPLOAD:
            raise BrowserError('Client-upload artifacts are not available yet; stage the file with Core first.')
        if location.scope not in (CORE_HOST,C64U):raise BrowserError('Unknown filesystem scope.')
        if not location.path:raise BrowserError('A file location needs a path.')
        return location.scope==CORE_HOST

    def _session(self, locations):
        return self._session_provider() if any(item.scope==C64U for item in locations) else None

    def _client(self, locations):
        return self._client_provider() if any(item.scope==C64U for item in locations) else None

    def _check_session(self, expected):
        if expected is not None and expected!=self._session_provider():
            raise FileJobFailure('session','The C64U connection changed. Prepare the operation again.')

    def prepare_copy(self, request):
        if not isinstance(request,CopyRequest) or not request.names:
            raise BrowserError('Choose at least one item to copy.')
        source_local=self._local(request.source);destination_local=self._local(request.destination)
        session=self._session((request.source,request.destination))
        def task(job):
            client=self._client((request.source,request.destination))
            plan=build_plan(client,source_local,request.source.path,request.names,
                            destination_local,request.destination.path,job.check_cancel)
            job.check_cancel()
            plan_id=uuid.uuid4().hex
            with self._lock:self._copy_plans[plan_id]=_CopyPlan(request,plan,session)
            return CopyPreview(plan_id,request.source,request.destination,
                tuple(request.names),tuple(plan.conflicts),
                tuple(step.relative for step in plan.replacements),
                len(plan.steps),time.time())
        return self._job('file.copy.prepare',task)

    def discard_plan(self, plan_id):
        with self._lock:
            return bool(self._copy_plans.pop(plan_id,None) or
                        self._delete_plans.pop(plan_id,None) or
                        self._native_plans.pop(plan_id,None))

    def execute_copy(self, plan_id, decision='skip'):
        if decision not in ('skip','replace'):
            raise BrowserError('Choose skip or replace for existing files.')
        with self._lock:stored=self._copy_plans.pop(plan_id,None)
        if stored is None:raise BrowserError('Copy plan is missing or was already used. Prepare it again.')
        request=stored.request;plan=copy.deepcopy(stored.plan)
        if decision=='replace':
            replaced={step.relative for step in plan.replacements}
            plan.conflicts=[name for name in plan.conflicts if name not in replaced]
            plan.steps.extend(plan.replacements)
        def task(job):
            self._check_session(stored.session)
            client=self._client((request.source,request.destination))
            report=execute_plan(client,plan,request.source.scope==CORE_HOST,
                                request.destination.scope==CORE_HOST,
                                job.byte_progress())
            result=CopyResult(tuple(report.completed),tuple(report.skipped),
                tuple(report.remaining),report.partial,report.error)
            if getattr(report,'cancelled',False):raise JobCancelled(result=result)
            if report.error:
                raise FileJobFailure('partial-upload' if report.partial else 'transfer',
                                     report.error,result)
            return result
        return self._job('file.copy.execute',task)

    def prepare_delete(self, locations):
        locations=tuple(locations)
        if not locations:raise BrowserError('Choose at least one item to delete.')
        scopes={item.scope for item in locations}
        if len(scopes)!=1:raise BrowserError('One deletion plan cannot mix filesystems.')
        local=self._local(locations[0])
        if any(self._local(item)!=local for item in locations):raise BrowserError('Deletion targets must share one filesystem.')
        targets=tuple(item.path for item in locations);session=self._session(locations)
        def task(job):
            client=self._client(locations);job.check_cancel()
            items=prepare_deletion(client,local,targets,job.check_cancel)
            job.check_cancel();plan_id=uuid.uuid4().hex
            with self._lock:self._delete_plans[plan_id]=_DeletePlan(locations[0].scope,targets,items,session)
            return DeletePreview(plan_id,locations[0].scope,targets,
                tuple(DeleteItem(item.path,item.kind) for item in items),time.time())
        return self._job('file.delete.prepare',task)

    def execute_delete(self, plan_id):
        with self._lock:stored=self._delete_plans.pop(plan_id,None)
        if stored is None:raise BrowserError('Deletion plan is missing or was already used. Review it again.')
        local=stored.scope==CORE_HOST
        def task(job):
            self._check_session(stored.session)
            client=self._client((FileLocation(stored.scope,stored.targets[0]),))
            removed,error=delete_reviewed(client,local,stored.targets,stored.items,
                                          check=job.check_cancel)
            result=DeleteResult(tuple(removed),len(stored.items),error or '')
            if error=='Operation cancelled by request.':raise JobCancelled(result=result)
            if error:raise FileJobFailure('delete',error,result)
            return result
        return self._job('file.delete.execute',task)

    def create_folder(self, parent, name):
        local=self._local(parent);session=self._session((parent,))
        child('/USB2',name)
        target=str(Path(parent.path)/name) if local else child(parent.path,name)
        def task(job):
            job.check_cancel();self._check_session(session)
            if local:Path(target).mkdir()
            else:operate(self._client((parent,)),'mkdir',target)
            return FileLocation(parent.scope,target)
        return self._job('file.folder.create',task)

    def prepare_native_upload(self, source, destination_folder, name):
        self._local(source)
        destination=FileLocation.c64u(posixpath.join(destination_folder,name))
        session=self._session((source,destination))
        def task(job):
            client=self._client((source,)) if source.scope==C64U else None
            job.check_cancel()
            data=read_local(source.path) if source.scope==CORE_HOST else read_remote(client,source.path)
            validate_upload(destination_folder,name,data);job.check_cancel()
            plan_id=uuid.uuid4().hex
            with self._lock:self._native_plans[plan_id]=_NativePlan(source,destination,data,session)
            return NativeUploadPreview(plan_id,source,destination,len(data),time.time())
        return self._job('file.native-upload.prepare',task)

    def execute_native_upload(self, plan_id):
        with self._lock:stored=self._native_plans.pop(plan_id,None)
        if stored is None:raise BrowserError('Upload plan is missing or was already used. Prepare it again.')
        def task(job):
            job.check_cancel();self._check_session(stored.session)
            folder,name=posixpath.split(stored.destination.path)
            result=upload_flash(self._client((stored.destination,)),folder,name,stored.data)
            return NativeUploadResult(FileLocation.c64u(result),len(stored.data))
        return self._job('file.native-upload.execute',task)

    def save_native_copy(self, source, destination):
        if source.scope!=C64U or destination.scope!=CORE_HOST:
            raise BrowserError('Native save-copy currently requires a C64U source and Core-host destination.')
        session=self._session((source,));self._local(destination)
        def task(job):
            job.check_cancel();self._check_session(session)
            data=read_remote(self._client((source,)),source.path);job.check_cancel()
            path=Path(destination.path);temporary=None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
                    temporary=stream.name;stream.write(data);stream.flush();os.fsync(stream.fileno())
                job.check_cancel();os.replace(temporary,path);temporary=None
            finally:
                if temporary and os.path.exists(temporary):os.unlink(temporary)
            return {'destination':destination,'bytes':len(data)}
        return self._job('file.native-save-copy',task)
