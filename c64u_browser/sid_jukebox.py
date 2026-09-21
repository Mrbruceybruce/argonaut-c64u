# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Core-owned SID catalog and persisted playlists; no playback or UI."""
from dataclasses import dataclass, replace
from pathlib import Path
from threading import RLock
import json
import math
import os
import tempfile
import time
import uuid

from . import development
from .api import BrowserError, ConnectionFailure
from .jobs import CoreJob, JobProgress
from .platform_support import config_base
from .scheduler import CoreScheduler, DeviceSession, JobBinding
from .sid_format import MAX_SID_BYTES, SidChip, SidFormatError, SidMetadata, parse_sid
from .storage import storage_root


CORE_HOST = 'core-host'
C64U = 'c64u'
SCHEMA_VERSION = 1
VALID_STATES = frozenset(('available', 'missing', 'changed', 'unavailable'))


class SidCatalogError(BrowserError):
    def __init__(self, code, message, *, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class SidSource:
    scope: str
    path: str
    device_id: str = ''
    volume: str = ''

    @classmethod
    def core_host(cls, path):
        return cls(CORE_HOST, str(Path(path).expanduser().absolute()))

    @classmethod
    def c64u(cls, device_id, path):
        path = str(path)
        return cls(C64U, path, str(device_id), storage_root(path) or '')


@dataclass(frozen=True)
class SidTune:
    id: str
    source: SidSource
    metadata: SidMetadata
    favorite: bool = False
    notes: str = ''
    state: str = 'available'
    state_message: str = ''
    created_at: float = 0.0
    updated_at: float = 0.0
    verified_at: float = 0.0

    @property
    def title(self):
        return self.metadata.title or Path(self.source.path).stem


@dataclass(frozen=True)
class PlaylistItem:
    id: str
    tune_id: str
    subtune: int


@dataclass(frozen=True)
class SidPlaylist:
    id: str
    title: str
    items: tuple[PlaylistItem, ...] = ()
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass(frozen=True)
class SidInspection:
    source: SidSource
    metadata: SidMetadata


@dataclass(frozen=True)
class AddResult:
    tune: SidTune
    created: bool
    duplicate_kind: str = ''
    expected_sha256: str = ''
    observed_sha256: str = ''


@dataclass(frozen=True)
class ValidationResult:
    tune: SidTune
    previous_state: str
    expected_sha256: str
    observed_sha256: str = ''


@dataclass(frozen=True)
class RelinkPreview:
    plan_id: str
    tune_id: str
    source: SidSource
    expected_sha256: str
    observed_sha256: str
    content_matches: bool
    metadata: SidMetadata


@dataclass(frozen=True)
class RelinkResult:
    tune: SidTune
    content_changed: bool


@dataclass(frozen=True)
class _RelinkPlan:
    preview: RelinkPreview
    inspection: SidInspection
    tune: SidTune
    session: DeviceSession | None
    created_at: float


def default_catalog_path():
    return config_base() / development.config_name() / 'sid-jukebox.json'


def _source_dict(source):
    return {'scope': source.scope, 'path': source.path,
            'device_id': source.device_id, 'volume': source.volume}


def _source_from_dict(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid SID source')
    source = SidSource(value.get('scope'), value.get('path'),
                       value.get('device_id', ''), value.get('volume', ''))
    _validate_source(source)
    return source


def _metadata_dict(metadata):
    return {
        'format': metadata.format, 'version': metadata.version,
        'title': metadata.title, 'author': metadata.author,
        'released': metadata.released,
        'declared_load_address': metadata.declared_load_address,
        'effective_load_address': metadata.effective_load_address,
        'init_address': metadata.init_address, 'play_address': metadata.play_address,
        'songs': metadata.songs, 'start_song': metadata.start_song,
        'speed': metadata.speed, 'song_speeds': list(metadata.song_speeds),
        'clock': metadata.clock,
        'chips': [{'address': chip.address, 'model': chip.model}
                  for chip in metadata.chips],
        'mus': metadata.mus, 'playsid_specific': metadata.playsid_specific,
        'rsid_basic': metadata.rsid_basic,
        'relocation_start_page': metadata.relocation_start_page,
        'relocation_pages': metadata.relocation_pages,
        'compatibility_flags': list(metadata.compatibility_flags),
        'warnings': list(metadata.warnings),
        'playback_classification': metadata.playback_classification,
        'playback_eligible': metadata.playback_eligible,
        'payload_size': metadata.payload_size, 'file_size': metadata.file_size,
        'sha256': metadata.sha256,
    }


def _metadata_from_dict(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid SID metadata')
    required = set(_metadata_dict(SidMetadata(
        'PSID', 1, '', '', '', 0, 0, 0, 0, 1, 1, 0, ('vbi',),
        'unknown', (SidChip(0xd400, 'unknown'),), False, False, False,
        0, 0, (), (), 'eligible', True, 1, 120, '0' * 64)))
    if set(value) != required or not isinstance(value.get('chips'), list):
        raise ValueError('Incomplete SID metadata')
    try:
        metadata = SidMetadata(
            value['format'], value['version'], value['title'], value['author'],
            value['released'], value['declared_load_address'],
            value['effective_load_address'], value['init_address'],
            value['play_address'], value['songs'], value['start_song'],
            value['speed'], tuple(value['song_speeds']), value['clock'],
            tuple(SidChip(chip['address'], chip['model'])
                  for chip in value['chips']), value['mus'],
            value['playsid_specific'], value['rsid_basic'],
            value['relocation_start_page'], value['relocation_pages'],
            tuple(value['compatibility_flags']), tuple(value['warnings']),
            value['playback_classification'], value['playback_eligible'],
            value['payload_size'], value['file_size'], value['sha256'])
    except (KeyError, TypeError) as exc:
        raise ValueError('Invalid SID metadata') from exc
    _validate_metadata(metadata)
    return metadata


def _tune_dict(tune):
    return {
        'id': tune.id, 'source': _source_dict(tune.source),
        'metadata': _metadata_dict(tune.metadata), 'favorite': tune.favorite,
        'notes': tune.notes, 'state': tune.state,
        'state_message': tune.state_message, 'created_at': tune.created_at,
        'updated_at': tune.updated_at, 'verified_at': tune.verified_at,
    }


def _tune_from_dict(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid SID tune')
    required = ('id', 'source', 'metadata', 'favorite', 'notes', 'state',
                'state_message', 'created_at', 'updated_at', 'verified_at')
    if any(key not in value for key in required):
        raise ValueError('Incomplete SID tune')
    tune = SidTune(value['id'], _source_from_dict(value['source']),
                   _metadata_from_dict(value['metadata']), value['favorite'],
                   value['notes'], value['state'], value['state_message'],
                   value['created_at'], value['updated_at'], value['verified_at'])
    _validate_tune(tune)
    return tune


def _playlist_dict(playlist):
    return {
        'id': playlist.id, 'title': playlist.title,
        'items': [{'id': item.id, 'tune_id': item.tune_id,
                   'subtune': item.subtune} for item in playlist.items],
        'created_at': playlist.created_at, 'updated_at': playlist.updated_at,
    }


def _playlist_from_dict(value, tunes):
    if not isinstance(value, dict) or not isinstance(value.get('items'), list):
        raise ValueError('Invalid SID playlist')
    try:
        playlist = SidPlaylist(
            value['id'], value['title'],
            tuple(PlaylistItem(item['id'], item['tune_id'], item['subtune'])
                  for item in value['items']),
            value['created_at'], value['updated_at'])
    except (KeyError, TypeError) as exc:
        raise ValueError('Invalid SID playlist') from exc
    _validate_playlist(playlist, tunes)
    return playlist


def _validate_source(source):
    if not isinstance(source, SidSource):
        raise SidCatalogError('source', 'Choose a SID source.')
    if source.scope == CORE_HOST:
        if (not isinstance(source.path, str) or not Path(source.path).is_absolute()
                or source.device_id or source.volume):
            raise SidCatalogError('source', 'A Core-host SID needs one absolute host path.')
    elif source.scope == C64U:
        root = storage_root(source.path) if isinstance(source.path, str) else None
        if (not source.device_id or not root or root == source.path
                or source.volume != root
                or any(part in ('', '.', '..') for part in source.path.split('/')[1:])):
            raise SidCatalogError(
                'source', 'A C64U SID needs a physical device identity and a path inside one USB/SD volume.')
    else:
        raise SidCatalogError('source', 'Unsupported SID source scope.')
    if not source.path.casefold().endswith('.sid'):
        raise SidCatalogError('unsupported-format', 'SID Jukebox supports .sid files.')


def _validate_metadata(metadata):
    if (not isinstance(metadata, SidMetadata)
            or metadata.format not in ('PSID', 'RSID')
            or type(metadata.version) is not int or not 1 <= metadata.version <= 4
            or (metadata.format == 'RSID' and metadata.version == 1)
            or type(metadata.songs) is not int or not 1 <= metadata.songs <= 256
            or type(metadata.start_song) is not int
            or not 1 <= metadata.start_song <= metadata.songs
            or not isinstance(metadata.title, str)
            or not isinstance(metadata.author, str)
            or not isinstance(metadata.released, str)
            or any(type(value) is not int or not 0 <= value <= 0xffff
                   for value in (metadata.declared_load_address,
                                 metadata.effective_load_address,
                                 metadata.init_address, metadata.play_address))
            or type(metadata.speed) is not int
            or not 0 <= metadata.speed <= 0xffffffff
            or not isinstance(metadata.song_speeds, tuple)
            or len(metadata.song_speeds) != metadata.songs
            or any(value not in ('vbi', 'cia-1', 'installed-interrupt')
                   for value in metadata.song_speeds)
            or metadata.clock not in ('unknown', 'PAL', 'NTSC', 'PAL-and-NTSC')
            or not 1 <= len(metadata.chips) <= 3
            or any(not isinstance(chip, SidChip)
                   or type(chip.address) is not int
                   or not 0xd000 <= chip.address <= 0xdff0
                   or chip.model not in ('unknown', 'MOS6581', 'MOS8580',
                                         'MOS6581-or-MOS8580')
                   for chip in metadata.chips)
            or metadata.chips[0].address != 0xd400
            or len({chip.address for chip in metadata.chips}) != len(metadata.chips)
            or type(metadata.mus) is not bool
            or type(metadata.playsid_specific) is not bool
            or type(metadata.rsid_basic) is not bool
            or type(metadata.relocation_start_page) is not int
            or not 0 <= metadata.relocation_start_page <= 0xff
            or type(metadata.relocation_pages) is not int
            or not 0 <= metadata.relocation_pages <= 0xff
            or not isinstance(metadata.compatibility_flags, tuple)
            or any(not isinstance(value, str)
                   for value in metadata.compatibility_flags)
            or not isinstance(metadata.warnings, tuple)
            or any(not isinstance(value, str) for value in metadata.warnings)
            or metadata.playback_classification not in ('eligible', 'warning', 'blocked')
            or type(metadata.playback_eligible) is not bool
            or metadata.playback_eligible != (metadata.playback_classification != 'blocked')
            or metadata.playback_eligible != (not (metadata.mus or metadata.playsid_specific))
            or type(metadata.file_size) is not int
            or not 0 < metadata.file_size <= MAX_SID_BYTES
            or type(metadata.payload_size) is not int
            or not 0 < metadata.payload_size < metadata.file_size
            or metadata.effective_load_address + metadata.payload_size > 0x10000
            or not isinstance(metadata.sha256, str) or len(metadata.sha256) != 64
            or any(char not in '0123456789abcdef' for char in metadata.sha256)):
        raise ValueError('Invalid SID metadata')


def _validate_tune(tune):
    _validate_source(tune.source)
    _validate_metadata(tune.metadata)
    if (not isinstance(tune.id, str) or not tune.id
            or type(tune.favorite) is not bool or not isinstance(tune.notes, str)
            or tune.state not in VALID_STATES or not isinstance(tune.state_message, str)
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in (tune.created_at, tune.updated_at,
                                 tune.verified_at))):
        raise ValueError('Invalid SID tune')


def _validate_playlist(playlist, tunes):
    if (not isinstance(playlist.id, str) or not playlist.id
            or not isinstance(playlist.title, str) or not playlist.title.strip()
            or len({item.id for item in playlist.items}) != len(playlist.items)
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in (playlist.created_at, playlist.updated_at))):
        raise ValueError('Invalid SID playlist')
    for item in playlist.items:
        tune = tunes.get(item.tune_id)
        if (not isinstance(item.id, str) or not item.id or tune is None
                or type(item.subtune) is not int
                or not 1 <= item.subtune <= tune.metadata.songs):
            raise ValueError('Invalid SID playlist item')


class SidCatalogService:
    """Headless SID references, metadata and playlists owned by Core."""
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
        self._tunes = {}
        self._playlists = {}
        self._plans = {}
        self._lock = RLock()
        self._loaded = False
        self._load_error = None

    def load(self):
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            if (not isinstance(raw, dict) or raw.get('schema_version') != SCHEMA_VERSION
                    or not isinstance(raw.get('tunes'), list)
                    or not isinstance(raw.get('playlists'), list)):
                raise ValueError('Unsupported SID Jukebox store')
            tunes = [_tune_from_dict(item) for item in raw['tunes']]
            if len({tune.id for tune in tunes}) != len(tunes):
                raise ValueError('Duplicate SID tune IDs')
            tune_map = {tune.id: tune for tune in tunes}
            playlists = [_playlist_from_dict(item, tune_map)
                         for item in raw['playlists']]
            if len({item.id for item in playlists}) != len(playlists):
                raise ValueError('Duplicate SID playlist IDs')
        except FileNotFoundError:
            tunes = []; playlists = []
        except (OSError, UnicodeError, ValueError, TypeError, KeyError,
                SidCatalogError) as exc:
            self._load_error = SidCatalogError(
                'catalog', 'Cannot load the SID Jukebox store; the original file has been kept.')
            raise self._load_error from exc
        with self._lock:
            self._tunes = {item.id: item for item in tunes}
            self._playlists = {item.id: item for item in playlists}
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
        data = {
            'schema_version': SCHEMA_VERSION,
            'tunes': [_tune_dict(item) for item in
                      sorted(self._tunes.values(), key=lambda item:item.id)],
            'playlists': [_playlist_dict(item) for item in
                          sorted(self._playlists.values(), key=lambda item:item.id)],
        }
        descriptor, temporary = tempfile.mkstemp(
            dir=self.path.parent, prefix='.sid-jukebox-', suffix='.json')
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False)
                stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            try:
                directory = os.open(self.path.parent,
                                    os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                try:os.fsync(directory)
                finally:os.close(directory)
            except OSError:
                pass
        finally:
            if os.path.exists(temporary):os.unlink(temporary)

    def _mutate(self, operation):
        self._ready()
        with self._lock:
            before_tunes = dict(self._tunes)
            before_playlists = dict(self._playlists)
            result = operation()
            try:self._save_locked()
            except BaseException:
                self._tunes = before_tunes
                self._playlists = before_playlists
                raise
            return result

    def list(self):
        self._ready()
        with self._lock:
            return tuple(sorted(self._tunes.values(),
                                key=lambda item:(item.title.casefold(), item.id)))

    def get(self, tune_id):
        self._ready()
        with self._lock:tune = self._tunes.get(tune_id)
        if tune is None:
            raise SidCatalogError('not-found', 'SID Jukebox tune was not found.')
        return tune

    def search(self, text='', *, favorite=None):
        if not isinstance(text, str) or favorite not in (None, True, False):
            raise SidCatalogError('query', 'Use text and an optional favorite filter.')
        query = text.strip().casefold()
        return tuple(tune for tune in self.list()
                     if (favorite is None or tune.favorite is favorite)
                     and (not query or query in ' '.join((
                         tune.title, tune.metadata.author, tune.metadata.released,
                         tune.notes, tune.source.path)).casefold()))

    def _edit(self, tune_id, **changes):
        tune = self.get(tune_id)
        def operation():
            updated = replace(tune, updated_at=self._clock(), **changes)
            _validate_tune(updated); self._tunes[tune_id] = updated
            return updated
        return self._mutate(operation)

    def set_favorite(self, tune_id, favorite):
        if type(favorite) is not bool:
            raise SidCatalogError('metadata', 'Favorite must be on or off.')
        return self._edit(tune_id, favorite=favorite)

    def set_notes(self, tune_id, notes):
        if not isinstance(notes, str):
            raise SidCatalogError('metadata', 'Notes must be text.')
        return self._edit(tune_id, notes=notes)

    def remove(self, tune_id):
        tune = self.get(tune_id)
        def operation():
            self._tunes.pop(tune_id)
            now = self._clock()
            for playlist_id, playlist in tuple(self._playlists.items()):
                items = tuple(item for item in playlist.items
                              if item.tune_id != tune_id)
                if items != playlist.items:
                    self._playlists[playlist_id] = replace(
                        playlist, items=items, updated_at=now)
            return tune
        return self._mutate(operation)

    def _session(self):
        value = self._session_provider()
        return value if isinstance(value, DeviceSession) else DeviceSession('', '')

    def _binding(self, source, *, allow_unavailable=False):
        if source.scope == CORE_HOST:return JobBinding.core_host(), None
        current = self._session()
        if (not current.device_id or source.device_id != current.device_id
                or not current.session_id):
            if allow_unavailable:return JobBinding.core_host(), None
            raise SidCatalogError('device-unavailable',
                                  'The source C64U is not the active connected device.')
        return JobBinding.device(current), current

    def _submit(self, operation, source, task, *, allow_unavailable=False):
        _validate_source(source)
        binding, session = self._binding(source, allow_unavailable=allow_unavailable)
        return self._scheduler.submit(
            CoreJob(operation, lambda job:task(job, session)), binding)

    def _read(self, source, job, expected_session=None):
        if source.scope == CORE_HOST:
            path = Path(source.path)
            if path.is_symlink() or not path.is_file():
                raise SidCatalogError('missing-source', 'The referenced SID file is missing.')
            before = path.stat()
            if not 0 < before.st_size <= MAX_SID_BYTES:
                raise SidCatalogError('malformed-sid',
                                      'SID file size is outside the supported validation bound.')
            with path.open('rb') as stream:data = stream.read(MAX_SID_BYTES + 1)
            job.report(JobProgress('hash', len(data), before.st_size, 'bytes',
                                   'Validating SID file…'))
            job.check_cancel()
            after = path.stat()
            if (after.st_size != before.st_size
                    or after.st_mtime_ns != before.st_mtime_ns
                    or getattr(after, 'st_ino', None) != getattr(before, 'st_ino', None)):
                raise SidCatalogError('changed-source',
                                      'The SID file changed while it was being validated.')
            return data
        current = self._session()
        if expected_session is None or current != expected_session:
            raise SidCatalogError('session',
                                  'The C64U connection changed. Validate the SID again.')
        if self._remote_reader is None:
            raise SidCatalogError('device-unavailable', 'C64U SID reading is unavailable.')
        try:data = self._remote_reader(source)
        except ConnectionFailure as exc:
            raise SidCatalogError('device-unavailable',
                                  'The source C64U is unavailable.', retryable=True) from exc
        if not isinstance(data, bytes):
            raise SidCatalogError('source', 'C64U SID reader returned invalid data.')
        job.report(JobProgress('hash', len(data), len(data), 'bytes',
                               'Validating C64U SID file…'))
        job.check_cancel()
        return data

    def _inspect(self, source, job, session=None):
        inspection, _data = self._inspect_data(source, job, session)
        return inspection

    def _inspect_data(self, source, job, session=None):
        """Internal Core handoff; SID bytes never enter public results."""
        data = self._read(source, job, session)
        try:metadata = parse_sid(data)
        except SidFormatError as exc:
            raise SidCatalogError('malformed-sid', str(exc)) from exc
        return SidInspection(source, metadata), data

    def add(self, source):
        self._ready()
        def task(job, session):
            inspection = self._inspect(source, job, session)
            with self._lock:
                same_source = next((item for item in self._tunes.values()
                                    if item.source == source), None)
                same_content = next((item for item in self._tunes.values()
                                     if item.metadata.sha256 == inspection.metadata.sha256), None)
                if same_source:
                    kind = ('source' if same_source.metadata.sha256 ==
                            inspection.metadata.sha256 else 'source-changed')
                    if kind == 'source-changed':
                        same_source = self._edit(
                            same_source.id, state='changed',
                            state_message='The referenced SID content changed.')
                    return AddResult(
                        same_source, False, kind, same_source.metadata.sha256,
                        inspection.metadata.sha256)
                if same_content:
                    return AddResult(same_content, False, 'content',
                                     same_content.metadata.sha256,
                                     inspection.metadata.sha256)
                now = self._clock()
                tune = SidTune(self._id_factory(), source, inspection.metadata,
                               created_at=now, updated_at=now, verified_at=now)
                self._mutate(lambda:(self._tunes.__setitem__(tune.id, tune), tune)[1])
                return AddResult(tune, True)
        return self._submit('sid-jukebox.add', source, task)

    def validate_source(self, tune_id):
        tune = self.get(tune_id)
        binding, session = self._binding(tune.source, allow_unavailable=True)
        def task(job):
            previous = self.get(tune_id)
            def unchanged():
                current = self.get(tune_id)
                if (current.source != previous.source
                        or current.metadata.sha256 != previous.metadata.sha256):
                    raise SidCatalogError(
                        'record-changed', 'The SID entry changed during validation.')
            if previous.source.scope == C64U and session is None:
                unchanged()
                updated = self._edit(tune_id, state='unavailable',
                                     state_message='The source C64U is not connected.')
                return ValidationResult(updated, previous.state,
                                        previous.metadata.sha256)
            try:inspection = self._inspect(previous.source, job, session)
            except SidCatalogError as exc:
                if exc.code == 'missing-source':
                    unchanged(); updated = self._edit(
                        tune_id, state='missing', state_message=str(exc))
                    return ValidationResult(updated, previous.state,
                                            previous.metadata.sha256)
                if exc.code in ('device-unavailable', 'session'):
                    unchanged(); updated = self._edit(
                        tune_id, state='unavailable', state_message=str(exc))
                    return ValidationResult(updated, previous.state,
                                            previous.metadata.sha256)
                if exc.code in ('malformed-sid', 'changed-source'):
                    unchanged(); updated = self._edit(
                        tune_id, state='changed',
                        state_message='The referenced SID changed and no longer validates.')
                    return ValidationResult(updated, previous.state,
                                            previous.metadata.sha256)
                raise
            unchanged()
            changed = inspection.metadata.sha256 != previous.metadata.sha256
            updated = self._edit(
                tune_id, metadata=(previous.metadata if changed else
                                   inspection.metadata),
                state='changed' if changed else 'available',
                state_message=('The referenced SID content changed.' if changed else ''),
                verified_at=self._clock())
            return ValidationResult(updated, previous.state,
                                    previous.metadata.sha256,
                                    inspection.metadata.sha256)
        return self._scheduler.submit(CoreJob('sid-jukebox.validate', task), binding)

    def _cleanup_plans_locked(self):
        now = self._clock()
        for plan_id, plan in tuple(self._plans.items()):
            if now - plan.created_at > self.plan_ttl:self._plans.pop(plan_id, None)
        while len(self._plans) > self.plan_limit:
            oldest = min(self._plans, key=lambda key:self._plans[key].created_at)
            self._plans.pop(oldest, None)

    def prepare_relink(self, tune_id, source):
        tune = self.get(tune_id); _validate_source(source)
        def task(job, session):
            inspection = self._inspect(source, job, session)
            plan_id = self._id_factory()
            preview = RelinkPreview(
                plan_id, tune_id, source, tune.metadata.sha256,
                inspection.metadata.sha256,
                tune.metadata.sha256 == inspection.metadata.sha256,
                inspection.metadata)
            with self._lock:
                self._cleanup_plans_locked()
                self._plans[plan_id] = _RelinkPlan(
                    preview, inspection, tune, session, self._clock())
                self._cleanup_plans_locked()
            return preview
        return self._submit('sid-jukebox.relink-preview', source, task)

    def execute_relink(self, plan_id, *, accept_changed=False):
        self._ready()
        with self._lock:
            self._cleanup_plans_locked(); plan = self._plans.pop(plan_id, None)
        if plan is None:
            raise SidCatalogError('plan',
                                  'Relink review is missing, expired, or already used.')
        if not plan.preview.content_matches and not accept_changed:
            raise SidCatalogError(
                'content-changed', 'The selected SID has different content. Review and explicitly accept it.')
        binding, current = self._binding(plan.preview.source)
        if current != plan.session:
            raise SidCatalogError('session',
                                  'The C64U connection changed. Prepare Relink again.')
        def task(job):
            tune = self.get(plan.preview.tune_id)
            if tune != plan.tune:
                raise SidCatalogError('plan-stale',
                                      'The SID entry changed after Relink review.')
            inspection = self._inspect(plan.preview.source, job, plan.session)
            if inspection.metadata.sha256 != plan.inspection.metadata.sha256:
                raise SidCatalogError('changed-source',
                                      'The selected SID changed after Relink review.')
            with self._lock:
                duplicate = next((item for item in self._tunes.values()
                                  if item.id != tune.id and item.metadata.sha256 ==
                                  inspection.metadata.sha256), None)
                if duplicate is not None:
                    raise SidCatalogError('duplicate-content',
                                          'That SID content is already in the Jukebox.')
                content_changed = (inspection.metadata.sha256 !=
                                   tune.metadata.sha256)
                updated = replace(
                    tune, source=inspection.source, metadata=inspection.metadata,
                    state='available', state_message='', updated_at=self._clock(),
                    verified_at=self._clock())
                self._mutate(lambda:(self._tunes.__setitem__(tune.id, updated), updated)[1])
                return RelinkResult(updated, content_changed)
        return self._scheduler.submit(CoreJob('sid-jukebox.relink', task), binding)

    def list_playlists(self):
        self._ready()
        with self._lock:
            return tuple(sorted(self._playlists.values(),
                                key=lambda item:(item.title.casefold(), item.id)))

    def get_playlist(self, playlist_id):
        self._ready()
        with self._lock:playlist = self._playlists.get(playlist_id)
        if playlist is None:
            raise SidCatalogError('not-found', 'SID playlist was not found.')
        return playlist

    def create_playlist(self, title):
        if not isinstance(title, str) or not title.strip():
            raise SidCatalogError('playlist', 'Enter a playlist title.')
        now = self._clock()
        playlist = SidPlaylist(self._id_factory(), title.strip(), (), now, now)
        return self._mutate(
            lambda:(self._playlists.__setitem__(playlist.id, playlist), playlist)[1])

    def rename_playlist(self, playlist_id, title):
        if not isinstance(title, str) or not title.strip():
            raise SidCatalogError('playlist', 'Enter a playlist title.')
        playlist = self.get_playlist(playlist_id)
        updated = replace(playlist, title=title.strip(), updated_at=self._clock())
        return self._mutate(
            lambda:(self._playlists.__setitem__(playlist_id, updated), updated)[1])

    def delete_playlist(self, playlist_id):
        playlist = self.get_playlist(playlist_id)
        return self._mutate(
            lambda:(self._playlists.pop(playlist_id), playlist)[1])

    def add_playlist_item(self, playlist_id, tune_id, subtune):
        playlist = self.get_playlist(playlist_id); tune = self.get(tune_id)
        if type(subtune) is not int or not 1 <= subtune <= tune.metadata.songs:
            raise SidCatalogError('subtune',
                                  f'Choose a subtune from 1 through {tune.metadata.songs}.')
        item = PlaylistItem(self._id_factory(), tune_id, subtune)
        updated = replace(playlist, items=playlist.items + (item,),
                          updated_at=self._clock())
        return self._mutate(
            lambda:(self._playlists.__setitem__(playlist_id, updated), item)[1])

    def remove_playlist_item(self, playlist_id, item_id):
        playlist = self.get_playlist(playlist_id)
        item = next((item for item in playlist.items if item.id == item_id), None)
        if item is None:
            raise SidCatalogError('not-found', 'SID playlist item was not found.')
        updated = replace(playlist,
                          items=tuple(value for value in playlist.items
                                      if value.id != item_id),
                          updated_at=self._clock())
        return self._mutate(
            lambda:(self._playlists.__setitem__(playlist_id, updated), item)[1])

    def reorder_playlist_item(self, playlist_id, item_id, new_index):
        playlist = self.get_playlist(playlist_id)
        if (type(new_index) is not int or not 0 <= new_index < len(playlist.items)):
            raise SidCatalogError('playlist', 'Playlist position is out of range.')
        items = list(playlist.items)
        try:old_index = next(index for index, item in enumerate(items)
                             if item.id == item_id)
        except StopIteration as exc:
            raise SidCatalogError('not-found', 'SID playlist item was not found.') from exc
        item = items.pop(old_index); items.insert(new_index, item)
        updated = replace(playlist, items=tuple(items), updated_at=self._clock())
        return self._mutate(
            lambda:(self._playlists.__setitem__(playlist_id, updated), updated)[1])

    def job(self, job_id):return self._scheduler.job(job_id)
    def cancel(self, job_id):return self._scheduler.cancel(job_id)

    def close(self):
        if self._owns_scheduler:self._scheduler.close()
