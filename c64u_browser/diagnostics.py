# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Structured operation events shared by transports, tests, and future tools."""
import json
import logging
import re
import time
from contextlib import contextmanager


LOGGER = logging.getLogger('argonaut.operations')
LOGGER.setLevel(logging.INFO)


SAFE_REST_ROUTES = frozenset({
    '/v1/version', '/v1/info', '/v1/drives', '/v1/configs',
    '/v1/configs:save_to_flash', '/v1/machine:reset',
    '/v1/machine:reboot', '/v1/machine:readmem',
    '/v1/runners:sidplay',
    '/v1/streams/video:start', '/v1/streams/video:stop',
    '/v1/streams/audio:start', '/v1/streams/audio:stop',
})


def rest_target(path):
    """Keep only recognized route labels; dynamic path segments are private."""
    route = path.split('?', 1)[0] if isinstance(path, str) else ''
    if route in SAFE_REST_ROUTES:
        return route
    if re.fullmatch(r'/v1/drives/[ab]:(reset|remove|on|off|mount|set_mode)', route):
        return route
    if route.startswith('/v1/configs/'):
        return '/v1/configs/category'
    return '/v1/other'


class JsonEventFormatter(logging.Formatter):
    """Serialize an operation event as one JSON object per line."""

    def format(self, record):
        return json.dumps(record.operation_event, sort_keys=True, separators=(',', ':'))


@contextmanager
def operation_event(transport, operation, target):
    """Emit a sanitized result while preserving the operation's exception."""
    started = time.monotonic()
    outcome, error_kind = 'ok', None
    try:
        yield
    except Exception as exc:
        outcome = 'error'
        error_kind = getattr(exc, 'kind', None) or type(exc).__name__
        raise
    finally:
        event = {
            'schema': 1,
            'transport': transport,
            'operation': operation,
            'target': target,
            'outcome': outcome,
            'error_kind': error_kind,
            'duration_ms': round((time.monotonic() - started) * 1000, 3),
        }
        LOGGER.info('operation', extra={'operation_event': event})
