# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""XDG preferences contain only an explicit allowlist of non-secret fields."""
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import os
import tempfile
import uuid
from .api import UltimateClient, BrowserError, ConnectionFailure

@dataclass
class Profile:
    id: str
    name: str
    host: str
    http_port: int = 80
    ftp_port: int = 21
    auto_connect: bool = False
    serial_number: str = ''
    case_edition: str = ''
    notes: str = ''
    device_id: str = ''
    device_mac: str = ''

    @classmethod
    def new(cls, name, host, **kwargs):
        return cls(str(uuid.uuid4()), name, host, **kwargs)

    def validate(self):
        if not isinstance(self.id, str) or not self.id or not isinstance(self.name, str) or not self.name.strip():
            raise BrowserError('A profile needs an ID and a name.')
        if type(self.auto_connect) is not bool:
            raise BrowserError('Invalid auto-connect preference.')
        if any(not isinstance(value,str) for value in (self.serial_number,self.case_edition,self.notes,self.device_id,self.device_mac)):
            raise BrowserError('Profile details must be text.')
        UltimateClient(self.host, port=self.ftp_port, http_port=self.http_port)
        return self

    def verify_identity(self, info, require_bound=False):
        reported=info.get('info',{}).get('unique_id')
        reported=reported if isinstance(reported,str) and reported.strip() and reported not in ('Default','None') else ''
        mac=info.get('network_mac','')
        mac=mac if isinstance(mac,str) else ''
        if self.device_id and reported:
            if reported.casefold()!=self.device_id.casefold():
                raise ConnectionFailure('identity','This address belongs to a different C64U. Expected ID '+self.device_id+'; reported '+reported+'. Check Connections.')
        elif self.device_mac:
            if not mac or mac.casefold()!=self.device_mac.casefold():
                raise ConnectionFailure('identity','The saved network MAC could not be verified. Expected '+self.device_mac+'; reported '+(mac or 'Not available')+'. Check the address and network interface in Connections.')
        elif self.device_id:
            raise ConnectionFailure('identity','The saved device ID is not reported and no MAC fallback was saved. Check Connections.')
        if require_bound and not (self.device_id or self.device_mac):
            raise ConnectionFailure('identity','Confirm this profile’s device in Connections before using automatic connection.')
        return reported

    def client(self, password=''):
        return UltimateClient(self.host, password, port=self.ftp_port, http_port=self.http_port)

from .platform_support import config_base

class Preferences:
    def __init__(self, path=None):
        base = config_base()
        self.path = Path(path) if path else base/'argonaut'/'config.json'
        self.profiles = []
        self.selected_id = None
        self.screenshot_folder = ''
        self.recording_folder = ''
        self.setting_favorites = set()

    def load(self):
        try:
            data = json.loads(self.path.read_text())
            if data.get('schema_version') != 1: raise ValueError('Unsupported preferences version')
            self.profiles = [Profile(**p).validate() for p in data['profiles']]
            ids = [p.id for p in self.profiles]
            if len(ids) != len(set(ids)): raise ValueError('Duplicate profile IDs')
            self.recording_folder = data.get('recording_folder', '')
            if not isinstance(self.recording_folder,str):raise ValueError('Invalid recording folder')
            self.screenshot_folder = data.get('screenshot_folder', '')
            if not isinstance(self.screenshot_folder,str):raise ValueError('Invalid screenshot folder')
            favorites = data.get('setting_favorites', [])
            if not isinstance(favorites, list) or any(
                not isinstance(key, list) or len(key) != 2 or
                any(not isinstance(part, str) or not part for part in key)
                for key in favorites
            ): raise ValueError('Invalid settings favorites')
            self.setting_favorites = {tuple(key) for key in favorites}
            self.selected_id = data.get('selected_id')
            if self.selected_id is not None and self.selected_id not in ids: raise ValueError('Unknown selected profile')
        except FileNotFoundError: pass
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise BrowserError('Cannot load Argonaut preferences; original file has been kept.') from exc
        return self

    def save(self):
        for p in self.profiles: p.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = {'schema_version': 1, 'selected_id': self.selected_id,
                'profiles': [asdict(p) for p in self.profiles], 'screenshot_folder': self.screenshot_folder, 'recording_folder': self.recording_folder,
                'setting_favorites': [list(key) for key in sorted(self.setting_favorites)]}
        fd, temp = tempfile.mkstemp(dir=self.path.parent, prefix='.config-')
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(data, stream, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp): os.unlink(temp)

    def selected(self):
        return next((p for p in self.profiles if p.id == self.selected_id), None)
