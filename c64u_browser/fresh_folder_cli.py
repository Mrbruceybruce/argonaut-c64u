# SPDX-License-Identifier: GPL-3.0-or-later
"""Identity-bound put-new client; legacy read commands keep their own parser route."""
from dataclasses import asdict, replace
import getpass
import json
import signal
import sys
import warnings

from .api import BrowserError, safe_argument
from .core import ArgonautCore
from .file_service import FileLocation
from .fresh_folder import FreshFolderResult, FreshFolderPreview, _outcome


class UsageError(Exception):
    pass


def emit(result, error=None, job_id=None):
    record = dict(schema_version=1, operation='file.fresh-folder-upload',
                  state=result.state, result=asdict(result), error=error)
    if job_id is not None:record['job_id'] = job_id
    print(json.dumps(record, ensure_ascii=True))


def usage_error():
    result = replace(FreshFolderResult(), state='failed', error_category='syntax', error_code='syntax')
    message = 'Invalid put-new syntax or unsupported option. Use --help for usage.'
    print(message, file=sys.stderr)
    emit(result, dict(code='syntax', message=message, retryable=False))
    return 2


def resolve_profile(core, selectors):
    if core.preferences_error:raise BrowserError('Cannot use corrupt preferences.')
    preferences = core.preferences
    ids = [p.id for p in preferences.profiles]
    if any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
        raise BrowserError('Ambiguous profile IDs.')
    selected = preferences.selected_id
    if selected is not None and (not isinstance(selected, str) or selected not in ids):
        raise BrowserError('Dangling profile selection.')
    if selectors is not None and len(selectors) != 1:raise UsageError()
    profile_id = selectors[0] if selectors is not None else selected
    if not isinstance(profile_id, str) or not profile_id or len(profile_id) > 120:
        raise BrowserError('Invalid profile selector.')
    safe_argument(profile_id)
    matches = [p for p in preferences.profiles if p.id == profile_id]
    if len(matches) != 1:raise BrowserError('Exactly one saved profile must match.')
    profile = matches[0].validate()
    if not (profile.device_id or profile.device_mac):raise BrowserError('Bound profile required.')
    for value in (profile.device_id, profile.device_mac):
        safe_argument(value)
        if len(value) > 120:raise BrowserError('Invalid identity binding.')
    return profile


def private_password():
    # Turn getpass's echoing fallback into refusal before it reads any input.
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        value = getpass.getpass('Network password: ', stream=sys.stderr)
    if len(value) > 1024:raise BrowserError('Password exceeds the input bound.')
    safe_argument(value)
    return value


def drain(job, cancelled):
    while True:
        try:
            if cancelled[0]:job.request_cancel()
            return job.wait()
        except KeyboardInterrupt:
            cancelled[0] = True
            job.request_cancel()


def run(args):
    core = None
    job = None
    cancelled = [False]
    active = [None]
    prior_handler = None
    result = FreshFolderResult()
    error = None
    code = 1
    phase = 'profile'

    def interrupt(signum, frame):
        cancelled[0] = True
        if phase == 'credential':raise KeyboardInterrupt()
        if active[0] is not None:active[0].request_cancel()

    def check():
        if cancelled[0]:raise KeyboardInterrupt()

    def wait(next_job):
        nonlocal job
        job = active[0] = next_job
        return drain(job, cancelled)

    try:
        prior_handler = signal.signal(signal.SIGINT, interrupt)
        core = ArgonautCore().load()
        profile = resolve_profile(core, args.profile_id)
        result = replace(result, profile_id=profile.id)
        phase = 'credential'
        entered = private_password() if args.password else ''
        check()
        phase = 'connection'
        core.connect(profile, entered_password=entered, require_bound=True,
                     bind_identity=False, persist=False, remember=False)
        entered = ''
        check()
        phase = 'preparation'
        result = replace(result, source=FileLocation.core_host(args.path), parent=args.destination,
                         device_id=core.device_session().device_id, session_id=core.device_session().session_id)
        snapshot = wait(core.prepare_fresh_folder_upload(result.source, result.parent))
        if snapshot.state == 'succeeded':
            preview = snapshot.result
            if not isinstance(preview, FreshFolderPreview):raise BrowserError('Invalid preparation result.')
            result = preview.evidence
            phase = 'execution'
            snapshot = wait(core.execute_fresh_folder_upload(preview.plan_id))
        result = snapshot.result
        error = (dict(code=snapshot.error.code, message=result.inspection_message(), retryable=False)
                 if snapshot.error else None)
        code = 0 if snapshot.state == 'succeeded' else 130 if snapshot.state == 'cancelled' else 1
    except UsageError:
        result = replace(result, state='failed', error_category='syntax', error_code='syntax')
        error = dict(code='syntax', message='Repeated profile selectors are not supported.', retryable=False)
        code = 2
    except (KeyboardInterrupt, EOFError):
        result = _outcome(replace(result, state='cancelled', phase=phase, cancellation_phase=phase,
                                 error_category='cancelled', error_code='cancelled'))
        error = dict(code='cancelled', message='Operation cancelled before publication.', retryable=False)
        code = 130
    except Exception as exc:
        # Connection failures may contain untrusted peer identity or filesystem prose.
        # The CLI emits a bounded category, never the arbitrary exception text.
        category = getattr(exc, 'code', None)
        category = category if category in ('identity', 'session', 'authentication', 'network', 'host') else phase
        retained = getattr(exc, 'result', None)
        if isinstance(retained, FreshFolderResult):
            result = retained
            error = dict(code='fresh-folder-' + (result.error_code or 'operation'),
                         message=result.inspection_message(), retryable=False)
        else:
            result = _outcome(replace(result, state='failed', phase=phase,
                                     error_category=category, error_code=category))
            error = dict(code=category, message='Fresh-folder upload stopped during ' + phase + '.', retryable=False)
    finally:
        active[0] = None
        if core is not None:
            try:core.close()
            except Exception:
                result = _outcome(replace(result, local_cleanup='failed',
                    secondary_failures=result.secondary_failures + (('core-close', 'cleanup-failed'),)))
                if code == 0:
                    result = replace(result, state='failed', error_category='cleanup', error_code='cleanup')
                    code = 1
                    error = dict(code='cleanup', message=result.inspection_message(), retryable=False)
        if prior_handler is not None:signal.signal(signal.SIGINT, prior_handler)
    if error:print(error['message'], file=sys.stderr)
    emit(result, error, job.id if job else None)
    return code
