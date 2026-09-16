# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Opt-in, read-only checks for the already connected C64 Ultimate."""

from .test_lab import Check, SkipCheck, require, run_checks


def run_hardware_checks(client, profile):
    """Verify bound identity before making any other device reads."""
    state = {'verified': False, 'version': None}

    def verified_client():
        if not state['verified']:
            raise SkipCheck('identity_prerequisite')
        return client

    def identity():
        if client is None or profile is None:
            raise SkipCheck('not_connected')
        if not (profile.device_id or profile.device_mac):
            raise SkipCheck('identity_unbound')
        info = client.test_connection()
        profile.verify_identity(info, require_bound=True)
        require(bool(info['info']['firmware_version']), 'Firmware version was empty')
        require(bool(info['version']['version']), 'API version was empty')
        state['version'] = info['version']['version']
        state['verified'] = True

    def drives():
        result = verified_client().read_drives()
        require(isinstance(result, dict), 'Drive status was not a mapping')
        require(set(result).issubset({'a', 'b'}), 'Drive status contained unknown drives')
        for item in result.values():
            require(type(item.get('enabled')) is bool, 'Drive enabled field was not Boolean')

    def storage_listing():
        actual, entries = verified_client().list_directory('/')
        require(isinstance(actual, str) and actual.startswith('/'),
                'FTP returned a nonabsolute directory')
        require(isinstance(entries, list), 'FTP entries were not a list')
        for entry in entries:
            require(isinstance(entry.name, str) and isinstance(entry.kind, str),
                    'FTP entry fields were unsupported')

    def version_stability():
        result = verified_client().read_about('version')
        require(result.get('version') == state['version'],
                'API version changed during the run')

    checks = (
        Check('hardware.identity', 'Bound C64U identity and firmware', identity),
        Check('hardware.drives', 'Read-only drive status', drives),
        Check('hardware.storage', 'Read-only FTP root listing', storage_listing),
        Check('hardware.version_stability', 'API version stability', version_stability),
    )
    report = run_checks(checks)
    report['suite'] = 'hardware'
    return report
