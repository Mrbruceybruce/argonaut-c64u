# SPDX-License-Identifier: GPL-3.0-or-later
"""Authoritative stable-release identity shared by runtime and packaging."""
import re


VERSION = '1.9'
PRODUCT_NAME = 'Argonaut'
PUBLISHER = 'Bruce Marcus'
COPYRIGHT = 'Copyright (C) 2026 Bruce Marcus'


def validate_version(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]*\.[0-9]+', value):
        raise ValueError('Stable release version must be MAJOR.MINOR.')
    return value


validate_version(VERSION)
_major, _minor = (int(part) for part in VERSION.split('.'))
WINDOWS_NUMERIC_VERSION = f'{_major}.{_minor}.0.0'
MAC_BUNDLE_VERSION = str(_major * 10000 + _minor * 100)
TAG = f'v{VERSION}'
RELEASE_TITLE = f'Argonaut {VERSION} — Debian, Windows and macOS'
RELEASE_NOTES = f'packaging/RELEASE-{VERSION}.md'


def artifact_names(version=VERSION):
    if validate_version(version) != VERSION:
        raise ValueError(f'Stable packaging is configured only for {VERSION}.')
    return (
        f'argonaut-c64u_{version}_all.deb',
        f'Argonaut-{version}-Windows-x64-Setup.exe',
        f'Argonaut-{version}-Windows-x64-Portable.zip',
        f'Argonaut-{version}-macOS-AppleSilicon.dmg',
        f'Argonaut-{version}-macOS-AppleSilicon.zip',
        f'Argonaut-{version}-macOS-Intel.dmg',
        f'Argonaut-{version}-macOS-Intel.zip',
        f'argonaut-{version}-source.zip',
    )
