# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit empty-library creation. All I/O uses the existing managed adapter."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from .managed_library import APPLICATION, LibraryError, parse_manifest, uuid_text
from .storage import storage_root
from .jobs import JobCancelled


@dataclass(frozen=True)
class CreationTarget:
    token: str
    device_id: str
    session_id: str
    root: str
    path: str


@dataclass(frozen=True)
class CreationRecovery:
    path: str
    phase: str
    removed: tuple
    retained: tuple
    message: str


class CreationError(LibraryError):
    code='library-creation'
    def __init__(self,result):
        super().__init__(result.message)
        self.result=result


def create_empty_library(adapter,target,check,session_check):
    """No recursive cleanup, mutation replay, overwrite or atomic-rename claim."""
    folder=target.path;created=[];phase='preflight'
    pending=folder+'/manifest.pending-'+target.token
    manifest=folder+'/manifest.json'
    data=(json.dumps(dict(schema_version=1,library_id=target.token,
        created_at=datetime.now(timezone.utc).isoformat(),application=APPLICATION,
        revision=0,games=[]),sort_keys=True)+'\n').encode()

    def listing(path):
        check();actual,entries=adapter.list_directory(path);check()
        if actual!=path:raise LibraryError('Creation path changed.')
        return tuple(entries)

    def absent(parent,name):
        if any(e.name.casefold()==name.casefold() for e in listing(parent)):
            raise LibraryError('Destination already exists; nothing will be adopted or overwritten.')

    def write(path,payload):
        check()
        with io.BytesIO(payload) as stream:sent=adapter.write_from(path,stream,len(payload))
        digest=hashlib.sha256(payload).hexdigest()
        if sent.transferred!=len(payload) or sent.sha256!=digest:
            raise LibraryError('Creation write was not verified.')
        observed=adapter.read(path,len(payload));check()
        if observed!=payload:raise LibraryError('Creation readback differs.')

    def verify_structure(manifest_name):
        entries=listing(folder)
        expected={'games','metadata','artwork',manifest_name}
        names={e.name for e in entries}
        extra=names-expected
        if extra:raise LibraryError('Unexpected content in new library: '+', '.join(sorted(extra)))
        missing=expected-names
        if missing:raise LibraryError('Missing expected creation evidence: '+', '.join(sorted(missing)))
        for name in expected:
            matches=[e for e in entries if e.name.casefold()==name.casefold()]
            kind='file' if name==manifest_name else 'dir'
            if len(matches)!=1 or matches[0].name!=name or matches[0].kind!=kind:
                raise LibraryError('Invalid/incomplete library structure: '+name)
            if kind=='dir' and listing(folder+'/'+name):
                raise LibraryError('Unexpected content in new library directory: '+name)

    try:
        if (storage_root(target.root)!=target.root or target.path!=target.root+'/ARGONAUT_LIBRARY'
                or not target.device_id or not target.session_id):
            raise LibraryError('Invalid USB/SD library creation target.')
        uuid_text(target.token)
        roots=listing('/')
        if not any(e.name==target.root[1:] and e.kind=='dir' for e in roots):
            raise LibraryError('Selected storage root is unavailable.')
        absent(target.root,'ARGONAUT_LIBRARY')
        phase='directory'
        check();adapter.mutate('mkdir',folder);created.append(folder)
        # Refuse unexpected content before publishing anything into a new folder.
        if listing(folder):raise LibraryError('New library directory is not empty.')
        for name in ('games','metadata','artwork'):
            phase=name
            absent(folder,name);check()
            adapter.mutate('mkdir',folder+'/'+name);created.append(folder+'/'+name)
        phase='manifest-staging';absent(folder,pending.rsplit('/',1)[1]);write(pending,data)
        # The manifest is the completion record. Verify all prerequisites before
        # publishing it; no hidden marker or atomic rename assumption is needed.
        phase='verification'
        verify_structure(pending.rsplit('/',1)[1])
        observed=adapter.read(pending,len(data));check()
        if observed!=data:raise LibraryError('Invalid staged manifest: readback differs.')
        library=parse_manifest(observed,target.device_id,folder)
        if library.identity.library_id!=target.token:
            raise LibraryError('Invalid library state: creation identity changed.')
        phase='manifest-publication';absent(folder,'manifest.json');check()
        adapter.mutate('rename',pending,manifest)
        phase='completion'
        verify_structure('manifest.json')
        observed=adapter.read(manifest,len(data));check()
        if observed!=data:raise LibraryError('Invalid published manifest: readback differs.')
        if parse_manifest(observed,target.device_id,folder)!=library:
            raise LibraryError('Invalid library state: published identity changed.')
        return library
    except Exception as exc:
        removed=[]
        # Once a mutation failed, open a fresh managed operation for cleanup.
        # Never replay the failed mutation or follow a replacement session.
        try:
            session_check()
            # Adapter context is scoped per call; an uncertain transport may refuse
            # further work. In that case all evidence remains for manual recovery.
            for path in reversed(created) if phase in ('directory','games','metadata','artwork','manifest-staging') else ():
                session_check()
                actual,entries=adapter.list_directory(path)
                if actual!=path or entries:continue
                adapter.mutate('rmdir',path);removed.append(path)
        except Exception:pass
        retained=tuple(p for p in created if p not in removed)
        message=('Library creation did not complete at '+folder+'. Phase: '+phase+'. '+str(exc))
        if retained or phase not in ('preflight',):
            message+=' Recovery required: inspect this exact location. No files were automatically deleted or retried.'
        result=CreationRecovery(folder,phase,tuple(removed),retained,message)
        if getattr(exc,'cancelled',False):raise JobCancelled(message,result) from None
        raise CreationError(result) from None
