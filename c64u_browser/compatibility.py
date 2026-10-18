# SPDX-License-Identifier: GPL-3.0-or-later
"""Ephemeral REST observations. None of these values grant command authority."""
from dataclasses import dataclass
from enum import Enum
import re
from urllib.error import HTTPError, URLError
from .api import BrowserError, ConnectionFailure
from .configuration import Configuration


class CapabilityState(str, Enum):
    OBSERVED = 'observed'
    UNKNOWN = 'unknown'
    UNQUALIFIED = 'unqualified'


class InspectionStatus(str, Enum):
    AVAILABLE = 'Available'
    UNSUPPORTED = 'Unsupported'
    AUTHENTICATION = 'Authentication required'
    COMMUNICATION = 'Communication failed'
    INVALID = 'Invalid response'
    UNKNOWN = 'Unknown'


def classify_failure(error, *, kind=None):
    """Translate structured transport evidence, never exception-message text."""
    if isinstance(error, ConnectionFailure):
        kind = error.kind
    status = {
        'unsupported_api': InspectionStatus.UNSUPPORTED,
        'authentication': InspectionStatus.AUTHENTICATION,
        'network': InspectionStatus.COMMUNICATION,
        'host': InspectionStatus.COMMUNICATION,
        'malformed': InspectionStatus.INVALID,
    }.get(kind)
    if status is not None:
        return status
    # The shared REST transport retains the original exception as its cause.
    evidence = error.__cause__ if isinstance(error, ConnectionFailure) and kind == 'api' else error
    if isinstance(evidence, HTTPError):
        if evidence.code in (404, 405, 501):
            return InspectionStatus.UNSUPPORTED
        if evidence.code in (401, 403):
            return InspectionStatus.AUTHENTICATION
        return InspectionStatus.UNKNOWN
    if isinstance(evidence, (URLError, OSError)):
        return InspectionStatus.COMMUNICATION
    if isinstance(evidence, RecursionError) or (
            isinstance(error, ConnectionFailure) and kind == 'api'
            and isinstance(evidence, ValueError)):
        return InspectionStatus.INVALID
    return InspectionStatus.UNKNOWN


@dataclass(frozen=True)
class Observation:
    name: str
    state: CapabilityState
    detail: str = ''
    status: InspectionStatus = InspectionStatus.UNKNOWN
    attempted: bool = False


@dataclass(frozen=True)
class CompatibilityResult:
    protocol: CapabilityState
    identity: tuple
    api_version: str
    categories: tuple
    observations: tuple
    operations: tuple

    def description(self):
        identity = dict(self.identity)
        return '\n'.join((
            'Ultimate REST interface recognized. Operational features require qualification.',
            'Product: ' + identity['product'],
            'Firmware: ' + identity['firmware_version'] + ' · API: ' + self.api_version,
            'Configuration categories: ' + (', '.join(self.categories) or 'Unavailable or unknown'),
            *(row.name + ': ' + row.status.value + (' · ' + row.detail if row.detail else '')
              for row in self.observations),
            'Unqualified by this inspection: ' + ', '.join(row.name for row in self.operations),
        ))


def validate_protocol(result):
    """Require both Ultimate v1 envelopes; product spelling is not a gate."""
    for route in ('version', 'info'):
        data = result.get(route)
        if not isinstance(data, dict) or data.get('errors') != []:
            raise ConnectionFailure('malformed', 'Malformed Ultimate REST information response.')
    info, version = result['info'], result['version'].get('version')
    for key in ('product', 'firmware_version'):
        value = info.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 256 or any(ord(c) < 32 for c in value):
            raise ConnectionFailure('malformed', 'Missing or malformed Ultimate identity fields.')
    for key in ('fpga_version', 'core_version', 'hostname', 'unique_id'):
        if key in info and (not isinstance(info[key], str) or len(info[key]) > 256
                           or any(ord(c) < 32 for c in info[key])):
            raise ConnectionFailure('malformed', 'Malformed optional Ultimate identity field.')
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]+\.[0-9]+', version):
        raise ConnectionFailure('malformed', 'Malformed Ultimate REST API version.')
    # UC-1 qualifies the documented/observed API contract only, not future versions.
    if version != '0.1':
        raise ConnectionFailure('unsupported_api', 'Unsupported Ultimate REST API version: ' + version)
    return result


class InspectionReader:
    """Expose only bounded GET routes to the existing metadata parser."""
    def __init__(self, client, identity):
        self._client, self._identity = client, identity

    def read_configuration(self, category=None):
        data = self._client.read_configuration(category)
        if not isinstance(data, dict):
            raise ConnectionFailure('malformed', 'Invalid configuration response.')
        if category is None:
            categories = data.get('categories')
            if (not isinstance(categories, list) or len(categories) > 64
                    or not all(isinstance(c, str) and c for c in categories)):
                raise ConnectionFailure('malformed', 'Invalid or excessive category enumeration.')
        else:
            items = data.get(category)
            if not isinstance(items, dict) or len(items) > 256:
                raise ConnectionFailure('malformed', 'Invalid or excessive configuration metadata.')
        return data

    def test_connection(self):
        return self._identity


def inspect(client, identity):
    config = Configuration(InspectionReader(client, identity))
    categories, observations = (), []
    try:
        categories = tuple(config.categories())
        if len(categories) > 64 or any(len(c) > 128 or any(ord(ch) < 32 for ch in c) for c in categories):
            raise ConnectionFailure('malformed', 'Invalid or excessive category enumeration.')
    except Exception as exc:
        categories = ()
        observations.append(Observation('Configuration enumeration', CapabilityState.UNKNOWN,
                                        status=classify_failure(exc), attempted=True))
    else:
        observations.append(Observation('Configuration enumeration', CapabilityState.OBSERVED,
                                        status=InspectionStatus.AVAILABLE, attempted=True))
    # At most four metadata requests, 256 settings each, 64 KiB per response.
    inspected = 0
    for inspected, category in enumerate(categories[:4], 1):
        try:
            rows = config.settings(category)
            available = sum(row.current != 'Unavailable' for row in rows)
            observations.append(Observation(category, CapabilityState.OBSERVED,
                str(available) + ' readable metadata entries; no write qualification',
                InspectionStatus.AVAILABLE, attempted=True))
        except Exception as exc:
            status = classify_failure(exc)
            observations.append(Observation(category, CapabilityState.UNKNOWN, status=status, attempted=True))
            # Preserve the previous stop-on-authentication policy without losing
            # earlier observations or adding requests after the rejected one.
            if (status == InspectionStatus.AUTHENTICATION
                    or not isinstance(exc, (BrowserError, RecursionError))):
                break
    for category in categories[inspected:]:
        observations.append(Observation(category, CapabilityState.UNKNOWN, 'Not inspected'))
    identity_fields = tuple((k, v) for k, v in identity['info'].items()
                            if k in ('product', 'firmware_version', 'fpga_version', 'core_version', 'hostname', 'unique_id'))
    return CompatibilityResult(CapabilityState.OBSERVED, identity_fields,
        identity['version']['version'], categories, tuple(observations),
        tuple(Observation(name, CapabilityState.UNQUALIFIED) for name in (
            'Reset/Reboot', 'Memory/DMA', 'Cartridge execution', 'SID playback',
            'Streaming', 'Drive mutation', 'Configuration writes', 'FTP mutation/publication')))
