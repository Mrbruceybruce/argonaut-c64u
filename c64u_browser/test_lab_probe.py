# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Intentional offline failure for exercising the separate AI diagnosis path."""
import ftplib
from unittest.mock import patch

from .api import UltimateClient
from .diagnostics import operation_origin
from .simulated_c64u import _FTP
from .test_lab import Check, run_checks


def _refused_ftp_login():
    ftp = _FTP(login_error=ftplib.error_perm('530 Simulated login refusal'))
    with patch('ftplib.FTP', return_value=ftp):
        UltimateClient('fixture.invalid').list_directory('/')


def run_diagnosis_probe():
    """Ordinary transport code marks this fixture failed; no device is contacted."""
    with operation_origin('simulation'):
        report = run_checks((Check(
            'probe.ftp_authentication', 'Simulated C64U FTP login refusal',
            _refused_ftp_login),))
    report['suite'] = 'diagnosis_probe'
    return report
