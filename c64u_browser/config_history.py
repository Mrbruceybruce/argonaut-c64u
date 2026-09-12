# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Per-profile recovery point containing only the settings about to be changed."""
import hashlib
from .backups import snapshot,write_backup,read_backup
from .api import BrowserError

def history_path(preferences,profile,client):
 key=getattr(profile,'id',None) or getattr(client,'host',None)
 if not isinstance(key,str) or not key:raise BrowserError('Cannot identify this connection for a settings backup.')
 return preferences.path.parent/'config-history'/(hashlib.sha256(key.encode()).hexdigest()+'.json')

def save_before_apply(path,settings,payload,host):
 selected={category:[s for s in rows if s.name in payload.get(category,{})] for category,rows in settings.items()}
 data=snapshot(selected,host)
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 write_backup(path,data)

def read_previous(path):
 if not path.is_file():raise BrowserError('No previous Apply backup is available for this profile yet.')
 return read_backup(path)
