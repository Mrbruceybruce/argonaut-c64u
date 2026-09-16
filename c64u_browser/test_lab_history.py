# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Private Test Lab run history and deterministic run comparison."""
import json
import hashlib
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone
import re
from uuid import uuid4


MAX_RUNS = 20


def profile_scope_key(profile_id):
    if not isinstance(profile_id, str) or not profile_id:
        raise ValueError('A hardware history scope needs a profile ID.')
    return hashlib.sha256(profile_id.encode('utf-8')).hexdigest()


def validate_report(report):
    """Reject damaged verdicts before they become a comparison baseline."""
    if not isinstance(report, dict) or report.get('schema') != 1:
        raise ValueError('Unsupported Test Lab report')
    checks = report.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('Test Lab report has no checks')
    ids = []
    statuses = set()
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError('Invalid Test Lab check')
        key, status = check.get('id'), check.get('status')
        if (not isinstance(key, str) or
                not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*', key) or
                status not in ('pass', 'fail', 'skip')):
            raise ValueError('Invalid Test Lab check verdict')
        ids.append(key)
        statuses.add(status)
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate Test Lab check IDs')
    expected = 'fail' if 'fail' in statuses else 'skip' if statuses == {'skip'} else 'pass'
    if report.get('status') != expected:
        raise ValueError('Inconsistent Test Lab verdict')
    return report


def compare_reports(previous, current):
    """Compare check verdicts by stable ID; never alter either verdict."""
    validate_report(current)
    if previous is None:
        return None
    validate_report(previous)
    old = {check['id']: check['status'] for check in previous['checks']}
    new = {check['id']: check['status'] for check in current['checks']}
    return {
        'new_failures': sorted(key for key, status in new.items()
                               if status == 'fail' and old.get(key) != 'fail'),
        'resolved': sorted(key for key, status in new.items()
                           if status == 'pass' and old.get(key) == 'fail'),
        'added': sorted(new.keys() - old.keys()),
        'removed': sorted(old.keys() - new.keys()),
    }


class TestLabHistory:
    def __init__(self, preferences_path, profile_id=None):
        base = Path(preferences_path).parent / 'test-lab'
        if profile_id is None:
            self.path = base / 'runs'
        else:
            self.path = base / 'devices' / profile_scope_key(profile_id) / 'runs'

    def most_recent(self, suite=None, include_skips=True):
        if not self.path.exists():
            return None
        for path in sorted(self.path.glob('*.json'), reverse=True):
            try:
                report = json.loads(path.read_text(encoding='utf-8'))
                validate_report(report)
                if ((include_skips or report.get('status') != 'skip')
                        and (suite is None or report.get('suite', 'offline') == suite)):
                    return report
            except (OSError, ValueError, AttributeError):
                continue
        return None

    def latest(self, suite=None):
        return self.most_recent(suite, include_skips=False)

    def verified_pair(self, suite=None):
        """Return the newest two non-skipped reports from this history scope."""
        found = []
        if self.path.exists():
            for path in sorted(self.path.glob('*.json'), reverse=True):
                try:
                    report = json.loads(path.read_text(encoding='utf-8'))
                    validate_report(report)
                    if (report['status'] != 'skip' and
                            (suite is None or report.get('suite', 'offline') == suite)):
                        found.append(report)
                        if len(found) == 2:
                            break
                except (OSError, ValueError, AttributeError):
                    continue
        return tuple((found + [None, None])[:2])

    def save(self, report):
        validate_report(report)
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + uuid4().hex + '.json'
        destination = self.path / name
        fd, temporary = tempfile.mkstemp(dir=self.path, prefix='.run-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(report, stream, indent=2, sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            for old in sorted(self.path.glob('*.json'), reverse=True)[MAX_RUNS:]:
                old.unlink()
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return destination


def run_with_history(preferences_path, runner, profile_id=None):
    """Keep a useful report even when its private history cannot be saved."""
    report = runner()
    validate_report(report)
    history = TestLabHistory(preferences_path, profile_id)
    try:
        previous = history.latest(report.get('suite', 'offline'))
        comparison = compare_reports(previous, report)
        history.save(report)
        saved = True
    except OSError:
        comparison, saved = None, False
    return {'report': report, 'comparison': comparison, 'saved': saved}
