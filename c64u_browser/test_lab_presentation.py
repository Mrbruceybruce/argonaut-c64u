# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Plain-text presentation of deterministic Test Lab reports."""


def summary(report):
    checks = report['checks']
    passed = sum(check['status'] == 'pass' for check in checks)
    failed = sum(check['status'] == 'fail' for check in checks)
    skipped = sum(check['status'] == 'skip' for check in checks)
    return f'{passed} passed · {failed} failed · {skipped} skipped · {len(checks)} total'


def comparison_summary(comparison):
    if comparison is None:
        return 'First saved run; no previous run to compare.'
    return (f"{len(comparison['new_failures'])} new failures · "
            f"{len(comparison['resolved'])} resolved · "
            f"{len(comparison['added'])} added · "
            f"{len(comparison['removed'])} removed")


def check_details(check):
    lines = [check['title'], f"Result: {check['status'].upper()}",
             f"Check ID: {check['id']}",
             f"Duration: {check['duration_ms']:.3f} ms"]
    if check['error_kind']:
        label = 'Skip category' if check['status'] == 'skip' else 'Failure category'
        lines.append(f"{label}: {check['error_kind']}")
    lines.append('')
    if not check['operations']:
        lines.append('No C64U operations in this check.')
    else:
        lines.append('C64U operations:')
        for event in check['operations']:
            line = (f"{event['transport'].upper()} {event['operation']} "
                    f"{event['target']} · {event['outcome']} · "
                    f"{event['duration_ms']:.3f} ms")
            if event['error_kind']:
                line += f" · {event['error_kind']}"
            lines.append(line)
    return '\n'.join(lines)
