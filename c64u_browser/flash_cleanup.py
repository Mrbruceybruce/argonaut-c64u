# SPDX-License-Identifier: GPL-3.0-or-later
"""Internal R6 qualification cleanup: one reviewed Flash file, never replayed."""
from dataclasses import dataclass, replace
import posixpath
import re
import uuid

from .api import BrowserError
from .fresh_folder import _binding
from .ftp_reads import adapter_for
from .jobs import JobCancelled
from .native_files import flash_path, MAX_BYTES


@dataclass(frozen=True)
class FlashCleanupEvidence:
    path: str
    expected_size: int
    expected_sha256: str
    device_id: str
    session_id: str
    plan_id: str
    phase: str = 'queued'
    observed_size: int | None = None
    observed_sha256: str | None = None
    preparation: str = 'unperformed'
    pre_delete: str = 'unperformed'
    mutation: dict | None = None
    absence: str = 'unperformed'
    error_category: str | None = None
    cancellation_phase: str | None = None

    @property
    def acknowledged(self):
        return bool(self.mutation and self.mutation['outcome'] == 'completed')

    @property
    def complete(self):
        return self.acknowledged and self.absence == 'passed'

    @property
    def message(self):
        if self.complete:return 'Exact Flash file deletion acknowledged and absence independently verified.'
        if self.acknowledged:
            return 'Exact Flash file deletion acknowledged; absence verification incomplete. Inspect the exact target independently; do not replay DELE.'
        if self.mutation and self.mutation['outcome'] == 'unknown':
            return 'Flash deletion state unknown. Inspect the exact target independently; do not retry DELE.'
        return 'Flash cleanup refused or stopped before acknowledged deletion. Fresh inspection and review required.'


@dataclass(frozen=True)
class _Plan:
    evidence: FlashCleanupEvidence
    session: object
    binding: tuple
    connection: object
    created_at: float


def _validate(path, size, digest):
    if not isinstance(path, str):raise BrowserError('An exact Flash file path is required.')
    folder, name = posixpath.split(path)
    if flash_path(folder, name) != path:raise BrowserError('An exact Flash file path is required.')
    if type(size) is not int or not 1 <= size <= MAX_BYTES:
        raise BrowserError('Supply the expected nonempty fixture size within the Flash bound.')
    if not isinstance(digest, str) or re.fullmatch('[0-9a-fA-F]{64}', digest) is None:
        raise BrowserError('Supply the expected SHA-256.')
    return digest.lower()


def _observe(adapter, path, *, absent=False):
    folder, name = posixpath.split(path)
    def entries(parent):
        actual, rows = adapter.list_directory(parent)
        if actual != parent:raise BrowserError('Flash directory identity changed.')
        return rows
    for parent, child in (('/', 'Flash'), ('/Flash', posixpath.basename(folder))):
        matches = [e for e in entries(parent) if e.name.casefold() == child.casefold()]
        if len(matches) != 1 or matches[0].name != child or matches[0].kind != 'dir':
            raise BrowserError('Exact existing Flash parent required.')
    matches = [e for e in entries(folder) if e.name.casefold() == name.casefold()]
    if absent:
        if matches:raise BrowserError('Exact Flash target absence not established.')
        return None
    if len(matches) != 1 or matches[0].name != name or matches[0].kind != 'file':
        raise BrowserError('Exact unambiguous Flash file required.')
    return matches[0].size


def _failure(evidence, exc):
    wire = getattr(exc, 'ftp_error', None)
    mutation = getattr(wire, 'mutation', None)
    cancelled = bool(getattr(exc, 'cancelled', False))
    return replace(evidence,
        mutation=mutation.as_dict() if evidence.phase == 'delete' and mutation else evidence.mutation,
        error_category='cancelled' if cancelled else 'transport' if wire else 'refused',
        cancellation_phase=evidence.phase if cancelled else None,
        pre_delete='failed' if evidence.pre_delete == 'pending' else evidence.pre_delete,
        absence='incomplete' if evidence.absence == 'pending' else evidence.absence)


def _raise(evidence):
    from .file_service import FileJobFailure
    if evidence.cancellation_phase:raise JobCancelled(evidence.message, evidence) from None
    raise FileJobFailure('flash-cleanup', evidence.message, evidence) from None


def _submit(service, task, evidence, session, operation):
    def failure_result(exc):
        result = getattr(exc, 'result', None)
        return result if isinstance(result, FlashCleanupEvidence) else _failure(evidence, exc)
    try:return service._job(operation, task, session=session, failure_result=failure_result)
    except Exception as exc:_raise(_failure(evidence, exc))


def _adapter(service, path, session, binding, connection=None):
    service._check_session(session)
    if _binding(service) != (binding, session):raise BrowserError('Reviewed Core binding changed.')
    from .file_service import FileLocation
    adapter = adapter_for(service._client((FileLocation.c64u(path),), session))
    if adapter is None:raise BrowserError('Managed Core adapter required.')
    if (adapter.binding.core_session_id != session.session_id or
            adapter.binding.device.physical_id != session.device_id or
            adapter.binding.host != binding[3] or adapter.binding.port != binding[5] or
            (connection is not None and adapter.binding != connection)):
        raise BrowserError('Reviewed connection binding changed.')
    return adapter


def _verify(adapter, evidence, update):
    """Fresh identity, SIZE, bounded full RETR/hash, SIZE, identity/size recheck."""
    size = _observe(adapter, evidence.path)
    evidence = replace(evidence, observed_size=size, observed_sha256=None)
    update(evidence)
    if size != evidence.expected_size or adapter.size(evidence.path) != evidence.expected_size:
        raise BrowserError('Flash fixture size changed.')
    read = adapter.readback(evidence.path, evidence.expected_size)
    evidence = replace(evidence, observed_size=read.transferred, observed_sha256=read.sha256)
    update(evidence)
    if read.transferred != evidence.expected_size or read.sha256 != evidence.expected_sha256:
        raise BrowserError('Flash fixture hash changed.')
    if (adapter.size(evidence.path) != evidence.expected_size or
            _observe(adapter, evidence.path) != evidence.expected_size):
        raise BrowserError('Flash fixture changed after readback.')


def prepare(service, path, expected_size, expected_sha256):
    digest = _validate(path, expected_size, expected_sha256)
    binding, session = _binding(service)
    intent = FlashCleanupEvidence(path, expected_size, digest, session.device_id,
                                  session.session_id, uuid.uuid4().hex)
    def task(job):
        e = intent
        def update(value):
            nonlocal e
            e = value
        try:
            adapter = _adapter(service, path, session, binding)
            connection = adapter.binding
            def check():
                _adapter(service, path, session, binding, connection)
                job.check_cancel()
            e = replace(e, phase='preparation')
            with adapter.operation(check):_verify(adapter, e, update)
            check()
            e = replace(e, phase='prepared', preparation='passed')
            with service._lock:
                service._cleanup_plans_locked()
                service._flash_cleanup_plans[e.plan_id] = _Plan(e, session, binding, connection, service._clock())
                service._cleanup_plans_locked()
            return e
        except Exception as exc:_raise(_failure(e, exc))
    return _submit(service, task, intent, session, 'file.flash-cleanup.prepare')


def execute(service, plan_id):
    plan = service._take_plan(service._flash_cleanup_plans, plan_id, 'Flash cleanup plan')
    intent = replace(plan.evidence, phase='queued', observed_size=None, observed_sha256=None)
    def task(job):
        e = intent
        def update(value):
            nonlocal e
            e = value
        try:
            adapter = _adapter(service, e.path, plan.session, plan.binding, plan.connection)
            def check():
                _adapter(service, e.path, plan.session, plan.binding, plan.connection)
                job.check_cancel()
            with adapter.operation(check):
                e = replace(e, phase='pre-delete', pre_delete='pending')
                _verify(adapter, e, update)
                e = replace(e, pre_delete='passed')
                check()
                e = replace(e, phase='delete')
                mutation = adapter.mutate('delete', e.path)
                # Record the reply before any cancellation/binding/read check.
                e = replace(e, mutation=mutation, phase='absence', absence='pending')
                if not e.acknowledged:raise BrowserError('Deletion acknowledgement required.')
                _observe(adapter, e.path, absent=True)
                e = replace(e, absence='passed', phase='complete')
            return e
        except Exception as exc:_raise(_failure(e, exc))
    return _submit(service, task, intent, plan.session, 'file.flash-cleanup.execute')
