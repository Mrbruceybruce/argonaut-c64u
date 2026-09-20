# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Generate, verify, and conservatively install the paired C64 AI client."""
from dataclasses import dataclass
from hashlib import sha256
import ipaddress
from pathlib import Path
import subprocess
import tempfile

from .api import BrowserError
from .c64_ai_client import render_chat_client, render_legacy_chat_client
from .c64_ai_bridge_config import load_bridge_config
from .c64_ai_bridge_control import activate_bridge, pair_bridge_address
from .c64_ai_launch import CLIENT_PATH
from .c64_basic import tokenize_basic_v2
from .files import inspect
from .folder_copy import Step
from .replacement import replace_file
from .transfers import download, upload


@dataclass(frozen=True)
class ClientInstallResult:
    path: str
    installed: bool
    size: int
    sha256: str


@dataclass(frozen=True)
class ClientProvisionResult:
    bridge: object
    client: ClientInstallResult


def build_c64_ai_client(config):
    source = render_chat_client(config.host, config.port, config.token)
    return tokenize_basic_v2(source)


def _build_legacy_c64_ai_client(config):
    source = render_legacy_chat_client(config.host, config.port, config.token)
    return tokenize_basic_v2(source)


def install_c64_ai_client(client, config, path=CLIENT_PATH):
    """Install when absent and safely upgrade Argonaut's exact ai.1 client."""
    program = build_c64_ai_client(config)
    digest = sha256(program).hexdigest()
    entry = inspect(client, path)
    if entry is not None and entry.kind != 'file':
        raise BrowserError('The Argonaut AI client path on USB2 is not a file.')
    with tempfile.TemporaryDirectory(prefix='argonaut-c64-ai-') as folder:
        local = Path(folder) / Path(path).name
        if entry is not None:
            download(client, path, local)
            existing = local.read_bytes()
            if existing == program:
                return ClientInstallResult(path, False, len(program), digest)
            if existing != _build_legacy_c64_ai_client(config):
                raise BrowserError(
                    'The existing USB2 Argonaut AI client differs from this pairing. '
                    'Keep or rename it in Files before installing the paired client.')
            local.write_bytes(program)
            replace_file(client, Step(
                Path(path).name, local, path, False, True,
                (entry.name, entry.size)), True, False, lambda _count: None)
            return ClientInstallResult(path, True, len(program), digest)
        local.write_bytes(program)
        result = upload(client, local, str(Path(path).parent).replace('\\', '/'))
    if (result.get('path') != path or result.get('bytes') != len(program)
            or result.get('sha256') != digest or result.get('verified') is not True):
        raise BrowserError('The uploaded C64 AI client could not be verified.')
    return ClientInstallResult(path, True, len(program), digest)


def install_and_pair_c64_ai(client, config_path, address,
                            runner=subprocess.run):
    """Install the matching client, pair its fixed address, and leave ready."""
    try:
        address = str(ipaddress.IPv4Address(address))
        config = load_bridge_config(config_path)
    except (OSError, ValueError) as exc:
        raise BrowserError('The private bridge setting or C64U address is invalid.') from exc
    if (address not in config.allowed_clients
            and len(config.allowed_clients) >= 4):
        raise BrowserError('The C64 AI bridge already has four paired addresses.')
    installed = install_c64_ai_client(client, config)
    status = pair_bridge_address(config_path, address, runner)
    if status.state == 'stopped':
        status = activate_bridge(config_path, runner)
    if status.state != 'ready':
        raise BrowserError('The C64 AI bridge is not ready after pairing.')
    return ClientProvisionResult(status, installed)
