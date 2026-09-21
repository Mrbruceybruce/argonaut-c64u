# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Headless, reviewed D64/CRT launch capability owned by Argonaut Core."""
from dataclasses import asdict, dataclass
from threading import Lock
import time
import uuid

from .api import BrowserError, ConnectionFailure
from .disk_run import DmaLaunchError, run_image_bytes
from .game_library import C64U, CORE_HOST
from .jobs import CoreJob, JobProgress
from .scheduler import DeviceSession, JobBinding


class GameLaunchError(BrowserError):
    def __init__(self, code, message, *, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class LaunchPreview:
    plan_id: str
    record_id: str
    title: str
    source: object
    format: str
    source_sha256: str
    target_device_id: str
    target_session_id: str
    mechanism: str
    reset_expected: bool
    running_program_interrupted: bool
    warnings: tuple[str, ...]
    created_at: float

    def as_dict(self):return asdict(self)


@dataclass(frozen=True)
class LaunchResult:
    record_id: str
    title: str
    source: object
    format: str
    target_device_id: str
    mechanism: str
    status: str
    command_accepted: bool
    playable_state_verified: bool
    message: str

    def as_dict(self):return asdict(self)


@dataclass(frozen=True)
class _LaunchPlan:
    preview: LaunchPreview
    record: object
    session: DeviceSession
    volume_identity: str
    created_at: float


class GameLaunchService:
    """Plan and execute consequential launches without exposing transport."""
    def __init__(self, catalog, client_provider, session_provider, scheduler, *,
                 volume_identity=None, attached_crt_runner=None,
                 resident_crt_runner=None, d64_runner=None,
                 plan_ttl=300, plan_limit=128, clock=time.time,
                 id_factory=lambda:uuid.uuid4().hex):
        self._catalog = catalog
        self._client_provider = client_provider
        self._session_provider = session_provider
        self._scheduler = scheduler
        self._volume_identity = volume_identity
        self._attached_crt_runner = attached_crt_runner or self._run_attached_crt
        self._resident_crt_runner = resident_crt_runner or self._run_resident_crt
        self._d64_runner = d64_runner or self._run_d64
        self.plan_ttl = max(0, float(plan_ttl))
        self.plan_limit = max(0, int(plan_limit))
        self._clock = clock
        self._id_factory = id_factory
        self._plans = {}
        self._lock = Lock()

    @staticmethod
    def _run_attached_crt(client, data, source):
        # The attachment name is intentionally fixed; a Core-host path is
        # private catalog state and is not needed by the runner.
        return client.run_crt_data(data, 'argonaut.crt')

    @staticmethod
    def _run_resident_crt(client, _data, source):
        return client.run_crt(source.path)

    @staticmethod
    def _run_d64(client, data, _source):
        return run_image_bytes(client, data)

    def _session(self):
        session = self._session_provider()
        if not isinstance(session, DeviceSession):
            raise GameLaunchError('device-unavailable', 'C64U session state is unavailable.')
        if not session.device_id or not session.session_id:
            raise GameLaunchError('device-unavailable', 'Connect to the target C64U first.')
        return session

    def _client(self, expected):
        current = self._session()
        if current.device_id != expected.device_id:
            raise GameLaunchError('device-changed',
                                  'The active C64U changed. Prepare launch again.')
        if current.session_id != expected.session_id:
            raise GameLaunchError('session-changed',
                                  'The C64U connection changed. Prepare launch again.')
        try:return self._client_provider()
        except ConnectionFailure as exc:
            raise GameLaunchError('device-unavailable',
                                  'The target C64U is unavailable.', retryable=True) from exc

    @staticmethod
    def _mechanism(record):
        if record.format == 'CRT':
            return ('rest-attached-crt' if record.source.scope == CORE_HOST
                    else 'rest-c64u-crt')
        return 'dma-run-img'

    @staticmethod
    def _warnings(record):
        warnings = [
            'Launching resets the C64 and interrupts its running program.',
            'Command acceptance does not prove the game reached a playable screen.',
        ]
        if record.format == 'CRT':
            hardware_type = dict(record.metadata).get('hardware_type', 'unknown')
            warnings.extend((
                f'CRT hardware type {hardware_type} is structurally valid; firmware support is unverified.',
                'The cartridge is temporary: Reset restarts it, Reboot returns to the permanently configured cartridge, and another CRT replaces it.',
            ))
        return tuple(warnings)

    def _media_identity(self, source, job):
        if source.scope != C64U:return ''
        if self._volume_identity is None:
            raise GameLaunchError('storage-unavailable',
                                  'C64U removable-media identity is unavailable.')
        try:return self._volume_identity(source, job.check_cancel)
        except GameLaunchError:raise
        except (ConnectionFailure, OSError) as exc:
            raise GameLaunchError('device-unavailable',
                                  'The source C64U storage is unavailable.',
                                  retryable=True) from exc
        except BrowserError as exc:
            raise GameLaunchError('storage-changed',
                                  'The source C64U storage could not be verified.') from exc

    def _cleanup_locked(self):
        now = self._clock()
        for plan_id, plan in tuple(self._plans.items()):
            if now - plan.created_at > self.plan_ttl:
                self._plans.pop(plan_id, None)
        while len(self._plans) > self.plan_limit:
            oldest = min(self._plans, key=lambda key:self._plans[key].created_at)
            self._plans.pop(oldest, None)

    def cleanup(self):
        with self._lock:self._cleanup_locked()
        self._scheduler.cleanup()

    def discard_plan(self, plan_id):
        with self._lock:
            self._cleanup_locked()
            return self._plans.pop(plan_id, None) is not None

    def prepare_launch(self, record_id):
        record = self._catalog.get(record_id)
        session = self._session()
        if record.source.scope == C64U and record.source.device_id != session.device_id:
            raise GameLaunchError('device-changed',
                                  'The game belongs to a different physical C64U.')

        def task(job):
            current = self._catalog.get(record_id)
            if current != record:
                raise GameLaunchError('record-changed',
                                      'The Game Library entry changed. Prepare launch again.')
            before_media = self._media_identity(record.source, job)
            inspection = self._catalog._inspect(
                record.source, job,
                session if record.source.scope == C64U else None)
            after_media = self._media_identity(record.source, job)
            if before_media != after_media:
                raise GameLaunchError('storage-changed',
                                      'The C64U removable media changed during launch review.')
            if inspection.sha256 != record.sha256:
                raise GameLaunchError('source-changed',
                                      'The referenced game changed. Validate or Relink it first.')
            if self._catalog.get(record_id) != record:
                raise GameLaunchError('record-changed',
                                      'The Game Library entry changed. Prepare launch again.')
            plan_id = self._id_factory()
            preview = LaunchPreview(
                plan_id, record.id, record.title, record.source, record.format,
                record.sha256, session.device_id, session.session_id,
                self._mechanism(record), True, True, self._warnings(record),
                self._clock())
            with self._lock:
                self._cleanup_locked()
                self._plans[plan_id] = _LaunchPlan(
                    preview, record, session, after_media, self._clock())
                self._cleanup_locked()
            return preview

        return self._scheduler.submit(
            CoreJob('game-library.launch-preview', task),
            JobBinding.device(session))

    def execute_launch(self, plan_id):
        with self._lock:
            self._cleanup_locked()
            plan = self._plans.pop(plan_id, None)
        if plan is None:
            raise GameLaunchError(
                'plan-expired',
                'Launch review is missing, expired, or already used. Prepare it again.')
        current = self._session()
        if current.device_id != plan.session.device_id:
            raise GameLaunchError('device-changed',
                                  'The active C64U changed. Prepare launch again.')
        if current.session_id != plan.session.session_id:
            raise GameLaunchError('session-changed',
                                  'The C64U connection changed. Prepare launch again.')

        def task(job):
            record = self._catalog.get(plan.preview.record_id)
            if record != plan.record:
                raise GameLaunchError('record-changed',
                                      'The Game Library entry changed after review.')
            before_media = self._media_identity(record.source, job)
            if before_media != plan.volume_identity:
                raise GameLaunchError('storage-changed',
                                      'The C64U removable media changed after review.')
            inspection, data = self._catalog._inspect_data(
                record.source, job,
                plan.session if record.source.scope == C64U else None)
            after_media = self._media_identity(record.source, job)
            if after_media != plan.volume_identity:
                raise GameLaunchError('storage-changed',
                                      'The C64U removable media changed after review.')
            if inspection.sha256 != record.sha256:
                raise GameLaunchError('source-changed',
                                      'The referenced game changed after launch review.')
            if self._catalog.get(record.id) != plan.record:
                raise GameLaunchError('record-changed',
                                      'The Game Library entry changed after review.')
            client = self._client(plan.session)
            job.report(JobProgress('ready', inspection.size, inspection.size,
                                   'bytes', 'Validated; ready to launch.'))
            # This is the last cooperative cancellation point. Once the call
            # begins, a response can be lost after the C64U acted.
            job.check_cancel()
            try:
                if record.format == 'CRT' and record.source.scope == CORE_HOST:
                    self._attached_crt_runner(client, data, record.source)
                elif record.format == 'CRT':
                    self._resident_crt_runner(client, data, record.source)
                else:
                    self._d64_runner(client, data, record.source)
            except DmaLaunchError as exc:
                code = ('launch-outcome-unknown' if exc.command_may_have_started
                        else 'firmware-rejection')
                raise GameLaunchError(code, str(exc)) from exc
            except ConnectionFailure as exc:
                if exc.kind in ('network', 'host'):
                    raise GameLaunchError(
                        'launch-outcome-unknown',
                        'The C64U launch response was lost. The command may have been accepted; inspect the C64U before retrying.') from exc
                code = ('authentication' if exc.kind == 'authentication'
                        else 'firmware-rejection')
                raise GameLaunchError(code, 'The C64U rejected the launch command.') from exc
            except BrowserError as exc:
                raise GameLaunchError('firmware-rejection',
                                      'The C64U rejected the launch command.') from exc
            return LaunchResult(
                record.id, record.title, record.source, record.format,
                plan.session.device_id, plan.preview.mechanism,
                'command-accepted', True, False,
                'The C64U accepted the launch command. Playable state was not verified.')

        return self._scheduler.submit(
            CoreJob('game-library.launch', task),
            JobBinding.device(plan.session))

    def job(self, job_id):return self._scheduler.job(job_id)
    def cancel(self, job_id):return self._scheduler.cancel(job_id)
