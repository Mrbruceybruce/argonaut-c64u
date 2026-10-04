# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Scoped Flash storage and native CFG conversion; never executes file contents."""
from pathlib import Path
from dataclasses import dataclass, replace
import io
import hashlib
import posixpath
import uuid
from .api import BrowserError,safe_argument
from .transfers import connect, UploadEvidence
from .ftp_reads import adapter_for
from .backups import allowed
from .storage import storage_root
from .diagnostics import operation_event

FLASH_FOLDERS={'ROMs':'/Flash/roms','Cartridges':'/Flash/carts','Configurations':'/Flash/configs'}
MAX_BYTES=16*1024*1024
MAX_GAME_BYTES=64*1024*1024

def flash_path(folder,name):
 if folder not in FLASH_FOLDERS.values():raise BrowserError('Choose a supported Flash folder.')
 safe_argument(name)
 if not name or name in ('.','..') or any(c in name for c in '/\\:*?') or name.endswith((' ','.')):raise BrowserError('Choose an ordinary filename.')
 if len(name.encode('utf-8'))>64:raise BrowserError('Filename is too long.')
 return folder+'/'+name

def read_remote(client,path,max_bytes=MAX_BYTES):
 with operation_event('ftp','read_remote','file'):
  return _read_remote(client,path,max_bytes,MAX_BYTES)

def read_remote_game(client,path,max_bytes,progress=None,check=None):
 """Read one explicitly bounded Game Library source from C64U storage.

 This deliberately separate entry point permits CRT validation up to 64 MiB
 without increasing the general remote-file limit used by other features.
 """
 with operation_event('ftp','read_remote_game','file'):
  return _read_remote(client,path,max_bytes,MAX_GAME_BYTES,progress,check)

def _read_remote(client,path,max_bytes=MAX_BYTES,absolute_max=MAX_BYTES,
                 progress=None,check=None):
 safe_argument(path)
 if type(max_bytes) is not int or not 1<=max_bytes<=absolute_max:raise BrowserError('Invalid remote file size bound.')
 if not ((storage_root(path) and storage_root(path)!=path) or any(path.startswith(folder+'/') for folder in FLASH_FOLDERS.values())) or any(p in ('','.','..') for p in path.split('/')[1:]):raise BrowserError('Choose a USB/SD or supported Flash file.')
 adapter=adapter_for(client)
 if adapter is not None:
  return adapter.read(path,max_bytes,progress=progress,check=check)
 ftp=connect(client)
 try:
  expected=ftp.size(path)
  if expected is None or not 0<expected<=max_bytes:
   limit='16 MB' if max_bytes==MAX_BYTES else f'{max_bytes:,} bytes'
   raise BrowserError(f'File must contain between 1 byte and {limit}.')
  data=bytearray()
  def receive(block):
   if check is not None:check()
   if len(data)+len(block)>max_bytes:raise BrowserError('File exceeds the supported size bound.')
   data.extend(block)
   if progress is not None:progress(len(data),expected)
  ftp.retrbinary('RETR '+path,receive)
  if check is not None:check()
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
  if extension!='.crt' or len(data)<64 or data[:16]!=b'C64 CARTRIDGE   ':raise BrowserError('Choose a C64 .crt cartridge image.')
 else:
  if extension not in ('.bin','.rom','.64c'):raise BrowserError('Choose a .bin, .rom or .64c ROM file.')
 if not folder.endswith('/configs') and len(name.encode('utf-8'))>30:raise BrowserError('Use a ROM or cartridge filename of at most 30 bytes.')

@dataclass(frozen=True)
class FlashEvidence:
    """Safe Flash consequences; never contains the private source bytes."""
    phase: str = 'validation'
    directory: str = ''
    directory_state: str = 'unobserved'
    mkdir: dict | None = None
    upload: UploadEvidence | None = None
    validation: str = 'pending'
    expected_sha256: str = ''
    source_observation: dict | None = None
    acknowledged: tuple[str, ...] = ()
    error_category: str | None = None
    cancellation_phase: str | None = None
    cancellation_requested: bool = False
    local_cleanup: tuple = ()

    @property
    def verified_staged(self):
        return bool(self.upload and self.upload.readback == 'passed' and self.upload.size == 'passed')

    def message(self):
        parts = []
        if self.directory_state == 'acknowledged-created':
            parts.append('Created directory: '+self.directory+'.')
        elif self.directory_state == 'creation-unknown':
            parts.append('Directory creation was not confirmed. Inspect '+self.directory+'.')
        if self.upload and self.upload.disposition == 'published':
            parts.append('Verified staged bytes were published: '+self.upload.destination+'.')
        else:
            parts.append('Flash upload stopped during '+self.phase+'.')
            if self.upload:
                if self.upload.disposition == 'location-unknown':
                    parts.append(self.upload.inspection_message())
                elif self.upload.disposition == 'staging-candidate':
                    parts.append('Possible staging file: '+self.upload.staging+'. Inspect before further action.')
            if self.validation == 'refused':parts.append('Source or destination validation refused before mutation.')
        parts.append('No automatic retry or remote cleanup was attempted.')
        return ' '.join(parts)


def upload_flash(client,folder,name,data,*,check=None,source_observation=None,
                 cancellation_requested=lambda:False):
    with operation_event('ftp','upload_flash','file'):
        return _upload_flash(client,folder,name,data,check=check,
                            source_observation=source_observation,
                            cancellation_requested=cancellation_requested)


def _upload_flash(client,folder,name,data,*,check=None,source_observation=None,
                  cancellation_requested=lambda:False):
    check = check or (lambda:None)
    evidence = FlashEvidence(source_observation=source_observation)
    upload = None
    try:
        # Only immutable private snapshots enter this publisher. Validate before
        # obtaining a mutation-capable lease; never reopen either source.
        if type(data) is not bytes:raise BrowserError('An immutable source snapshot is required.')
        validate_upload(folder,name,data)
        destination = flash_path(folder,name)
        temporary = flash_path(folder,'argonaut-part-'+uuid.uuid4().hex)
        digest = hashlib.sha256(data).hexdigest()
        upload = UploadEvidence('preflight',temporary,destination,len(data))
        evidence = replace(evidence,phase='directory',directory=folder,
                           validation='passed',expected_sha256=digest)
        check()
        adapter = adapter_for(client)
        if adapter is None:raise BrowserError('Flash upload requires a managed Core session.')
        with adapter.operation(check):
            def listing(path):
                actual, entries = adapter.list_directory(path)
                if actual != path:raise BrowserError('Flash directory identity refused.')
                return entries
            def exact_directory(parent,child):
                matches = [e for e in listing(parent) if e.name.casefold()==child.casefold()]
                if not matches:return False
                if len(matches)!=1 or matches[0].name!=child or matches[0].kind!='dir':
                    raise BrowserError('Flash directory identity refused.')
                return True
            def selected():
                if not exact_directory('/','Flash'):raise BrowserError('Flash parent unavailable.')
                return exact_directory('/Flash',posixpath.basename(folder))
            present = selected()
            if not present:
                # Immediately observe the exact parent/child again before MKD.
                present = selected()
            if present:
                evidence = replace(evidence,directory_state='already-present')
            else:
                evidence = replace(evidence,phase='mkdir')
                check()
                created = adapter.mutate('mkdir',folder)
                # No check between the acknowledged reply and recording it.
                evidence = replace(evidence,directory_state='acknowledged-created',
                                   mkdir=created,acknowledged=('directory-created',))
                evidence = replace(evidence,phase='directory-recheck')
                if not selected():raise BrowserError('Created Flash directory unavailable.')
            def absent(path):
                if any(e.name.casefold()==posixpath.basename(path).casefold() for e in listing(folder)):
                    raise BrowserError('Flash filename collision; publication refused.')
            evidence = replace(evidence,phase='preflight')
            absent(destination);absent(temporary)
            evidence = replace(evidence,phase='stor')
            upload = replace(upload,phase='stor')
            with io.BytesIO(data) as stream:
                sent = adapter.write_from(temporary,stream,len(data))
            upload = replace(upload,stor=sent.transfer.as_dict(),disposition='staging-candidate')
            if sent.transferred!=len(data) or sent.sha256!=digest:
                raise BrowserError('Snapshot transfer mismatch.')
            evidence = replace(evidence,phase='readback')
            upload = replace(upload,phase='readback',readback='pending')
            observed = adapter.readback(temporary,len(data))
            if observed.transferred!=len(data) or observed.sha256!=digest:
                raise BrowserError('Flash readback verification failed.')
            evidence = replace(evidence,phase='size')
            upload = replace(upload,phase='size',readback='passed',size='pending')
            if adapter.size(temporary)!=len(data):raise BrowserError('Flash SIZE verification failed.')
            evidence = replace(evidence,phase='destination-recheck')
            upload = replace(upload,phase='destination-recheck',size='passed',destination_recheck='pending')
            if not selected():raise BrowserError('Flash directory disappeared.')
            absent(destination)
            evidence = replace(evidence,phase='publication')
            upload = replace(upload,phase='publication',destination_recheck='passed')
            check()
            publication = adapter.mutate('rename',temporary,destination)
            upload = replace(upload,phase='complete',publication=publication,disposition='published')
            # No cancellation check or read after acknowledged publication.
            return replace(evidence,phase='complete',upload=upload,
                           acknowledged=evidence.acknowledged+('published',),
                           cancellation_requested=cancellation_requested())
    except Exception as exc:
        wire = getattr(exc,'ftp_error',None)
        mutation = getattr(wire,'mutation',None)
        cancelled = bool(getattr(exc,'cancelled',False))
        if evidence.phase == 'validation':evidence = replace(evidence,validation='refused')
        if evidence.phase in ('directory','directory-recheck') and evidence.directory_state!='acknowledged-created':
            evidence = replace(evidence,directory_state='refused')
        if evidence.phase == 'mkdir':
            result = mutation.as_dict() if mutation else None
            evidence = replace(evidence,mkdir=result,directory_state=(
                'creation-unknown' if result and result['consequential_submitted'] and result['outcome']=='unknown'
                else 'refused'))
        category = ('cancelled' if cancelled else 'transport' if wire else
                    'validation' if evidence.validation=='refused' else 'refusal')
        if upload:
            if evidence.phase=='stor' and getattr(wire,'transfer',None):
                stor=wire.transfer.as_dict()
                refused=stor['preliminary_reply'] is not None and stor['preliminary_reply']>=400
                upload=replace(upload,stor=stor,disposition='no-candidate' if refused else
                               'staging-candidate' if stor['submitted'] else 'not-started')
            if evidence.phase=='publication' and mutation:
                result=mutation.as_dict()
                upload=replace(upload,publication=result)
                if result['consequential_submitted'] and result['outcome']=='unknown':
                    upload=replace(upload,disposition='location-unknown')
            upload=replace(upload,error_category=category,error_code=wire.code.value if wire else category,
                           transport_error=wire.as_dict() if wire else None,
                           **{key:'failed' for key in ('readback','size','destination_recheck')
                              if getattr(upload,key)=='pending'})
        evidence=replace(evidence,upload=upload,error_category=category,
                         cancellation_phase=evidence.phase if cancelled else None,
                         cancellation_requested=cancelled or cancellation_requested())
        if cancelled:
            exc.flash_evidence=evidence
            raise
        failure=BrowserError(evidence.message())
        failure.flash_evidence=evidence
        failure.retryable=False
        raise failure from None
