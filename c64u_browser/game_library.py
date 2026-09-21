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
from .jobs import CoreJob, JobProgress
from .platform_support import config_base
from .scheduler import CoreScheduler, DeviceSession, JobBinding
from .storage import storage_root


CORE_HOST = 'core-host'
C64U = 'c64u'
SCHEMA_VERSION = 1
MAX_CRT_BYTES = 64 * 1024 * 1024
VALID_STATES = frozenset(('available', 'missing', 'changed', 'unavailable'))


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
class _RelinkPlan:
    preview: RelinkPreview
    inspection: SourceInspection
    record: GameRecord
    session: DeviceSession | None
    created_at: float


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
    def __init__(self, path=None, *, remote_reader=None, session_provider=None,
                 scheduler=None, plan_ttl=300, plan_limit=128,
                 clock=time.time, id_factory=lambda: uuid.uuid4().hex):
        self.path = Path(path) if path else default_catalog_path()
        self._remote_reader = remote_reader
        self._session_provider = session_provider or (lambda: DeviceSession('', ''))
        self._scheduler = scheduler or CoreScheduler(self._session_provider, clock=clock)
        self._owns_scheduler = scheduler is None
        self._clock = clock
        self._id_factory = id_factory
        self.plan_ttl = max(0, float(plan_ttl))
        self.plan_limit = max(0, int(plan_limit))
        self._records = {}
        self._plans = {}
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
        return SourceInspection(source, format_name, digest, len(data), metadata), data

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

    def job(self, job_id):return self._scheduler.job(job_id)
    def cancel(self, job_id):return self._scheduler.cancel(job_id)

    def close(self):
        if self._owns_scheduler:self._scheduler.close()
