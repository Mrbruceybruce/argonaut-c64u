# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Intentional offline failure for exercising the separate AI diagnosis path."""
from .diagnostics import operation_origin
from .simulated_ftp_reads import MemoryReads
from .test_lab import Check, run_checks


def _refused_ftp_login():
    MemoryReads(failure='authentication-failed').attach().list_directory('/')


def run_diagnosis_probe():
    """Ordinary transport code marks this fixture failed; no device is contacted."""
    with operation_origin('simulation'):
        report = run_checks((Check(
            'probe.ftp_authentication', 'Simulated C64U FTP login refusal',
            _refused_ftp_login),))
    report['suite'] = 'diagnosis_probe'
    return report
