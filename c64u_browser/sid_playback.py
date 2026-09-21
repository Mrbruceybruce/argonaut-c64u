# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Reviewed SID playback and in-memory playlist navigation owned by Core."""
from dataclasses import asdict, dataclass, replace
from threading import RLock
import random
import time
import uuid

from .api import BrowserError, ConnectionFailure
from .jobs import CoreJob, JobCancelled, JobProgress
from .scheduler import DeviceSession, JobBinding
from .sid_jukebox import C64U, CORE_HOST, SidCatalogError


class SidJukeboxError(BrowserError):
    def __init__(self, code, message, *, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class PlaylistContext:
    playlist_id: str
    item_id: str

    def as_dict(self):return asdict(self)


@dataclass(frozen=True)
class PlaybackPreview:
    plan_id: str
    tune_id: str
    title: str
    source: object
    format: str
    version: int
    selected_subtune: int
    default_subtune: int
    used_file_default: bool
    target_device_id: str
    target_session_id: str
    mechanism: str
    running_program_interrupted: bool
    sid_count: int
    sid_addresses: tuple[int, ...]
    sid_models: tuple[str, ...]
    clock: str
    warnings: tuple[str, ...]
    duration_ms: int | None
    duration_source: str
    playlist_context: PlaylistContext | None
    created_at: float

    def as_dict(self):return asdict(self)


@dataclass(frozen=True)
class PlaybackResult:
    tune_id: str
    title: str
    source: object
    selected_subtune: int
    target_device_id: str
    mechanism: str
    status: str
    command_accepted: bool
    audible_playback_verified: bool
    running_program_interrupted: bool
    sid_count: int
    sid_addresses: tuple[int, ...]
    sid_models: tuple[str, ...]
    clock: str
    warnings: tuple[str, ...]
    message: str

    def as_dict(self):return asdict(self)


@dataclass(frozen=True)
class PlaylistTransitionResult:
    direction: str
    status: str
    message: str
    playback: PlaybackResult | None = None

    def as_dict(self):return asdict(self)


@dataclass(frozen=True)
class PlaybackSnapshot:
    status: str = 'idle'
    tune_id: str = ''
    title: str = ''
    selected_subtune: int | None = None
    target_device_id: str = ''
    target_session_id: str = ''
    mechanism: str = ''
    playlist_id: str = ''
    playlist_item_id: str = ''
    playlist_authorized: bool = False
    authorization_expires_at: float | None = None
    shuffle: bool = False
    updated_at: float = 0.0
    message: str = ''

    def as_dict(self):return asdict(self)


@dataclass(frozen=True)
class _PlaybackPlan:
    preview: PlaybackPreview
    tune: object
    session: DeviceSession
    volume_identity: str
    playlist_signature: tuple[tuple[str, str, int], ...]
    runner_song: int | None
    created_at: float


@dataclass(frozen=True)
class _PlaylistAuthorization:
    playlist_id: str
    playlist_signature: tuple[tuple[str, str, int], ...]
    device_id: str
    session_id: str
    cursor_item_id: str
    expires_at: float
    transitions: int = 0
    shuffle: bool = False
    bag: tuple[str, ...] = ()
    history: tuple[str, ...] = ()
    history_position: int = 0


class SidJukeboxService:
    """Headless reviewed playback; the catalog remains the source of truth."""
    def __init__(self, catalog, client_provider, session_provider, scheduler, *,
                 volume_identity=None, attached_runner=None, resident_runner=None,
                 plan_ttl=300, plan_limit=128, authorization_ttl=1800,
                 authorization_transition_limit=256, clock=time.time,
                 id_factory=lambda:uuid.uuid4().hex, random_source=None):
        self._catalog = catalog
        self._client_provider = client_provider
        self._session_provider = session_provider
        self._scheduler = scheduler
        self._volume_identity = volume_identity
        self._attached_runner = attached_runner or self._run_attached
        self._resident_runner = resident_runner or self._run_resident
        self.plan_ttl = max(0, float(plan_ttl))
        self.plan_limit = max(0, int(plan_limit))
        self.authorization_ttl = max(0, float(authorization_ttl))
        self.authorization_transition_limit = max(
            0, int(authorization_transition_limit))
        self._clock = clock
        self._id_factory = id_factory
        self._random = random_source or random.Random()
        self._plans = {}
        self._authorization = None
        self._snapshot = PlaybackSnapshot(updated_at=self._clock())
        self._lock = RLock()

    @staticmethod
    def _run_attached(client, data, song, _source):
        return client.play_sid_data(data, song, 'argonaut.sid')

    @staticmethod
    def _run_resident(client, _data, song, source):
        return client.play_sid(source.path, song)

    @staticmethod
    def _playlist_signature(playlist):
        return tuple((item.id, item.tune_id, item.subtune)
                     for item in playlist.items)

    @staticmethod
    def _mechanism(tune):
        return ('rest-attached-sid' if tune.source.scope == CORE_HOST
                else 'rest-c64u-sid')

    @staticmethod
    def _warnings(tune):
        return tuple((
            'SID playback takes over the C64 and interrupts its running program; unsaved work may be lost.',
            'Command acceptance does not prove audible playback.',
            *tune.metadata.warnings,
        ))

    def _session(self):
        session = self._session_provider()
        if (not isinstance(session, DeviceSession) or not session.device_id
                or not session.session_id):
            raise SidJukeboxError('device-unavailable',
                                  'Connect to the target C64U first.')
        return session

    def _client(self, expected):
        current = self._session()
        if current.device_id != expected.device_id:
            raise SidJukeboxError('device-changed',
                                  'The active C64U changed. Prepare playback again.')
        if current.session_id != expected.session_id:
            raise SidJukeboxError('session-changed',
                                  'The C64U connection changed. Prepare playback again.')
        try:return self._client_provider()
        except ConnectionFailure as exc:
            raise SidJukeboxError('device-unavailable',
                                  'The target C64U is unavailable.', retryable=True) from exc

    def _media_identity(self, source, job):
        if source.scope != C64U:return ''
        if self._volume_identity is None:
            raise SidJukeboxError('storage-unavailable',
                                  'C64U removable-media identity is unavailable.')
        try:return self._volume_identity(source, job.check_cancel)
        except JobCancelled:raise
        except SidJukeboxError:raise
        except (ConnectionFailure, OSError) as exc:
            raise SidJukeboxError('device-unavailable',
                                  'The source C64U storage is unavailable.',
                                  retryable=True) from exc
        except BrowserError as exc:
            raise SidJukeboxError('storage-changed',
                                  'The source C64U storage could not be verified.') from exc

    @staticmethod
    def _subtune(tune, subtune):
        if subtune is None:return tune.metadata.start_song, None
        if type(subtune) is not int or not 1 <= subtune <= tune.metadata.songs:
            raise SidJukeboxError(
                'subtune', f'Choose a subtune from 1 through {tune.metadata.songs}.')
        return subtune, subtune

    @staticmethod
    def _playable(tune):
        if tune.state != 'available':
            raise SidJukeboxError(
                'target-unavailable',
                f'The SID source is {tune.state}. Validate or Relink it before playback.')
        if not tune.metadata.playback_eligible:
            reason = ('MUS data requires an external player.' if tune.metadata.mus
                      else 'PlaySID-specific data is not compatible with physical C64 playback.')
            raise SidJukeboxError('playback-blocked', reason)

    def _context(self, tune, selected_subtune, context):
        if context is None:return None, ()
        if not isinstance(context, PlaylistContext):
            raise SidJukeboxError('playlist', 'Choose a SID playlist item.')
        try:playlist = self._catalog.get_playlist(context.playlist_id)
        except SidCatalogError as exc:
            raise SidJukeboxError('playlist-changed',
                                  'The SID playlist no longer exists.') from exc
        item = next((item for item in playlist.items if item.id == context.item_id), None)
        if (item is None or item.tune_id != tune.id
                or item.subtune != selected_subtune):
            raise SidJukeboxError(
                'playlist-changed',
                'The selected playlist item does not match this tune and subtune.')
        return context, self._playlist_signature(playlist)

    def _cleanup_locked(self):
        now = self._clock()
        for plan_id, plan in tuple(self._plans.items()):
            if now - plan.created_at > self.plan_ttl:
                self._plans.pop(plan_id, None)
        while len(self._plans) > self.plan_limit:
            oldest = min(self._plans, key=lambda key:self._plans[key].created_at)
            self._plans.pop(oldest, None)
        if (self._authorization is not None
                and now > self._authorization.expires_at):
            self._authorization = None

    def cleanup(self):
        with self._lock:self._cleanup_locked()
        self._scheduler.cleanup()

    def discard_plan(self, plan_id):
        with self._lock:
            self._cleanup_locked()
            return self._plans.pop(plan_id, None) is not None

    def prepare_play(self, record_id, subtune=None, playlist_context=None):
        tune = self._catalog.get(record_id)
        self._playable(tune)
        selected_subtune, runner_song = self._subtune(tune, subtune)
        context, signature = self._context(
            tune, selected_subtune, playlist_context)
        session = self._session()
        if tune.source.scope == C64U and tune.source.device_id != session.device_id:
            raise SidJukeboxError('device-changed',
                                  'The SID belongs to a different physical C64U.')

        def task(job):
            current = self._catalog.get(record_id)
            if current != tune:
                raise SidJukeboxError('record-changed',
                                      'The SID entry changed. Prepare playback again.')
            if context is not None:
                _context, current_signature = self._context(
                    current, selected_subtune, context)
                if current_signature != signature:
                    raise SidJukeboxError('playlist-changed',
                                          'The playlist changed. Prepare playback again.')
            before_media = self._media_identity(tune.source, job)
            inspection = self._catalog._inspect(
                tune.source, job,
                session if tune.source.scope == C64U else None)
            after_media = self._media_identity(tune.source, job)
            if before_media != after_media:
                raise SidJukeboxError('storage-changed',
                                      'C64U removable media changed during playback review.')
            if inspection.metadata.sha256 != tune.metadata.sha256:
                raise SidJukeboxError('source-changed',
                                      'The referenced SID changed. Validate or Relink it first.')
            if self._catalog.get(record_id) != tune:
                raise SidJukeboxError('record-changed',
                                      'The SID entry changed. Prepare playback again.')
            plan_id = self._id_factory()
            preview = PlaybackPreview(
                plan_id, tune.id, tune.title, tune.source, tune.metadata.format,
                tune.metadata.version, selected_subtune,
                tune.metadata.start_song, runner_song is None,
                session.device_id, session.session_id, self._mechanism(tune),
                True, tune.metadata.sid_count,
                tuple(chip.address for chip in tune.metadata.chips),
                tuple(chip.model for chip in tune.metadata.chips),
                tune.metadata.clock, self._warnings(tune), None, 'unknown',
                context, self._clock())
            with self._lock:
                self._cleanup_locked()
                self._plans[plan_id] = _PlaybackPlan(
                    preview, tune, session, after_media, signature, runner_song,
                    self._clock())
                self._cleanup_locked()
            return preview

        return self._scheduler.submit(
            CoreJob('sid-jukebox.playback-preview', task),
            JobBinding.device(session))

    def _inspect_for_execution(self, tune, session, expected_volume, job):
        before_media = self._media_identity(tune.source, job)
        if expected_volume is not None and before_media != expected_volume:
            raise SidJukeboxError('storage-changed',
                                  'C64U removable media changed after review.')
        try:
            inspection, data = self._catalog._inspect_data(
                tune.source, job,
                session if tune.source.scope == C64U else None)
        except SidCatalogError as exc:
            raise SidJukeboxError(exc.code, str(exc),
                                  retryable=exc.retryable) from exc
        after_media = self._media_identity(tune.source, job)
        if before_media != after_media:
            raise SidJukeboxError('storage-changed',
                                  'C64U removable media changed during validation.')
        if inspection.metadata.sha256 != tune.metadata.sha256:
            raise SidJukeboxError('source-changed',
                                  'The referenced SID changed after playback review.')
        return data

    def _accepted_result(self, tune, subtune, session, mechanism):
        return PlaybackResult(
            tune.id, tune.title, tune.source, subtune, session.device_id,
            mechanism, 'command-accepted', True, False, True,
            tune.metadata.sid_count,
            tuple(chip.address for chip in tune.metadata.chips),
            tuple(chip.model for chip in tune.metadata.chips),
            tune.metadata.clock, self._warnings(tune),
            'The C64U accepted the SID playback command. Audible playback was not verified.')

    def _run_command(self, tune, data, runner_song, session, job):
        client = self._client(session)
        job.report(JobProgress('ready', tune.metadata.file_size,
                               tune.metadata.file_size, 'bytes',
                               'Validated; ready to request SID playback.'))
        # Last cooperative cancellation point. A lost response after this call
        # leaves the playback outcome uncertain and must never be retried.
        job.check_cancel()
        try:
            if tune.source.scope == CORE_HOST:
                self._attached_runner(client, data, runner_song, tune.source)
            else:
                self._resident_runner(client, data, runner_song, tune.source)
        except ConnectionFailure as exc:
            if exc.kind in ('network', 'host'):
                self._record_uncertain(tune, session)
                raise SidJukeboxError(
                    'playback-outcome-unknown',
                    'The SID playback response was lost. The command may have been accepted; inspect the C64U before retrying.') from exc
            code = ('authentication' if exc.kind == 'authentication'
                    else 'firmware-rejection')
            raise SidJukeboxError(code,
                                  'The C64U rejected the SID playback command.') from exc
        except BrowserError as exc:
            raise SidJukeboxError('firmware-rejection',
                                  'The C64U rejected the SID playback command.') from exc

    def _record_uncertain(self, tune, session):
        with self._lock:
            self._authorization = None
            self._snapshot = PlaybackSnapshot(
                'playback-outcome-unknown', tune.id, tune.title, None,
                session.device_id, session.session_id, self._mechanism(tune),
                updated_at=self._clock(),
                message='The playback command may have been accepted; audible playback is unknown.')

    def _record_accepted(self, tune, subtune, session, mechanism, *,
                         context=None, signature=()):
        with self._lock:
            if context is not None:
                authorization = _PlaylistAuthorization(
                    context.playlist_id, signature, session.device_id,
                    session.session_id, context.item_id,
                    self._clock() + self.authorization_ttl,
                    history=(context.item_id,))
                self._authorization = authorization
            else:
                self._authorization = None
            authorization = self._authorization
            self._snapshot = PlaybackSnapshot(
                'command-accepted', tune.id, tune.title, subtune,
                session.device_id, session.session_id, mechanism,
                context.playlist_id if context else '',
                context.item_id if context else '', context is not None,
                authorization.expires_at if authorization else None,
                authorization.shuffle if authorization else False,
                self._clock(),
                'The C64U accepted the command; audible playback is unverified.')

    def execute_play(self, plan_id):
        with self._lock:
            self._cleanup_locked(); plan = self._plans.pop(plan_id, None)
        if plan is None:
            raise SidJukeboxError(
                'plan-expired',
                'Playback review is missing, expired, or already used. Prepare it again.')
        current_session = self._session()
        if current_session.device_id != plan.session.device_id:
            raise SidJukeboxError('device-changed',
                                  'The active C64U changed. Prepare playback again.')
        if current_session.session_id != plan.session.session_id:
            raise SidJukeboxError('session-changed',
                                  'The C64U connection changed. Prepare playback again.')

        def task(job):
            tune = self._catalog.get(plan.preview.tune_id)
            if tune != plan.tune:
                raise SidJukeboxError('record-changed',
                                      'The SID entry changed after playback review.')
            self._playable(tune)
            selected, _runner = self._subtune(tune, plan.preview.selected_subtune)
            if plan.preview.playlist_context is not None:
                _context, signature = self._context(
                    tune, selected, plan.preview.playlist_context)
                if signature != plan.playlist_signature:
                    raise SidJukeboxError('playlist-changed',
                                          'The playlist changed after playback review.')
            data = self._inspect_for_execution(
                tune, plan.session, plan.volume_identity, job)
            if self._catalog.get(tune.id) != plan.tune:
                raise SidJukeboxError('record-changed',
                                      'The SID entry changed after playback review.')
            if plan.preview.playlist_context is not None:
                _context, signature = self._context(
                    tune, selected, plan.preview.playlist_context)
                if signature != plan.playlist_signature:
                    raise SidJukeboxError('playlist-changed',
                                          'The playlist changed after playback review.')
            self._run_command(tune, data, plan.runner_song, plan.session, job)
            result = self._accepted_result(
                tune, selected, plan.session, plan.preview.mechanism)
            self._record_accepted(
                tune, selected, plan.session, plan.preview.mechanism,
                context=plan.preview.playlist_context,
                signature=plan.playlist_signature)
            return result

        return self._scheduler.submit(
            CoreJob('sid-jukebox.play', task), JobBinding.device(plan.session))

    def _require_authorization(self):
        with self._lock:
            self._cleanup_locked(); authorization = self._authorization
        if authorization is None:
            raise SidJukeboxError(
                'authorization', 'Start a playlist with reviewed Play first.')
        current = self._session()
        if (current.device_id != authorization.device_id
                or current.session_id != authorization.session_id):
            with self._lock:self._authorization = None
            raise SidJukeboxError(
                'authorization', 'The C64U connection changed. Review playlist playback again.')
        try:playlist = self._catalog.get_playlist(authorization.playlist_id)
        except SidCatalogError as exc:
            with self._lock:self._authorization = None
            raise SidJukeboxError(
                'authorization', 'The playlist was deleted. Review playback again.') from exc
        signature = self._playlist_signature(playlist)
        if (signature != authorization.playlist_signature
                or authorization.cursor_item_id not in
                {item.id for item in playlist.items}):
            with self._lock:self._authorization = None
            raise SidJukeboxError(
                'authorization', 'The playlist changed. Review playback again.')
        if authorization.transitions >= self.authorization_transition_limit:
            with self._lock:self._authorization = None
            raise SidJukeboxError(
                'authorization', 'Playlist authorization reached its transition limit. Review playback again.')
        return authorization, playlist, current

    def current_playback(self):
        try:authorization, _playlist, _session = self._require_authorization()
        except SidJukeboxError:
            with self._lock:
                return replace(self._snapshot, playlist_authorized=False,
                               authorization_expires_at=None, shuffle=False)
        with self._lock:
            return replace(self._snapshot, playlist_authorized=True,
                           authorization_expires_at=authorization.expires_at,
                           shuffle=authorization.shuffle)

    def set_shuffle(self, enabled):
        if type(enabled) is not bool:
            raise SidJukeboxError('shuffle', 'Shuffle must be on or off.')
        authorization, playlist, _session = self._require_authorization()
        if enabled:
            bag = [item.id for item in playlist.items
                   if item.id != authorization.cursor_item_id]
            self._random.shuffle(bag)
            updated = replace(
                authorization, shuffle=True, bag=tuple(bag),
                history=(authorization.cursor_item_id,), history_position=0)
        else:
            updated = replace(
                authorization, shuffle=False, bag=(),
                history=(authorization.cursor_item_id,), history_position=0)
        with self._lock:
            if self._authorization != authorization:
                raise SidJukeboxError('authorization',
                                      'Playlist authorization changed.')
            self._authorization = updated
            self._snapshot = replace(self._snapshot, shuffle=enabled,
                                     updated_at=self._clock())
        return self.current_playback()

    def _shuffled_cycle(self, playlist, current_item_id):
        bag = [item.id for item in playlist.items]
        self._random.shuffle(bag)
        if len(bag) > 1 and bag[0] == current_item_id:
            bag[0], bag[1] = bag[1], bag[0]
        return bag

    def _propose_transition(self, authorization, playlist, direction):
        item_ids = [item.id for item in playlist.items]
        if authorization.shuffle:
            history = list(authorization.history)
            position = authorization.history_position
            bag = list(authorization.bag)
            if direction == 'previous':
                if position == 0:return None, authorization
                position -= 1; target_id = history[position]
            elif position < len(history) - 1:
                position += 1; target_id = history[position]
            else:
                if not bag:
                    bag = self._shuffled_cycle(
                        playlist, authorization.cursor_item_id)
                if not bag:return None, authorization
                target_id = bag.pop(0)
                history = history[:position + 1] + [target_id]
                position += 1
            proposed = replace(
                authorization, cursor_item_id=target_id, bag=tuple(bag),
                history=tuple(history), history_position=position,
                transitions=authorization.transitions + 1)
        else:
            index = item_ids.index(authorization.cursor_item_id)
            target_index = index + (1 if direction == 'next' else -1)
            if not 0 <= target_index < len(item_ids):return None, authorization
            target_id = item_ids[target_index]
            proposed = replace(
                authorization, cursor_item_id=target_id,
                transitions=authorization.transitions + 1,
                history=(target_id,), history_position=0, bag=())
        return next(item for item in playlist.items if item.id == target_id), proposed

    def _transition(self, direction):
        authorization, _playlist, session = self._require_authorization()

        def task(job):
            current_auth, playlist, current_session = self._require_authorization()
            if current_auth != authorization:
                raise SidJukeboxError('authorization',
                                      'Playlist position changed before this operation ran.')
            target, proposed = self._propose_transition(
                current_auth, playlist, direction)
            if target is None:
                return PlaylistTransitionResult(
                    direction, 'boundary',
                    f'Already at the {"end" if direction == "next" else "beginning"} of the playlist.')
            tune = self._catalog.get(target.tune_id)
            self._playable(tune)
            selected, runner_song = self._subtune(tune, target.subtune)
            before_media = self._media_identity(tune.source, job)
            data = self._inspect_for_execution(
                tune, current_session, before_media, job)
            if self._catalog.get(tune.id) != tune:
                raise SidJukeboxError('record-changed',
                                      'The SID entry changed during playlist navigation.')
            latest_auth, _latest_playlist, _latest_session = (
                self._require_authorization())
            if latest_auth != current_auth:
                raise SidJukeboxError(
                    'authorization',
                    'Playlist authorization changed during validation.')
            self._run_command(tune, data, runner_song, current_session, job)
            playback = self._accepted_result(
                tune, selected, current_session, self._mechanism(tune))
            with self._lock:
                if self._authorization == current_auth:
                    self._authorization = proposed
                    self._snapshot = PlaybackSnapshot(
                        'command-accepted', tune.id, tune.title, selected,
                        current_session.device_id, current_session.session_id,
                        self._mechanism(tune), proposed.playlist_id,
                        proposed.cursor_item_id, True, proposed.expires_at,
                        proposed.shuffle, self._clock(),
                        'The C64U accepted the command; audible playback is unverified.')
                else:
                    self._authorization = None
                    self._snapshot = PlaybackSnapshot(
                        'command-accepted', tune.id, tune.title, selected,
                        current_session.device_id, current_session.session_id,
                        self._mechanism(tune), updated_at=self._clock(),
                        message='Command accepted, but playlist authorization changed and was cleared.')
            return PlaylistTransitionResult(
                direction, 'command-accepted',
                'The C64U accepted the playlist transition; audible playback is unverified.',
                playback)

        return self._scheduler.submit(
            CoreJob('sid-jukebox.' + direction, task),
            JobBinding.device(session))

    def next(self):return self._transition('next')
    def previous(self):return self._transition('previous')
    def job(self, job_id):return self._scheduler.job(job_id)
    def cancel(self, job_id):return self._scheduler.cancel(job_id)
