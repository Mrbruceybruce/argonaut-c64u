# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Inspect and update the private managed C64 AI bridge."""
from dataclasses import dataclass, replace
import ipaddress
from pathlib import Path
import subprocess

from .api import BrowserError
from .c64_ai_bridge_config import load_bridge_config, save_bridge_config


SERVICE = 'argonaut-c64-ai-bridge.service'


@dataclass(frozen=True)
class BridgeStatus:
    state: str
    message: str
    model: str = ''
    host: str = ''
    port: int = 0
    allowed_clients: tuple = ()
    enabled: bool = False


def _systemctl(command, runner=subprocess.run):
    try:
        return runner(
            ['systemctl', '--user', command, SERVICE], capture_output=True,
            text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BrowserError('The C64 AI bridge service could not be checked.') from exc


def bridge_status(path, runner=subprocess.run):
    path = Path(path)
    if not path.exists():
        return BridgeStatus('setup', 'Setup needed · no private bridge setting found')
    try:
        config = load_bridge_config(path)
    except (OSError, ValueError) as exc:
        return BridgeStatus('error', 'Setup needs attention · private bridge setting is invalid')
    try:
        active = _systemctl('is-active', runner)
        enabled = _systemctl('is-enabled', runner).returncode == 0
    except BrowserError:
        return BridgeStatus(
            'unavailable', 'Status unavailable · background services could not be checked',
            config.model, config.host, config.port, config.allowed_clients)
    running = active.returncode == 0 and active.stdout.strip() == 'active'
    detail = (f'{config.model} · {config.host}:{config.port} · '
              f'{len(config.allowed_clients)} paired address'
              f'{"es" if len(config.allowed_clients) != 1 else ""}')
    if running:
        message = 'Ready · ' + detail
        if not enabled:
            message += ' · automatic start is off'
        state = 'ready'
    else:
        message = 'Stopped · ' + detail
        state = 'stopped'
    return BridgeStatus(state, message, config.model, config.host, config.port,
                        config.allowed_clients, enabled)


def activate_bridge(path, runner=subprocess.run):
    try:
        load_bridge_config(path)
    except FileNotFoundError as exc:
        raise BrowserError('Set up the private C64 AI bridge before starting it.') from exc
    except (OSError, ValueError) as exc:
        raise BrowserError('The private C64 AI bridge setting could not be read.') from exc
    restarted = _systemctl('restart', runner)
    if restarted.returncode != 0:
        raise BrowserError('The C64 AI bridge could not be started.')
    status = bridge_status(path, runner)
    if status.state != 'ready':
        raise BrowserError('The C64 AI bridge did not become ready.')
    return status


def pair_bridge_address(path, address, runner=subprocess.run):
    """Add one verified device address without exposing or rotating the token."""
    try:
        address = str(ipaddress.IPv4Address(address))
    except (ipaddress.AddressValueError, ValueError) as exc:
        raise BrowserError('The connected C64U needs a fixed IPv4 address for pairing.') from exc
    try:
        config = load_bridge_config(path)
    except FileNotFoundError as exc:
        raise BrowserError('Set up the private C64 AI bridge before pairing a C64U.') from exc
    except (OSError, ValueError) as exc:
        raise BrowserError('The private C64 AI bridge setting could not be read.') from exc
    if address in config.allowed_clients:
        return bridge_status(path, runner)
    if len(config.allowed_clients) >= 4:
        raise BrowserError('The C64 AI bridge already has four paired addresses.')
    updated = replace(config, allowed_clients=config.allowed_clients + (address,))
    try:
        save_bridge_config(path, updated)
        restarted = _systemctl('restart', runner)
        if restarted.returncode != 0:
            raise BrowserError('The C64 AI bridge could not restart with the new pairing.')
    except Exception:
        try:
            save_bridge_config(path, config)
            _systemctl('restart', runner)
        except Exception:
            pass
        raise
    status = bridge_status(path, runner)
    if status.state != 'ready':
        try:
            save_bridge_config(path, config)
            _systemctl('restart', runner)
        except Exception:
            pass
        raise BrowserError('The C64 AI bridge did not become ready; pairing was restored.')
    return status
