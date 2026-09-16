# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Deterministic checks and structured results for a future Developer Mode UI."""
from dataclasses import dataclass
import logging
import re
import threading
import time

from .api import BrowserError, UltimateClient, parse_list
from .diagnostics import LOGGER


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    run: object


class SkipCheck(Exception):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)


def require(condition, message):
    """Assertion that remains active under Python's optimized mode."""
    if not condition:
        raise AssertionError(message)


class _EventCollector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events = []
        self.thread = threading.get_ident()

    def emit(self, record):
        event = getattr(record, 'operation_event', None)
        if event is not None and record.thread == self.thread:
            self.events.append(dict(event))


def run_checks(checks):
    """Run checks in order; only their assertions determine pass or fail."""
    checks = tuple(checks)
    ids = [check.id for check in checks]
    if (not ids or any(not isinstance(key, str) or
                       not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*', key) for key in ids)
            or len(ids) != len(set(ids))):
        raise ValueError('Test Lab checks need distinct, valid IDs.')
    results = []
    for check in checks:
        collector = _EventCollector()
        LOGGER.addHandler(collector)
        started = time.monotonic()
        try:
            try:
                check.run()
                status, error_kind = 'pass', None
            except SkipCheck as exc:
                status, error_kind = 'skip', exc.kind
            except Exception as exc:
                status = 'fail'
                error_kind = getattr(exc, 'kind', None) or type(exc).__name__
        finally:
            LOGGER.removeHandler(collector)
        results.append({
            'id': check.id,
            'title': check.title,
            'status': status,
            'error_kind': error_kind,
            'duration_ms': round((time.monotonic() - started) * 1000, 3),
            'operations': collector.events,
        })
    statuses = {result['status'] for result in results}
    overall = 'fail' if 'fail' in statuses else 'skip' if statuses == {'skip'} else 'pass'
    return {'schema': 1, 'status': overall,
        'checks': results}


def _check_listing_parser():
    entry = parse_list('-rw-rw-rw- 1 user ftp 123 Sep 07 12:30 My  game.d64')
    require((entry.name, entry.kind, entry.size) == ('My  game.d64', 'file', 123),
            'FTP listing fields differed')
    try:
        parse_list('malformed listing')
    except BrowserError:
        pass
    else:
        raise AssertionError('Malformed FTP listing was accepted')


def _check_sid_path_validation():
    require(UltimateClient.sid_parameters('/music/song.sid', 2) == {
        'file': '/music/song.sid', 'songnr': 2}, 'SID parameters differed')
    try:
        UltimateClient.sid_parameters('/music/../song.sid')
    except BrowserError:
        pass
    else:
        raise AssertionError('Parent traversal was accepted')


DEFAULT_CHECKS = (
    Check('ftp.listing_parser', 'FTP listing parser', _check_listing_parser),
    Check('rest.sid_path_validation', 'SID path validation', _check_sid_path_validation),
)


def run_default_checks():
    """Offline and simulated checks; safe without a connected C64U."""
    from .simulated_c64u import SIMULATED_CHECKS
    report = run_checks(DEFAULT_CHECKS + SIMULATED_CHECKS)
    report['suite'] = 'offline'
    return report


if __name__ == '__main__':
    from .test_lab_cli import main
    raise SystemExit(main())
