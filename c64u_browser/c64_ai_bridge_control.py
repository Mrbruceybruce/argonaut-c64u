# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Inspect and update the private managed C64 AI bridge."""
from dataclasses import dataclass, replace
import ipaddress
from pathlib import Path
import secrets
import socket
import subprocess
import json
import urllib.error
import urllib.request

from .api import BrowserError
from .c64_ai_bridge_config import (
    C64BridgeConfig, load_bridge_config, save_bridge_config,
)


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
    model_status: str = 'unchecked'


def _systemctl(command, runner=subprocess.run):
    try:
        return runner(
            ['systemctl', '--user', command, SERVICE], capture_output=True,
            text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BrowserError('The C64 AI bridge service could not be checked.') from exc


def _reload_user_services(runner=subprocess.run):
    try:
        return runner(
            ['systemctl', '--user', 'daemon-reload'], capture_output=True,
            text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BrowserError('The background service list could not be refreshed.') from exc


def _local_model_names():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(
        'http://127.0.0.1:11434/api/tags', headers={'Accept': 'application/json'})
    with opener.open(request, timeout=3) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError('Local model list is too large.')
    data = json.loads(raw)
    models = data.get('models') if isinstance(data, dict) else None
    if not isinstance(models, list):
        raise ValueError('Local model list is invalid.')
    names = set()
    for item in models:
        if not isinstance(item, dict):
            raise ValueError('Local model entry is invalid.')
        for key in ('name', 'model'):
            value = item.get(key)
            if isinstance(value, str) and value:
                names.add(value.casefold())
    return names


def local_model_status(model, fetcher=None):
    try:
        names = (fetcher or _local_model_names)()
    except (OSError, TimeoutError, ValueError, urllib.error.URLError,
            urllib.error.HTTPError):
        return ('model_unavailable',
                'Local AI service unavailable · Start Ollama, then refresh')
    if model.casefold() not in names:
        return ('model_missing',
                f'Local model {model} is not downloaded · Download it in Ollama, then refresh')
    return 'ready', 'Local AI ready'


def local_address_available(address, socket_factory=socket.socket):
    probe = socket_factory(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((address, 0))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def bridge_status(path, runner=subprocess.run, check_model=False,
                  model_checker=None, network_checker=None):
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
        model_state, model_message = (
            (model_checker or local_model_status)(config.model)
            if check_model else ('unchecked', ''))
        state = 'ready' if model_state in ('ready', 'unchecked') else model_state
        message = (('Ready · ' if state == 'ready' else model_message + ' · Bridge running · ')
                   + detail)
        if not enabled:
            message += ' · automatic start is off'
    else:
        if not (network_checker or local_address_available)(config.host):
            message = ('Network changed · bridge address is unavailable · '
                       'Reconnect this computer to the C64U network, then retry · '
                       + detail)
            state = 'network_changed'
        else:
            message = 'Stopped · ' + detail
            state = 'stopped'
        model_state = 'unchecked'
    return BridgeStatus(state, message, config.model, config.host, config.port,
                        config.allowed_clients, enabled, model_state)


def activate_bridge(path, runner=subprocess.run):
    try:
        load_bridge_config(path)
    except FileNotFoundError as exc:
        raise BrowserError('Set up the private C64 AI bridge before starting it.') from exc
    except (OSError, ValueError) as exc:
        raise BrowserError('The private C64 AI bridge setting could not be read.') from exc
    restarted = _systemctl('restart', runner)
    if restarted.returncode != 0:
        _reload_user_services(runner)
        restarted = _systemctl('restart', runner)
        if restarted.returncode != 0:
            raise BrowserError('The C64 AI bridge could not be started.')
    status = bridge_status(path, runner)
    if status.state != 'ready':
        raise BrowserError('The C64 AI bridge did not become ready.')
    return status


def local_bridge_host(address, socket_factory=socket.socket):
    try:
        address = str(ipaddress.IPv4Address(address))
        probe = socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect((address, 9))
            host = str(ipaddress.IPv4Address(probe.getsockname()[0]))
        finally:
            probe.close()
    except (OSError, ValueError) as exc:
        raise BrowserError(
            'Argonaut could not determine this computer’s address for the C64U.') from exc
    if ipaddress.IPv4Address(host).is_loopback:
        raise BrowserError('The C64U cannot reach the local AI bridge address.')
    return host


def setup_bridge(path, model, address, runner=subprocess.run,
                 socket_factory=socket.socket, token_factory=secrets.token_hex):
    path = Path(path)
    if path.exists():
        raise BrowserError('The private C64 AI bridge is already set up.')
    saved = False
    was_enabled = True
    try:
        address = str(ipaddress.IPv4Address(address))
        config = C64BridgeConfig(
            model, local_bridge_host(address, socket_factory), 6464,
            (address,), token_factory(32).upper())
        save_bridge_config(path, config)
        saved = True
        _reload_user_services(runner)
        was_enabled = _systemctl('is-enabled', runner).returncode == 0
        if _systemctl('enable', runner).returncode != 0:
            raise BrowserError('Automatic start could not be enabled for the C64 AI bridge.')
        return activate_bridge(path, runner)
    except Exception:
        if saved:
            try:
                _systemctl('stop', runner)
            except Exception:
                pass
            if not was_enabled:
                try:
                    _systemctl('disable', runner)
                except Exception:
                    pass
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


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
