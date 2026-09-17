# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Changed-state alerts for the deterministic end-to-end C64 AI test."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from .c64_ai_bridge_check import (
    default_preferences_path, run_bridge_checks,
)
from .c64_ai_bridge_cli import default_config_path
from .test_lab_alert import desktop_notify
from .test_lab_history import run_with_history


STATE_NAME = 'c64-ai-test-state.json'
STATES = frozenset({'pass', 'fail', 'skip'})


def read_state(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        state = value.get('state')
        if value.get('schema') == 1 and state in STATES:
            return state
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def save_state(path, state):
    if state not in STATES:
        raise ValueError('Invalid automatic C64 AI test state.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.c64-ai-test-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'schema': 1, 'state': state}, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def alert_text(previous, current):
    if current == 'pass':
        return ('Argonaut C64 AI test recovered',
                'The end-to-end local AI response test passes again.')
    if current == 'skip':
        body = ('The end-to-end local AI response test could not complete. '
                'Open Test Lab for the saved result.')
    else:
        body = ('The end-to-end local AI response test failed. '
                'Open Test Lab for the saved result.')
    title = ('Argonaut C64 AI test changed' if previous
             else 'Argonaut C64 AI test needs attention')
    return title, body


def check(config_path, preferences_path, state_path, notify=desktop_notify,
          runner=run_bridge_checks):
    result = run_with_history(
        preferences_path, lambda: runner(config_path))
    current = result['report']['status']
    previous = read_state(state_path)
    changed = current != previous
    if changed and not (previous is None and current == 'pass'):
        title, body = alert_text(previous, current)
        if not notify(title, body):
            return result, False
    if changed:
        save_state(state_path, current)
    return result, True


def main(argv=None, stdout=None, stderr=None, notify=desktop_notify):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = argparse.ArgumentParser(
        description='Run the C64 AI bridge test and notify on verdict changes.')
    parser.add_argument('--config', type=Path, default=default_config_path())
    parser.add_argument('--preferences', type=Path,
                        default=default_preferences_path())
    parser.add_argument('--state', type=Path)
    args = parser.parse_args(argv)
    state = args.state or args.config.parent / STATE_NAME
    try:
        result, alert_saved = check(
            args.config, args.preferences, state, notify)
    except (OSError, ValueError, TypeError):
        print('Automatic C64 AI test result could not be recorded.', file=stderr)
        return 3
    print(json.dumps({
        'schema': 1, 'report': result['report'],
        'comparison': result['comparison'], 'saved': result['saved'],
    }, sort_keys=True), file=stdout)
    if not alert_saved:
        print('C64 AI test alert unavailable; the test will run again.',
              file=stderr)
    return {'pass': 0, 'fail': 1, 'skip': 2}[result['report']['status']]


if __name__ == '__main__':
    raise SystemExit(main())
