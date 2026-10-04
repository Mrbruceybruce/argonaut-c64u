# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Safe AI installation results and file-before-bridge orchestration."""
from dataclasses import dataclass
import subprocess

from .c64_ai_client import render_chat_client, render_legacy_chat_client
from .c64_ai_launch import CLIENT_PATH
from .c64_basic import tokenize_basic_v2


@dataclass(frozen=True)
class ClientInstallResult:
    path: str
    installed: bool
    size: int
    sha256: str
    classification: str = 'unverified'
    action: str = 'not-completed'
    disposition: str = 'not-completed'
    device_id: str = ''
    session_id: str = ''
    epoch: str = ''
    address: str = ''
    port: int = 0
    preparation_id: str = ''
    config_id: str = ''
    current_verification: object = None
    legacy_eligibility: tuple = ()
    upload: object = None
    replacement: object = None
    transport_error: object = None
    cancellation_phase: str | None = None
    cancellation_requested: bool = False
    cancellation_observed: bool = False
    cancellation_deferred: bool = False
    local_cleanup: str = 'unneeded'
    local_cleanup_error: str | None = None
    reason: str | None = None

    @property
    def permits_provisioning(self):
        if (self.local_cleanup == 'failed' or self.cancellation_requested or
                self.cancellation_observed):return False
        if self.disposition == 'verified-current':
            return bool(self.current_verification and
                        self.current_verification.status == 'full-byte-match')
        if self.disposition == 'installed':
            e = self.upload
            return bool(e and e.disposition == 'published' and e.readback == 'passed' and
                        e.size == 'passed' and e.publication and e.publication['outcome'] == 'completed')
        if self.disposition == 'upgraded':
            e = self.replacement
            return bool(e and e.publication == 'completed' and e.cleanup == 'completed' and
                len(self.legacy_eligibility) == 2 and
                tuple(item.slot for item in self.legacy_eligibility) == ('original-before', 'original-after') and
                all(item.status == 'full-byte-match' for item in self.legacy_eligibility))
        return False

    def inspection_message(self):
        if self.replacement:return self.replacement.inspection_message()
        if self.upload:return self.upload.inspection_message()
        return ('File outcome: ' + self.disposition + '. Prepare a new operation to inspect; '
                'this result does not authorize replay or cleanup.')


@dataclass(frozen=True)
class ClientProvisionResult:
    bridge: object
    client: ClientInstallResult
    bridge_disposition: str = 'not-started'
    reason: str | None = None
    pending_id: str | None = None
    bridge_commands: tuple = ()


def build_c64_ai_client(config):
    return tokenize_basic_v2(render_chat_client(config.host, config.port, config.token))


def _build_legacy_c64_ai_client(config):
    return tokenize_basic_v2(render_legacy_chat_client(config.host, config.port, config.token))


def install_c64_ai_client(service, config, path=CLIENT_PATH, *, address):
    """File-only synchronous convenience over the Core scheduled capability."""
    return service.execute(service.prepare(config, address, path)).wait().result


def install_and_pair_c64_ai(service, config_path, address, runner=subprocess.run,
                            *, model='gemma3:4b', cancelled=lambda: False):
    from .c64_ai_preparation import prepare_bridge, finalize_bridge
    from .c64_ai_bridge_config import configuration_guard
    def cancellation_pending():
        try:return bool(cancelled())
        except Exception:return True
    # Raise outside the original handler: even __context__ must contain no private I/O.
    handle = None
    phase = 'context'
    try:
        context = service.preparation_context(address)
        phase = 'configuration'
        prepared = prepare_bridge(config_path, model, address, device_id=context.device_id)
        with configuration_guard(config_path):
            prepared.validate()
            phase = 'generation'
            handle = service.prepare(prepared.config, address, config_id=prepared.identity,
                                     config_check=prepared.validate, expected_session=context)
            phase = 'validation'
            prepared.validate()
        phase = 'submission'
        job = service.execute(handle, cancel_requested=cancellation_pending())
    except Exception:
        if handle is not None:
            try:service.discard(handle)
            except Exception:pass
    else:
        phase = None
    if phase is not None:
        from .api import BrowserError
        raise BrowserError('AI ' + phase + ' could not complete; review private configuration and device context.') from None
    while True:
        try:
            snapshot = job.wait(.1)
            break
        except TimeoutError:
            if cancellation_pending():job.request_cancel()
    file = snapshot.result
    pending_id = prepared.identity if prepared.pending else None
    if not file.permits_provisioning or cancellation_pending():
        return ClientProvisionResult(None, file, 'held', 'file-gate', pending_id)
    def bridge_context():
        from .jobs import JobCancelled
        if cancellation_pending():raise JobCancelled()
        service.validate_result_context(file)
    commands = []
    def recorded_runner(args, **kwargs):
        consequential = args[2] in ('daemon-reload', 'enable', 'disable', 'start', 'stop', 'restart')
        command = (args[2], 'health' if args[-1].endswith('health.timer') else 'bridge')
        outcome = 'unknown'
        try:
            response = runner(args, **kwargs)
            outcome = 'completed' if response.returncode == 0 else 'failed'
            return response
        finally:
            if consequential:commands.append((*command, outcome))
    try:
        with configuration_guard(config_path):
            prepared.validate()
            service.validate_result_context(file)
            if cancellation_pending():
                return ClientProvisionResult(None, file, 'cancelled', 'pre-bridge', pending_id)
            bridge = finalize_bridge(prepared, recorded_runner,
                                     context_check=bridge_context)
        return ClientProvisionResult(bridge, file, 'ready', bridge_commands=tuple(commands))
    except Exception as exc:
        disposition = 'cancelled' if getattr(exc, 'cancelled', False) else 'failed'
        reason = ('configuration-changed' if getattr(exc, 'code', None) == 'ai-configuration' else
                  'stale-context' if getattr(exc, 'code', None) == 'ai-context' else 'bridge-failed')
    return ClientProvisionResult(None, file, disposition, reason, pending_id, tuple(commands))
