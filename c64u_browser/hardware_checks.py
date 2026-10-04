# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Opt-in, read-only checks for the already connected C64 Ultimate."""

from .test_lab import Check, SkipCheck, require, run_checks


def run_hardware_checks(client, profile):
    """Existing GUI route: the connected compatibility service is managed."""
    def identity_info():
        info = client.test_connection()
        profile.verify_identity(info, require_bound=True)
        return info
    return _run_checks(profile, identity_info,
        lambda: client.read_drives(), lambda: client.list_directory('/'),
        lambda: client.read_about('version'), connected=client is not None)


def run_core_hardware_checks(core, profile, entered_password=''):
    """Connect in identity; acquire the first FTP lease only in storage."""
    from .api import BrowserError, ConnectionFailure
    session = [None]
    def core_call(operation):
        try:
            return operation()
        except BrowserError as exc:
            # Core/scheduler use code; the collector's public contract is kind.
            code = getattr(exc, 'code', None)
            if code is None:raise
            kind = code if code in ('identity', 'authentication', 'host', 'network', 'session') else 'connection'
            raise ConnectionFailure(kind, 'Core diagnostic read failed.') from None
    def identity_info():
        result = core_call(lambda: core.connect(profile, entered_password=entered_password,
            require_bound=True, bind_identity=False, persist=False,
            remember=False, initial_browse=False))
        session[0] = core.device_session()
        return result.device_info
    return _run_checks(profile, identity_info,
        lambda: core_call(lambda: core.diagnostic_rest(session[0], 'drives')),
        lambda: core_call(lambda: core.diagnostic_listing(session[0], '/')),
        lambda: core_call(lambda: core.diagnostic_rest(session[0], 'version')))


def _run_checks(profile, identity_info, drives_read, storage_read, version_read, *, connected=True):
    state = {'verified': False, 'version': None}

    def verified():
        if not state['verified']:
            raise SkipCheck('identity_prerequisite')

    def identity():
        if not connected or profile is None:
            raise SkipCheck('not_connected')
        if not (profile.device_id or profile.device_mac):
            raise SkipCheck('identity_unbound')
        info = identity_info()
        require(bool(info['info']['firmware_version']), 'Firmware version was empty')
        require(bool(info['version']['version']), 'API version was empty')
        state['version'] = info['version']['version']
        state['verified'] = True

    def drives():
        verified()
        result = drives_read()
        require(isinstance(result, dict), 'Drive status was not a mapping')
        require(set(result).issubset({'a', 'b'}), 'Drive status contained unknown drives')
        for item in result.values():
            require(type(item.get('enabled')) is bool, 'Drive enabled field was not Boolean')

    def storage_listing():
        verified()
        actual, entries = storage_read()
        require(isinstance(actual, str) and actual.startswith('/'),
                'FTP returned a nonabsolute directory')
        require(isinstance(entries, list), 'FTP entries were not a list')
        for entry in entries:
            require(isinstance(entry.name, str) and isinstance(entry.kind, str),
                    'FTP entry fields were unsupported')

    def version_stability():
        verified()
        result = version_read()
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
