# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Map private per-profile Test Lab history to local Development UI choices."""
from .test_lab_history import TestLabHistory


def saved_hardware_results(preferences):
    records = []
    for profile in preferences.profiles:
        if not (profile.device_id or profile.device_mac):
            continue
        history = TestLabHistory(preferences.path, profile.id)
        records.append({'profile': profile,
                        'recent': history.most_recent('hardware'),
                        'verified': history.latest('hardware')})
    return records


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
