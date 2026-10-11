# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded read-only managed library contracts; no catalog or storage writes."""
from dataclasses import dataclass
from datetime import datetime
import json
import posixpath
from uuid import UUID
from .api import BrowserError
from .storage import storage_root

MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_GAMES = 10000
APPLICATION = 'argonaut'


class LibraryError(BrowserError):
    pass


def uuid_text(value):
    if not isinstance(value, str):raise LibraryError('Invalid library or game UUID.')
    try:parsed = UUID(value)
    except ValueError as exc:raise LibraryError('Invalid library or game UUID.') from exc
    if str(parsed) != value or parsed.int == 0:raise LibraryError('Use a canonical nonzero UUID.')
    return value


def library_path(path):
    root = storage_root(path)
    if root is None or posixpath.basename(path) != 'ARGONAUT_LIBRARY':
        raise LibraryError('Choose an ARGONAUT_LIBRARY folder inside USB or SD storage.')
    return root


def location(value):
    """One preference, binding an explicit path to a device and optional UUID."""
    if value is None:return None
    if not isinstance(value, dict) or set(value) != {'device_id', 'root', 'path', 'library_id'}:
        raise LibraryError('Invalid configured Game Library location.')
    if not isinstance(value['device_id'], str) or not value['device_id'].strip():
        raise LibraryError('A Game Library location needs a device identity.')
    if library_path(value['path']) != value['root']:raise LibraryError('Library root mismatch.')
    if value['library_id']:uuid_text(value['library_id'])
    elif value['library_id'] != '':raise LibraryError('Invalid library UUID.')
    return dict(value)


def relative_path(value, area):
    if (not isinstance(value, str) or len(value) > 1024 or not value.startswith(area + '/')
            or any(part in ('', '.', '..') for part in value.split('/'))
            or any(ord(c) < 32 or ord(c) == 127 or c in '\\:' for c in value)):
        raise LibraryError('Invalid managed-library relative path.')
    return value


@dataclass(frozen=True)
class LibraryIdentity:
    library_id: str
    device_id: str
    root: str
    path: str

    def preference(self):
        return dict(library_id=self.library_id, device_id=self.device_id,
                    root=self.root, path=self.path)


@dataclass(frozen=True)
class ManagedGame:
    id: str
    path: str
    title: str
    format: str
    size: int
    sha256: str
    metadata_path: str = ''
    artwork_path: str = ''


@dataclass(frozen=True)
class ManagedLibrary:
    identity: LibraryIdentity
    created_at: str
    revision: int
    games: tuple


@dataclass(frozen=True)
class LibraryState:
    status: str
    message: str
    libraries: tuple = ()
    session_id: str = ''


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:raise LibraryError('Duplicate JSON identifier.')
        result[key] = value
    return result


def parse_manifest(data, device_id, path):
    root = library_path(path)
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_MANIFEST_BYTES:
        raise LibraryError('Manifest exceeds its size bound or is empty.')
    try:
        doc = json.loads(data.decode('utf-8'), object_pairs_hook=_object)
        if not isinstance(doc, dict):raise ValueError()
        if set(doc) - {'schema_version','library_id','created_at','application','revision','games'}:
            raise LibraryError('Unknown manifest fields.')
        if type(doc['schema_version']) is not int or doc['schema_version'] != 1:
            raise LibraryError('Unsupported managed-library schema.')
        library_id = uuid_text(doc['library_id'])
        stamp = doc['created_at']
        if not isinstance(stamp,str):raise ValueError()
        created = datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if created.tzinfo is None:raise ValueError()
        if doc['application'] != APPLICATION:raise LibraryError('Manifest does not identify Argonaut.')
        revision = doc['revision']
        if type(revision) is not int or not 0 <= revision <= 2**63-1:raise ValueError()
        entries = doc.get('games', [])
        if not isinstance(entries,list) or len(entries) > MAX_GAMES:raise ValueError()
        games=[];ids=set();paths=set()
        for item in entries:
            if not isinstance(item,dict) or set(item) - {'id','path','title','format','size','sha256','metadata_path','artwork_path'}:
                raise ValueError()
            identity=uuid_text(item['id']);game_path=relative_path(item['path'],'games')
            if identity in ids or game_path.casefold() in paths:
                raise LibraryError('Duplicate game identifier or conflicting path.')
            ids.add(identity);paths.add(game_path.casefold())
            format_=item['format']
            if format_ not in ('D64','CRT') or not game_path.casefold().endswith('.'+format_.lower()):
                raise LibraryError('Only D64 and CRT game entries are supported.')
            size=item['size'];digest=item['sha256'];title=item.get('title',posixpath.basename(game_path))
            if type(size) is not int or not 0 < size <= (206114 if format_=='D64' else 64*1024*1024):raise ValueError()
            if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError()
            if not isinstance(title,str) or not 0 < len(title) <= 512 or any(ord(c)<32 for c in title):raise ValueError()
            metadata=item.get('metadata_path','');artwork=item.get('artwork_path','')
            if metadata:relative_path(metadata,'metadata')
            elif metadata != '':raise ValueError()
            if artwork:relative_path(artwork,'artwork')
            elif artwork != '':raise ValueError()
            games.append(ManagedGame(identity,game_path,title,format_,size,digest,metadata,artwork))
        return ManagedLibrary(LibraryIdentity(library_id,device_id,root,path),stamp,revision,tuple(games))
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError) as exc:
        raise LibraryError('Malformed or invalid managed-library manifest.') from exc


class ManagedLibraryReader:
    """Injected managed read operations only. No recursive traversal."""
    def __init__(self, listing, read, session, check):
        self.listing,self.read,self.session,self.check=listing,read,session,check

    def entries(self,path):
        self.check()
        actual,entries=self.listing(path)
        self.check()
        if actual!=path:raise LibraryError('Storage returned a different library path.')
        return tuple(entries)

    def load(self,path,expected_id=''):
        entries=self.entries(path)
        if any(e.name.startswith(('.argonaut-creation-','manifest.pending-')) for e in entries):
            raise LibraryError('Library creation is incomplete; recovery is required.')
        if not any(e.name=='manifest.json' and e.kind=='file' for e in entries):
            raise LibraryError('Invalid/incomplete library: manifest is missing.')
        for name in ('games','metadata','artwork'):
            matches=[e for e in entries if e.name.casefold()==name]
            if len(matches)!=1 or matches[0].name!=name or matches[0].kind!='dir':
                raise LibraryError('Invalid/incomplete library structure: '+name)
        data=self.read(path+'/manifest.json',MAX_MANIFEST_BYTES)
        self.check()
        library=parse_manifest(data,self.session.device_id,path)
        if expected_id and library.identity.library_id!=expected_id:
            raise LibraryError('The configured library identity changed.')
        return library

    def discover(self,configured=None):
        configured=location(configured)
        if configured:
            if configured['device_id']!=self.session.device_id:
                return LibraryState('unavailable','The configured library belongs to another device.')
            try:library=self.load(configured['path'],configured['library_id'])
            except LibraryError as exc:return LibraryState('unavailable',str(exc))
            return LibraryState('valid','Managed library loaded; game content has not been verified.',(library,),self.session.session_id)
        roots=sorted({ '/'+e.name for e in self.entries('/')
            if e.kind=='dir' and storage_root('/'+e.name)=='/'+e.name })
        libraries=[];errors=[]
        for root in roots:
            # A complete root listing distinguishes absence from an inaccessible path.
            entries=self.entries(root)
            candidate=next((e for e in entries if e.name=='ARGONAUT_LIBRARY'),None)
            if candidate is None:continue
            if candidate.kind!='dir':
                errors.append(root+': ARGONAUT_LIBRARY is not a folder.');continue
            try:libraries.append(self.load(root+'/ARGONAUT_LIBRARY'))
            except LibraryError as exc:errors.append(root+': '+str(exc))
        self.check()
        if errors:return LibraryState('unavailable','Library discovery needs attention. '+' '.join(errors))
        if not libraries:return LibraryState('none','Game Library is not configured. No managed library was found.',(),self.session.session_id)
        if len(libraries)==1:
            return LibraryState('valid','Managed library loaded; game content has not been verified.',tuple(libraries),self.session.session_id)
        duplicate=len({v.identity.library_id for v in libraries})!=len(libraries)
        message=('Copied libraries share a UUID. Select the exact device/location to use.' if duplicate
                 else 'Multiple libraries found. Select one; libraries are never merged.')
        return LibraryState('multiple',message,tuple(libraries),self.session.session_id)
