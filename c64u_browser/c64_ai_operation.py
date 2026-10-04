# SPDX-License-Identifier: GPL-3.0-or-later
"""Core-private, single-use managed AI file operation. No transport escapes."""
from dataclasses import dataclass, replace
from hashlib import sha256
import ipaddress
import os
from pathlib import Path
import posixpath
import shutil
import tempfile
from threading import Lock, Timer
import time
import uuid

from .api import BrowserError, UltimateClient
from .c64_ai_install import ClientInstallResult, build_c64_ai_client, _build_legacy_c64_ai_client
from .c64_ai_launch import CLIENT_PATH
from .c64_ai_bridge_config import C64BridgeConfig, validate_bridge_config
from .files import child
from .folder_copy import Step
from .ftp_reads import adapter_for
from .jobs import CoreJob, JobCancelled
from .managed_replacement import replace_managed
from .scheduler import JobBinding
from .transfers import remote_file, upload_managed


@dataclass(frozen=True)
class EligibilityObservation:
    slot: str
    path: str
    device_id: str
    session_id: str
    preparation_id: str
    count: int | None = None
    sha256: str | None = None
    status: str = 'unverified'


class _ExactSink:
    """Private streaming predicate. Never retains received content."""
    def __init__(self, expected, observation):
        self.__expected = expected
        self.__observation = observation
        self.__count = 0
        self.__equal = True

    def write(self, block):
        start = self.__count
        self.__count += len(block)
        self.__equal &= block == self.__expected[start:self.__count]
        return len(block)

    def observation(self, result=None):
        if result is None:return self.__observation
        matched = self.__equal and self.__count == len(self.__expected)
        return replace(self.__observation, count=result.transferred, sha256=result.sha256,
                       status='full-byte-match' if matched else 'mismatch')


class _PairSink:
    def __init__(self, current, legacy):self.current, self.legacy = current, legacy
    def write(self, block):
        self.current.write(block)
        return self.legacy.write(block)


class _ContextFailure(BrowserError):
    code = 'ai-context'


class _FileFailure(BrowserError):
    code = 'ai-file'
    def __init__(self, result):
        super().__init__('Managed AI file work stopped; inspect the recorded result.')
        self.result = result


class AIFileService:
    """Private plans expire after five minutes and are consumed on submission."""
    def __init__(self, core, *, clock=time.monotonic):
        self.__core = core
        self.__clock = clock
        self.__plans = {}
        self.__lock = Lock()

    def _context(self):
        core = self.__core
        session = core.device_session()
        profile = core.active_profile
        if profile is None:raise BrowserError('Connect an identity-bound C64U first.')
        profile.verify_identity(core.device_info, require_bound=True)
        if not session.device_id or not session.session_id:
            raise BrowserError('Connect an identity-bound C64U first.')
        return session, profile

    def preparation_context(self, address):
        """Capture local bound identity for pending provenance; no device traffic."""
        try:
            session, profile = self._context()
            if address != profile.host:raise ValueError()
            return session
        except Exception:
            pass
        raise _ContextFailure('AI device context changed; prepare again.') from None

    def prepare(self, config, address, path=CLIENT_PATH, *, config_id=None, config_check=None,
                expected_session=None):
        # No FTP, service or REST traffic during capture.
        try:
            path = remote_file(path)
            child(posixpath.dirname(path), posixpath.basename(path))
            if not isinstance(config, C64BridgeConfig):raise ValueError()
            config = validate_bridge_config(dict(schema=1, model=config.model, host=config.host,
                port=config.port, token=config.token, allowed_clients=list(config.allowed_clients)))
            address = str(ipaddress.IPv4Address(address))
            if address not in config.allowed_clients and len(config.allowed_clients) >= 4:
                raise ValueError()
            session, profile = self._context()
            if expected_session is not None and session != expected_session:raise ValueError()
            client = self.__core._require_client()
            if self._context() != (session, profile):raise ValueError()
            adapter = adapter_for(client)
            if not isinstance(client, UltimateClient) or adapter is None:raise ValueError()
            binding = adapter.binding
            if (binding.device.physical_id != session.device_id or
                binding.core_session_id != session.session_id or
                address != profile.host or address != client.host or
                (client.host, client.port) != (binding.host, binding.port)):
                raise ValueError()
            adapter._manager._check(binding)
            current, legacy = build_c64_ai_client(config), _build_legacy_c64_ai_client(config)
            handle = uuid.uuid4().hex
            result = ClientInstallResult(path, False, len(current), sha256(current).hexdigest(),
                device_id=session.device_id, session_id=session.session_id,
                epoch=binding.core_session_id, address=address, port=binding.port,
                preparation_id=handle, config_id=config_id or uuid.uuid4().hex)
            plan = (client, adapter, binding, session, profile, current, legacy, config_check, result)
            with self.__lock:
                self.__expire()
                if len(self.__plans) >= 128:raise ValueError()
                self.__plans[handle] = (self.__clock(), plan)
            timer = Timer(300, self.discard, (handle,))
            timer.daemon = True
            timer.start()
            return handle
        except Exception:
            if 'handle' in locals():self.discard(handle)
        raise BrowserError('AI preparation context is invalid; prepare again.')

    def __expire(self):
        now = self.__clock()
        for key, (created, _) in tuple(self.__plans.items()):
            if now-created > 300:self.__plans.pop(key)

    def close(self):
        with self.__lock:self.__plans.clear()

    def discard(self, handle):
        with self.__lock:self.__plans.pop(handle, None)

    def validate_result_context(self, result):
        try:
            session, profile = self._context()
            binding = self.__core._ftp_binding(session.device_id)
            if (session.device_id != result.device_id or session.session_id != result.session_id or
                binding is None or binding.core_session_id != result.epoch or
                (binding.host, binding.port) != (result.address, result.port) or
                profile.host != result.address or
                (self.__core._client.host, self.__core._client.port) != (result.address, result.port)):
                raise ValueError()
            self.__core._ftp_manager._check(binding)
            return
        except Exception:
            pass
        raise _ContextFailure('AI device context changed; prepare again.')

    def execute(self, handle, *, cancel_requested=False):
        with self.__lock:
            self.__expire()
            record = self.__plans.pop(handle, None)
        if record is None:raise BrowserError('AI preparation expired or was already consumed.')
        _, plan = record
        base = plan[-1]
        holder = [plan]
        def task(job):
            captured = holder.pop()
            return self._execute(captured, job)
        def failure_result(exc):
            holder.clear()  # Also releases a plan cancelled in the scheduler queue.
            if isinstance(getattr(exc, 'result', None), ClientInstallResult):return exc.result
            return replace(base, reason='cancelled' if getattr(exc, 'cancelled', False) else 'stale-context',
                cancellation_phase='queued' if getattr(exc, 'cancelled', False) else None,
                cancellation_requested=getattr(exc, 'cancelled', False),
                cancellation_observed=getattr(exc, 'cancelled', False))
        job = CoreJob('ai.file.execute', task, failure_result=failure_result)
        # Preserve PENDING for scheduler admission; run observes cancellation before preflight.
        if cancel_requested:job._cancel.set()
        try:return self.__core.scheduler.submit(job, JobBinding.device(plan[3]))
        except Exception:
            holder.clear()
            raise BrowserError('AI file job could not be queued; prepare again.') from None

    def _execute(self, plan, job):
        client, adapter, binding, session, profile, current, legacy, config_check, result = plan
        folder = None
        failure = False
        phase = 'classification'
        def check():
            self.validate_result_context(result)
            if (adapter.binding != binding or (client.host, client.port) != (binding.host, binding.port)):
                raise _ContextFailure('AI captured endpoint changed.')
            job.check_cancel()
        def progress(count):pass
        progress.check = check
        def observation(slot):
            return EligibilityObservation(slot, result.path, session.device_id,
                                          session.session_id, result.preparation_id)
        def validator(slot):return _ExactSink(legacy, observation(slot))
        try:
            if config_check is not None:config_check()
            check()
            with adapter.operation(check):
                parent, name = posixpath.split(result.path)
                _, entries = client.list_directory(parent)
                matches = [entry for entry in entries if entry.name.casefold() == name.casefold()]
                if len(matches) > 1 or (matches and matches[0].name != name):
                    result = replace(result, classification='non-file', action='refused',
                                     disposition='refused-unchanged', reason='ambiguous-target')
                elif matches and matches[0].kind != 'file':
                    result = replace(result, classification='non-file', action='refused',
                                     disposition='refused-unchanged', reason='non-file')
                else:
                    if matches:
                        now = _ExactSink(current, observation('current-execution'))
                        old = validator('classification')
                        result = replace(result, current_verification=now.observation())
                        read = adapter.read_into(result.path, _PairSink(now, old), check=check)
                        current_observation, legacy_observation = now.observation(read), old.observation(read)
                        result = replace(result, current_verification=current_observation)
                        classification = ('current' if current_observation.status == 'full-byte-match' else
                                          'recognized-legacy' if legacy_observation.status == 'full-byte-match' else 'foreign')
                    else:classification = 'missing'
                    result = replace(result, classification=classification)
                    if classification == 'current':
                        result = replace(result, action='no-op', disposition='verified-current')
                    elif classification == 'foreign':
                        result = replace(result, action='refused', disposition='refused-unchanged', reason='foreign')
                    else:
                        phase = 'staging'
                        folder = tempfile.mkdtemp(prefix='argonaut-ai-private-')
                        os.chmod(folder, 0o700)
                        local = Path(folder)/name
                        fd = os.open(local, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(fd, 'wb') as stream:stream.write(current)
                        if classification == 'missing':
                            upload = upload_managed(client, local, parent, progress)
                            result = replace(result, installed=True, action='installed', disposition='installed',
                                             upload=upload['upload'])
                        else:
                            phase = 'replacement'
                            step = Step(name, local, result.path, False, True, (name, matches[0].size))
                            replaced = replace_managed(client, step, True, progress,
                                                       original_validator_factory=validator)
                            result = replace(result, installed=True, action='upgraded', disposition='upgraded',
                                replacement=replaced, legacy_eligibility=replaced.original_eligibility or (),
                                cancellation_observed=replaced.cancellation_observed,
                                cancellation_deferred=replaced.cancellation_deferred)
        except Exception as exc:
            failure = True
            upload = getattr(exc, 'upload_evidence', None)
            replacement = getattr(exc, 'replacement_evidence', None)
            wire = getattr(exc, 'ftp_error', None)
            cancelled = bool(getattr(exc, 'cancelled', False))
            eligibility = (replacement.original_eligibility or ()) if replacement else ()
            mismatch = any(item.status == 'mismatch' for item in eligibility)
            published = bool(replacement and replacement.publication == 'completed')
            uncertain = bool((replacement and (replacement.uncertain_step or replacement.uncertain_paths)) or
                             (upload and upload.disposition == 'location-unknown'))
            refused = mismatch or bool(upload and upload.error_category == 'conflict')
            result = replace(result, upload=upload, replacement=replacement, legacy_eligibility=eligibility,
                installed=published, action='upgraded' if published else 'refused' if refused else 'not-completed',
                disposition='published-cleanup-incomplete' if published else 'uncertain' if uncertain else
                            'refused-unchanged' if refused else 'not-completed',
                reason='legacy-mismatch' if mismatch else 'cancelled' if cancelled else
                       'target-conflict' if refused else
                       'configuration-changed' if getattr(exc, 'code', None) == 'ai-configuration' else
                       'stale-context' if getattr(exc, 'code', None) == 'ai-context' or
                           (wire and wire.code.value == 'stale-session') else 'file-unverified',
                cancellation_observed=cancelled or bool(replacement and replacement.cancellation_observed),
                cancellation_deferred=bool(replacement and replacement.cancellation_deferred),
                cancellation_phase=(replacement.phase if replacement else upload.phase if upload else phase) if cancelled else None,
                transport_error=wire.as_dict() if wire else None)
        finally:
            # Preserve normalized remote facts before touching local resources.
            cleanup = 'unneeded'
            if folder is not None:
                try:
                    shutil.rmtree(folder)
                    cleanup = 'completed'
                except Exception:cleanup = 'failed'
            result = replace(result, local_cleanup=cleanup,
                             local_cleanup_error='local-cleanup-failed' if cleanup == 'failed' else None,
                             cancellation_requested=job._cancel.is_set(),
                             cancellation_phase=result.cancellation_phase or
                                 ('post-file' if job._cancel.is_set() else None))
        if failure:
            # Raise only a new sanitized exception outside the original except context.
            if result.cancellation_observed and result.action not in ('installed', 'upgraded'):
                raise JobCancelled(result=result)
            raise _FileFailure(result)
        return result
