# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Move legacy Development user services to package-scoped unit names."""
import subprocess
from pathlib import Path

from . import development
from .api import BrowserError


LEGACY_UNITS = (
    ('argonaut-c64-ai-bridge.service',
     'argonaut-development-c64-ai-bridge.service'),
    ('argonaut-c64-ai-health.timer',
     'argonaut-development-c64-ai-health.timer'),
    ('argonaut-c64-ai-test.timer',
     'argonaut-development-c64-ai-test.timer'),
    ('argonaut-test-lab-fleet.timer',
     'argonaut-development-test-lab-fleet.timer'),
)


def _run(runner, *args):
    try:
        return runner(['systemctl', '--user', *args], capture_output=True,
                      text=True, timeout=12, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BrowserError(
            'The Development background services could not be migrated.') from exc


def _mark_complete(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text('service-scope-v1\n', encoding='utf-8')
    path.chmod(0o600)


def migrate_legacy_services(marker_path, runner=subprocess.run):
    """Preserve enabled Development services after their one-time rename."""
    marker_path = Path(marker_path)
    if not development.enabled() or marker_path.exists():
        return False
    enabled = []
    for old, new in LEGACY_UNITS:
        is_enabled = _run(runner, 'is-enabled', old).returncode == 0
        definition = _run(runner, 'cat', old)
        is_development = ('argonaut-development' in definition.stdout
                          if definition.returncode == 0 else False)
        if is_enabled and is_development:
            enabled.append((old, new))
    if not enabled:
        _mark_complete(marker_path)
        return False
    for old, _new in enabled:
        _run(runner, 'disable', '--now', old)
    if _run(runner, 'daemon-reload').returncode != 0:
        raise BrowserError(
            'The Development background service list could not be refreshed.')
    for _old, new in enabled:
        if _run(runner, 'enable', '--now', new).returncode != 0:
            raise BrowserError(
                'A Development background service could not be restored.')
    _mark_complete(marker_path)
    return True
