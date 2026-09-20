# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Desktop alerts for changed fleet failures; never influence test verdicts."""
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from . import development
from .platform_support import config_base
from .ai_gateway import GatewayError
from .test_lab_auto_analysis import (
    CACHE_NAME, CONFIG_NAME, alert_excerpt, diagnose_saved_fleet, mark_notified,
)
from .test_lab_fleet import main as run_fleet


STATE_NAME = 'alert-state.json'
FAILURE_ID = re.compile(r'[a-z0-9][a-z0-9_.-]*\Z')
PROFILE_KEY = re.compile(r'[0-9a-f]{16}\Z')


def failure_set(output, exit_code):
    """Use only opaque profile keys and stable deterministic check IDs."""
    if exit_code == 3 and not output:
        return ('setup',)
    try:
        fleet = json.loads(output)
    except (TypeError, ValueError):
        return ('setup',) if exit_code == 3 else ()
    if not isinstance(fleet, dict) or fleet.get('schema') != 1:
        return ('setup',) if exit_code == 3 else ()
    failures = set()
    for profile in fleet.get('profiles', []):
        if not isinstance(profile, dict):
            continue
        key = profile.get('key')
        if not isinstance(key, str) or not PROFILE_KEY.fullmatch(key):
            continue
        if profile.get('exit_code') == 3:
            failures.add('setup:' + key)
        report = profile.get('result')
        if not isinstance(report, dict):
            continue
        for check in report.get('checks', []):
            if not isinstance(check, dict) or check.get('status') != 'fail':
                continue
            check_id = check.get('id')
            if isinstance(check_id, str) and FAILURE_ID.fullmatch(check_id):
                failures.add(key + ':' + check_id)
    if exit_code == 3 and not failures:
        failures.add('setup')
    return tuple(sorted(failures))


def merge_unconfirmed(previous, current, output, exit_code):
    """A skipped or absent check cannot prove that an earlier failure recovered."""
    failures = set(current)
    try:
        fleet = json.loads(output)
        profiles = {item['key']: item for item in fleet['profiles']
                    if isinstance(item, dict) and
                    isinstance(item.get('key'), str) and
                    PROFILE_KEY.fullmatch(item['key'])}
    except (TypeError, ValueError, KeyError, AttributeError):
        profiles = {}
    for item in previous:
        if item in failures:
            continue
        if item == 'setup':
            if exit_code not in (0, 1):
                failures.add(item)
            continue
        if item.startswith('setup:'):
            profile = profiles.get(item.split(':', 1)[1])
            if not profile or profile.get('exit_code') not in (0, 1):
                failures.add(item)
            continue
        key, check_id = item.split(':', 1)
        profile = profiles.get(key)
        report = profile.get('result') if profile else None
        checks = (report.get('checks', []) if isinstance(report, dict) and
                  profile.get('exit_code') in (0, 1) else [])
        if not any(isinstance(check, dict) and check.get('id') == check_id and
                   check.get('status') == 'pass' for check in checks):
            failures.add(item)
    return tuple(sorted(failures))


def read_state(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        failures = value['failures']
        if (value.get('schema') == 1 and isinstance(failures, list) and
                all(isinstance(item, str) and
                    (item == 'setup' or re.fullmatch(r'setup:[0-9a-f]{16}', item) or
                     re.fullmatch(r'[0-9a-f]{16}:[a-z0-9][a-z0-9_.-]*', item))
                    for item in failures)):
            return tuple(sorted(set(failures)))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return ()


def save_state(path, failures):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.alert-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'schema': 1, 'failures': list(failures)}, stream,
                      sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def desktop_notify(title, body):
    executable = shutil.which('notify-send')
    if not executable:
        return False
    try:
        result = subprocess.run([executable, '--app-name=Argonaut Test Lab',
                                 title, body], timeout=5,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, check=False)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def alert_text(previous, current):
    qualifier = 'Development ' if development.enabled() else ''
    app_name = 'Argonaut Development' if development.enabled() else 'Argonaut'
    if not current:
        return ('Argonaut Test Lab recovered',
                f'All saved {qualifier}C64U checks passed again.')
    count = len({item.split(':', 1)[0] for item in current})
    if previous:
        title = 'Argonaut Test Lab failures changed'
    else:
        title = 'Argonaut Test Lab needs attention'
    noun = 'connection' if count == 1 else 'connections'
    return title, (f'{count} {qualifier}C64U {noun} need review. '
                   f'Open {app_name}’s Test Lab for the saved results.')


def main(argv=None, stdin=None, stdout=None, stderr=None, *,
         state_path=None, notify=desktop_notify):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    buffer = io.StringIO()
    code = run_fleet(argv, stdin=stdin, stdout=buffer, stderr=stderr)
    output = buffer.getvalue()
    stdout.write(output)
    path = (Path(state_path) if state_path is not None else
            config_base() / development.config_name() / 'test-lab' / STATE_NAME)
    previous = read_state(path)
    current = merge_unconfirmed(previous, failure_set(output, code), output, code)
    diagnosis = None
    if code == 1:
        try:
            diagnosis = diagnose_saved_fleet(
                output, path.parent / CONFIG_NAME, path.parent / CACHE_NAME)
        except (GatewayError, OSError, ValueError, TypeError):
            print('Local AI diagnosis unavailable; saved test verdict is unchanged.',
                  file=stderr)
    changed = current != previous
    diagnosis_notice = bool(diagnosis and current and not diagnosis.notified)
    if changed or diagnosis_notice:
        if current or previous:
            title, body = alert_text(previous, current)
            if diagnosis is not None and current:
                body += ' Local AI: ' + alert_excerpt(diagnosis)
            if diagnosis_notice and not changed:
                title = 'Argonaut Test Lab local diagnosis ready'
            if not notify(title, body):
                print('Test Lab desktop alert unavailable; verdict and report are saved.',
                      file=stderr)
                return code
        if diagnosis_notice:
            try:
                mark_notified(path.parent / CACHE_NAME, diagnosis)
            except OSError:
                print('Local AI alert state could not be saved; verdict is unchanged.',
                      file=stderr)
    if changed:
        try:
            save_state(path, current)
        except OSError:
            print('Test Lab alert state could not be saved; verdict is unchanged.',
                  file=stderr)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
