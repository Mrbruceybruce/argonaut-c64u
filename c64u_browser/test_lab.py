# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Deterministic checks and structured results for a future Developer Mode UI."""
from dataclasses import dataclass
import logging
import re
import threading
import time

from .api import BrowserError, UltimateClient, parse_list
from .diagnostics import LOGGER, operation_origin
from .disk_image import D64Image, D71Image, D81Image, sectors_on_track, sectors_on_d71_track
from .disk_image_edit import D64EditSession


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


def _check_d64_parser():
    data = bytearray(174848)
    header = sum(sectors_on_track(track) for track in range(1, 18)) * 256
    directory = header + 256
    data[header:header + 3] = bytes((18, 1, 0x41))
    data[header + 0x90:header + 0xa0] = b'ARGONAUT' + b'\xa0' * 8
    data[header + 0xa2:header + 0xa4] = b'64'
    data[header + 0xa5:header + 0xa7] = b'2A'
    data[directory:directory + 2] = bytes((0, 255))
    entry = directory + 2
    data[entry:entry + 3] = bytes((0x82, 1, 0))
    data[entry + 3:entry + 19] = b'HELLO' + b'\xa0' * 11
    data[entry + 28:entry + 30] = bytes((1, 0))
    data[0:5] = bytes((0, 4, 1, 8, 0))
    image = D64Image(data)
    parsed = image.directory()
    require((parsed.disk_name, parsed.disk_id, parsed.dos_type) ==
            ('ARGONAUT', '64', '2A'), 'D64 header fields differed')
    require(len(parsed.entries) == 1 and
            (parsed.entries[0].name, parsed.entries[0].file_type,
             parsed.entries[0].blocks) == ('HELLO', 'PRG', 1),
            'D64 flat directory entry differed')
    require(image.read_file(parsed.entries[0]) == b'\x01\x08\x00',
            'D64 file chain differed')
    validation = image.validate()
    require(validation.standard_compatible and validation.entries_checked == 1,
            'D64 standard structure validation differed')
    source = image.source_bytes
    edit = D64EditSession(image)
    edit.rename(parsed.entries[0], 'RENAMED')
    require(edit.image.directory().entries[0].name == 'RENAMED',
            'Staged D64 rename differed')
    require(edit.validated_bytes() != source and image.source_bytes == source,
            'Staged D64 edit changed its source image')


def _check_d71_parser():
    data = bytearray(349696)
    header = sum(sectors_on_d71_track(track) for track in range(1, 18)) * 256
    directory = header + 256
    side_two_file = sum(sectors_on_d71_track(track) for track in range(1, 36)) * 256
    data[header:header + 4] = bytes((18, 1, 0x41, 0x80))
    data[header + 0x90:header + 0xa0] = b'ARGONAUT' + b'\xa0' * 8
    data[header + 0xa2:header + 0xa4] = b'71'
    data[header + 0xa5:header + 0xa7] = b'2A'
    data[directory:directory + 2] = bytes((0, 255))
    entry = directory + 2
    data[entry:entry + 3] = bytes((0x82, 36, 0))
    data[entry + 3:entry + 19] = b'SIDE TWO' + b'\xa0' * 8
    data[entry + 28:entry + 30] = bytes((1, 0))
    data[side_two_file:side_two_file + 5] = bytes((0, 4, 1, 8, 0))
    image = D71Image(data)
    parsed = image.directory()
    require((parsed.disk_name, parsed.disk_id, parsed.geometry.tracks) ==
            ('ARGONAUT', '71', 70), 'D71 header or geometry differed')
    require(len(parsed.entries) == 1 and parsed.entries[0].name == 'SIDE TWO',
            'D71 flat directory entry differed')
    require(image.read_file(parsed.entries[0]) == b'\x01\x08\x00',
            'D71 second-side file chain differed')
    validation = image.validate()
    require(validation.standard_compatible and validation.entries_checked == 1,
            'D71 double-sided structure validation differed')


def _check_d81_parser():
    data = bytearray(819200)
    header = (40 - 1) * 40 * 256
    first_bam = header + 256
    second_bam = header + 2 * 256
    directory = header + 3 * 256
    data[header:header + 3] = bytes((40, 3, 0x44))
    data[header + 4:header + 20] = b'ARGONAUT' + b'\xa0' * 8
    data[header + 0x16:header + 0x18] = b'81'
    data[header + 0x19:header + 0x1b] = b'3D'
    data[first_bam:first_bam + 6] = bytes((40, 2, 0x44, 0xbb, 0x38, 0x31))
    data[second_bam:second_bam + 6] = bytes((0, 255, 0x44, 0xbb, 0x38, 0x31))
    data[directory:directory + 2] = bytes((0, 255))
    entry = directory + 2
    data[entry:entry + 3] = bytes((0x82, 41, 0))
    data[entry + 3:entry + 19] = b'SIDE TWO' + b'\xa0' * 8
    data[entry + 28:entry + 30] = bytes((1, 0))
    side_two_file = 40 * 40 * 256
    data[side_two_file:side_two_file + 5] = bytes((0, 4, 1, 8, 0))
    image = D81Image(data)
    parsed = image.directory()
    require((parsed.disk_name, parsed.disk_id, parsed.dos_type,
             parsed.geometry.tracks) == ('ARGONAUT', '81', '3D', 80),
            'D81 header or geometry differed')
    require(len(parsed.entries) == 1 and parsed.entries[0].name == 'SIDE TWO',
            'D81 flat root-directory entry differed')
    require(image.read_file(parsed.entries[0]) == b'\x01\x08\x00',
            'D81 second-BAM file chain differed')
    validation = image.validate()
    require(validation.standard_compatible and validation.entries_checked == 1,
            'D81 double-BAM structure validation differed')


DEFAULT_CHECKS = (
    Check('ftp.listing_parser', 'FTP listing parser', _check_listing_parser),
    Check('rest.sid_path_validation', 'SID path validation', _check_sid_path_validation),
    Check('disk.d64_parser', 'D64 parser and staged editor', _check_d64_parser),
    Check('disk.d71_parser', 'Read-only D71 parser', _check_d71_parser),
    Check('disk.d81_parser', 'Read-only D81 parser', _check_d81_parser),
)


def run_default_checks():
    """Offline and simulated checks; safe without a connected C64U."""
    from .simulated_c64u import SIMULATED_CHECKS
    with operation_origin('simulation'):
        report = run_checks(DEFAULT_CHECKS + SIMULATED_CHECKS)
    report['suite'] = 'offline'
    return report


if __name__ == '__main__':
    from .test_lab_cli import main
    raise SystemExit(main())
