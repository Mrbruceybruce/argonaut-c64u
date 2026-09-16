# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Changed-state desktop alerts for deterministic C64 AI bridge health."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from .c64_ai_bridge_cli import default_config_path
from .c64_ai_bridge_control import bridge_status
from .test_lab_alert import desktop_notify


STATE_NAME = 'c64-ai-health-state.json'
STATES = frozenset({
    'ready', 'setup', 'error', 'unavailable', 'stopped', 'network_changed',
    'model_unavailable', 'model_missing',
})


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
        raise ValueError('Invalid C64 AI health state.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.c64-ai-health-')
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
    if current == 'ready':
        return ('Argonaut C64 AI recovered',
                'The local bridge and downloaded AI model are ready again.')
    labels = {
        'setup': 'C64 AI setup has not been completed.',
        'error': 'The private C64 AI setting needs attention.',
        'unavailable': 'The local background service manager is unavailable.',
        'stopped': 'The C64 AI bridge is stopped. Open Test Lab to start it.',
        'network_changed': ('The bridge address is unavailable. Reconnect this '
                            'computer to the C64U network, then retry in Test Lab.'),
        'model_unavailable': ('Ollama is unavailable. Start Ollama, then refresh '
                              'the bridge status in Test Lab.'),
        'model_missing': ('The configured local model is not downloaded. Open '
                          'Test Lab for the model name.'),
    }
    title = ('Argonaut C64 AI health changed' if previous
             else 'Argonaut C64 AI needs attention')
    return title, labels[current]


def check(config_path, state_path, notify=desktop_notify):
    status = bridge_status(config_path, check_model=True)
    current = status.state if status.state in STATES else 'error'
    previous = read_state(state_path)
    changed = current != previous
    if changed and not (previous is None and current == 'ready'):
        title, body = alert_text(previous, current)
        if not notify(title, body):
            return status, False
    if changed:
        save_state(state_path, current)
    return status, True


def main(argv=None, stdout=None, stderr=None, notify=desktop_notify):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = argparse.ArgumentParser(
        description='Check the local C64 AI bridge and notify on health changes.')
    parser.add_argument('--config', type=Path, default=default_config_path())
    parser.add_argument('--state', type=Path)
    args = parser.parse_args(argv)
    state = args.state or args.config.parent / STATE_NAME
    try:
        status, saved = check(args.config, state, notify)
    except OSError:
        print('C64 AI health state could not be saved.', file=stderr)
        return 3
    print(json.dumps({
        'schema': 1, 'state': status.state, 'model_status': status.model_status,
        'paired_addresses': len(status.allowed_clients),
    }, sort_keys=True), file=stdout)
    if not saved:
        print('C64 AI desktop alert unavailable; health will be checked again.',
              file=stderr)
    return 0 if status.state == 'ready' else 2 if status.state == 'setup' else 1


if __name__ == '__main__':
    raise SystemExit(main())
