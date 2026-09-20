# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Structured deterministic result for the deployed C64 AI bridge probe."""
import argparse
import json
from pathlib import Path
import sys

from . import development
from .c64_ai_bridge_control import probe_bridge
from .c64_ai_bridge_cli import default_config_path
from .platform_support import config_base
from .test_lab import Check, run_checks
from .test_lab_history import run_with_history


def run_bridge_checks(path, prober=probe_bridge):
    report = run_checks((Check(
        'bridge.end_to_end', 'End-to-end local C64 AI bridge',
        lambda: prober(path)),))
    report['suite'] = 'bridge'
    return report


def default_preferences_path():
    app = 'argonaut-development' if development.enabled() else 'argonaut'
    return config_base() / app / 'config.json'


def main(argv=None, stdout=None, stderr=None):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = argparse.ArgumentParser(
        description='Run the structured C64 AI bridge readiness check.')
    parser.add_argument('--config', type=Path, default=default_config_path())
    parser.add_argument('--preferences', type=Path,
                        default=default_preferences_path())
    args = parser.parse_args(argv)
    try:
        result = run_with_history(
            args.preferences, lambda: run_bridge_checks(args.config))
    except (OSError, ValueError, TypeError):
        print('Bridge readiness result could not be recorded.', file=stderr)
        return 3
    print(json.dumps({
        'schema': 1, 'report': result['report'],
        'comparison': result['comparison'], 'saved': result['saved'],
    }, sort_keys=True), file=stdout)
    return {'pass': 0, 'fail': 1, 'skip': 2}[result['report']['status']]


if __name__ == '__main__':
    raise SystemExit(main())
