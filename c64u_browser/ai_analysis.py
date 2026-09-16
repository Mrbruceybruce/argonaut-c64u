# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Failure-only evidence boundary for future local and cloud AI adapters."""
from .diagnostics import rest_target


SAFE_OPERATIONS = {
    'rest': frozenset(('GET', 'PUT', 'POST', 'DELETE')),
    'ftp': frozenset(('list_directory', 'download', 'upload',
                      'upload_new_folder', 'read_remote', 'upload_flash',
                      'replace_file', 'file_mkdir', 'file_rename',
                      'file_delete', 'file_unknown')),
    'dma': frozenset(('mount_and_run', 'send_text')),
    'local': frozenset(('replace_file',)),
}
SAFE_TARGETS = {
    'ftp': frozenset(('directory', 'file', 'entry')),
    'dma': frozenset(('disk', 'keyboard')),
    'local': frozenset(('file',)),
}
SAFE_ERROR_KINDS = frozenset((
    'authentication', 'network', 'host', 'api', 'ftp', 'identity',
    'BrowserError', 'UploadFailure', 'AssertionError', 'ValueError',
    'OSError', 'EOFError', 'TimeoutError', 'UnicodeError',
))


def safe_operation(event):
    transport = event.get('transport')
    if not isinstance(transport, str) or transport not in SAFE_OPERATIONS:
        transport = 'other'
    operation = event.get('operation')
    if (not isinstance(operation, str) or
            operation not in SAFE_OPERATIONS.get(transport, ())):
        operation = 'other'
    target = event.get('target')
    if transport == 'rest':
        target = rest_target(target)
    elif (not isinstance(target, str) or
          target not in SAFE_TARGETS.get(transport, ())):
        target = 'other'
    outcome = event.get('outcome')
    if outcome not in ('ok', 'error'):
        outcome = 'other'
    error_kind = event.get('error_kind')
    if error_kind is not None and (not isinstance(error_kind, str) or
                                   error_kind not in SAFE_ERROR_KINDS):
        error_kind = 'other'
    return {'transport': transport, 'operation': operation, 'target': target,
            'outcome': outcome, 'error_kind': error_kind}


def failure_evidence(report):
    """Whitelisted, bounded evidence; no credentials or exception messages."""
    if report.get('schema') != 1 or not isinstance(report.get('checks'), list):
        raise ValueError('Unsupported Test Lab report')
    failures = []
    for check in report['checks']:
        if not isinstance(check, dict):
            continue
        if check.get('status') != 'fail':
            continue
        operations = []
        events = check.get('operations', [])
        if isinstance(events, list):
            for event in events[-20:]:
                if isinstance(event, dict):
                    operations.append(safe_operation(event))
        error_kind = check.get('error_kind')
        if error_kind is not None and (not isinstance(error_kind, str) or
                                       error_kind not in SAFE_ERROR_KINDS):
            error_kind = 'other'
        failures.append({
            'id': check.get('id'),
            'title': check.get('title'),
            'error_kind': error_kind,
            'operations': operations,
        })
    return {'schema': 1, 'failures': failures}


def analyze_failures(report, adapter):
    """Ask an adapter for a diagnosis; its output cannot change the report."""
    evidence = failure_evidence(report)
    if not evidence['failures']:
        return {'schema': 1, 'status': 'no_failures', 'diagnosis': None,
                'check_ids': []}
    diagnosis = adapter(evidence)
    if not isinstance(diagnosis, str):
        raise TypeError('AI adapter must return text')
    return {'schema': 1, 'status': 'analyzed', 'diagnosis': diagnosis[:8000],
            'check_ids': [failure['id'] for failure in evidence['failures']]}
