# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Structured operation events shared by transports, tests, and future tools."""
import json
import logging
import time
from contextlib import contextmanager


LOGGER = logging.getLogger('argonaut.operations')
LOGGER.setLevel(logging.INFO)


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
