# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Explicit, reviewed regular-file replacement with a verified staged copy."""
import os
from pathlib import Path
import posixpath
import tempfile
from .api import BrowserError
from .files import inspect
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
 if not local:raise BrowserError('Remote replacement requires the managed replacement operation.')
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
