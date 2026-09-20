# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Opt-in stable Test Lab access and background service control."""
from pathlib import Path
import subprocess
import sys

from . import development
from .api import BrowserError


TIMERS = (
    'argonaut-c64-ai-health.timer',
    'argonaut-c64-ai-test.timer',
    'argonaut-test-lab-fleet.timer',
)
UNITS = ('argonaut-c64-ai-bridge.service',) + TIMERS


def enabled(preferences):
    return (development.enabled() or
            preferences.app_options.get('developer_mode') is True)


def stop_background(runner=subprocess.run, platform=None):
    """Best-effort stop of Argonaut timers when stable Developer Mode is off."""
    platform = sys.platform if platform is None else platform
    if not platform.startswith('linux'):
        return True
    stopped = True
    for timer in UNITS:
        try:
            result = runner(
                ['systemctl', '--user', 'disable', '--now', timer],
                capture_output=True, text=True, timeout=8, check=False)
            stopped = result.returncode == 0 and stopped
        except (OSError, subprocess.SubprocessError):
            stopped = False
    return stopped


def initialize_stable_automation(marker_path, runner=subprocess.run,
                                 platform=None):
    """Clear pre-1.6 generic enablements before stable automation opt-in."""
    platform = sys.platform if platform is None else platform
    marker_path = Path(marker_path)
    if (development.enabled() or not platform.startswith('linux') or
            marker_path.exists()):
        return False
    for unit in UNITS:
        try:
            result = runner(
                ['systemctl', '--user', 'disable', '--now', unit],
                capture_output=True, text=True, timeout=8, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise BrowserError(
                'Stable background services could not be initialized.') from exc
        if result.returncode != 0:
            raise BrowserError(
                'Stable background services could not be initialized.')
    marker_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker_path.write_text('stable-service-opt-in-v1\n', encoding='utf-8')
    marker_path.chmod(0o600)
    return True
