# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Private validated configuration for the paired C64 AI listener."""
from dataclasses import dataclass, field
from contextlib import contextmanager
from functools import wraps
from threading import RLock
import ipaddress
import json
import os
from pathlib import Path
import tempfile

from .ai_gateway import GatewayConfig


_GUARDS_LOCK = RLock()
_GUARDS = {}
_REVISIONS = {}
_UNCHECKED = object()


def _key(path):return str(Path(path).resolve())


@contextmanager
def configuration_guard(path):
    key = _key(path)
    with _GUARDS_LOCK:guard = _GUARDS.setdefault(key, RLock())
    with guard:yield


def guarded_configuration(function):
    @wraps(function)
    def guarded(path, *args, **kwargs):
        with configuration_guard(path):return function(path, *args, **kwargs)
    return guarded


@guarded_configuration
def configuration_revision(path):
    try:content = Path(path).read_bytes()
    except FileNotFoundError:content = None
    return (_REVISIONS.get(_key(path), 0), content)


@dataclass(frozen=True)
class C64BridgeConfig:
    model: str
    host: str
    port: int
    allowed_clients: tuple
    token: str = field(repr=False)


def validate_bridge_config(value):
    if not isinstance(value, dict) or value.get('schema') != 1:
        raise ValueError('Invalid C64 AI bridge setting.')
    model = GatewayConfig('ollama', value.get('model')).model
    host = str(ipaddress.IPv4Address(value.get('host')))
    port = value.get('port')
    clients = value.get('allowed_clients')
    token = value.get('token')
    if (ipaddress.IPv4Address(host).is_unspecified
            or ipaddress.IPv4Address(host).is_multicast):
        raise ValueError('Invalid C64 AI bridge host.')
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Invalid C64 AI bridge port.')
    if (not isinstance(clients, list) or not 1 <= len(clients) <= 4
            or len(set(clients)) != len(clients)):
        raise ValueError('Invalid paired C64U addresses.')
    addresses = tuple(str(ipaddress.IPv4Address(item)) for item in clients)
    if any(ipaddress.IPv4Address(item).is_unspecified
           or ipaddress.IPv4Address(item).is_multicast for item in addresses):
        raise ValueError('Invalid paired C64U address.')
    if (not isinstance(token, str) or not 32 <= len(token) <= 96
            or not token.isascii() or not token.isalnum()
            or token != token.upper()):
        raise ValueError('Invalid C64 AI bridge token.')
    return C64BridgeConfig(model, host, port, addresses, token)


def load_bridge_config(path):
    return validate_bridge_config(json.loads(Path(path).read_text(encoding='utf-8')))


@guarded_configuration
def save_bridge_config(path, config, *, expected_revision=_UNCHECKED, before_publish=None):
    if expected_revision is not _UNCHECKED and configuration_revision(path) != expected_revision:
        raise ValueError("Bridge configuration changed; prepare again.")
    if not isinstance(config, C64BridgeConfig):
        raise ValueError('Invalid C64 AI bridge setting.')
    config = validate_bridge_config({
        'schema': 1, 'model': config.model, 'host': config.host,
        'port': config.port, 'allowed_clients': list(config.allowed_clients),
        'token': config.token,
    })
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.c64-ai-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({
                'schema': 1, 'model': config.model, 'host': config.host,
                'port': config.port,
                'allowed_clients': list(config.allowed_clients),
                'token': config.token,
            }, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        if before_publish is not None:
            before_publish()
            if expected_revision is not _UNCHECKED and configuration_revision(path) != expected_revision:
                raise ValueError('Bridge configuration changed; prepare again.')
        os.replace(temporary, path)
        _REVISIONS[_key(path)] = _REVISIONS.get(_key(path), 0) + 1
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

