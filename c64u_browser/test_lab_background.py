# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Control the independent read-only Test Lab fleet timer."""
from dataclasses import dataclass
import subprocess

from . import development
from .api import BrowserError


TIMER = development.service_name('test-lab-fleet.timer')


@dataclass(frozen=True)
class BackgroundStatus:
    state: str
    message: str


def _systemctl(command, runner=subprocess.run, options=()):
    try:
        return runner(
            ['systemctl', '--user', command, *options, TIMER],
            capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BrowserError(
            'The unattended Test Lab schedule could not be checked.') from exc


def status(runner=subprocess.run):
    try:
        enabled = _systemctl('is-enabled', runner).returncode == 0
        if not enabled:
            return BackgroundStatus(
                'disabled', 'Off · no background C64U checks are scheduled')
        active = _systemctl('is-active', runner)
    except BrowserError:
        return BackgroundStatus(
            'unavailable', 'Status unavailable · background services could not be checked')
    if active.returncode == 0 and active.stdout.strip() == 'active':
        return BackgroundStatus('ready', 'On · checks saved C64Us every 30 minutes')
    return BackgroundStatus(
        'stopped', 'Scheduled but stopped · restart background checks')


def set_enabled(enabled, runner=subprocess.run):
    try:
        reload_result = runner(
            ['systemctl', '--user', 'daemon-reload'], capture_output=True,
            text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BrowserError(
            'The background service list could not be refreshed.') from exc
    if reload_result.returncode != 0:
        raise BrowserError('The background service list could not be refreshed.')
    command = 'enable' if enabled else 'disable'
    result = _systemctl(command, runner, ('--now',))
    if result.returncode != 0:
        action = 'enabled' if enabled else 'stopped'
        raise BrowserError(f'Unattended C64U checks could not be {action}.')
    current = status(runner)
    expected = 'ready' if enabled else 'disabled'
    if current.state != expected:
        raise BrowserError('The unattended Test Lab schedule did not change.')
    return current
