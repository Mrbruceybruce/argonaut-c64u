# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only picker contracts. Selections are references, never execution authority."""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import posixpath
from .storage import recognized_root, storage_root


class PickerError(ValueError):
    pass


class PickerMode(str, Enum):
    OPEN_FILE = 'open-file'
    OPEN_FILES = 'open-files'
    OPEN_FOLDER = 'open-folder'


@dataclass(frozen=True)
class PickerFilter:
    category: str
    label: str
    extensions: tuple[str, ...]

    def matches(self, name):
        return not self.extensions or Path(name).suffix.casefold() in self.extensions


SID = PickerFilter('sid', 'SID files (.sid)', ('.sid',))
DRIVES = PickerFilter('drives', 'Disk images', ('.d64', '.g64', '.d71', '.g71', '.d81'))
GAMES = PickerFilter('games', 'D64 and CRT games', ('.d64', '.crt'))


@dataclass(frozen=True)
class PickerSelection:
    scope: str
    path: str
    filename: str
    storage_root: str
    device_id: str
    session_id: str
    category: str
    kind: str

    def validate_session(self, session):
        """Consumers must call at submission; content validation remains theirs."""
        if self.scope == 'c64u' and (not self.session_id or
                (self.device_id, self.session_id) != (session.device_id, session.session_id)):
            raise PickerError('Connection changed. Select the file again.')


@dataclass(frozen=True)
class BrowseToken:
    generation: int
    scope: str
    path: str
    device_id: str
    session_id: str


@dataclass(frozen=True)
class PickerEntry:
    name: str
    kind: str
    size: int | None = None


def safe_name(name):
    return (isinstance(name, str) and name not in ('', '.', '..') and
            not any(c in name for c in '/\\') and
            not any(ord(c) < 32 or ord(c) == 127 for c in name))


class PickerModel:
    def __init__(self, mode=PickerMode.OPEN_FILE, scopes=('core-host', 'c64u'),
                 filter=SID, limit=1):
        self.mode = PickerMode(mode)
        self.scopes = tuple(scopes)
        if not self.scopes or any(s not in ('core-host', 'c64u') for s in self.scopes):
            raise PickerError('Choose supported source scopes.')
        if type(limit) is not int or limit < 1:
            raise PickerError('Selection limit must be positive.')
        if not isinstance(filter, PickerFilter):raise PickerError('A picker filter is required.')
        self.filter, self.limit = filter, limit if self.mode == PickerMode.OPEN_FILES else 1
        self.generation = 0
        self.pending = self.loaded = None
        self.entries = ()

    def invalidate(self):
        self.generation += 1
        self.pending = self.loaded = None
        self.entries = ()

    def begin(self, scope, path, session):
        self.invalidate()
        if scope not in self.scopes:raise PickerError('Source is not allowed.')
        if scope == 'c64u':
            if path != '/' and recognized_root(path) is None:
                raise PickerError('Choose an exact USB, SD, Flash or Temp path.')
            if not session.device_id or not session.session_id:
                raise PickerError('Connect to a C64 Ultimate first.')
            device, connection = session.device_id, session.session_id
        else:
            path = str(Path(path).expanduser().absolute())
            device = connection = ''
        self.pending = BrowseToken(self.generation, scope, path, device, connection)
        return self.pending

    def current(self, token, session):
        return (token is not None and token.generation == self.generation and
                (token.scope == 'core-host' or
                 (token.device_id, token.session_id) == (session.device_id, session.session_id)))

    @staticmethod
    def local_listing(path):
        rows = []
        for item in Path(path).iterdir():
            try:rows.append(PickerEntry(item.name, 'dir' if item.is_dir() else 'file', item.stat().st_size))
            except OSError:continue
        return path, rows

    def complete(self, token, actual, entries, session):
        if token != self.pending or not self.current(token, session):return False
        if actual != token.path:
            self.invalidate();raise PickerError('Storage path changed or is unavailable.')
        rows = []
        for item in entries:
            if not safe_name(item.name) or item.kind not in ('file', 'dir'):continue
            if token.scope == 'c64u' and token.path == '/':
                if item.kind != 'dir' or recognized_root('/' + item.name) != '/' + item.name:continue
            if item.kind == 'file' and (self.mode == PickerMode.OPEN_FOLDER or not self.filter.matches(item.name)):continue
            rows.append(PickerEntry(item.name, item.kind, item.size))
        self.entries = tuple(sorted(rows, key=lambda e: (e.kind != 'dir', e.name.casefold())))
        self.loaded, self.pending = token, None
        return True

    def parent(self):
        token = self.loaded
        if token is None:raise PickerError('Choose a folder first.')
        return str(Path(token.path).parent) if token.scope == 'core-host' else posixpath.dirname(token.path) or '/'

    def child(self, name):
        if not safe_name(name):raise PickerError('Invalid filename.')
        if self.loaded is None:raise PickerError('Choose a folder first.')
        return (str(Path(self.loaded.path) / name) if self.loaded.scope == 'core-host'
                else posixpath.join(self.loaded.path, name))

    def choose(self, names, session):
        token = self.loaded
        if not self.current(token, session):
            self.invalidate();raise PickerError('Connection or folder changed. Select again.')
        names = tuple(names)
        if self.mode == PickerMode.OPEN_FOLDER and not names:
            paths = [(token.path, 'dir')]
        else:
            if not 1 <= len(names) <= self.limit or len(set(names)) != len(names):
                raise PickerError('Choose the permitted number of items.')
            by_name = {e.name: e for e in self.entries}
            paths = []
            for name in names:
                entry = by_name.get(name)
                kind = 'dir' if self.mode == PickerMode.OPEN_FOLDER else 'file'
                if entry is None or entry.kind != kind:raise PickerError('Choose a supported item.')
                paths.append((self.child(name), kind))
        result = []
        for path, kind in paths:
            root = storage_root(path) if token.scope == 'c64u' else ''
            if token.scope == 'c64u' and not root:
                raise PickerError('Flash and Temp support browsing only; choose USB or SD.')
            result.append(PickerSelection(token.scope, path, Path(path).name, root,
                token.device_id, token.session_id, self.filter.category, kind))
        return tuple(result)
