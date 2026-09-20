# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Headless application boundary for Argonaut device and profile state.

The desktop currently runs this facade in-process.  Future transports and
clients must call the same application operations instead of owning an
``UltimateClient`` themselves.
"""
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Callable, Mapping
import copy
import ftplib
import socket
import struct
import urllib.request

from .api import BrowserError, ConnectionFailure, UltimateClient
from .credentials import Credentials
from .discovery import local_networks, standard_scan, subnet_scan
from .profiles import Preferences, Profile
from .storage import initial_directory


@dataclass(frozen=True)
class CoreEvent:
    """A presentation-neutral notification from Core."""
    kind: str
    profile_id: str = ''
    message: str = ''
    data: Mapping[str, Any] | None = None


class CoreError(BrowserError):
    """Sanitized, categorized failure safe to show to any client."""
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    def as_dict(self):
        return {'code': self.code, 'message': str(self),
                'retryable': self.retryable}


@dataclass(frozen=True)
class ConnectionTestResult:
    profile: Profile
    device_info: Mapping[str, Any]
    reported_device_id: str


@dataclass(frozen=True)
class ConnectionResult:
    profile: Profile
    device_info: Mapping[str, Any]
    remote_path: str
    entries: tuple

    @property
    def listing(self):
        return self.remote_path, list(self.entries)


@dataclass(frozen=True)
class CoreSession:
    state: str
    profile: Profile | None
    device_info: Mapping[str, Any] | None


def _public_info(value):
    """Detach returned state from mutable transport-owned dictionaries."""
    return MappingProxyType(copy.deepcopy(value))


class CoreDeviceOperations:
    """Temporary explicit service used by desktop workflows not migrated yet.

    This is deliberately not an UltimateClient and never reveals credentials.
    Its methods form a narrow compatibility seam while file, settings, drive,
    machine and media operations move behind dedicated Core capabilities.
    """
    credentials_encapsulated = True

    def __init__(self, core):
        self._core = core

    def _client(self):
        return self._core._require_client()

    @property
    def host(self): return self._client().host
    @property
    def port(self): return self._client().port
    @property
    def http_port(self): return self._client().http_port
    @property
    def timeout(self): return self._client().timeout
    @property
    def encoding(self): return self._client().encoding
    @property
    def storage_roots(self): return self._client().storage_roots
    @storage_roots.setter
    def storage_roots(self, value): self._client().storage_roots = value

    def list_directory(self, *args, **kwargs): return self._client().list_directory(*args, **kwargs)
    def read_about(self, *args, **kwargs): return self._client().read_about(*args, **kwargs)
    def read_configuration(self, *args, **kwargs): return self._client().read_configuration(*args, **kwargs)
    def read_drives(self, *args, **kwargs): return self._client().read_drives(*args, **kwargs)
    def drive_action(self, *args, **kwargs): return self._client().drive_action(*args, **kwargs)
    def mount_disk(self, *args, **kwargs): return self._client().mount_disk(*args, **kwargs)
    def create_d64(self, *args, **kwargs): return self._client().create_d64(*args, **kwargs)
    def set_drive_type(self, *args, **kwargs): return self._client().set_drive_type(*args, **kwargs)
    def apply_configuration(self, *args, **kwargs): return self._client().apply_configuration(*args, **kwargs)
    def save_configuration(self, *args, **kwargs): return self._client().save_configuration(*args, **kwargs)
    def machine_action(self, *args, **kwargs): return self._client().machine_action(*args, **kwargs)
    def run_prg(self, *args, **kwargs): return self._client().run_prg(*args, **kwargs)
    def write_memory(self, *args, **kwargs): return self._client().write_memory(*args, **kwargs)
    def play_sid(self, *args, **kwargs): return self._client().play_sid(*args, **kwargs)
    def start_stream(self, *args, **kwargs): return self._client().start_stream(*args, **kwargs)
    def stop_stream(self, *args, **kwargs): return self._client().stop_stream(*args, **kwargs)
    def info(self, *args, **kwargs): return self._client().info(*args, **kwargs)
    def test_connection(self, *args, **kwargs): return self._client().test_connection(*args, **kwargs)

    def open_ftp(self):
        """Return an authenticated FTP channel without exposing its secret."""
        client = self._client()
        ftp = ftplib.FTP(timeout=client.timeout, encoding=client.encoding)
        try:
            ftp.connect(client.host, client.port)
            ftp.login('anonymous', client.password)
            ftp.set_pasv(True)
            ftp.voidcmd('TYPE I')
            return ftp
        except BaseException:
            ftp.close()
            raise

    def read_memory(self, address, length):
        """Read bytes through the authenticated REST API."""
        client = self._client()
        from .api import NoRedirect
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(
            f'http://{client.host}:{client.http_port}/v1/machine:readmem'
            f'?address={address:04X}&length={length}',
            headers={'X-Password': client.password,
                     'Accept': 'application/octet-stream'})
        with opener.open(request, timeout=client.timeout) as response:
            return response.read(length + 1)

    def open_dma(self, timeout=None):
        """Return an authenticated command-interface channel."""
        client = self._client()
        connection = socket.create_connection(
            (client.host, 64), timeout=client.timeout if timeout is None else timeout)
        try:
            password = client.password.encode('utf-8')
            if len(password) > 65535:
                raise CoreError('authentication', 'Network password is too long.')
            connection.sendall(struct.pack('<HH', 0xff1f, len(password)) + password)
            response = connection.recv(1)
            if response != b'\x01':
                raise CoreError('authentication', 'DMA authentication failed.')
            return connection
        except BaseException:
            connection.close()
            raise


class ArgonautCore:
    """Own profiles, secrets, discovery and the active C64U session."""
    def __init__(self, *, preferences=None, credentials=None,
                 client_factory: Callable[..., UltimateClient] = UltimateClient,
                 standard_discovery=standard_scan,
                 subnet_discovery=subnet_scan,
                 networks=local_networks):
        self.preferences = preferences or Preferences()
        self._credentials = credentials or Credentials()
        self._client_factory = client_factory
        self._standard_discovery = standard_discovery
        self._subnet_discovery = subnet_discovery
        self._networks = networks
        self._session_passwords = {}
        self.preferences_error = None
        self._client = None
        self._active_profile = None
        self._device_info = None
        self._listeners = []
        self._device_operations = CoreDeviceOperations(self)

    def load(self):
        try:
            self.preferences.load()
        except (BrowserError, OSError) as exc:
            self.preferences_error = str(exc)
        return self

    @property
    def active_profile(self): return self._active_profile

    @property
    def credentials_session_only(self):
        return getattr(self._credentials, 'session_only', False) is True

    @property
    def device_info(self):
        return _public_info(self._device_info) if self._device_info else None

    @property
    def device_operations(self):
        """Compatibility service for desktop capabilities still being migrated."""
        return self._device_operations

    def session(self):
        return CoreSession('connected' if self._client else
                           'offline' if self._active_profile else 'disconnected',
                           self._active_profile, self.device_info)

    def add_listener(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _emit(self, kind, message='', data=None, profile_id=None):
        event = CoreEvent(kind, profile_id if profile_id is not None else
                          self._active_profile.id if self._active_profile else '',
                          message, _public_info(data) if data else None)
        for listener in tuple(self._listeners): listener(event)

    def profiles(self): return tuple(self.preferences.profiles)
    def selected_profile(self): return self.preferences.selected()

    def _new_client(self, profile, password):
        try:
            return self._client_factory(profile.host, password,
                                        port=profile.ftp_port,
                                        http_port=profile.http_port)
        except BrowserError:
            raise
        except Exception as exc:
            raise CoreError('client', 'Could not prepare the C64U connection.') from exc

    def credential_for(self, profile, entered=''):
        if entered: return entered
        old = next((p for p in self.preferences.profiles if p.id == profile.id), None)
        if old and (old.host, old.http_port, old.ftp_port) == (
                profile.host, profile.http_port, profile.ftp_port):
            return (self._session_passwords.get(profile.id) or
                    self._credentials.get(profile.id) or '')
        return ''

    def forget_credential(self, profile_id):
        self._credentials.delete(profile_id)
        self._session_passwords.pop(profile_id, None)

    def save_profile(self, profile, entered_password='', remember=False):
        profile.validate()
        prefs = self.preferences
        old = next((item for item in prefs.profiles if item.id == profile.id), None)
        changed = old and (old.host, old.http_port, old.ftp_port) != (
            profile.host, profile.http_port, profile.ftp_port)
        if changed:
            profile = replace(profile, id=Profile.new(profile.name, profile.host).id)
        if remember and entered_password:
            self._credentials.set(profile.id, entered_password)
        before, selected = prefs.profiles, prefs.selected_id
        prefs.profiles = [profile if item.id == (old.id if old else profile.id)
                          else item for item in before]
        if not old: prefs.profiles.append(profile)
        prefs.selected_id = profile.id
        try: prefs.save()
        except Exception:
            prefs.profiles, prefs.selected_id = before, selected
            raise
        if entered_password:
            self._session_passwords[profile.id] = entered_password
        self._emit('profile-saved', data={'profile_id': profile.id},
                   profile_id=profile.id)
        return profile

    def delete_profile(self, profile_id):
        self._credentials.delete(profile_id)
        prefs = self.preferences
        before, selected = prefs.profiles, prefs.selected_id
        prefs.profiles = [p for p in before if p.id != profile_id]
        if prefs.selected_id == profile_id: prefs.selected_id = None
        try: prefs.save()
        except Exception:
            prefs.profiles, prefs.selected_id = before, selected
            raise
        self._session_passwords.pop(profile_id, None)
        if self._active_profile and self._active_profile.id == profile_id:
            self.disconnect()
        self._emit('profile-deleted', data={'profile_id': profile_id},
                   profile_id=profile_id)

    def discover(self, *, subnet=''):
        if subnet:
            return tuple(self._subnet_discovery(subnet)), (
                'Controlled LAN scan complete.',), ()
        known = [(p.host, p.http_port) for p in self.preferences.profiles]
        candidates, notes = self._standard_discovery(known_hosts=known)
        return tuple(candidates), tuple(notes), tuple(self._networks())

    def test_profile(self, profile, entered_password=''):
        try:
            client = self._new_client(profile,
                                      self.credential_for(profile, entered_password))
            info = client.test_connection()
            reported = profile.verify_identity(info)
            return ConnectionTestResult(profile, _public_info(info), reported)
        except ConnectionFailure as exc:
            raise CoreError(exc.kind, str(exc), retryable=exc.kind in ('host', 'network')) from exc

    def read_model(self, profile, entered_password=''):
        client = self._new_client(profile,
                                  self.credential_for(profile, entered_password))
        try:
            info = client.test_connection()
            profile.verify_identity(info)
        except ConnectionFailure as exc:
            raise CoreError(exc.kind, str(exc),
                            retryable=exc.kind in ('host', 'network')) from exc
        from .configuration import Configuration
        return next((row.current for row in Configuration(client).settings(
            'U64 Specific Settings') if row.name == 'C64U Model'), 'Not reported')

    def connect(self, profile, *, entered_password='', remember=False,
                require_bound=False, bind_identity=False, persist=False,
                remote_folder=None):
        try:
            password = self.credential_for(profile, entered_password)
            client = self._new_client(profile, password)
            info = client.test_connection()
            reported = profile.verify_identity(info, require_bound=require_bound)
            if bind_identity:
                profile = replace(profile,
                    device_id=reported or profile.device_id,
                    device_mac=info.get('network_mac', '') or profile.device_mac)
                profile.verify_identity(client.test_connection())
            folder = remote_folder or '/USB2'
            path, entries = initial_directory(client, folder)
            if persist:
                profile = self.save_profile(profile, entered_password, remember)
            self._client = client
            self._active_profile = profile
            self._device_info = copy.deepcopy(info)
            result = ConnectionResult(profile, _public_info(info), path,
                                      tuple(entries))
            self._emit('connected', data={'host': profile.host})
            return result
        except ConnectionFailure as exc:
            raise CoreError(exc.kind, str(exc), retryable=exc.kind in ('host', 'network')) from exc

    def connect_selected(self, *, require_bound=True):
        profile = self.selected_profile()
        if not profile:
            raise CoreError('profile', 'Choose or create a device profile first.')
        folder = (self.preferences.app_options['remote_folders'].get(
            profile.id, '/USB2')
            if self.preferences.app_options['remember_folders'] else '/USB2')
        return self.connect(profile, require_bound=require_bound,
                            remote_folder=folder)

    def mark_connection_lost(self, message=''):
        if not self._active_profile: return
        self._client = None
        self._emit('offline', message)

    def check_health(self):
        """Verify that the active transport still answers as the same device."""
        client = self._require_client()
        try:
            info = client.test_connection()
            self._active_profile.verify_identity(info)
            if not (self._active_profile.device_id or
                    self._active_profile.device_mac):
                expected = (self._device_info or {}).get(
                    'info', {}).get('unique_id')
                reported = info.get('info', {}).get('unique_id')
                if expected and reported != expected:
                    raise ConnectionFailure(
                        'identity',
                        'A different device answered at this address. Connect manually.')
            return _public_info(info)
        except ConnectionFailure as exc:
            raise CoreError(exc.kind, str(exc),
                            retryable=exc.kind in ('host', 'network')) from exc

    def reconnect(self, remote_folder='/USB2'):
        if not self._active_profile:
            raise CoreError('session', 'No C64U session is available to reconnect.')
        profile = self._active_profile
        old_info = self._device_info or {}
        password = self.credential_for(profile)
        client = self._new_client(profile, password)
        try:
            info = client.test_connection()
            profile.verify_identity(info, require_bound=bool(
                profile.device_id or profile.device_mac))
            path, entries = initial_directory(client, remote_folder)
        except ConnectionFailure as exc:
            raise CoreError(exc.kind, str(exc),
                            retryable=exc.kind in ('host', 'network')) from exc
        expected = old_info.get('info', {}).get('unique_id')
        reported = info.get('info', {}).get('unique_id')
        if not (profile.device_id or profile.device_mac):
            if not expected:
                self.mark_connection_lost('No device ID was available to verify reconnection.')
                raise CoreError('identity',
                    'No device ID was available to verify reconnection. Connect manually.')
            if reported != expected:
                self.mark_connection_lost('A different device answered at this address.')
                raise CoreError('identity',
                    'A different device answered at this address. Connect manually.')
        self._client = client
        self._device_info = copy.deepcopy(info)
        result = ConnectionResult(profile, _public_info(info), path,
                                  tuple(entries))
        self._emit('reconnected', data={'host': profile.host})
        return result

    def disconnect(self):
        profile_id = self._active_profile.id if self._active_profile else ''
        self._client = self._active_profile = self._device_info = None
        self._emit('disconnected', data={'profile_id': profile_id},
                   profile_id=profile_id)

    def _require_client(self):
        if self._client is None:
            raise CoreError('session', 'Connect to a C64U first.')
        return self._client
