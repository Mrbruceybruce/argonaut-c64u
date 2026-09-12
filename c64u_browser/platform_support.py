# SPDX-License-Identifier: GPL-3.0-or-later
"""Small platform boundaries for paths, storage, and atomic file publication."""
import os
import posixpath
import sys
from pathlib import Path

def portable_root():
    if getattr(sys,"frozen",False):
        root=Path(sys.executable).resolve().parent
        if (root/"portable.flag").is_file():return root
    return None

def config_base():
    root=portable_root()
    if root is not None:return root/"Data"
    if sys.platform == 'win32':
        return Path(os.environ.get('APPDATA') or Path.home()/'AppData'/'Roaming')
    base=os.environ.get('XDG_CONFIG_HOME','')
    return Path(base) if base and Path(base).is_absolute() else Path.home()/'.config'

def publish_new(temporary,destination):
    # Windows rename refuses an existing destination and also works on FAT/exFAT.
    if sys.platform == 'win32':os.rename(temporary,destination)
    else:os.link(temporary,destination)

def parents(path,local):
    parent=lambda p:str(Path(p).parent) if local else posixpath.dirname(p)
    current=parent(str(path))
    while current and parent(current)!=current:
        yield current
        current=parent(current)

def local_roots():
    if sys.platform != 'win32':return [('Computer','/','drive-harddisk-symbolic')]
    import ctypes
    mask=ctypes.windll.kernel32.GetLogicalDrives()
    return [(chr(65+i)+':',chr(65+i)+':\\','drive-removable-media-symbolic') for i in range(26) if mask & (1<<i)]

def contains_path(root,path):
    try:Path(path).relative_to(root);return True
    except ValueError:return False
