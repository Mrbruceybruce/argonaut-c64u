# SPDX-License-Identifier: GPL-3.0-or-later
"""Private pending configuration, separate from the service-consumed setting."""
import ipaddress
import json
from hashlib import sha256
from pathlib import Path
import os
import secrets
import socket
import stat
import uuid
from dataclasses import replace

from .api import BrowserError
from .c64_ai_bridge_config import (C64BridgeConfig, configuration_guard,
    configuration_revision, load_bridge_config, save_bridge_config)
from .c64_ai_bridge_control import (local_bridge_host, finish_bridge_setup,
                                    pair_bridge_address, activate_bridge)


class ConfigurationChanged(BrowserError):
    code = 'ai-configuration'


def _private(path, directory=False):
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid != os.getuid() or
            stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600) or
            (not directory and info.st_nlink != 1)):
        raise ValueError()
    return info


def _fingerprint(path):
    info = _private(path)
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            sha256(path.read_bytes()).hexdigest()]


class _Preparation:
    # Deliberately not a dataclass: no automatic secret serialization/repr.
    def __init__(self, path, config, revision, pending, identity):
        self.path, self.config, self.revision = path, config, revision
        self.pending, self.identity = pending, identity
        self.pending_revision = configuration_revision(pending) if pending else None
        self.provenance = pending.parent / 'preparation.json' if pending else None
        self.provenance_revision = configuration_revision(self.provenance) if pending else None

    def validate_pending(self):
        if self.pending:
            _private(self.pending.parent.parent, True)
            _private(self.pending.parent, True)
            _private(self.provenance)
            metadata = json.loads(self.provenance.read_text())
            if (configuration_revision(self.pending) != self.pending_revision or
                    configuration_revision(self.provenance) != self.provenance_revision or
                    _fingerprint(self.pending) != metadata['revision']):
                raise ConfigurationChanged('Pending configuration changed; review before preparing again.')

    def validate(self):
        if configuration_revision(self.path) != self.revision:
            raise ConfigurationChanged('Bridge configuration changed; prepare again.')
        self.validate_pending()


def _retained(path, model, address, device_id, socket_factory):
    directory = path.parent / '.c64-ai-pending'
    if not directory.exists() and not directory.is_symlink():return None
    _private(directory, True)
    candidates = list(directory.iterdir())
    if not candidates:return None
    if len(candidates) != 1:raise ValueError()
    candidate = candidates[0]
    _private(candidate, True)
    if len(candidate.name) != 32 or uuid.UUID(hex=candidate.name).hex != candidate.name:
        raise ValueError()
    if {p.name for p in candidate.iterdir()} != {'configuration.json', 'preparation.json'}:
        raise ValueError()
    pending, provenance = candidate/'configuration.json', candidate/'preparation.json'
    _private(provenance)
    metadata = json.loads(provenance.read_text())
    if metadata != dict(schema=1, preparation=candidate.name, active=str(path.resolve()),
                        address=address, device=device_id, revision=_fingerprint(pending)):
        raise ValueError()
    config = load_bridge_config(pending)
    if (config.allowed_clients != (address,) or config.model != model or config.port != 6464 or
            config.host != local_bridge_host(address, socket_factory)):
        raise ValueError()
    return pending, config, candidate.name


def prepare_bridge(path, model, address, *, socket_factory=socket.socket,
                   token_factory=secrets.token_hex, device_id=None):
    try:
        path = Path(path)
        address = str(ipaddress.IPv4Address(address))
        if ipaddress.IPv4Address(address).is_unspecified or ipaddress.IPv4Address(address).is_multicast:
            raise ValueError()
        with configuration_guard(path):
            revision = configuration_revision(path)
            identity = uuid.uuid4().hex
            pending = None
            retained = _retained(path, model, address, device_id, socket_factory)
            if revision[1] is not None:
                if retained is not None:raise ValueError()
                config = load_bridge_config(path)
                if address not in config.allowed_clients and len(config.allowed_clients) >= 4:
                    raise ValueError()
            elif retained is not None:
                pending, config, identity = retained
            else:
                config = C64BridgeConfig(model, local_bridge_host(address, socket_factory),
                                        6464, (address,), token_factory(32).upper())
                directory = path.parent / '.c64-ai-pending' / identity
                directory.mkdir(parents=True, mode=0o700)
                os.chmod(directory.parent, 0o700)
                os.chmod(directory, 0o700)
                pending = directory / 'configuration.json'
                save_bridge_config(pending, config)
                metadata = dict(schema=1, preparation=identity, active=str(path.resolve()),
                                address=address, device=device_id, revision=_fingerprint(pending))
                fd = os.open(directory/'preparation.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    json.dump(metadata, stream, sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
            prepared = _Preparation(path, config, revision, pending, identity)
            prepared.address = address
            prepared.validate()
            return prepared
    except Exception:
        pass
    raise BrowserError('Private AI configuration needs review; check retained preparation and device context before retrying.') from None


def finalize_bridge(prepared, runner, *, context_check):
    """Caller holds the configuration guard; FTP lifetime has already ended."""
    prepared.validate()
    context_check()
    def check_prepared():
        prepared.validate()
        context_check()
    expected = prepared.config
    revision = prepared.revision
    def accept_committed(config, committed_revision):
        nonlocal revision
        if config != expected:
            raise ConfigurationChanged('Bridge configuration changed; prepare again.')
        revision = committed_revision
    def check_committed():
        prepared.validate_pending()
        if (configuration_revision(prepared.path) != revision or
                load_bridge_config(prepared.path) != expected):
            raise ConfigurationChanged('Bridge configuration changed; prepare again.')
        context_check()
    if prepared.pending:
        status = finish_bridge_setup(prepared.path, prepared.config, runner,
                                     expected_revision=prepared.revision, context_check=context_check,
                                     pending_check=prepared.validate_pending, before_publish=check_prepared)
        # The helper checks its captured committed revision after its final observation.
        revision = configuration_revision(prepared.path)
    else:
        if prepared.address not in expected.allowed_clients:
            expected = replace(expected, allowed_clients=expected.allowed_clients + (prepared.address,))
        status = pair_bridge_address(prepared.path, prepared.address, runner,
                                     expected_revision=prepared.revision, context_check=context_check,
                                     committed_check=accept_committed, before_publish=check_prepared)
        check_committed()  # Status observation may have raced an external edit.
        if status.state == 'stopped':
            status = activate_bridge(prepared.path, runner, consequence_check=check_committed)
    check_committed()
    if status.state != 'ready':
        raise BrowserError('Bridge finalization did not verify; inspect before another attempt.')
    if prepared.pending:
        # Only the exact verified private preparation is consumed. No recursive cleanup.
        check_committed()
        prepared.pending.unlink()
        prepared.provenance.unlink()
        prepared.pending.parent.rmdir()
    return status
