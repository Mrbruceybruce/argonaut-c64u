# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Failure-only evidence boundary for future local and cloud AI adapters."""


def failure_evidence(report):
    """Whitelisted, bounded evidence; no credentials or exception messages."""
    if report.get('schema') != 1 or not isinstance(report.get('checks'), list):
        raise ValueError('Unsupported Test Lab report')
    failures = []
    for check in report['checks']:
        if check.get('status') != 'fail':
            continue
        operations = []
        for event in check.get('operations', [])[-20:]:
            operations.append({
                'transport': event.get('transport'),
                'operation': event.get('operation'),
                'target': str(event.get('target', '')).split('?', 1)[0],
                'outcome': event.get('outcome'),
                'error_kind': event.get('error_kind'),
            })
        failures.append({
            'id': check.get('id'),
            'title': check.get('title'),
            'error_kind': check.get('error_kind'),
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
