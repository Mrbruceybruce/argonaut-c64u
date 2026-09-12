# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Portable, credential-free configuration snapshots and validated restore diffs."""
import json
import math
import os
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from .configuration import display

FORMAT='argonaut-settings'

def allowed(category,setting):
 return setting.editable and setting.current!='Hidden' and setting.name!='C64U Model' and not any(w in setting.name.casefold() for w in ('password','secret','passphrase','credential'))

def snapshot(settings,host):
 values={}
 for category,rows in settings.items():
  for setting in rows:
   if allowed(category,setting):
    try:value=setting.parse(setting.current)
    except ValueError:continue
    values.setdefault(category,{})[setting.name]=value
 return {'format':FORMAT,'version':1,'created':datetime.now(timezone.utc).isoformat(),'source_host':host,'settings':values}

def read_backup(path):
 with open(path,'rb') as stream:raw=stream.read(2*1024*1024+1)
 if len(raw)>2*1024*1024:raise ValueError('Backup is too large.')
 data=json.loads(raw)
 if not isinstance(data,dict) or data.get('format')!=FORMAT or type(data.get('version')) is not int or data['version']!=1:raise ValueError('Not a supported Argonaut settings backup.')
 values=data.get('settings')
 if not isinstance(values,dict):raise ValueError('Invalid backup settings.')
 for category,items in values.items():
  if not isinstance(category,str) or not isinstance(items,dict):raise ValueError('Invalid backup category.')
  for name,value in items.items():
   if not isinstance(name,str) or type(value) not in (str,int,float,bool) or (type(value) is float and not math.isfinite(value)):raise ValueError('Invalid backup value.')
 return data

def write_backup(path,data):
 path=Path(path);temporary=None
 try:
  with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as stream:
   temporary=stream.name;json.dump(data,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')
  os.replace(temporary,path)
 finally:
  if temporary and os.path.exists(temporary):os.unlink(temporary)

def differences(data,settings):
 current={(c,s.name):s for c,rows in settings.items() for s in rows};changes=[];skipped=0
 for category,items in data['settings'].items():
  for name,value in items.items():
   setting=current.get((category,name))
   if setting is None or not allowed(category,setting):skipped+=1;continue
   try:
    parsed=setting.parse(display(value))
    if type(parsed) is not type(value) or parsed!=value:raise ValueError()
   except ValueError:skipped+=1;continue
   if setting.current!=display(value):changes.append((category,setting,value))
 return changes,skipped
