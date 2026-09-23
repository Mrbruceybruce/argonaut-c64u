# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Headless Game Library catalog for referenced D64 and CRT files.

The catalog owns metadata only.  It never moves, copies, mounts, uploads,
launches, or deletes a referenced game or its artwork.
"""
from dataclasses import dataclass, replace
from pathlib import Path
from threading import RLock
import hashlib
import json
import math
import os
import posixpath
import tempfile
import time
import uuid

from .api import BrowserError, ConnectionFailure
from . import development
from .disk_image import D64Image, DiskImageError
from .jobs import CoreJob, JobCancelled, JobProgress
from .platform_support import config_base, local_hidden
from .scheduler import CoreScheduler, DeviceSession, JobBinding
from .storage import storage_root


CORE_HOST = 'core-host'
C64U = 'c64u'
SCHEMA_VERSION = 1
MAX_CRT_BYTES = 64 * 1024 * 1024
VALID_STATES = frozenset(('available', 'missing', 'changed', 'unavailable'))
BULK_MAX_DIRECTORIES = 10000
BULK_MAX_ENTRIES = 100000
BULK_MAX_CANDIDATES = 50000
BULK_MAX_DEPTH = 32
BULK_MAX_DECLARED_BYTES = 32 * 1024 * 1024 * 1024
BULK_PLAN_TTL = 30 * 60
BULK_PLAN_LIMIT = 8
BULK_IMPORTABLE = frozenset(('new-valid',))


class GameLibraryError(BrowserError):
    def __init__(self, code, message, *, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class GameSource:
    scope: str
    path: str
    device_id: str = ''
    volume: str = ''

    @classmethod
    def core_host(cls, path):
        return cls(CORE_HOST, str(Path(path).expanduser().absolute()))

    @classmethod
    def c64u(cls, device_id, path):
        return cls(C64U, str(path), str(device_id), storage_root(str(path)) or '')


@dataclass(frozen=True)
class ArtworkReference:
    scope: str
    path: str

    @classmethod
    def core_host(cls, path):
        return cls(CORE_HOST, str(Path(path).expanduser().absolute()))


@dataclass(frozen=True)
class GameRecord:
    id: str
    title: str
    source: GameSource
    format: str
    sha256: str
    size: int
    favorite: bool = False
    notes: str = ''
    artwork: ArtworkReference | None = None
    state: str = 'available'
    state_message: str = ''
    metadata: tuple[tuple[str, object], ...] = ()
    created_at: float = 0.0
    updated_at: float = 0.0
    verified_at: float = 0.0


@dataclass(frozen=True)
class SourceInspection:
    source: GameSource
    format: str
    sha256: str
    size: int
    metadata: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class AddResult:
    record: GameRecord
    created: bool
    duplicate_kind: str = ''
    expected_sha256: str = ''
    observed_sha256: str = ''


@dataclass(frozen=True)
class ValidationResult:
    record: GameRecord
    previous_state: str
    expected_sha256: str
    observed_sha256: str = ''


@dataclass(frozen=True)
class RelinkPreview:
    plan_id: str
    record_id: str
    source: GameSource
    expected_sha256: str
    observed_sha256: str
    content_matches: bool
    size: int
    format: str


@dataclass(frozen=True)
class RelinkResult:
    record: GameRecord
    content_changed: bool


@dataclass(frozen=True)
class BulkImportRequest:
    """One bounded Core-host or C64U discovery request."""
    scope: str
    roots: tuple[str, ...]
    recursive: bool = False
    device_id: str = ''
    include_hidden: bool = False
    kind: str = 'folder'

    @classmethod
    def core_host_folder(cls, path, *, recursive=False, include_hidden=False):
        return cls(CORE_HOST, (str(Path(path).expanduser().absolute()),),
                   bool(recursive), '', bool(include_hidden), 'folder')

    @classmethod
    def c64u_folder(cls, device_id, path, *, recursive=False,
                    include_hidden=False):
        return cls(C64U, (str(path),), bool(recursive), str(device_id),
                   bool(include_hidden), 'folder')

    @classmethod
    def c64u_sources(cls, device_id, paths):
        return cls(C64U, tuple(str(path) for path in paths), False,
                   str(device_id), False, 'sources')

    def as_dict(self):
        return {'scope': self.scope, 'roots': list(self.roots),
                'recursive': self.recursive, 'device_id': self.device_id,
                'include_hidden': self.include_hidden, 'kind': self.kind}


@dataclass(frozen=True)
class BulkCandidate:
    id: str
    source: GameSource
    relative_path: str
    classification: str
    importable: bool = False
    format: str = ''
    declared_size: int | None = None
    size: int | None = None
    sha256: str = ''
    metadata: tuple[tuple[str, object], ...] = ()
    existing_record_id: str = ''
    duplicate_candidate_id: str = ''
    error_code: str = ''
    message: str = ''

    def as_dict(self):
        return {
            'id': self.id, 'source': _source_dict(self.source),
            'relative_path': self.relative_path,
            'classification': self.classification,
            'importable': self.importable, 'format': self.format,
            'declared_size': self.declared_size, 'size': self.size,
            'sha256': self.sha256, 'metadata': dict(self.metadata),
            'existing_record_id': self.existing_record_id,
            'duplicate_candidate_id': self.duplicate_candidate_id,
            'error_code': self.error_code, 'message': self.message,
        }


@dataclass(frozen=True)
class BulkScanIssue:
    scope: str
    path: str
    classification: str
    error_code: str
    message: str

    def as_dict(self):
        return {'scope': self.scope, 'path': self.path,
                'classification': self.classification,
                'error_code': self.error_code, 'message': self.message}


@dataclass(frozen=True)
class BulkImportPreview:
    plan_id: str
    request: BulkImportRequest
    candidates: tuple[BulkCandidate, ...]
    issues: tuple[BulkScanIssue, ...]
    eligible_candidate_ids: tuple[str, ...]
    default_selected_candidate_ids: tuple[str, ...]
    classification_counts: tuple[tuple[str, int], ...]
    directories_scanned: int
    entries_seen: int
    supported_candidates: int
    declared_candidate_bytes: int
    created_at: float
    expires_at: float

    def as_dict(self):
        return {
            'plan_id': self.plan_id, 'request': self.request.as_dict(),
            'candidates': [item.as_dict() for item in self.candidates],
            'issues': [item.as_dict() for item in self.issues],
            'eligible_candidate_ids': list(self.eligible_candidate_ids),
            'default_selected_candidate_ids':
                list(self.default_selected_candidate_ids),
            'classification_counts': dict(self.classification_counts),
            'directories_scanned': self.directories_scanned,
            'entries_seen': self.entries_seen,
            'supported_candidates': self.supported_candidates,
            'declared_candidate_bytes': self.declared_candidate_bytes,
            'created_at': self.created_at, 'expires_at': self.expires_at,
        }


@dataclass(frozen=True)
class BulkImportSelection:
    """Serializable approved subset for the later admission slice."""
    plan_id: str
    approved_candidate_ids: tuple[str, ...]

    def as_dict(self):
        return {'plan_id': self.plan_id,
                'approved_candidate_ids': list(self.approved_candidate_ids)}


@dataclass(frozen=True)
class BulkCandidateOutcome:
    candidate_id: str
    source: GameSource
    status: str
    classification: str
    record_id: str = ''
    expected_sha256: str = ''
    observed_sha256: str = ''
    error_code: str = ''
    message: str = ''

    def as_dict(self):
        return {
            'candidate_id': self.candidate_id,
            'source': _source_dict(self.source), 'status': self.status,
            'classification': self.classification,
            'record_id': self.record_id,
            'expected_sha256': self.expected_sha256,
            'observed_sha256': self.observed_sha256,
            'error_code': self.error_code, 'message': self.message,
        }


@dataclass(frozen=True)
class BulkImportResult:
    plan_id: str
    approved_candidate_ids: tuple[str, ...]
    records_created: tuple[GameRecord, ...]
    outcomes: tuple[BulkCandidateOutcome, ...]
    created_count: int
    skipped_count: int
    failure_count: int
    classification_counts: tuple[tuple[str, int], ...]
    catalog_published: bool
    publication_status: str
    catalog_changed_since_review: bool

    def as_dict(self):
        return {
            'plan_id': self.plan_id,
            'approved_candidate_ids': list(self.approved_candidate_ids),
            'records_created': [_record_dict(item)
                                for item in self.records_created],
            'outcomes': [item.as_dict() for item in self.outcomes],
            'created_count': self.created_count,
            'skipped_count': self.skipped_count,
            'failure_count': self.failure_count,
            'classification_counts': dict(self.classification_counts),
            'catalog_published': self.catalog_published,
            'publication_status': self.publication_status,
            'catalog_changed_since_review':
                self.catalog_changed_since_review,
        }


@dataclass(frozen=True)
class _RelinkPlan:
    preview: RelinkPreview
    inspection: SourceInspection
    record: GameRecord
    session: DeviceSession | None
    created_at: float


@dataclass(frozen=True)
class _BulkPlan:
    preview: BulkImportPreview
    session: DeviceSession | None
    created_at: float
    catalog_version: str


def default_catalog_path():
    return config_base() / development.config_name() / 'game-library.json'


def _source_dict(source):
    return {'scope': source.scope, 'path': source.path,
            'device_id': source.device_id, 'volume': source.volume}


def _source_from_dict(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid game source')
    source = GameSource(value.get('scope'), value.get('path'),
                        value.get('device_id', ''), value.get('volume', ''))
    _validate_source(source)
    return source


def _artwork_dict(artwork):
    return None if artwork is None else {'scope': artwork.scope, 'path': artwork.path}


def _artwork_from_dict(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('Invalid artwork reference')
    artwork = ArtworkReference(value.get('scope'), value.get('path'))
    _validate_artwork(artwork, require_file=False)
    return artwork


def _record_dict(record):
    return {
        'id': record.id, 'title': record.title,
        'source': _source_dict(record.source), 'format': record.format,
        'sha256': record.sha256, 'size': record.size,
        'favorite': record.favorite, 'notes': record.notes,
        'artwork': _artwork_dict(record.artwork), 'state': record.state,
        'state_message': record.state_message,
        'metadata': dict(record.metadata),
        'created_at': record.created_at, 'updated_at': record.updated_at,
        'verified_at': record.verified_at,
    }


def _record_from_dict(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid game record')
    required = ('id', 'title', 'source', 'format', 'sha256', 'size',
                'favorite', 'notes', 'state', 'state_message', 'metadata',
                'created_at', 'updated_at', 'verified_at')
    if any(key not in value for key in required):
        raise ValueError('Incomplete game record')
    metadata = value['metadata']
    if not isinstance(metadata, dict) or any(not isinstance(key, str)
                                             for key in metadata):
        raise ValueError('Invalid game metadata')
    record = GameRecord(
        value['id'], value['title'], _source_from_dict(value['source']),
        value['format'], value['sha256'], value['size'], value['favorite'],
        value['notes'], _artwork_from_dict(value.get('artwork')),
        value['state'], value['state_message'], tuple(sorted(metadata.items())),
        value['created_at'], value['updated_at'], value['verified_at'])
    _validate_record(record)
    return record


def _validate_source(source):
    if not isinstance(source, GameSource):
        raise GameLibraryError('source', 'Choose a game source.')
    if source.scope == CORE_HOST:
        path = Path(source.path)
        if not path.is_absolute() or source.device_id or source.volume:
            raise GameLibraryError('source', 'A Core-host source needs one absolute host path.')
    elif source.scope == C64U:
        root = storage_root(source.path)
        if (not source.device_id or not root or root == source.path
                or source.volume != root
                or any(part in ('', '.', '..') for part in source.path.split('/')[1:])):
            raise GameLibraryError(
                'source', 'A C64U source needs a physical device identity and a file inside one USB/SD volume.')
    else:
        raise GameLibraryError('source', 'Unsupported game source scope.')
    suffix = Path(source.path).suffix.casefold()
    if suffix not in ('.d64', '.crt'):
        raise GameLibraryError('unsupported-format', 'Game Library supports D64 and CRT files.')
    return suffix[1:].upper()


def _validate_artwork(artwork, *, require_file=True):
    if not isinstance(artwork, ArtworkReference) or artwork.scope != CORE_HOST:
        raise GameLibraryError('artwork', 'Artwork must reference an image on the Core host.')
    path = Path(artwork.path)
    if not path.is_absolute():
        raise GameLibraryError('artwork', 'Artwork needs an absolute Core-host path.')
    if path.suffix.casefold() not in ('.png', '.jpg', '.jpeg', '.webp'):
        raise GameLibraryError('artwork', 'Choose PNG, JPEG, or WebP artwork.')
    if require_file and (path.is_symlink() or not path.is_file()):
        raise GameLibraryError('artwork', 'Choose an existing regular artwork file.')


def _validate_record(record):
    if (not isinstance(record.id, str) or not record.id
            or not isinstance(record.title, str) or not record.title.strip()
            or record.format not in ('D64', 'CRT')
            or not isinstance(record.sha256, str) or len(record.sha256) != 64
            or any(character not in '0123456789abcdef' for character in record.sha256)
            or type(record.size) is not int or record.size <= 0
            or type(record.favorite) is not bool
            or not isinstance(record.notes, str)
            or record.state not in VALID_STATES
            or not isinstance(record.state_message, str)
            or any(type(value) not in (int, str, bool) for _, value in record.metadata)
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in
                   (record.created_at, record.updated_at, record.verified_at))):
        raise ValueError('Invalid game record')
    if _validate_source(record.source) != record.format:
        raise ValueError('Game source format mismatch')
    if record.artwork is not None:
        _validate_artwork(record.artwork, require_file=False)


def inspect_crt(data):
    """Validate the bounded CRT container and return useful header metadata."""
    data = bytes(data)
    if not 64 <= len(data) <= MAX_CRT_BYTES:
        raise GameLibraryError('malformed-image', 'CRT size is outside the supported validation bound.')
    if data[:16] != b'C64 CARTRIDGE   ':
        raise GameLibraryError('malformed-image', 'The file is not a C64 CRT image.')
    header_length = int.from_bytes(data[0x10:0x14], 'big')
    if not 64 <= header_length <= min(len(data), 4096):
        raise GameLibraryError('malformed-image', 'CRT header length is invalid.')
    version = int.from_bytes(data[0x14:0x16], 'big')
    if version == 0:
        raise GameLibraryError('malformed-image', 'CRT format version is invalid.')
    hardware_type = int.from_bytes(data[0x16:0x18], 'big')
    if data[0x18] not in (0, 1) or data[0x19] not in (0, 1):
        raise GameLibraryError('malformed-image', 'CRT GAME/EXROM flags are invalid.')
    offset = header_length
    chips = 0
    rom_bytes = 0
    while offset < len(data):
        if len(data) - offset < 16 or data[offset:offset + 4] != b'CHIP':
            raise GameLibraryError('malformed-image', 'CRT contains an invalid or truncated CHIP packet.')
        packet_length = int.from_bytes(data[offset + 4:offset + 8], 'big')
        chip_type = int.from_bytes(data[offset + 8:offset + 10], 'big')
        image_size = int.from_bytes(data[offset + 14:offset + 16], 'big')
        if (chip_type not in (0, 1, 2, 3)
                or packet_length != 16 + image_size
                or (image_size == 0 and chip_type != 1)
                or offset + packet_length > len(data)):
            raise GameLibraryError('malformed-image', 'CRT CHIP packet length is invalid.')
        load_address = int.from_bytes(data[offset + 12:offset + 14], 'big')
        if load_address + image_size > 0x10000:
            raise GameLibraryError('malformed-image', 'CRT CHIP packet exceeds the C64 address space.')
        chips += 1
        rom_bytes += image_size
        offset += packet_length
    if not chips:
        raise GameLibraryError('malformed-image', 'CRT contains no CHIP packets.')
    try:
        name = data[0x20:0x40].split(b'\0', 1)[0].decode('ascii').strip()
    except UnicodeDecodeError as exc:
        raise GameLibraryError('malformed-image', 'CRT name is not valid ASCII.') from exc
    return tuple(sorted({
        'cartridge_name': name, 'chips': chips, 'hardware_type': hardware_type,
        'rom_bytes': rom_bytes, 'version': version,
    }.items()))


class GameLibraryService:
    """Core-owned metadata catalog with explicit source identity."""
    def __init__(self, path=None, *, remote_reader=None, remote_lister=None,
                 bulk_remote_reader=None, session_provider=None,
                 scheduler=None, plan_ttl=300, plan_limit=128,
                 bulk_plan_ttl=BULK_PLAN_TTL,
                 bulk_plan_limit=BULK_PLAN_LIMIT,
                 bulk_max_directories=BULK_MAX_DIRECTORIES,
                 bulk_max_entries=BULK_MAX_ENTRIES,
                 bulk_max_candidates=BULK_MAX_CANDIDATES,
                 bulk_max_depth=BULK_MAX_DEPTH,
                 bulk_max_declared_bytes=BULK_MAX_DECLARED_BYTES,
                 clock=time.time, id_factory=lambda: uuid.uuid4().hex):
        self.path = Path(path) if path else default_catalog_path()
        self._remote_reader = remote_reader
        self._remote_lister = remote_lister
        self._bulk_remote_reader = bulk_remote_reader
        self._session_provider = session_provider or (lambda: DeviceSession('', ''))
        self._scheduler = scheduler or CoreScheduler(self._session_provider, clock=clock)
        self._owns_scheduler = scheduler is None
        self._clock = clock
        self._id_factory = id_factory
        self.plan_ttl = max(0, float(plan_ttl))
        self.plan_limit = max(0, int(plan_limit))
        self.bulk_plan_ttl = max(0, float(bulk_plan_ttl))
        self.bulk_plan_limit = max(0, int(bulk_plan_limit))
        self.bulk_max_directories = max(0, int(bulk_max_directories))
        self.bulk_max_entries = max(0, int(bulk_max_entries))
        self.bulk_max_candidates = max(0, int(bulk_max_candidates))
        self.bulk_max_depth = max(0, int(bulk_max_depth))
        self.bulk_max_declared_bytes = max(0, int(bulk_max_declared_bytes))
        self._records = {}
        self._plans = {}
        self._bulk_plans = {}
        self._lock = RLock()
        self._loaded = False
        self._load_error = None

    def load(self):
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            if (not isinstance(raw, dict) or raw.get('schema_version') != SCHEMA_VERSION
                    or not isinstance(raw.get('games'), list)):
                raise ValueError('Unsupported Game Library catalog')
            records = [_record_from_dict(item) for item in raw['games']]
            if len({record.id for record in records}) != len(records):
                raise ValueError('Duplicate game IDs')
        except FileNotFoundError:
            records = []
        except (OSError, UnicodeError, ValueError, TypeError, KeyError,
                GameLibraryError) as exc:
            self._load_error = GameLibraryError(
                'catalog', 'Cannot load the Game Library catalog; the original file has been kept.')
            raise self._load_error from exc
        with self._lock:
            self._records = {record.id: record for record in records}
            self._loaded = True
            self._load_error = None
        return self

    def _ready(self):
        if self._load_error is not None:
            raise self._load_error
        if not self._loaded:
            self.load()

    def _save_locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = {'schema_version': SCHEMA_VERSION,
                'games': [_record_dict(record) for record in
                          sorted(self._records.values(), key=lambda item: item.id)]}
        descriptor, temporary = tempfile.mkstemp(
            dir=self.path.parent, prefix='.game-library-', suffix='.json')
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            try:
                directory = os.open(self.path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                try: os.fsync(directory)
                finally: os.close(directory)
            except OSError:
                pass
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def _catalog_version_locked(self):
        payload = [_record_dict(record) for record in
                   sorted(self._records.values(), key=lambda item:item.id)]
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

    def _replace(self, record):
        _validate_record(record)
        with self._lock:
            previous = self._records.get(record.id)
            self._records[record.id] = record
            try: self._save_locked()
            except BaseException:
                if previous is None:self._records.pop(record.id, None)
                else:self._records[record.id] = previous
                raise
        return record

    def list(self):
        self._ready()
        with self._lock:return tuple(sorted(self._records.values(), key=lambda item:(item.title.casefold(), item.id)))

    def get(self, record_id):
        self._ready()
        with self._lock:record = self._records.get(record_id)
        if record is None:raise GameLibraryError('not-found', 'Game Library entry was not found.')
        return record

    def search(self, text='', *, favorite=None):
        if not isinstance(text, str) or favorite not in (None, True, False):
            raise GameLibraryError('query', 'Use a text search and an optional favorite filter.')
        query = text.strip().casefold()
        return tuple(record for record in self.list()
                     if (favorite is None or record.favorite is favorite)
                     and (not query or query in ' '.join((record.title, record.notes,
                                                          record.source.path)).casefold()))

    def _edit(self, record_id, **changes):
        record = self.get(record_id)
        return self._replace(replace(record, updated_at=self._clock(), **changes))

    def edit_title(self, record_id, title):
        if not isinstance(title, str) or not title.strip():
            raise GameLibraryError('metadata', 'Enter a game title.')
        return self._edit(record_id, title=title.strip())

    def set_favorite(self, record_id, favorite):
        if type(favorite) is not bool:
            raise GameLibraryError('metadata', 'Favorite must be on or off.')
        return self._edit(record_id, favorite=favorite)

    def set_notes(self, record_id, notes):
        if not isinstance(notes, str):
            raise GameLibraryError('metadata', 'Notes must be text.')
        return self._edit(record_id, notes=notes)

    def set_artwork(self, record_id, artwork):
        if artwork is not None:_validate_artwork(artwork)
        return self._edit(record_id, artwork=artwork)

    def remove(self, record_id):
        record = self.get(record_id)
        with self._lock:
            self._records.pop(record_id)
            try:self._save_locked()
            except BaseException:
                self._records[record_id] = record
                raise
        return record

    def _session(self):
        value = self._session_provider()
        return value if isinstance(value, DeviceSession) else DeviceSession('test-device', str(value))

    def _binding(self, source, *, allow_unavailable=False):
        if source.scope == CORE_HOST:return JobBinding.core_host(), None
        current = self._session()
        if not current.device_id or source.device_id != current.device_id:
            if allow_unavailable:return JobBinding.core_host(), None
            raise GameLibraryError('device-unavailable', 'The source C64U is not the active device.')
        if not current.session_id:
            if allow_unavailable:return JobBinding.core_host(), None
            raise GameLibraryError('device-unavailable', 'Connect to the source C64U first.')
        return JobBinding.device(current), current

    def _submit(self, operation, source, task, *, allow_unavailable=False):
        _validate_source(source)
        binding, session = self._binding(source, allow_unavailable=allow_unavailable)
        return self._scheduler.submit(CoreJob(operation, lambda job:task(job, session)), binding)

    def _read(self, source, job, expected_session=None):
        if source.scope == CORE_HOST:
            path = Path(source.path)
            if path.is_symlink() or not path.is_file():
                raise GameLibraryError('missing-source', 'The referenced game file is missing.')
            before = path.stat()
            size = before.st_size
            limit = 206114 if path.suffix.casefold() == '.d64' else MAX_CRT_BYTES
            if not 0 < size <= limit:
                raise GameLibraryError('malformed-image', 'Game file size is outside the supported validation bound.')
            chunks = []
            completed = 0
            with path.open('rb') as stream:
                while True:
                    block = stream.read(1024 * 1024)
                    if not block:break
                    chunks.append(block);completed += len(block)
                    job.report(JobProgress('hash', completed, size, 'bytes', 'Validating game file…'))
                    job.check_cancel()
            after = path.stat()
            if (after.st_size != size or after.st_mtime_ns != before.st_mtime_ns
                    or getattr(after, 'st_ino', None) != getattr(before, 'st_ino', None)):
                raise GameLibraryError('changed-source', 'The game file changed while it was being validated.')
            return b''.join(chunks)
        current = self._session()
        if expected_session is None or current != expected_session or source.device_id != current.device_id:
            raise GameLibraryError('session', 'The C64U connection changed. Validate the game again.')
        if self._remote_reader is None:
            raise GameLibraryError('device-unavailable', 'C64U source reading is unavailable.')
        try:data = self._remote_reader(source)
        except ConnectionFailure as exc:
            raise GameLibraryError('device-unavailable', 'The source C64U is unavailable.', retryable=True) from exc
        if not isinstance(data, bytes):
            raise GameLibraryError('source', 'C64U source reader returned invalid data.')
        job.report(JobProgress('hash', len(data), len(data), 'bytes', 'Validating C64U game file…'))
        job.check_cancel()
        return data

    def _inspect(self, source, job, session=None):
        inspection, _data = self._inspect_data(source, job, session)
        return inspection

    def _inspect_data(self, source, job, session=None):
        """Internal Core-service handoff; game bytes never enter client results."""
        format_name = _validate_source(source)
        data = self._read(source, job, session)
        return self._inspection_from_data(source, format_name, data), data

    @staticmethod
    def _inspection_from_data(source, format_name, data):
        digest = hashlib.sha256(data).hexdigest()
        if format_name == 'D64':
            try:
                image = D64Image(data)
                directory = image.directory()
                validation = image.validate()
            except (DiskImageError, ValueError) as exc:
                raise GameLibraryError('malformed-image', 'The D64 image is malformed or unsupported.') from exc
            serious = tuple(issue for issue in validation.issues
                            if issue != 'geometry.extended_tracks')
            if serious:
                raise GameLibraryError('malformed-image', 'The D64 image failed structural validation.')
            metadata = tuple(sorted({
                'blocks_free': directory.blocks_free,
                'disk_name': directory.disk_name,
                'entries': len(directory.entries),
                'standard': validation.standard_compatible,
                'tracks': directory.geometry.tracks,
            }.items()))
        else:
            metadata = inspect_crt(data)
        return SourceInspection(source, format_name, digest, len(data), metadata)

    def add(self, source, *, title=''):
        self._ready()
        if not isinstance(title, str):
            raise GameLibraryError('metadata', 'Game title must be text.')
        def task(job, session):
            inspection = self._inspect(source, job, session)
            with self._lock:
                same_source = next((record for record in self._records.values()
                                    if record.source == source), None)
                same_content = next((record for record in self._records.values()
                                     if record.sha256 == inspection.sha256), None)
                if same_source:
                    kind = ('source' if same_source.sha256 == inspection.sha256
                            else 'source-changed')
                    if kind == 'source-changed':
                        self._edit(same_source.id, state='changed',
                                   state_message='The referenced file content changed.')
                        same_source = self.get(same_source.id)
                    return AddResult(same_source, False, kind, same_source.sha256,
                                     inspection.sha256)
                if same_content:
                    return AddResult(same_content, False, 'content',
                                     same_content.sha256, inspection.sha256)
                now = self._clock()
                display = title.strip() if title.strip() else Path(source.path).stem
                record = GameRecord(self._id_factory(), display, source,
                                    inspection.format, inspection.sha256,
                                    inspection.size, metadata=inspection.metadata,
                                    created_at=now, updated_at=now, verified_at=now)
                self._replace(record)
                return AddResult(record, True)
        return self._submit('game-library.add', source, task)

    def validate_source(self, record_id):
        record = self.get(record_id)
        binding, session = self._binding(record.source, allow_unavailable=True)
        def task(job):
            previous = self.get(record_id)
            def unchanged():
                current = self.get(record_id)
                if (current.source != previous.source
                        or current.sha256 != previous.sha256):
                    raise GameLibraryError(
                        'record-changed', 'The Game Library entry changed during validation. Validate it again.')
            if previous.source.scope == C64U and session is None:
                unchanged()
                updated = self._edit(record_id, state='unavailable',
                                     state_message='The source C64U is not connected.')
                return ValidationResult(updated, previous.state, previous.sha256)
            try:inspection = self._inspect(previous.source, job, session)
            except GameLibraryError as exc:
                if exc.code == 'missing-source':
                    unchanged()
                    updated = self._edit(record_id, state='missing', state_message=str(exc))
                    return ValidationResult(updated, previous.state, previous.sha256)
                if exc.code in ('device-unavailable', 'session'):
                    unchanged()
                    updated = self._edit(record_id, state='unavailable', state_message=str(exc))
                    return ValidationResult(updated, previous.state, previous.sha256)
                if exc.code in ('malformed-image', 'changed-source'):
                    unchanged()
                    updated = self._edit(
                        record_id, state='changed',
                        state_message='The referenced file changed and no longer validates.')
                    return ValidationResult(updated, previous.state, previous.sha256)
                raise
            unchanged()
            changed = inspection.sha256 != previous.sha256
            updated = self._edit(
                record_id, state='changed' if changed else 'available',
                state_message='The referenced file content changed.' if changed else '',
                size=inspection.size, metadata=inspection.metadata,
                verified_at=self._clock())
            return ValidationResult(updated, previous.state, previous.sha256,
                                    inspection.sha256)
        return self._scheduler.submit(CoreJob('game-library.validate', task), binding)

    def _cleanup_plans_locked(self):
        now = self._clock()
        for plan_id, plan in tuple(self._plans.items()):
            if now - plan.created_at > self.plan_ttl:self._plans.pop(plan_id, None)
        while len(self._plans) > self.plan_limit:
            oldest = min(self._plans, key=lambda key:self._plans[key].created_at)
            self._plans.pop(oldest, None)

    def prepare_relink(self, record_id, source):
        record = self.get(record_id)
        if _validate_source(source) != record.format:
            raise GameLibraryError('unsupported-format', 'Relink to the same game format.')
        def task(job, session):
            inspection = self._inspect(source, job, session)
            plan_id = self._id_factory()
            preview = RelinkPreview(plan_id, record_id, source, record.sha256,
                                    inspection.sha256,
                                    record.sha256 == inspection.sha256,
                                    inspection.size, inspection.format)
            with self._lock:
                self._cleanup_plans_locked()
                self._plans[plan_id] = _RelinkPlan(
                    preview, inspection, record, session, self._clock())
                self._cleanup_plans_locked()
            return preview
        return self._submit('game-library.relink-preview', source, task)

    def execute_relink(self, plan_id, *, accept_changed=False):
        self._ready()
        with self._lock:
            self._cleanup_plans_locked()
            plan = self._plans.pop(plan_id, None)
        if plan is None:
            raise GameLibraryError('plan', 'Relink review is missing, expired, or already used. Prepare it again.')
        if not plan.preview.content_matches and not accept_changed:
            raise GameLibraryError(
                'content-changed', 'The selected file has different content. Review and explicitly accept the new content.')
        binding, current = self._binding(plan.preview.source)
        if current != plan.session:
            raise GameLibraryError('session', 'The C64U connection changed. Prepare Relink again.')
        def task(job):
            record = self.get(plan.preview.record_id)
            if record != plan.record:
                raise GameLibraryError(
                    'plan-stale', 'The Game Library entry changed after Relink review. Prepare it again.')
            inspection = self._inspect(plan.preview.source, job, plan.session)
            if inspection.sha256 != plan.inspection.sha256:
                raise GameLibraryError('changed-source', 'The selected file changed after Relink review.')
            with self._lock:
                if self._records.get(record.id) != record:
                    raise GameLibraryError(
                        'plan-stale', 'The Game Library entry changed after Relink review. Prepare it again.')
                duplicate = next((item for item in self._records.values()
                                  if item.id != record.id
                                  and item.sha256 == inspection.sha256), None)
                if duplicate is not None:
                    raise GameLibraryError(
                        'duplicate-content', 'That content is already present in the Game Library.')
                content_changed = inspection.sha256 != record.sha256
                updated = replace(
                    record, source=inspection.source, sha256=inspection.sha256,
                    size=inspection.size, metadata=inspection.metadata,
                    state='available', state_message='', updated_at=self._clock(),
                    verified_at=self._clock())
                self._replace(updated)
                return RelinkResult(updated, content_changed)
        return self._scheduler.submit(CoreJob('game-library.relink', task), binding)

    @staticmethod
    def _bulk_candidate_id(source, occurrence=0):
        identity = '\0'.join((source.scope, source.device_id, source.volume,
                              source.path, str(occurrence)))
        return 'candidate-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]

    @staticmethod
    def _validate_bulk_request(request):
        if not isinstance(request, BulkImportRequest):
            raise GameLibraryError('scan-request', 'Choose a Bulk Import scan request.')
        if (request.scope not in (CORE_HOST, C64U)
                or request.kind not in ('folder', 'sources')
                or type(request.recursive) is not bool
                or type(request.include_hidden) is not bool
                or not request.roots
                or any(not isinstance(path, str) or not path for path in request.roots)):
            raise GameLibraryError('scan-request', 'Bulk Import scan options are invalid.')
        if request.scope == CORE_HOST:
            if request.device_id or request.kind != 'folder' or len(request.roots) != 1:
                raise GameLibraryError('scan-request', 'Core-host scanning needs one folder.')
            if not Path(request.roots[0]).is_absolute():
                raise GameLibraryError('scan-request', 'Core-host scanning needs an absolute folder.')
        else:
            if not request.device_id:
                raise GameLibraryError('scan-request', 'C64U scanning needs a physical device identity.')
            if request.kind == 'folder' and len(request.roots) != 1:
                raise GameLibraryError('scan-request', 'C64U folder scanning needs one folder.')
            volumes = set()
            for path in request.roots:
                root = storage_root(path)
                if (not root or any(part in ('', '.', '..')
                                    for part in path.split('/')[1:])):
                    raise GameLibraryError('scan-request', 'Choose safe paths inside C64U USB/SD storage.')
                if request.kind == 'sources' and root == path:
                    raise GameLibraryError('scan-request', 'Choose C64U game files, not volume roots.')
                volumes.add(root)
            if len(volumes) != 1:
                raise GameLibraryError('scan-request', 'One scan may use only one C64U volume.')
        return request

    @staticmethod
    def _scan_limit(message):
        raise GameLibraryError('scan-limit', message)

    def _check_bulk_session(self, request, expected):
        if request.scope != C64U:
            return
        current = self._session()
        if current.device_id != request.device_id:
            raise GameLibraryError('device', 'The active C64U changed during Bulk Import scanning.')
        if expected is None or current.session_id != expected.session_id:
            raise GameLibraryError('session', 'The C64U connection changed during Bulk Import scanning.')

    def _discover_local(self, request, job):
        root = Path(request.roots[0])
        if root.is_symlink() or not root.is_dir():
            raise GameLibraryError('scan-root', 'Choose an existing Core-host folder that is not a symlink.')
        pending = [(root, 0)]
        listed = set()
        files = []
        issues = []
        entries_seen = directories = supported = declared = 0
        while pending:
            directory, depth = pending.pop(0)
            job.check_cancel()
            key = str(directory)
            if key in listed:
                continue
            listed.add(key); directories += 1
            if directories > self.bulk_max_directories:
                self._scan_limit(
                    f'Bulk Import exceeded the {self.bulk_max_directories:,}-directory limit.')
            try:
                entries = sorted(os.scandir(directory),
                                 key=lambda item: (item.name.casefold(), item.name))
            except OSError as exc:
                if directory == root:
                    raise GameLibraryError('scan-root', 'The Core-host scan root cannot be read.') from exc
                issues.append(BulkScanIssue(CORE_HOST, key, 'branch-unavailable',
                                            'filesystem', 'This folder could not be read.'))
                continue
            for entry in entries:
                job.check_cancel(); entries_seen += 1
                if entries_seen > self.bulk_max_entries:
                    self._scan_limit(
                        f'Bulk Import exceeded the {self.bulk_max_entries:,}-entry limit.')
                path = Path(entry.path)
                if not request.include_hidden and local_hidden(path):
                    continue
                try:
                    is_link = entry.is_symlink()
                    is_dir = entry.is_dir(follow_symlinks=False)
                    is_file = entry.is_file(follow_symlinks=False)
                except OSError:
                    is_link = is_dir = is_file = False
                if is_dir:
                    if request.recursive:
                        if depth + 1 > self.bulk_max_depth:
                            self._scan_limit(
                                'Bulk Import exceeded the recursion-depth limit '
                                f'of {self.bulk_max_depth:,}.')
                        pending.append((path, depth + 1))
                    continue
                relative = path.relative_to(root).as_posix()
                suffix = path.suffix.casefold()
                declared_size = None
                try:
                    declared_size = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    pass
                files.append((GameSource.core_host(path), relative, suffix,
                              declared_size, is_file and not is_link,
                              'symlink' if is_link else 'filesystem'))
                if suffix in ('.d64', '.crt'):
                    supported += 1
                    if supported > self.bulk_max_candidates:
                        self._scan_limit(
                            f'Bulk Import exceeded the {self.bulk_max_candidates:,}-candidate limit.')
                    if isinstance(declared_size, int) and declared_size > 0:
                        declared += declared_size
                        if declared > self.bulk_max_declared_bytes:
                            self._scan_limit(
                                'Bulk Import exceeded the configured candidate-byte limit.')
            job.report(JobProgress('discover', directories, None, 'directories',
                                    f'Discovered {entries_seen:,} entries in {directories:,} folders'))
        files.sort(key=lambda item: (item[1].casefold(), item[1]))
        return files, issues, directories, entries_seen, supported, declared

    def _discover_c64u(self, request, job, session):
        if request.kind == 'sources':
            rows = []
            declared = 0
            for path in sorted(request.roots, key=lambda value:(value.casefold(), value)):
                source = GameSource.c64u(request.device_id, path)
                rows.append((source, posixpath.basename(path),
                             Path(path).suffix.casefold(), None, True, ''))
            supported = sum(1 for row in rows if row[2] in ('.d64', '.crt'))
            if len(rows) > self.bulk_max_entries:
                self._scan_limit(
                    f'Bulk Import exceeded the {self.bulk_max_entries:,}-entry limit.')
            if supported > self.bulk_max_candidates:
                self._scan_limit(
                    f'Bulk Import exceeded the {self.bulk_max_candidates:,}-candidate limit.')
            return rows, [], 0, len(rows), supported, declared
        if self._remote_lister is None:
            raise GameLibraryError('device-unavailable', 'C64U folder scanning is unavailable.')
        root = posixpath.normpath(request.roots[0])
        volume = storage_root(root)
        pending = [(root, 0)]
        listed = set(); files = []; issues = []
        entries_seen = directories = supported = declared = 0
        while pending:
            directory, depth = pending.pop(0)
            job.check_cancel(); self._check_bulk_session(request, session)
            if directory in listed:
                continue
            listed.add(directory); directories += 1
            if directories > self.bulk_max_directories:
                self._scan_limit(
                    f'Bulk Import exceeded the {self.bulk_max_directories:,}-directory limit.')
            try:
                actual, entries = self._remote_lister(directory)
            except (ConnectionFailure, BrowserError, OSError) as exc:
                self._check_bulk_session(request, session)
                if directory == root:
                    raise GameLibraryError('scan-root', 'The C64U scan root cannot be read.', retryable=True) from exc
                issues.append(BulkScanIssue(C64U, directory, 'branch-unavailable',
                                            'device-unavailable', 'This C64U folder could not be read.'))
                continue
            self._check_bulk_session(request, session)
            actual = posixpath.normpath(str(actual))
            if actual != directory or storage_root(actual) != volume:
                raise GameLibraryError('scan-path', 'C64U returned an unexpected directory while scanning.')
            entries = sorted(entries, key=lambda item:(item.name.casefold(), item.name))
            for entry in entries:
                job.check_cancel(); entries_seen += 1
                if entries_seen > self.bulk_max_entries:
                    self._scan_limit(
                        f'Bulk Import exceeded the {self.bulk_max_entries:,}-entry limit.')
                if (not request.include_hidden and str(entry.name).startswith('.')):
                    continue
                if (not entry.name or entry.name in ('.', '..')
                        or '/' in entry.name or '\\' in entry.name):
                    issues.append(BulkScanIssue(C64U, directory,
                                                'branch-unavailable', 'unsafe-name',
                                                'C64U returned an unsafe entry name.'))
                    continue
                path = posixpath.join(directory, entry.name)
                if storage_root(path) != volume:
                    raise GameLibraryError('scan-path', 'C64U scan escaped the expected storage volume.')
                if entry.kind == 'dir':
                    if request.recursive:
                        if depth + 1 > self.bulk_max_depth:
                            self._scan_limit(
                                'Bulk Import exceeded the recursion-depth limit '
                                f'of {self.bulk_max_depth:,}.')
                        pending.append((path, depth + 1))
                    continue
                relative = posixpath.relpath(path, root)
                suffix = Path(path).suffix.casefold()
                size = entry.size if type(entry.size) is int and entry.size >= 0 else None
                readable = entry.kind in ('file', 'unknown')
                files.append((GameSource.c64u(request.device_id, path), relative,
                              suffix, size, readable, 'device-entry'))
                if suffix in ('.d64', '.crt'):
                    supported += 1
                    if supported > self.bulk_max_candidates:
                        self._scan_limit(
                            f'Bulk Import exceeded the {self.bulk_max_candidates:,}-candidate limit.')
                    if size:
                        declared += size
                        if declared > self.bulk_max_declared_bytes:
                            self._scan_limit(
                                'Bulk Import exceeded the configured candidate-byte limit.')
            job.report(JobProgress('discover', directories, None, 'directories',
                                    f'Discovered {entries_seen:,} entries in {directories:,} C64U folders'))
        files.sort(key=lambda item:(item[1].casefold(), item[1]))
        return files, issues, directories, entries_seen, supported, declared

    def _bulk_inspect(self, source, job, session, declared_size,
                      progress_phase='validate-bytes'):
        format_name = _validate_source(source)
        if source.scope == CORE_HOST:
            return self._inspect(source, job, session)
        self._check_bulk_session(
            BulkImportRequest(C64U, (source.path,), False, source.device_id,
                              False, 'sources'), session)
        limit = 206114 if format_name == 'D64' else MAX_CRT_BYTES
        if self._bulk_remote_reader is None:
            data = self._read(source, job, session)
        else:
            def progress(completed, total):
                job.report(JobProgress(progress_phase, completed, total,
                                       'bytes', 'Reading and validating game image…'))
            try:
                data = self._bulk_remote_reader(source, limit, progress,
                                                job.check_cancel)
            except JobCancelled:
                raise
            except ConnectionFailure as exc:
                raise GameLibraryError('device-unavailable',
                                       'The source C64U is unavailable.',
                                       retryable=True) from exc
            except BrowserError as exc:
                raise GameLibraryError('inaccessible-file',
                                       'The C64U candidate could not be read.') from exc
            self._check_bulk_session(
                BulkImportRequest(C64U, (source.path,), False,
                                  source.device_id, False, 'sources'), session)
            if not isinstance(data, bytes):
                raise GameLibraryError('source', 'C64U source reader returned invalid data.')
        return self._inspection_from_data(source, format_name, data)

    def prepare_bulk_import(self, request):
        """Discover and classify candidates without modifying the catalog."""
        self._ready(); request = self._validate_bulk_request(request)
        if request.scope == CORE_HOST:
            binding, session = JobBinding.core_host(), None
        else:
            probe = GameSource.c64u(request.device_id,
                                    request.roots[0] if request.kind == 'sources'
                                    else posixpath.join(request.roots[0], 'scan.d64'))
            binding, session = self._binding(probe)

        def task(job):
            before_catalog = tuple(self.list())
            if request.scope == CORE_HOST:
                discovered = self._discover_local(request, job)
            else:
                discovered = self._discover_c64u(request, job, session)
            rows, issues, directories, entries, supported, declared = discovered
            job.report(JobProgress('discovered', supported, entries,
                                   'candidates',
                                   f'Discovered {supported:,} D64/CRT candidates'))
            existing_source = {record.source:record for record in before_catalog}
            existing_hash = {record.sha256:record for record in before_catalog}
            seen_sources = {}; seen_hashes = {}; candidates = []
            source_occurrences = {}
            unknown_bytes = actual_validated_bytes = 0
            candidate_number = 0
            for source, relative, suffix, stated_size, readable, read_error in rows:
                job.check_cancel()
                occurrence = source_occurrences.get(source, 0)
                source_occurrences[source] = occurrence + 1
                candidate_id = self._bulk_candidate_id(source, occurrence)
                common = dict(id=candidate_id, source=source,
                              relative_path=relative,
                              declared_size=stated_size)
                if suffix not in ('.d64', '.crt'):
                    candidates.append(BulkCandidate(
                        **common, classification='unsupported-file',
                        error_code='unsupported-format',
                        message='Game Library supports D64 and CRT files.'))
                    continue
                candidate_number += 1
                if source in seen_sources:
                    candidates.append(BulkCandidate(
                        **common, classification='duplicate-scan-path',
                        format=suffix[1:].upper(),
                        duplicate_candidate_id=seen_sources[source],
                        message='This source was already discovered in the scan.'))
                    continue
                seen_sources[source] = candidate_id
                if not readable:
                    candidates.append(BulkCandidate(
                        **common, classification='inaccessible-file',
                        format=suffix[1:].upper(), error_code=read_error,
                        message='The candidate is not a readable regular file.'))
                    continue
                per_file_limit = 206114 if suffix == '.d64' else MAX_CRT_BYTES
                if (isinstance(stated_size, int)
                        and not 0 < stated_size <= per_file_limit):
                    candidates.append(BulkCandidate(
                        **common, classification='invalid-image',
                        format=suffix[1:].upper(), error_code='size-bound',
                        message='Game file size is outside the supported validation bound.'))
                    continue
                job.report(JobProgress('validate', candidate_number - 1,
                                        supported, 'candidates',
                                        f'Validating {relative}'))
                try:
                    inspection = self._bulk_inspect(source, job, session,
                                                    stated_size)
                except JobCancelled:
                    raise
                except GameLibraryError as exc:
                    if exc.code in ('session', 'device', 'scan-limit'):
                        raise
                    classification = ('invalid-image' if exc.code == 'malformed-image'
                                      else 'inaccessible-file')
                    candidates.append(BulkCandidate(
                        **common, classification=classification,
                        format=suffix[1:].upper(), error_code=exc.code,
                        message=str(exc)))
                    continue
                except (OSError, BrowserError):
                    candidates.append(BulkCandidate(
                        **common, classification='inaccessible-file',
                        format=suffix[1:].upper(), error_code='filesystem',
                        message='The candidate could not be read.'))
                    continue
                if stated_size is None:
                    unknown_bytes += inspection.size
                    if declared + unknown_bytes > self.bulk_max_declared_bytes:
                        self._scan_limit(
                            'Bulk Import exceeded the configured candidate-byte limit.')
                actual_validated_bytes += inspection.size
                if actual_validated_bytes > self.bulk_max_declared_bytes:
                    self._scan_limit(
                        'Bulk Import exceeded the configured candidate-byte limit.')
                same_source = existing_source.get(source)
                same_content = existing_hash.get(inspection.sha256)
                scan_content = seen_hashes.get(inspection.sha256)
                if same_source is not None:
                    classification = ('already-cataloged-source'
                                      if same_source.sha256 == inspection.sha256
                                      else 'changed-existing-source')
                    existing_id = same_source.id
                    duplicate_id = ''
                elif same_content is not None:
                    classification = 'duplicate-catalog-content'
                    existing_id = same_content.id; duplicate_id = ''
                elif scan_content is not None:
                    classification = 'duplicate-scan-content'
                    existing_id = ''; duplicate_id = scan_content
                else:
                    classification = 'new-valid'; existing_id = duplicate_id = ''
                    seen_hashes[inspection.sha256] = candidate_id
                candidates.append(BulkCandidate(
                    **common, classification=classification,
                    importable=classification in BULK_IMPORTABLE,
                    format=inspection.format, size=inspection.size,
                    sha256=inspection.sha256, metadata=inspection.metadata,
                    existing_record_id=existing_id,
                    duplicate_candidate_id=duplicate_id))
            counts = {}
            for candidate in candidates:
                counts[candidate.classification] = counts.get(candidate.classification, 0) + 1
            for issue in issues:
                counts[issue.classification] = counts.get(issue.classification, 0) + 1
            eligible = tuple(item.id for item in candidates if item.importable)
            now = self._clock(); plan_id = self._id_factory()
            preview = BulkImportPreview(
                plan_id, request, tuple(candidates), tuple(issues), eligible,
                eligible, tuple(sorted(counts.items())), directories, entries,
                supported, declared + unknown_bytes, now,
                now + self.bulk_plan_ttl)
            self._check_bulk_session(request, session)
            if tuple(self.list()) != before_catalog:
                raise GameLibraryError('catalog-changed',
                                       'The Game Library changed during scanning. Scan again.')
            with self._lock:
                self._cleanup_bulk_plans_locked()
                self._bulk_plans[plan_id] = _BulkPlan(
                    preview, session, now, self._catalog_version_locked())
                self._cleanup_bulk_plans_locked()
            return preview
        return self._scheduler.submit(CoreJob('game-library.bulk-scan', task),
                                      binding)

    def _cleanup_bulk_plans_locked(self):
        now = self._clock()
        for plan_id, plan in tuple(self._bulk_plans.items()):
            if now - plan.created_at > self.bulk_plan_ttl:
                self._bulk_plans.pop(plan_id, None)
        while len(self._bulk_plans) > self.bulk_plan_limit:
            oldest = min(self._bulk_plans,
                         key=lambda key:self._bulk_plans[key].created_at)
            self._bulk_plans.pop(oldest, None)

    def select_bulk_candidates(self, plan_id, candidate_ids):
        """Validate and serialize the explicitly approved import subset."""
        if not isinstance(plan_id, str) or not plan_id:
            raise GameLibraryError('plan', 'Bulk Import review is missing.')
        try:
            approved = tuple(candidate_ids)
        except TypeError as exc:
            raise GameLibraryError('selection', 'Choose eligible Bulk Import candidates.') from exc
        if any(not isinstance(item, str) or not item for item in approved):
            raise GameLibraryError('selection', 'Choose eligible Bulk Import candidates.')
        if len(set(approved)) != len(approved):
            raise GameLibraryError('selection', 'A Bulk Import candidate may be selected only once.')
        with self._lock:
            self._cleanup_bulk_plans_locked()
            plan = self._bulk_plans.get(plan_id)
        if plan is None:
            raise GameLibraryError('plan', 'Bulk Import review is missing or expired. Scan again.')
        eligible = set(plan.preview.eligible_candidate_ids)
        if any(item not in eligible for item in approved):
            raise GameLibraryError('selection', 'Only new valid candidates can be selected for import.')
        order = {candidate.id:index for index, candidate in
                 enumerate(plan.preview.candidates)}
        approved = tuple(sorted(approved, key=order.__getitem__))
        return BulkImportSelection(plan_id, approved)

    def execute_bulk_import(self, selection):
        """Consume one reviewed plan and atomically admit its approved subset."""
        self._ready()
        if (not isinstance(selection, BulkImportSelection)
                or not isinstance(selection.plan_id, str)
                or not selection.plan_id
                or not isinstance(selection.approved_candidate_ids, tuple)
                or any(not isinstance(item, str) or not item
                       for item in selection.approved_candidate_ids)
                or len(set(selection.approved_candidate_ids))
                   != len(selection.approved_candidate_ids)):
            raise GameLibraryError('selection', 'Bulk Import selection is invalid.')
        with self._lock:
            self._cleanup_bulk_plans_locked()
            plan = self._bulk_plans.get(selection.plan_id)
            if plan is None:
                raise GameLibraryError(
                    'plan', 'Bulk Import review is missing, expired, or already used. Scan again.')
            candidates = plan.preview.candidates
            candidate_ids = tuple(item.id for item in candidates)
            eligible = set(plan.preview.eligible_candidate_ids)
            approved = selection.approved_candidate_ids
            if (len(set(candidate_ids)) != len(candidate_ids)
                    or set(plan.preview.default_selected_candidate_ids) - eligible
                    or any(item not in eligible for item in approved)):
                raise GameLibraryError('selection', 'Bulk Import selection does not match this review.')
            # A valid consequential attempt owns the plan from this point. It
            # cannot be replayed after cancellation, stale state, or failure.
            self._bulk_plans.pop(selection.plan_id, None)
        approved_set = set(approved)
        selected = tuple(item for item in candidates if item.id in approved_set)
        if tuple(item.id for item in selected) != tuple(
                item for item in candidate_ids if item in approved_set):
            raise GameLibraryError('plan', 'Bulk Import review data is inconsistent.')
        request = plan.preview.request
        if request.scope == CORE_HOST:
            binding = JobBinding.core_host()
        else:
            current = self._session()
            if current.device_id != request.device_id:
                raise GameLibraryError('device', 'The active C64U changed after Bulk Import review.')
            if plan.session is None or current.session_id != plan.session.session_id:
                raise GameLibraryError('session', 'The C64U connection changed after Bulk Import review.')
            binding = JobBinding.device(plan.session)

        def task(job):
            inspections = []
            outcomes = {}
            total = len(selected)
            job.report(JobProgress('executing', 0, total, 'candidates',
                                   'Executing reviewed Bulk Import selection'))
            for number, candidate in enumerate(selected, 1):
                job.check_cancel()
                if request.scope == C64U:
                    self._check_bulk_session(request, plan.session)
                job.report(JobProgress(
                    'revalidating', number - 1, total, 'candidates',
                    f'Revalidating {candidate.relative_path}'))
                try:
                    inspection = self._bulk_inspect(
                        candidate.source, job, plan.session,
                        candidate.declared_size, 'bounded-reading')
                except JobCancelled:
                    raise
                except GameLibraryError as exc:
                    if exc.code in ('session', 'device', 'device-unavailable'):
                        raise
                    classification = {
                        'missing-source':'source-missing',
                        'changed-source':'source-changed',
                        'malformed-image':'invalid-image',
                    }.get(exc.code, 'inaccessible-file')
                    outcomes[candidate.id] = BulkCandidateOutcome(
                        candidate.id, candidate.source, 'failed',
                        classification, expected_sha256=candidate.sha256,
                        error_code=exc.code, message=str(exc))
                    continue
                except OSError:
                    outcomes[candidate.id] = BulkCandidateOutcome(
                        candidate.id, candidate.source, 'failed',
                        'inaccessible-file', expected_sha256=candidate.sha256,
                        error_code='filesystem',
                        message='The candidate could not be read.')
                    continue
                if (inspection.format != candidate.format
                        or inspection.size != candidate.size
                        or inspection.sha256 != candidate.sha256
                        or inspection.metadata != candidate.metadata):
                    outcomes[candidate.id] = BulkCandidateOutcome(
                        candidate.id, candidate.source, 'failed',
                        'source-changed', expected_sha256=candidate.sha256,
                        observed_sha256=inspection.sha256,
                        error_code='changed-source',
                        message='The candidate changed after Bulk Import review.')
                    continue
                inspections.append((candidate, inspection))
                job.report(JobProgress(
                    'revalidating', number, total, 'candidates',
                    f'Revalidated {number:,} of {total:,} candidates'))
            job.check_cancel()
            if request.scope == C64U:
                self._check_bulk_session(request, plan.session)
            job.report(JobProgress('classifying', 0, len(inspections),
                                   'candidates',
                                   'Classifying reviewed candidates against the current catalog'))
            created = []
            with self._lock:
                catalog_changed = (
                    self._catalog_version_locked() != plan.catalog_version)
                previous = self._records
                resulting = dict(previous)
                now = self._clock()
                for number, (candidate, inspection) in enumerate(inspections, 1):
                    same_source = next((record for record in resulting.values()
                                        if record.source == inspection.source), None)
                    same_content = next((record for record in resulting.values()
                                         if record.sha256 == inspection.sha256), None)
                    if same_source is not None:
                        classification = ('already-cataloged-source'
                                          if same_source.sha256 == inspection.sha256
                                          else 'changed-existing-source')
                        outcomes[candidate.id] = BulkCandidateOutcome(
                            candidate.id, candidate.source, 'skipped',
                            classification, record_id=same_source.id,
                            expected_sha256=candidate.sha256,
                            observed_sha256=inspection.sha256,
                            message='The source is already represented in the current catalog.')
                    elif same_content is not None:
                        outcomes[candidate.id] = BulkCandidateOutcome(
                            candidate.id, candidate.source, 'skipped',
                            'duplicate-catalog-content',
                            record_id=same_content.id,
                            expected_sha256=candidate.sha256,
                            observed_sha256=inspection.sha256,
                            message='Byte-identical content is already in the current catalog.')
                    else:
                        record_id = self._id_factory()
                        if record_id in resulting:
                            raise GameLibraryError(
                                'catalog', 'A unique Game Library record ID could not be created.')
                        record = GameRecord(
                            record_id, Path(candidate.source.path).stem,
                            inspection.source, inspection.format,
                            inspection.sha256, inspection.size,
                            metadata=inspection.metadata, created_at=now,
                            updated_at=now, verified_at=now)
                        _validate_record(record)
                        resulting[record.id] = record
                        created.append(record)
                        outcomes[candidate.id] = BulkCandidateOutcome(
                            candidate.id, candidate.source, 'created',
                            'created', record_id=record.id,
                            expected_sha256=candidate.sha256,
                            observed_sha256=inspection.sha256)
                    job.report(JobProgress(
                        'classifying', number, len(inspections), 'candidates',
                        f'Classified {number:,} of {len(inspections):,} candidates'))
                job.check_cancel()
                if request.scope == C64U:
                    self._check_bulk_session(request, plan.session)
                if created:
                    job.report(JobProgress('persisting', 0, 1, 'catalogs',
                                           'Publishing the Game Library catalog atomically'))
                    job.check_cancel()
                    self._records = resulting
                    try:
                        self._save_locked()
                    except BaseException:
                        self._records = previous
                        raise
                ordered_outcomes = tuple(outcomes[item.id] for item in selected)
                counts = {}
                for outcome in ordered_outcomes:
                    counts[outcome.classification] = counts.get(
                        outcome.classification, 0) + 1
                result = BulkImportResult(
                    selection.plan_id, tuple(item.id for item in selected),
                    tuple(created), ordered_outcomes,
                    len(created),
                    sum(item.status == 'skipped' for item in ordered_outcomes),
                    sum(item.status == 'failed' for item in ordered_outcomes),
                    tuple(sorted(counts.items())), bool(created),
                    'published' if created else 'unchanged', catalog_changed)
            progress = JobProgress('complete', total, total, 'candidates',
                                   'Bulk Import execution is complete')
            if created:
                job.report_committed(progress)
            else:
                job.report(progress)
            return result
        return self._scheduler.submit(
            CoreJob('game-library.bulk-import', task), binding)

    def discard_bulk_plan(self, plan_id):
        with self._lock:
            self._cleanup_bulk_plans_locked()
            return self._bulk_plans.pop(plan_id, None) is not None

    def job(self, job_id):return self._scheduler.job(job_id)
    def cancel(self, job_id):return self._scheduler.cancel(job_id)

    def close(self):
        if self._owns_scheduler:self._scheduler.close()
