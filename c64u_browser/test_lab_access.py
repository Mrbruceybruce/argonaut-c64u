# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Opt-in stable Test Lab access and background shutdown."""
import subprocess
import sys

from . import development


TIMERS = (
    'argonaut-c64-ai-health.timer',
    'argonaut-c64-ai-test.timer',
    'argonaut-test-lab-fleet.timer',
)


def enabled(preferences):
    return (development.enabled() or
            preferences.app_options.get('developer_mode') is True)


def stop_background(runner=subprocess.run, platform=None):
    """Best-effort stop of Argonaut timers when stable Developer Mode is off."""
    platform = sys.platform if platform is None else platform
    if not platform.startswith('linux'):
        return True
    stopped = True
    for timer in TIMERS:
        try:
            result = runner(
                ['systemctl', '--user', 'disable', '--now', timer],
                capture_output=True, text=True, timeout=8, check=False)
            stopped = result.returncode == 0 and stopped
        except (OSError, subprocess.SubprocessError):
            stopped = False
    return stopped
