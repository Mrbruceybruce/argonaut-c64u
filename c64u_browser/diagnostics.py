# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Structured operation events shared by transports, tests, and future tools."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar


LOGGER = logging.getLogger('argonaut.operations')
LOGGER.setLevel(logging.INFO)
_ORIGIN = ContextVar('argonaut_operation_origin', default='device')


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
    if re.fullmatch(r'/v1/files/.+:create_d64', route):
        return '/v1/files/image:create_d64'
    if route.startswith('/v1/configs/'):
        return '/v1/configs/category'
    return '/v1/other'


class PrivateRotatingHandler(RotatingFileHandler):
    """Open every rotated JSONL file with private permissions."""

    def _open(self):
        descriptor = os.open(self.baseFilename,
                             os.O_WRONLY | os.O_APPEND | os.O_CREAT |
                             getattr(os, 'O_NOFOLLOW', 0), 0o600)
        if hasattr(os, 'fchmod'):
            os.fchmod(descriptor, 0o600)
        else:
            os.chmod(self.baseFilename, 0o600)
        return os.fdopen(descriptor, 'a', encoding=self.encoding)

    def filter(self, record):
        event = getattr(record, 'operation_event', None)
        return bool(event and event.get('origin') == 'device')


def enable_private_log(preferences_path, max_bytes=1024 * 1024, backups=2):
    """Keep bounded development-operation events outside Test Lab runs."""
    directory = Path(preferences_path).parent / 'diagnostics'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    path = directory / 'operations.jsonl'
    handler = PrivateRotatingHandler(path, maxBytes=max_bytes,
                                     backupCount=backups)
    handler.setFormatter(JsonEventFormatter())
    LOGGER.addHandler(handler)
    return handler


def disable_private_log(handler):
    if handler is not None:
        LOGGER.removeHandler(handler)
        handler.close()


@contextmanager
def operation_origin(origin):
    if origin not in ('device', 'simulation'):
        raise ValueError('Unsupported operation origin')
    token = _ORIGIN.set(origin)
    try:
        yield
    finally:
        _ORIGIN.reset(token)


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
            'origin': _ORIGIN.get(),
            'transport': transport,
            'operation': operation,
            'target': target,
            'outcome': outcome,
            'error_kind': error_kind,
            'duration_ms': round((time.monotonic() - started) * 1000, 3),
        }
        LOGGER.info('operation', extra={'operation_event': event})
