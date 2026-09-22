# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Scoped Flash storage and native CFG conversion; never executes file contents."""
from pathlib import Path
import io
import hashlib
import posixpath
import uuid
from .api import BrowserError,safe_argument
from .transfers import connect
from .backups import allowed
from .storage import storage_root
from .diagnostics import operation_event

FLASH_FOLDERS={'ROMs':'/Flash/roms','Cartridges':'/Flash/carts','Configurations':'/Flash/configs'}
MAX_BYTES=16*1024*1024

def flash_path(folder,name):
 if folder not in FLASH_FOLDERS.values():raise BrowserError('Choose a supported Flash folder.')
 safe_argument(name)
 if not name or name in ('.','..') or any(c in name for c in '/\\:*?') or name.endswith((' ','.')):raise BrowserError('Choose an ordinary filename.')
 if len(name.encode('utf-8'))>64:raise BrowserError('Filename is too long.')
 return folder+'/'+name

def read_remote(client,path,max_bytes=MAX_BYTES):
 with operation_event('ftp','read_remote','file'):
  return _read_remote(client,path,max_bytes)

def _read_remote(client,path,max_bytes=MAX_BYTES):
 safe_argument(path)
 if type(max_bytes) is not int or not 1<=max_bytes<=MAX_BYTES:raise BrowserError('Invalid remote file size bound.')
 if not ((storage_root(path) and storage_root(path)!=path) or any(path.startswith(folder+'/') for folder in FLASH_FOLDERS.values())) or any(p in ('','.','..') for p in path.split('/')[1:]):raise BrowserError('Choose a USB/SD or supported Flash file.')
 ftp=connect(client)
 try:
  expected=ftp.size(path)
  if expected is None or not 0<expected<=max_bytes:
   limit='16 MB' if max_bytes==MAX_BYTES else f'{max_bytes:,} bytes'
   raise BrowserError(f'File must contain between 1 byte and {limit}.')
  data=bytearray()
  def receive(block):
   if len(data)+len(block)>max_bytes:raise BrowserError('File exceeds the supported size bound.')
   data.extend(block)
  ftp.retrbinary('RETR '+path,receive)
  if len(data)!=expected or ftp.size(path)!=expected:raise BrowserError('File changed or download was incomplete.')
  return bytes(data)
 finally:ftp.close()

def read_local(path):
 path=Path(path)
 if path.is_symlink() or not path.is_file():raise BrowserError('Choose a regular file.')
 with path.open('rb') as stream:data=stream.read(MAX_BYTES+1)
 if not 0<len(data)<=MAX_BYTES:raise BrowserError('File must contain between 1 byte and 16 MB.')
 return data

def parse_cfg(data):
 if len(data)>256*1024:raise BrowserError('Configuration file exceeds 256 KB.')
 # Native files use byte strings; preserve their single-byte values and case.
 try:text=data.decode('utf-8-sig')
 except UnicodeDecodeError:text=data.decode('latin-1')
 values={};section=None
 for number,line in enumerate(text.splitlines(),1):
  if len(line.encode('latin-1',errors='replace'))>127 or any(ord(c)<32 and c!='\t' for c in line):raise BrowserError(f'Unsupported configuration line {number}.')
  if not line or line.startswith(('#',';')):continue
  if line.startswith('[') and line.endswith(']'):
   section=line[1:-1]
   if not section or section in values:raise BrowserError(f'Invalid or repeated section at line {number}.')
   values[section]={};continue
  if section is None or '=' not in line:raise BrowserError(f'Invalid configuration syntax at line {number}.')
  name,value=line.split('=',1)
  if not name or name in values[section]:raise BrowserError(f'Invalid or repeated setting at line {number}.')
  values[section][name]=value
 if not any(values.values()):raise BrowserError('Configuration contains no settings.')
 return values

def config_backup(data,settings):
 values=parse_cfg(data)
 current={(c,s.name):s for c,rows in settings.items() for s in rows}
 compatible={};skipped=0
 for category,items in values.items():
  for name,text in items.items():
   setting=current.get((category,name))
   if setting is None or not allowed(category,setting):skipped+=1;continue
   if setting.choices:
    matches=[choice for choice in setting.choices if choice.strip().casefold()==text.strip().casefold()]
    if len(matches)==1:text=matches[0]
   try:parsed=setting.parse(text)
   except ValueError:skipped+=1;continue
   compatible.setdefault(category,{})[name]=parsed
 return {'settings':compatible},skipped

def validate_upload(folder,name,data):
 flash_path(folder,name)
 if not 0<len(data)<=MAX_BYTES:raise BrowserError('File must contain between 1 byte and 16 MB.')
 extension=Path(name).suffix.casefold()
 if folder.endswith('/configs'):
  if extension!='.cfg':raise BrowserError('Choose a native .cfg configuration file.')
  parse_cfg(data)
  if not data.endswith(b'\n'):raise BrowserError('Native configuration uploads must end with a newline.')
 elif folder.endswith('/carts'):
  if extension!='.crt' or len(data)<64 or data[:16]!=b'C64 CARTRIDGE   \x00':raise BrowserError('Choose a C64 .crt cartridge image.')
 else:
  if extension not in ('.bin','.rom','.64c'):raise BrowserError('Choose a .bin, .rom or .64c ROM file.')
 if not folder.endswith('/configs') and len(name.encode('utf-8'))>30:raise BrowserError('Use a ROM or cartridge filename of at most 30 bytes.')

def upload_flash(client,folder,name,data):
 with operation_event('ftp','upload_flash','file'):
  return _upload_flash(client,folder,name,data)

def _upload_flash(client,folder,name,data):
 validate_upload(folder,name,data)
 destination=flash_path(folder,name)
 temporary=flash_path(folder,'argonaut-part-'+uuid.uuid4().hex)
 ftp=connect(client);started=False
 try:
  # Create only the selected, known folder if it is absent from Flash's root.
  _,root=client.list_directory('/Flash')
  item=next((e for e in root if e.name.casefold()==posixpath.basename(folder).casefold()),None)
  if item is None:ftp.mkd(folder)
  elif item.kind!='dir' or item.name!=posixpath.basename(folder):raise BrowserError('Flash folder is unavailable or ambiguous.')
  def exists(path):
   return any(e.name.casefold()==posixpath.basename(path).casefold() for e in client.list_directory(folder)[1])
  if exists(destination):raise BrowserError('That filename already exists in Flash. Choose a different filename; nothing was overwritten.')
  if exists(temporary):raise BrowserError('Temporary filename already exists.')
  started=True
  ftp.storbinary('STOR '+temporary,io.BytesIO(data))
  digest=hashlib.sha256();count=0
  def verify(block):
   nonlocal count
   count+=len(block)
   if count>len(data):raise BrowserError('Upload verification failed.')
   digest.update(block)
  ftp.retrbinary('RETR '+temporary,verify)
  if count!=len(data) or ftp.size(temporary)!=len(data) or digest.digest()!=hashlib.sha256(data).digest():raise BrowserError('Upload verification failed.')
  if exists(destination):raise BrowserError('Destination appeared during upload; publication refused.')
  ftp.rename(temporary,destination)
  return destination
 except Exception as exc:
  raise BrowserError(str(exc)+(f' Inspect {temporary} and {destination} before retrying.' if started else '')) from exc
 finally:ftp.close()
