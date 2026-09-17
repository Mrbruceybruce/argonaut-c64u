# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Map private per-profile Test Lab history to local Development UI choices."""
from .test_lab_history import TestLabHistory, compare_reports


def saved_hardware_results(preferences):
    records = []
    for profile in preferences.profiles:
        if not (profile.device_id or profile.device_mac):
            continue
        history = TestLabHistory(preferences.path, profile.id)
        runs = history.recent_runs('hardware')
        verified, previous_verified = history.verified_pair('hardware', runs=runs)
        records.append({'profile': profile,
                        'recent': runs[0]['report'] if runs else None,
                        'verified': verified,
                        'previous_verified': previous_verified,
                        'runs': runs})
    return records


def saved_suite_result(preferences, suite):
    """Load one unscoped suite for a UI that must reopen unattended results."""
    history = TestLabHistory(preferences.path)
    runs = history.recent_runs(suite)
    verified, previous_verified = history.verified_pair(suite, runs=runs)
    return {
        'recent': runs[0]['report'] if runs else None,
        'verified': verified,
        'previous_verified': previous_verified,
        'runs': runs,
    }


def saved_comparison(record, report):
    """A skipped saved run cannot prove any check recovered."""
    if report['status'] == 'skip':
        return None
    for index, item in enumerate(record['runs']):
        if item['report'] is report:
            previous = next((older['report'] for older in record['runs'][index + 1:]
                             if older['report']['status'] != 'skip'), None)
            return compare_reports(previous, report)
    return None


def saved_run_label(item, index):
    saved_at = item['saved_at']
    date = (saved_at.astimezone().strftime('%Y-%m-%d %I:%M %p')
            if saved_at is not None else f'Saved run {index + 1}')
    return f"{date} — {item['report']['status'].capitalize()}"


def saved_status(record):
    recent = record['recent']
    verified = record['verified']
    if recent is None:
        return 'No saved run'
    if recent['status'] == 'skip' and verified is not None:
        return f"Skipped · last verified {verified['status']}"
    return recent['status'].capitalize()


def preferred_record(records, selected_id):
    for index, record in enumerate(records):
        if (record['recent'] and record['recent']['status'] == 'fail' or
                record['verified'] and record['verified']['status'] == 'fail'):
            return index
    for index, record in enumerate(records):
        if record['profile'].id == selected_id:
            return index
    return 0
