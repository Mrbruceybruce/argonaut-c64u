# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Structured deterministic result for the deployed C64 AI bridge probe."""

from .c64_ai_bridge_control import probe_bridge
from .test_lab import Check, run_checks


def run_bridge_checks(path, prober=probe_bridge):
    report = run_checks((Check(
        'bridge.end_to_end', 'End-to-end local C64 AI bridge',
        lambda: prober(path)),))
    report['suite'] = 'bridge'
    return report
