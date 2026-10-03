# SPDX-License-Identifier: GPL-3.0-or-later
"""R2 reviewed fresh-folder composite. Paths and evidence never authorize replay."""
from dataclasses import dataclass, replace
from pathlib import Path
import stat
import uuid

from .api import BrowserError
from .files import child, inspect, operate_managed
from .ftp_reads import adapter_for
from .jobs import CoreJob, JobCancelled, TERMINAL_STATES
from .scheduler import JobBinding
from .storage import storage_root
from .transfers import upload_managed


@dataclass(frozen=True)
class FreshFolderResult:
    phase: str = 'setup'
    preparation: str = 'unperformed'
    execution: str = 'unperformed'
    source: object = None
    observed_size: int | None = None
    execution_size: int | None = None
    profile_id: str | None = None
    device_id: str | None = None
    session_id: str | None = None
    parent: str | None = None
    directory: str | None = None
    path: str | None = None
    mkdir_state: str = 'not-submitted'
    mutation: object = None
    directory_disposition: str = 'not-established'
    upload_state: str = 'not-started'
    upload: object = None
    bytes: int | None = None
    sha256: str | None = None
    verified: bool | None = None
    cancellation_phase: str | None = None
    error_category: str | None = None
    error_code: str | None = None
    transport_error: object = None
    local_cleanup: str = 'not-required'
    secondary_failures: tuple = ()
    disposition: str = 'no-creation-established'
    state: str = 'pending'
    inspection: str = 'No creation established. No automatic retry or cleanup.'

    def inspection_message(self):
        return self.inspection


@dataclass(frozen=True)
class FreshFolderPreview:
    plan_id: str
    source: object
    observed_size: int
    parent: str
    directory: str
    path: str
    profile_id: str
    device_id: str
    session_id: str
    evidence: FreshFolderResult


@dataclass(frozen=True)
class _Plan:
    preview: FreshFolderPreview
    session: object
    binding: tuple
    ancestors: tuple
    created_at: float


class _FreshFolderJob(CoreJob):
    """Normalize only R2 pre-task refusal; generic scheduling stays unchanged.

    Snapshot normalization also covers events, scheduler lookups and wait(),
    without racing a post-completion listener or inventing worker observations.
    """
    def __init__(self, operation, task, intent):
        super().__init__(operation, task)
        self.intent = intent

    def snapshot(self):
        snapshot = super().snapshot()
        if snapshot.state in TERMINAL_STATES and snapshot.result is None:
            cancelled = snapshot.state == 'cancelled'
            code = 'cancelled' if cancelled else snapshot.error.code if snapshot.error else 'session'
            evidence = replace(self.intent, phase='queued', state=snapshot.state,
                               error_category=code, error_code=code,
                               cancellation_phase='queued' if cancelled else None)
            return replace(snapshot, result=evidence)
        return snapshot


def _submit(service, operation, task, intent, session):
    try:
        return service._scheduler.submit(_FreshFolderJob(operation, task, intent),
                                         JobBinding.device(session))
    except Exception as exc:_raise(_normalize(replace(intent, phase='queued'), exc))


def _binding(service):
    profile = service._bound_profile_provider() if service._bound_profile_provider else None
    session = service._device_session()
    if profile is None or not (profile.device_id or profile.device_mac):
        raise BrowserError('Fresh-folder upload requires an identity-bound Core profile.')
    identity = 'id:' + profile.device_id if profile.device_id else 'mac:' + profile.device_mac.lower()
    # Core can use a reported ID when a MAC-only profile was verified.
    if not session.session_id or not session.device_id or session.device_id.startswith('profile:'):
        raise BrowserError('A verified Core session is required.')
    if profile.device_id and session.device_id != identity:
        raise BrowserError('The bound profile and Core session differ.')
    return (profile.id, profile.device_id, profile.device_mac, profile.host,
            profile.http_port, profile.ftp_port), session


def _check_binding(service, plan):
    service._check_session(plan.session)
    binding, session = _binding(service)
    if binding != plan.binding or session != plan.session:
        raise BrowserError('The reviewed profile binding changed.')


def _source(source):
    if source.scope != 'core-host':
        raise BrowserError('Fresh-folder source must belong to the Core host.')
    path = Path(source.path)
    child('/USB1', path.name)
    observed = path.stat()  # Follow a regular-file symlink, matching legacy policy.
    if not stat.S_ISREG(observed.st_mode) or observed.st_size <= 0:
        raise BrowserError('Choose a nonempty regular file.')
    return observed.st_size


def _review(client, parent):
    if not parent.startswith('/') or not storage_root(parent):
        raise BrowserError('Choose an exact absolute USB/SD directory.')
    observations = []
    previous = '/'
    for name in parent[1:].split('/'):
        # Validate each component, including names accepted by storage_root().
        if previous != '/':child(previous, name)
        actual, entries = client.list_directory(previous)
        matches = [entry for entry in entries if entry.name.casefold() == name.casefold()]
        if actual != previous or len(matches) != 1 or matches[0].name != name or matches[0].kind != 'dir':
            raise BrowserError('The exact parent or ancestor is unavailable or ambiguous.')
        previous = previous.rstrip('/') + '/' + name
        observations.append((previous, matches[0].kind))
    actual, _ = client.list_directory(parent)
    if actual != parent:raise BrowserError('The parent path changed.')
    return tuple(observations)


def _normalize(evidence, exc):
    upload = getattr(exc, 'upload_evidence', None) or evidence.upload
    mutation = evidence.mutation
    if evidence.phase == 'mkdir':mutation = getattr(exc, 'result', None) or mutation
    wire = getattr(exc, 'ftp_error', None)
    cancelled = isinstance(exc, JobCancelled)
    category = ('cancelled' if cancelled else upload.error_category if upload and upload.error_category else
                'transport' if wire else 'source' if evidence.phase in ('preparation-source', 'execution-source') else
                'session' if evidence.phase == 'binding' else 'validation' if evidence.phase == 'validation' else
                'cleanup' if evidence.phase == 'cleanup' else 'operation')
    code = wire.code.value if wire else upload.error_code if upload and upload.error_code else category
    evidence = replace(evidence, upload=upload, mutation=mutation,
        error_category=category, error_code=code, state='cancelled' if cancelled else 'failed',
        cancellation_phase=evidence.phase if cancelled else None,
        transport_error=wire.as_dict() if wire else upload.transport_error if upload else evidence.transport_error)
    if evidence.phase == 'preparation-source':evidence = replace(evidence, preparation='failed')
    if evidence.phase == 'execution-source':evidence = replace(evidence, execution='failed')
    cleanup = tuple(getattr(exc, 'local_cleanup', ()))
    if cleanup:
        evidence = replace(evidence, local_cleanup='failed', secondary_failures=evidence.secondary_failures + cleanup)
    return _outcome(evidence)


def _outcome(e):
    mkd, directory = e.mkdir_state, e.directory_disposition
    if e.mutation:
        if e.mutation.completed:
            mkd, directory = 'completed', 'created'
        elif e.mutation.stopped:
            stopped = e.mutation.stopped
            if stopped['outcome'] == 'rejected':mkd = 'refused'
            elif stopped['consequential_submitted']:
                mkd, directory = 'unknown', 'outcome-unknown'
    disposition = ('directory-outcome-unknown' if mkd == 'unknown' else
                   'directory-refused' if mkd == 'refused' else 'no-creation-established')
    upload_state = e.upload.disposition if e.upload else 'not-started'
    if directory == 'created':
        disposition = ('directory-created-upload-not-started' if e.state == 'cancelled' and
                       upload_state == 'not-started' else 'directory-created-upload-failed')
        if upload_state == 'staging-candidate':disposition = 'directory-created-upload-incomplete'
        if upload_state == 'location-unknown':disposition = 'directory-created-file-location-unknown'
        if upload_state == 'published':
            disposition = 'published-local-cleanup-failed' if e.local_cleanup == 'failed' else 'published'
    guidance = {
        'no-creation-established': 'No creation established.',
        'directory-refused': 'MKD was refused; no upload attempted. Absence is not established.',
        'directory-outcome-unknown': 'MKD outcome is unknown. Inspect the intended directory in a new operation.',
        'directory-created-upload-not-started': 'Directory creation acknowledged; upload not started. Directory was left in place.',
        'directory-created-upload-failed': 'Directory creation acknowledged; upload failed. Inspect the recorded upload evidence.',
        'directory-created-upload-incomplete': 'Directory creation acknowledged; a staging candidate may remain.',
        'directory-created-file-location-unknown': 'Directory created; file may be at either recorded staging or final path.',
        'published': 'Verified file publication acknowledged. Do not replay.',
        'published-local-cleanup-failed': 'Verified file publication acknowledged; local finalization failed. Do not replay.',
    }[disposition]
    return replace(e, mkdir_state=mkd, directory_disposition=directory,
                   upload_state=upload_state, disposition=disposition,
                   inspection=guidance + ' No automatic retry, rollback or deletion. Further action requires fresh inspection and review.')


def _raise(evidence):
    from .file_service import FileJobFailure
    if evidence.state == 'cancelled':raise JobCancelled(result=evidence)
    raise FileJobFailure('fresh-folder-' + (evidence.error_code or 'operation'),
                         evidence.inspection_message(), evidence)


def prepare(service, source, parent):
    from .file_service import FileLocation
    valid_source = (isinstance(source, FileLocation) and source.scope == 'core-host'
                    and isinstance(source.path, str) and source.artifact_id == '')
    intent = FreshFolderResult(source=source if valid_source else None,
                               parent=parent if isinstance(parent, str) else None)
    try:
        if not valid_source or not isinstance(parent, str):
            raise BrowserError('A Core-host file and remote parent path are required.')
        binding, session = _binding(service)
        intent = replace(intent, profile_id=binding[0], device_id=session.device_id, session_id=session.session_id)
    except Exception as exc:_raise(_normalize(replace(intent, phase='binding'), exc))
    def task(job):
        e = intent
        try:
            e = replace(e, phase='preparation-source')
            size = _source(source)
            e = replace(e, preparation='passed', observed_size=size, phase='binding')
            client = service._client((remote_location(parent),), session)
            adapter = adapter_for(client)
            if adapter is None:raise BrowserError('Managed adapter required.')
            if _binding(service) != (binding, session):raise BrowserError('Profile binding changed.')
            e = replace(e, phase='validation')
            with adapter.operation(job.check_cancel):
                ancestors = _review(client, parent)
                directory = child(parent, 'c64u-transfer-' + uuid.uuid4().hex)
                destination = child(directory, Path(source.path).name)
                e = replace(e, directory=directory, path=destination)
                if inspect(client, directory) is not None:raise BrowserError('Generated directory already exists.')
            job.check_cancel()
            plan_id = uuid.uuid4().hex
            preview = FreshFolderPreview(plan_id, source, size, parent, directory, destination,
                binding[0], session.device_id, session.session_id, replace(e, phase='prepared'))
            with service._lock:
                service._cleanup_plans_locked()
                service._fresh_plans[plan_id] = _Plan(preview, session, binding, ancestors, service._clock())
                service._cleanup_plans_locked()
            return preview
        except Exception as exc:_raise(_normalize(e, exc))
    return _submit(service, 'file.fresh-folder-upload.prepare', task, intent, session)


def remote_location(path):
    from .file_service import FileLocation
    return FileLocation.c64u(path)


def execute(service, plan_id):
    try:plan = service._take_plan(service._fresh_plans, plan_id, 'Fresh-folder plan')
    except Exception as exc:_raise(_normalize(FreshFolderResult(phase='plan'), exc))
    intent = replace(plan.preview.evidence, phase='queued')
    def task(job):
        e = intent
        primary = None
        entered = False
        try:
            e = replace(e, phase='execution-source')
            size = _source(e.source)
            e = replace(e, execution='passed', execution_size=size, phase='binding')
            _check_binding(service, plan)
            client = service._client((remote_location(e.parent),), plan.session)
            adapter = adapter_for(client)
            if adapter is None:raise BrowserError('Managed adapter required.')
            job.check_cancel()
            with adapter.operation(job.check_cancel):
                entered = True
                try:
                    e = replace(e, phase='validation')
                    if _review(client, e.parent) != plan.ancestors or inspect(client, e.directory) is not None:
                        raise BrowserError('Reviewed destination changed.')
                    _check_binding(service, plan)
                    e = replace(e, phase='mkdir')
                    mutation = operate_managed(client, 'mkdir', e.directory, check=job.check_cancel)
                    # Retain the consequence BEFORE checking cancellation or nesting upload.
                    e = _outcome(replace(e, mutation=mutation, phase='after-mkdir'))
                    if e.mkdir_state != 'completed':raise BrowserError('MKD acknowledgement required.')
                    job.check_cancel()
                    e = replace(e, phase='upload')
                    result = upload_managed(client, e.source.path, e.directory, job.byte_progress(),
                                            require_nonempty_regular=True)
                    e = _outcome(replace(e, upload=result['upload'], bytes=result['bytes'],
                        sha256=result['sha256'], verified=True, phase='complete', state='succeeded'))
                except Exception as exc:
                    e = _normalize(e, exc)
                    primary = exc
            entered = False
        except Exception as exc:
            if entered:
                # The body has already normalized its primary outcome. Release
                # failure cannot erase uncertainty, cancellation or publication.
                e = replace(e, local_cleanup='failed', secondary_failures=e.secondary_failures +
                            (('operation-release', 'cleanup-failed'),))
                if primary is None:
                    e = replace(e, phase='cleanup', state='failed', error_category='cleanup', error_code='cleanup')
                e = _outcome(e)
            else:e = _normalize(e, exc)
        if e.state != 'succeeded':_raise(e)
        return e
    return _submit(service, 'file.fresh-folder-upload', task, intent, plan.session)
