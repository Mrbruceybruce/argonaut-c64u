# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Explicit, reviewed regular-file replacement with a verified staged copy."""
import hashlib
import os
from pathlib import Path
import posixpath
import tempfile
import uuid
from .api import BrowserError
from .files import inspect, operate, child
from .transfers import connect
from .file_copy import copy_files
from .diagnostics import operation_event

def signature(client,local,path):
 if local:
  p=Path(path)
  if p.is_symlink() or not p.is_file():raise BrowserError('Replacement target is not a regular file.')
  s=p.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
 e=inspect(client,path)
 if e is None or e.kind!='file' or e.name!=posixpath.basename(path):raise BrowserError('Replacement target changed.')
 return (e.name,e.size)

def replace_file(client,step,source_local,local,progress):
 with operation_event('local' if local else 'ftp','replace_file','file'):
  return _replace_file(client,step,source_local,local,progress)

def _replace_file(client,step,source_local,local,progress):
 check=getattr(progress,'check',lambda:None)
 check()
 if signature(client,local,step.destination)!=step.signature:raise BrowserError('Replacement target changed since review.')
 source_parent=Path(step.source).parent if source_local else posixpath.dirname(step.source)
 name=Path(step.source).name
 def stage(folder):
  message,partial=copy_files(client,source_local,source_parent,[name],local,folder,progress)
  if not message.startswith('Copied 1 file(s):'):raise BrowserError(message+(f' Partial upload: {partial}' if partial else ''))
 if local:
  destination=Path(step.destination)
  with tempfile.TemporaryDirectory(prefix='.argonaut-replace-',dir=destination.parent) as folder:
   stage(folder);check()
   if signature(client,True,destination)!=step.signature:raise BrowserError('Replacement target changed during copy.')
   os.replace(Path(folder)/name,destination)
  return
 # FTP has no atomic exchange. Keep the old file until the staged file is published.
 destination_parent=posixpath.dirname(step.destination)
 folder=child(destination_parent,'c64u-replace-'+uuid.uuid4().hex)
 backup=child(destination_parent,'c64u-old-'+uuid.uuid4().hex)
 ftp=None
 try:
  operate(client,'mkdir',folder)
  # Verify the original content is unchanged across the staged transfer as well.
  ftp=connect(client)
  digest=hashlib.sha256()
  def original(block):check();digest.update(block)
  ftp.retrbinary('RETR '+step.destination,original)
  before=digest.digest()
  stage(folder);check()
  if signature(client,False,step.destination)!=step.signature:raise BrowserError('Replacement target changed during copy.')
  digest=hashlib.sha256();ftp.retrbinary('RETR '+step.destination,original)
  if digest.digest()!=before:raise BrowserError('Replacement target contents changed during copy.')
  check()
  if inspect(client,backup) is not None:raise BrowserError('Backup name already exists.')
  ftp.rename(step.destination,backup)
  # Finish the exchange even if cancellation arrives between the two renames.
  ftp.rename(child(folder,name),step.destination)
  ftp.delete(backup);ftp.rmd(folder)
 except Exception as exc:
  raise BrowserError(f'Replacement could not be verified: {exc}. Inspect {step.destination}, staging folder {folder}, and original backup {backup} before retrying. No automatic rollback was attempted.') from exc
 finally:
  if ftp:ftp.close()
