# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Control the scheduled end-to-end C64 AI bridge test."""
from dataclasses import dataclass
import subprocess

from .api import BrowserError


TIMER = 'argonaut-c64-ai-test.timer'


@dataclass(frozen=True)
class BridgeTestStatus:
    state: str
    message: str


def _systemctl(command, runner=subprocess.run, options=()):
    try:
        return runner(
            ['systemctl', '--user', command, *options, TIMER],
            capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BrowserError(
            'The automatic C64 AI test schedule could not be checked.') from exc


def status(runner=subprocess.run):
    try:
        enabled = _systemctl('is-enabled', runner).returncode == 0
        if not enabled:
            return BridgeTestStatus(
                'disabled', 'Off · no end-to-end AI tests are scheduled')
        active = _systemctl('is-active', runner)
    except BrowserError:
        return BridgeTestStatus(
            'unavailable',
            'Status unavailable · background services could not be checked')
    if active.returncode == 0 and active.stdout.strip() == 'active':
        return BridgeTestStatus('ready', 'On · tests the local AI every 6 hours')
    return BridgeTestStatus(
        'stopped', 'Scheduled but stopped · restart automatic AI tests')


def set_enabled(enabled, runner=subprocess.run):
    try:
        reloaded = runner(
            ['systemctl', '--user', 'daemon-reload'], capture_output=True,
            text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BrowserError(
            'The background service list could not be refreshed.') from exc
    if reloaded.returncode != 0:
        raise BrowserError('The background service list could not be refreshed.')
    command = 'enable' if enabled else 'disable'
    changed = _systemctl(command, runner, ('--now',))
    if changed.returncode != 0:
        action = 'enabled' if enabled else 'stopped'
        raise BrowserError(f'Automatic C64 AI tests could not be {action}.')
    current = status(runner)
    expected = 'ready' if enabled else 'disabled'
    if current.state != expected:
        raise BrowserError('The automatic C64 AI test schedule did not change.')
    return current
