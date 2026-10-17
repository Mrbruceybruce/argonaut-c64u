# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only managed D64 launch evidence. This module has no dispatch capability."""
from dataclasses import dataclass
import hashlib
from threading import Lock
import time
import uuid

from .api import BrowserError
from .disk_image import D64Image, DiskImageError
from .ftp_reads import read_operation
from .jobs import CoreJob
from .managed_library import ManagedLibrary, ManagedLibraryReader, LibraryIdentity, ManagedGame, location
from .native_files import read_remote_game
from .scheduler import DeviceSession, JobBinding


@dataclass(frozen=True)
class ManagedD64Selection:
    session: DeviceSession
    library: LibraryIdentity
    revision: int
    manifest_sha256: str
    game: ManagedGame
    context_epoch: int

    @property
    def game_path(self):
        return self.library.path+'/'+self.game.path


@dataclass(frozen=True)
class ManagedD64Plan:
    plan_id: str
    selection: ManagedD64Selection
    created_at: float
    expires_at: float
    method: str = 'dma-run-img'
    warning: str = 'Execution may interrupt the running program and reset the C64. No command has been sent.'

    @property
    def title(self):return self.selection.game.title
    @property
    def device_id(self):return self.selection.session.device_id
    @property
    def library_path(self):return self.selection.library.path
    @property
    def game_path(self):return self.selection.game_path
    @property
    def format(self):return self.selection.game.format
    @property
    def verified_size(self):return self.selection.game.size
    @property
    def verified_sha256(self):return self.selection.game.sha256


class ManagedD64Preflight:
    """Core-owned bounded plans; consumption returns evidence, never executes it.

    A future executor must revalidate content and context again before dispatch.
    No game bytes, transport handles or credentials are returned to callers.
    """
    def __init__(self, core, *, clock=time.monotonic, ttl=300, limit=64):
        self._core=core;self._clock=clock;self._ttl=max(0,min(float(ttl),300))
        self._limit=max(1,min(int(limit),128))
        self._lock=Lock();self._epoch=0;self._plans={};self._closed=False
        self._unsubscribe=core.add_listener(self._event)

    def _event(self,event):
        if event.kind in ('connected','reconnected','offline','disconnected','library-location-changed'):
            self.invalidate()

    def invalidate(self):
        with self._lock:
            self._epoch+=1;self._plans.clear()

    def close(self):
        with self._lock:
            if self._closed:return
            self._closed=True;self._epoch+=1;self._plans.clear()
        self._unsubscribe()

    def _check(self,selection,client=None,job=None):
        if job is not None:job.check_cancel()
        with self._lock:
            if self._closed or selection.context_epoch!=self._epoch:
                raise BrowserError('Managed launch context changed. Prepare again.')
        if self._core.device_session()!=selection.session or not selection.session.session_id:
            raise BrowserError('Managed launch device or session changed.')
        current=self._core._require_client()
        if client is not None and current is not client:raise BrowserError('Managed launch client changed.')
        configured=location(self._core.preferences.game_library_location)
        if configured is None or configured!=selection.library.preference():
            raise BrowserError('Configured library changed. No discovery was performed.')
        if selection.library.device_id!=selection.session.device_id:
            raise BrowserError('Managed game belongs to another device.')

    def selection(self,library,game_id,expected_session):
        """Bind a validated library snapshot and game UUID, never GUI text."""
        with self._core._session_admission():
            if type(library) is not ManagedLibrary or not library.manifest_sha256:
                raise BrowserError('A validated managed-library snapshot is required.')
            matches=[game for game in library.games if game.id==game_id]
            if len(matches)!=1 or matches[0].format!='D64':
                raise BrowserError('Select exactly one managed D64 game.')
            with self._lock:epoch=self._epoch
            selected=ManagedD64Selection(expected_session,library.identity,library.revision,
                                         library.manifest_sha256,matches[0],epoch)
            self._check(selected)
            return selected

    def _prune(self):
        now=self._clock()
        for key,plan in tuple(self._plans.items()):
            if now>=plan.expires_at:self._plans.pop(key)
        while len(self._plans)>self._limit:self._plans.pop(next(iter(self._plans)))

    def _validated_bytes(self, selection, client, job):
        """Shared strict read; return verified bytes only after FTP scope cleanup."""
        check=lambda:self._check(selection,client,job)
        with read_operation(client,check):
            reader=ManagedLibraryReader(client.list_directory,
                lambda path,maximum:read_remote_game(client,path,maximum,check=check),
                selection.session,check)
            def validate_library():
                # Exact configured path; never invoke discovery.
                library=reader.load(selection.library.path,selection.library.library_id)
                if (library.identity!=selection.library or library.revision!=selection.revision
                        or library.manifest_sha256!=selection.manifest_sha256
                        or [g for g in library.games if g.id==selection.game.id]!=[selection.game]
                        or selection.game.format!='D64'):
                    raise BrowserError('Managed library manifest or selected game changed.')
            def validate_path():
                parent=selection.library.path
                parts=selection.game.path.split('/')
                for part in parts[:-1]:
                    parent+='/'+part
                    reader.entries(parent)  # PWD must equal each requested directory.
                entries=reader.entries(parent)
                matches=[e for e in entries if e.name.casefold()==parts[-1].casefold()]
                if (len(matches)!=1 or matches[0].name!=parts[-1] or matches[0].kind!='file'
                        or matches[0].size!=selection.game.size):
                    raise BrowserError('Managed D64 path or directory size changed.')
            validate_library();validate_path()
            data=read_remote_game(client,selection.game_path,206114,check=check)
            check()
            if len(data)!=selection.game.size or hashlib.sha256(data).hexdigest()!=selection.game.sha256:
                raise BrowserError('Managed D64 byte count or SHA-256 changed.')
            try:
                disk=D64Image(data);disk.directory();validation=disk.validate()
            except (DiskImageError,ValueError) as exc:
                raise BrowserError('Managed D64 structure is invalid.') from exc
            if any(issue!='geometry.extended_tracks' for issue in validation.issues):
                raise BrowserError('Managed D64 failed structural validation.')
            check();validate_path();validate_library();check()
        return data

    def prepare(self,selection):
        if type(selection) is not ManagedD64Selection:raise BrowserError('Managed D64 selection required.')
        with self._core._session_admission():
            self._check(selection)
            client=self._core._require_client()
        def task(job):
            check=lambda:self._check(selection,client,job)
            self._validated_bytes(selection,client,job)
            # Close the FTP scope before publishing evidence. The session gate
            # excludes configuration/connection replacement at publication.
            with self._core._session_admission():
                check()
                now=self._clock()
                plan=ManagedD64Plan(uuid.uuid4().hex,selection,now,now+self._ttl)
                with self._lock:
                    if self._closed or selection.context_epoch!=self._epoch:
                        raise BrowserError('Managed launch context changed.')
                    self._plans[plan.plan_id]=plan;self._prune()
                return plan
        return self._core.scheduler.submit(CoreJob('game-library.managed-preflight',task),
                                           JobBinding.device(selection.session))

    def consume_plan(self,plan_id):
        """Single-use evidence handoff ONLY. No dispatch exists in this slice."""
        # Claim once before admission: every subsequent failure burns the token.
        with self._lock:
            self._prune();plan=self._plans.pop(plan_id,None)
        if plan is None:raise BrowserError('Managed launch plan expired, invalidated or already used.')
        with self._core._session_admission():
            self._check(plan.selection)
            return plan

    def discard_plan(self,plan_id):
        with self._lock:return self._plans.pop(plan_id,None) is not None
