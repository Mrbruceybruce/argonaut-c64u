# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Headless, manifest-backed C64U USB/SD backup and restore capability."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import posixpath
import shutil
import tempfile
import time
import uuid
from threading import Lock

from .api import BrowserError
from .file_service import (C64U, CORE_HOST, CLIENT_UPLOAD, FileLocation,
                           PartialUpload)
from .folder_copy import Plan, Step, execute_plan
from .jobs import CoreJob, JobCancelled, JobProgress
from .replacement import signature
from .scheduler import JobBinding
from .storage import storage_root
from .transfers import connect, download


MANIFEST_NAME='.argonaut-usb-backup.json'
MANIFEST_FORMAT='argonaut-c64u-usb-backup'
MANIFEST_VERSION=1
MAX_ITEMS=10000
MAX_DEPTH=64
_WINDOWS_RESERVED={
    'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),
    *(f'LPT{i}' for i in range(1,10))}


@dataclass(frozen=True)
class BackupRequest:
    source_volume: FileLocation
    source_paths: tuple[str, ...]
    destination: FileLocation


@dataclass(frozen=True)
class BackupPreview:
    plan_id: str
    source_device_id: str
    source_volume: str
    selected_paths: tuple[str, ...]
    destination: FileLocation
    directories: int
    files: int
    bytes: int
    estimated_c64u_read_bytes: int
    warning: str
    created_at: float


@dataclass(frozen=True)
class BackupResult:
    backup_folder: FileLocation
    manifest_path: str
    state: str
    completed_directories: tuple[str, ...]
    completed_files: tuple[str, ...]
    remaining: tuple[str, ...]
    bytes: int
    failure: str = ''

    @property
    def message(self):
        text=(f'USB backup {self.state}: {len(self.completed_files)} file(s), '
              f'{len(self.completed_directories)} folder(s), {self.bytes:,} bytes.')
        return text+((' Stopped: '+self.failure) if self.failure else '')


@dataclass(frozen=True)
class RestoreIssue:
    path: str
    reason: str


@dataclass(frozen=True)
class RestorePreview:
    plan_id: str
    backup_folder: FileLocation
    target_device_id: str
    target_volume: str
    additions: tuple[str, ...]
    replacements: tuple[str, ...]
    unchanged: tuple[str, ...]
    conflicts: tuple[str, ...]
    missing: tuple[RestoreIssue, ...]
    bytes: int
    replacement_bytes: int
    extra_destination_files_deleted: bool
    created_at: float

    @property
    def can_restore(self):return not self.missing


@dataclass(frozen=True)
class RestoreResult:
    added: tuple[str, ...]
    replaced: tuple[str, ...]
    unchanged: tuple[str, ...]
    skipped: tuple[str, ...]
    conflicts: tuple[str, ...]
    remaining: tuple[str, ...]
    bytes: int
    partial_path: str | None = None
    failure: str = ''
    partial_upload: PartialUpload | None = None

    @property
    def message(self):
        text=(f'Restore completed {len(self.added)} addition(s) and '
              f'{len(self.replaced)} replacement(s); '
              f'{len(self.unchanged)} unchanged; {len(self.skipped)} skipped.')
        return text+((' Stopped: '+self.failure) if self.failure else '')


@dataclass(frozen=True)
class _RemoteItem:
    relative: str
    path: str
    directory: bool
    size: int
    sha256: str = ''


@dataclass
class _BackupPlan:
    request: BackupRequest
    session: object
    volume_fingerprint: str
    destination_identity: tuple
    items: tuple[_RemoteItem, ...]
    selected: tuple[str, ...]
    created_at: float


@dataclass(frozen=True)
class _ManifestFile:
    path: str
    size: int
    sha256: str


@dataclass
class _RestorePlan:
    backup_folder: Path
    backup_identity: tuple
    target_volume: str
    session: object
    volume_fingerprint: str
    manifest: dict
    files: tuple[_ManifestFile, ...]
    directories: tuple[str, ...]
    classification: object
    created_at: float


@dataclass(frozen=True)
class _Classification:
    additions: tuple[str, ...]
    replacements: tuple[str, ...]
    unchanged: tuple[str, ...]
    conflicts: tuple[str, ...]
    remote_digests: tuple[tuple[str,str], ...]


class UsbBackupFailure(BrowserError):
    def __init__(self,code,message,result=None,retryable=False):
        super().__init__(message);self.code=code;self.result=result;self.retryable=retryable


def _portable_component(name):
    if (not name or name in ('.','..') or name==MANIFEST_NAME or
            any(ord(char)<32 or char in '<>:"/\\|?*' for char in name) or
            name.endswith((' ','.')) or
            name.split('.',1)[0].upper() in _WINDOWS_RESERVED):
        raise BrowserError('USB backup cannot safely represent this name on all supported platforms: '+repr(name))


def _safe_relative(value):
    if not isinstance(value,str) or not value or value.startswith('/'):
        raise BrowserError('Backup manifest contains an invalid relative path.')
    parts=value.split('/')
    for part in parts:_portable_component(part)
    return value


def _backup_path(folder,relative):
    root=Path(folder).resolve();path=root.joinpath(*relative.split('/'))
    try:path.resolve(strict=False).relative_to(root)
    except ValueError:raise BrowserError('Backup path escapes its backup folder: '+relative)
    current=root
    for part in relative.split('/')[:-1]:
        current=current/part
        if current.is_symlink():raise BrowserError('Backup path contains a symbolic link: '+relative)
    return path


def _json_write(path,value):
    path=Path(path);temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,
                                         prefix='.argonaut-manifest-',delete=False) as stream:
            temporary=stream.name
            json.dump(value,stream,indent=2,sort_keys=True)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path);temporary=None
    finally:
        if temporary and os.path.exists(temporary):os.unlink(temporary)


def _local_hash(path,check=lambda:None):
    digest=hashlib.sha256();count=0
    with Path(path).open('rb') as stream:
        while block:=stream.read(1024*1024):
            check();digest.update(block);count+=len(block)
    return count,digest.hexdigest()


class UsbBackupService:
    """Core capability for verified USB/SD backup and non-mirroring restore."""
    def __init__(self,client_provider,session_provider,scheduler,*,
                 plan_ttl=300,plan_limit=128,clock=time.time):
        self._client_provider=client_provider;self._session_provider=session_provider
        self._scheduler=scheduler;self._clock=clock
        self.plan_ttl=max(0,float(plan_ttl));self.plan_limit=max(0,int(plan_limit))
        self._backups={};self._restores={};self._lock=Lock()

    def cancel(self,job_id):return self._scheduler.cancel(job_id)
    def job(self,job_id):return self._scheduler.job(job_id)

    def discard_plan(self,plan_id):
        with self._lock:
            self._cleanup_locked()
            return bool(self._backups.pop(plan_id,None) or self._restores.pop(plan_id,None))

    def cleanup(self):
        with self._lock:self._cleanup_locked()
        self._scheduler.cleanup()

    def _cleanup_locked(self):
        now=self._clock();registries=(self._backups,self._restores)
        for registry in registries:
            for plan_id,plan in tuple(registry.items()):
                if now-plan.created_at>self.plan_ttl:registry.pop(plan_id,None)
        rows=sorted((plan.created_at,plan_id,registry) for registry in registries
                    for plan_id,plan in registry.items())
        while len(rows)>self.plan_limit:
            _,plan_id,registry=rows.pop(0);registry.pop(plan_id,None)

    def _store(self,registry,plan):
        plan_id=uuid.uuid4().hex
        with self._lock:
            self._cleanup_locked();registry[plan_id]=plan;self._cleanup_locked()
        return plan_id

    def _take(self,registry,plan_id,label):
        with self._lock:
            self._cleanup_locked();plan=registry.pop(plan_id,None)
        if plan is None:
            raise BrowserError(f'{label} is missing, expired, or already used. Create a fresh preview.')
        return plan

    @staticmethod
    def _locations(request):
        for location in request:
            if location.scope==CLIENT_UPLOAD:
                raise BrowserError('Client-upload artifacts are not available yet; stage the file with Core first.')

    def _client(self,expected):
        client=self._client_provider()
        if expected!=self._session_provider():
            raise UsbBackupFailure('session','The C64U connection changed. Create a fresh preview.')
        return client

    def _submit(self,operation,task,session):
        return self._scheduler.submit(CoreJob(operation,task),JobBinding.device(session))

    @staticmethod
    def _volume_fingerprint(client,volume,check=lambda:None):
        rows=[]
        def visit(path,relative='',depth=0):
            check()
            if depth>MAX_DEPTH or len(rows)>=MAX_ITEMS:
                raise BrowserError('The C64U volume exceeds the 10,000 item or 64 level identity limit.')
            actual,entries=client.list_directory(path)
            if posixpath.normpath(actual).casefold()!=posixpath.normpath(path).casefold():
                raise BrowserError('The selected C64U storage volume changed.')
            for entry in sorted(entries,key=lambda row:(row.kind!='dir',row.name.casefold())):
                item=posixpath.join(relative,entry.name) if relative else entry.name
                rows.append((item,entry.kind,entry.size))
                if entry.kind=='dir':visit(posixpath.join(path,entry.name),item,depth+1)
        visit(volume)
        payload=json.dumps(rows,separators=(',',':'),ensure_ascii=False).encode('utf-8')
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _backup_identity(folder):
        folder=Path(folder)
        if not folder.is_dir() or folder.is_symlink():
            raise BrowserError('The backup folder changed or is unavailable.')
        stat=folder.stat();return (str(folder.resolve()),stat.st_dev,stat.st_ino)

    @staticmethod
    def _local_destination_identity(destination):
        path=Path(destination)
        if os.path.lexists(path):raise BrowserError('Choose a new backup folder; the destination already exists.')
        parent=path.parent
        if not parent.is_dir() or parent.is_symlink():
            raise BrowserError('The backup destination parent must be an existing ordinary folder.')
        stat=parent.stat();return (str(parent.resolve()),stat.st_dev,stat.st_ino)

    @staticmethod
    def _check_local_destination(destination,identity,required=0):
        path=Path(destination);parent=path.parent
        if os.path.lexists(path):raise BrowserError('The backup destination appeared after preview.')
        if not parent.is_dir() or parent.is_symlink():raise BrowserError('The backup destination changed.')
        stat=parent.stat();current=(str(parent.resolve()),stat.st_dev,stat.st_ino)
        if current!=identity:raise BrowserError('The local storage containing the backup destination changed.')
        if shutil.disk_usage(parent).free<required:
            raise BrowserError('The backup destination does not have enough free space.')

    def _enumerate_remote(self,client,volume,paths,job):
        items=[];seen=set()
        def add_ancestor(relative):
            if not relative or relative=='.' or relative.casefold() in seen:return
            parent=posixpath.dirname(relative);add_ancestor(parent)
            path=posixpath.join(volume,relative);directory,name=posixpath.split(path)
            _,entries=client.list_directory(directory)
            matches=[entry for entry in entries if entry.name.casefold()==name.casefold()]
            if len(matches)!=1 or matches[0].name!=name or matches[0].kind!='dir':
                raise BrowserError('A backup source parent changed or is unsupported: '+path)
            for part in relative.split('/'):_portable_component(part)
            seen.add(relative.casefold());items.append(_RemoteItem(relative,path,True,0))
        def visit(path,depth=0):
            job.check_cancel()
            if depth>MAX_DEPTH or len(items)>=MAX_ITEMS:
                raise BrowserError('USB backup exceeds 10,000 items or 64 folder levels; select a smaller backup.')
            relative=posixpath.relpath(path,volume)
            if relative.startswith('../') or relative in ('.','..'):
                raise BrowserError('Every backup source must be inside the selected volume.')
            for part in relative.split('/'):_portable_component(part)
            parent,name=posixpath.split(path)
            _,entries=client.list_directory(parent)
            matches=[entry for entry in entries if entry.name.casefold()==name.casefold()]
            if len(matches)!=1 or matches[0].name!=name:
                raise BrowserError('A selected backup source changed or has a case collision: '+path)
            entry=matches[0]
            if entry.kind not in ('file','dir'):
                raise BrowserError('USB backup supports ordinary files and folders only: '+path)
            key=relative.casefold()
            if key in seen:raise BrowserError('Two source paths differ only by letter case: '+relative)
            seen.add(key);items.append(_RemoteItem(relative,path,entry.kind=='dir',entry.size or 0))
            job.report(JobProgress('enumerate',len(items),None,'items','Reviewing USB contents…'))
            if entry.kind=='dir':
                _,children=client.list_directory(path);folded={}
                for child in children:
                    _portable_component(child.name);other=folded.setdefault(child.name.casefold(),child.name)
                    if other!=child.name:raise BrowserError('A folder contains names differing only by letter case: '+path)
                for child in sorted(children,key=lambda row:(row.kind!='dir',row.name.casefold())):
                    visit(posixpath.join(path,child.name),depth+1)
        selected=[]
        for path in sorted(set(paths),key=lambda value:(value.count('/'),value.casefold())):
            if any(path==parent or path.startswith(parent.rstrip('/')+'/') for parent in selected):continue
            selected.append(path)
            add_ancestor(posixpath.dirname(posixpath.relpath(path,volume)))
            visit(path)
        return tuple(items)

    def prepare_backup(self,request):
        if not isinstance(request,BackupRequest):raise BrowserError('Invalid USB backup request.')
        self._locations((request.source_volume,request.destination))
        if request.source_volume.scope!=C64U or request.destination.scope!=CORE_HOST:
            raise BrowserError('USB backup requires a C64U source and Core-host destination.')
        volume=storage_root(request.source_volume.path)
        if not volume or request.source_volume.path!=volume:
            raise BrowserError('Choose a C64U USB or SD volume root.')
        session=self._session_provider();identity=self._local_destination_identity(request.destination.path)
        def task(job):
            client=self._client(session);fingerprint=self._volume_fingerprint(client,volume,job.check_cancel)
            paths=tuple(request.source_paths)
            if any(not isinstance(path,str) for path in paths):
                raise BrowserError('Backup source paths must be C64U path strings.')
            if not paths:
                _,entries=client.list_directory(volume)
                paths=tuple(posixpath.join(volume,entry.name) for entry in entries)
            for path in paths:
                if storage_root(path)!=volume or path==volume:
                    raise BrowserError('Backup selections must be children of the chosen volume.')
            items=self._enumerate_remote(client,volume,paths,job)
            required=sum(item.size for item in items if not item.directory)
            reviewed=[];base=0
            for item in items:
                if item.directory:reviewed.append(item);continue
                size,digest=self._remote_hash(client,item.path,job,'review-source',base,required)
                if size!=item.size:raise BrowserError('A C64U source file changed during backup review: '+item.path)
                reviewed.append(_RemoteItem(item.relative,item.path,False,item.size,digest));base+=item.size
            items=tuple(reviewed)
            self._check_local_destination(request.destination.path,identity,required)
            selected=tuple(posixpath.relpath(path,volume) for path in paths)
            plan=_BackupPlan(request,session,fingerprint,identity,items,selected,self._clock())
            plan_id=self._store(self._backups,plan)
            return BackupPreview(plan_id,session.device_id,volume,selected,
                request.destination,sum(item.directory for item in items),
                sum(not item.directory for item in items),required,required*3,
                'Keep the C64U volume quiet during backup. Planning reads each file once; execution reads it twice more for verification.',
                self._clock())
        return self._submit('usb.backup.prepare',task,session)

    def _remote_hash(self,client,path,job,phase,base,total):
        ftp=connect(client);digest=hashlib.sha256();count=0
        try:
            expected=ftp.size(path)
            if expected is None:raise BrowserError('The C64U did not report a file size: '+path)
            def receive(block):
                nonlocal count
                job.check_cancel();digest.update(block);count+=len(block)
                job.report(JobProgress(phase,base+count,total,'bytes','Verifying USB backup data…'))
            ftp.retrbinary('RETR '+path,receive)
            if count!=expected or ftp.size(path)!=expected:
                raise BrowserError('A C64U source file changed during verification: '+path)
            return count,digest.hexdigest()
        finally:ftp.close()

    def execute_backup(self,plan_id):
        stored=self._take(self._backups,plan_id,'Backup plan')
        def task(job):
            client=self._client(stored.session);request=stored.request
            if self._volume_fingerprint(client,request.source_volume.path,job.check_cancel)!=stored.volume_fingerprint:
                raise UsbBackupFailure('storage','The C64U volume changed. Create a fresh backup preview.')
            total=sum(item.size for item in stored.items if not item.directory)
            self._check_local_destination(request.destination.path,stored.destination_identity,total)
            folder=Path(request.destination.path);folder.mkdir()
            manifest={'format':MANIFEST_FORMAT,'version':MANIFEST_VERSION,'state':'incomplete',
                'created_at':time.time(),'completed_at':None,
                'source':{'device_id':stored.session.device_id,
                          'volume':request.source_volume.path,
                          'volume_fingerprint':stored.volume_fingerprint,
                          'selected':list(stored.selected)},
                'directories':[],'files':[],'failure':''}
            completed_dirs=[];completed_files=[];bytes_done=0
            _json_write(folder/MANIFEST_NAME,manifest)
            try:
                for item in stored.items:
                    job.check_cancel();target=folder/Path(*item.relative.split('/'))
                    if item.directory:
                        entry=next((row for row in client.list_directory(
                            posixpath.dirname(item.path))[1]
                            if row.name==posixpath.basename(item.path)),None)
                        if entry is None or entry.kind!='dir':
                            raise BrowserError('A C64U source folder changed after preview: '+item.path)
                        target.mkdir(parents=True)
                        completed_dirs.append(item.relative);manifest['directories'].append(item.relative)
                        _json_write(folder/MANIFEST_NAME,manifest);continue
                    target.parent.mkdir(parents=True,exist_ok=True)
                    entry=next((row for row in client.list_directory(posixpath.dirname(item.path))[1]
                                if row.name==posixpath.basename(item.path)),None)
                    if entry is None or entry.kind!='file' or entry.size!=item.size:
                        raise BrowserError('A C64U source file changed after preview: '+item.path)
                    base=bytes_done
                    progress=job.byte_progress('backup-download')
                    def overall(count):
                        progress.check();job.report(JobProgress('backup-download',base+count,total,'bytes','Backing up USB files…'))
                    overall.check=job.check_cancel
                    first=download(client,item.path,target,overall)
                    local_size,local_digest=_local_hash(target,job.check_cancel)
                    second_size,second_digest=self._remote_hash(
                        client,item.path,job,'backup-verify',base,total)
                    if (first['bytes']!=item.size or local_size!=item.size or second_size!=item.size or
                            first['sha256']!=local_digest or local_digest!=second_digest or
                            local_digest!=item.sha256):
                        target.unlink(missing_ok=True)
                        raise BrowserError('A source file changed or verification failed: '+item.path)
                    bytes_done+=item.size;completed_files.append(item.relative)
                    manifest['files'].append({'path':item.relative,'size':item.size,'sha256':local_digest})
                    _json_write(folder/MANIFEST_NAME,manifest)
                manifest.update(state='complete',completed_at=time.time())
                _json_write(folder/MANIFEST_NAME,manifest)
                return BackupResult(request.destination,str(folder/MANIFEST_NAME),'complete',
                    tuple(completed_dirs),tuple(completed_files),(),bytes_done)
            except Exception as exc:
                message=(str(exc) if isinstance(exc,(BrowserError,OSError))
                         else 'Backup stopped because of an internal error.')
                remaining=tuple(item.relative for item in stored.items
                                if not item.directory and item.relative not in completed_files)
                manifest['failure']=message;_json_write(folder/MANIFEST_NAME,manifest)
                result=BackupResult(request.destination,str(folder/MANIFEST_NAME),'incomplete',
                    tuple(completed_dirs),tuple(completed_files),remaining,bytes_done,message)
                if getattr(exc,'cancelled',False):raise JobCancelled(result=result)
                raise UsbBackupFailure('backup',message,result)
        return self._submit('usb.backup.execute',task,stored.session)

    @staticmethod
    def _load_manifest(folder):
        path=Path(folder)/MANIFEST_NAME
        try:
            if path.stat().st_size>16*1024*1024:
                raise BrowserError('USB backup manifest is too large.')
        except OSError as exc:raise BrowserError('Could not read a valid Argonaut USB backup manifest.') from exc
        try:data=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError) as exc:raise BrowserError('Could not read a valid Argonaut USB backup manifest.') from exc
        if data.get('format')!=MANIFEST_FORMAT or data.get('version')!=MANIFEST_VERSION:
            raise BrowserError('Unsupported USB backup manifest format or version.')
        if not isinstance(data.get('directories'),list) or not isinstance(data.get('files'),list):
            raise BrowserError('USB backup manifest has invalid contents.')
        if len(data['directories'])+len(data['files'])>MAX_ITEMS:
            raise BrowserError('USB backup manifest exceeds the 10,000 item limit.')
        return data

    def _verify_manifest(self,folder,manifest,job):
        issues=[];directories=[];files=[];seen=set()
        for relative in manifest['directories']:
            try:relative=_safe_relative(relative)
            except BrowserError as exc:issues.append(RestoreIssue(str(relative),str(exc)));continue
            key=relative.casefold()
            if key in seen:issues.append(RestoreIssue(relative,'Duplicate or case-colliding manifest path.'));continue
            seen.add(key)
            try:path=_backup_path(folder,relative)
            except BrowserError as exc:issues.append(RestoreIssue(relative,str(exc)));directories.append(relative);continue
            if not path.is_dir() or path.is_symlink():issues.append(RestoreIssue(relative,'Backup folder is missing or unsupported.'))
            directories.append(relative)
        for index,row in enumerate(manifest['files']):
            job.check_cancel();relative=row.get('path') if isinstance(row,dict) else ''
            try:
                relative=_safe_relative(relative);size=row['size'];digest=row['sha256']
                if (type(size) is not int or size<0 or not isinstance(digest,str) or
                        len(digest)!=64 or any(char not in '0123456789abcdef' for char in digest)):raise ValueError
            except (BrowserError,KeyError,ValueError,TypeError):
                issues.append(RestoreIssue(str(relative),'Invalid manifest file record.'));continue
            key=relative.casefold()
            if key in seen:issues.append(RestoreIssue(relative,'Duplicate or case-colliding manifest path.'));continue
            seen.add(key)
            try:path=_backup_path(folder,relative)
            except BrowserError as exc:
                issues.append(RestoreIssue(relative,str(exc)));files.append(_ManifestFile(relative,size,digest));continue
            if not path.is_file() or path.is_symlink():issues.append(RestoreIssue(relative,'Backup file is missing or unsupported.'))
            else:
                actual_size,actual_digest=_local_hash(path,job.check_cancel)
                if actual_size!=size or actual_digest!=digest:issues.append(RestoreIssue(relative,'Backup bytes do not match the manifest.'))
            files.append(_ManifestFile(relative,size,digest))
            job.report(JobProgress('verify-backup',index+1,len(manifest['files']),'files','Verifying backup files…'))
        if manifest.get('state')!='complete':issues.append(RestoreIssue(MANIFEST_NAME,'Backup is incomplete.'))
        return tuple(directories),tuple(files),tuple(issues)

    def _classify(self,client,volume,folder,directories,files,job):
        additions=[];replacements=[];unchanged=[];conflicts=[];digests=[]
        missing_directories=set();conflict_directories=set()
        cache={}
        def entry(relative):
            parent=posixpath.dirname(relative);name=posixpath.basename(relative)
            if any(parent==item or parent.startswith(item+'/') for item in missing_directories):return None
            if any(parent==item or parent.startswith(item+'/') for item in conflict_directories):return 'collision'
            rows=cache.setdefault(parent,client.list_directory(
                volume if not parent else posixpath.join(volume,parent))[1])
            matches=[row for row in rows if row.name.casefold()==name.casefold()]
            if not matches:return None
            if len(matches)!=1 or matches[0].name!=name:return 'collision'
            return matches[0]
        for relative in sorted(directories,key=lambda value:(value.count('/'),value.casefold())):
            job.check_cancel();target=entry(relative)
            if target is None:additions.append(relative+'/');missing_directories.add(relative)
            elif target=='collision' or target.kind!='dir':conflicts.append(relative+'/');conflict_directories.add(relative)
            else:unchanged.append(relative+'/')
        for index,item in enumerate(files):
            job.check_cancel();target=entry(item.path)
            if target is None:additions.append(item.path)
            elif target=='collision' or target.kind!='file':conflicts.append(item.path)
            else:
                remote_path=posixpath.join(volume,item.path)
                if target.size!=item.size:
                    replacements.append(item.path);digests.append((item.path,'size:'+str(target.size)))
                else:
                    _,digest=self._remote_hash(client,remote_path,job,'compare',index,len(files))
                    digests.append((item.path,digest))
                    (unchanged if digest==item.sha256 else replacements).append(item.path)
            job.report(JobProgress('compare',index+1,len(files),'files','Comparing restore destination…'))
        return _Classification(tuple(additions),tuple(replacements),tuple(unchanged),
                               tuple(conflicts),tuple(digests))

    def prepare_restore(self,backup_folder,target_volume):
        self._locations((backup_folder,target_volume))
        if backup_folder.scope!=CORE_HOST or target_volume.scope!=C64U:
            raise BrowserError('USB restore requires a Core-host backup and C64U destination.')
        folder=Path(backup_folder.path)
        if not folder.is_dir() or folder.is_symlink():raise BrowserError('Choose an Argonaut USB backup folder.')
        volume=storage_root(target_volume.path)
        if not volume or target_volume.path!=volume:raise BrowserError('Choose a C64U USB or SD volume root.')
        session=self._session_provider()
        def task(job):
            manifest=self._load_manifest(folder)
            directories,files,issues=self._verify_manifest(folder,manifest,job)
            client=self._client(session);fingerprint=self._volume_fingerprint(client,volume,job.check_cancel)
            classification=(_Classification((),(),(),(),()) if issues else
                            self._classify(client,volume,folder,directories,files,job))
            plan=_RestorePlan(folder,self._backup_identity(folder),volume,session,fingerprint,manifest,files,
                              directories,classification,self._clock())
            plan_id=self._store(self._restores,plan)
            sizes={item.path:item.size for item in files}
            return RestorePreview(plan_id,backup_folder,session.device_id,volume,
                classification.additions,classification.replacements,
                classification.unchanged,classification.conflicts,issues,
                sum(sizes.get(path.rstrip('/'),0) for path in classification.additions+classification.replacements),
                sum(sizes.get(path,0) for path in classification.replacements),False,self._clock())
        return self._submit('usb.restore.prepare',task,session)

    def execute_restore(self,plan_id,*,replace=False):
        stored=self._take(self._restores,plan_id,'Restore plan')
        def task(job):
            if self._backup_identity(stored.backup_folder)!=stored.backup_identity:
                raise UsbBackupFailure('storage','The storage containing the backup folder changed. Create a fresh preview.')
            directories,files,issues=self._verify_manifest(stored.backup_folder,stored.manifest,job)
            if issues:raise UsbBackupFailure('backup-invalid','The backup changed or is incomplete. Create a fresh restore preview.')
            client=self._client(stored.session)
            if self._volume_fingerprint(client,stored.target_volume,job.check_cancel)!=stored.volume_fingerprint:
                raise UsbBackupFailure('storage','The selected C64U volume changed. Create a fresh restore preview.')
            current=self._classify(client,stored.target_volume,stored.backup_folder,directories,files,job)
            if current!=stored.classification:
                raise UsbBackupFailure('changed','The restore source or destination changed. Create a fresh preview.')
            if stored.classification.replacements and replace is not True:
                replacement_set=set()
            else:replacement_set=set(stored.classification.replacements)
            additions=set(stored.classification.additions)
            file_map={item.path:item for item in files};steps=[]
            for relative in sorted(directories,key=lambda value:(value.count('/'),value.casefold())):
                display=relative+'/'
                if display in additions:
                    steps.append(Step(relative,_backup_path(stored.backup_folder,relative),
                        posixpath.join(stored.target_volume,relative),True,False))
            for item in files:
                source=_backup_path(stored.backup_folder,item.path)
                destination=posixpath.join(stored.target_volume,item.path)
                if item.path in additions:steps.append(Step(item.path,source,destination,False,False))
                elif item.path in replacement_set:
                    steps.append(Step(item.path,source,destination,False,True,
                                      signature(client,False,destination)))
            plan=Plan(steps=steps)
            report=execute_plan(client,plan,True,False,job.byte_progress('restore'))
            completed=set(value.rstrip('/') for value in report.completed)
            replaced=tuple(path for path in replacement_set if path in completed)
            added=tuple(path for path in stored.classification.additions if path.rstrip('/') in completed)
            skipped=tuple(path for path in stored.classification.replacements if path not in replacement_set)
            partial=(PartialUpload(FileLocation.c64u(report.partial),
                        stored.session.device_id,stored.session.session_id)
                     if report.partial else None)
            result=RestoreResult(added,replaced,stored.classification.unchanged,skipped,
                stored.classification.conflicts,tuple(report.remaining),
                sum(file_map[path].size for path in completed if path in file_map),
                report.partial,report.error,partial)
            if report.cancelled:raise JobCancelled(result=result)
            if report.error:raise UsbBackupFailure('restore',report.error,result)
            return result
        return self._submit('usb.restore.execute',task,stored.session)
