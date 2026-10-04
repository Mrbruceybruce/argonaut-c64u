from .platform_support import parents
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Review a bounded deletion snapshot; never recursively delete unseen entries."""
from dataclasses import dataclass
from contextlib import nullcontext
from pathlib import Path
import stat
from .api import BrowserError
from .storage import storage_root
from .files import child, inspect, operate_managed
from .ftp_reads import adapter_for

@dataclass(frozen=True)
class Item:
    path: str
    kind: str
    fingerprint: tuple


def snapshot(client, local, path):
    if local:
        info=Path(path).lstat()
        kind='dir' if stat.S_ISDIR(info.st_mode) else 'link' if stat.S_ISLNK(info.st_mode) else 'file'
        signature=(info.st_dev,info.st_ino,info.st_mode)
        if kind!='dir': signature+=(info.st_size,info.st_mtime_ns)
    else:
        entry=inspect(client,path)
        if entry is None or entry.name!=path.rsplit('/',1)[-1] or entry.kind not in ('file','dir'):
            raise BrowserError('Entry changed or unsupported: '+path)
        kind=entry.kind;signature=(kind,entry.size if kind=='file' else None)
    return Item(str(path),kind,signature)


def prepare(client,local,targets,check=lambda:None):
    items=[];seen=set()
    def visit(path,depth=0):
        check()
        path=str(path)
        if path in seen:return
        if depth>64 or len(seen)>=10000:raise BrowserError('Select fewer than 10,000 items and 64 folder levels.')
        seen.add(path)
        if local and Path(path).absolute().parent==Path(path).absolute():raise BrowserError('Cannot delete the filesystem root.')
        if not local and (path=='/' or storage_root(path)==path):raise BrowserError('Cannot delete a storage root.')
        item=snapshot(client,local,path)
        if item.kind=='dir':
            if local:children=sorted(str(p) for p in Path(path).iterdir())
            else:children=sorted(child(path,e.name) for e in client.list_directory(path)[1])
            for sub in children:visit(sub,depth+1)
        items.append(item)
    for target in targets:visit(target)
    return tuple(items)


@dataclass
class DeletionReport:
    removed: list
    stopped_target: str | None = None
    mutation: object = None
    not_attempted: tuple[str, ...] = ()
    error: Exception | None = None


def delete_reviewed(client,local,targets,items,check=lambda:None):
    managed=not local
    adapter=adapter_for(client) if managed else None
    removed=[]
    try:
        if managed and adapter is None:
            raise BrowserError('Reviewed remote deletion requires a Core-managed session.')
        with adapter.operation(check) if adapter is not None else nullcontext():
            return _delete_items(client,local,targets,items,check,managed,removed)
    except Exception as exc:
        # _delete_items carries the exact stopped item and completed prefix.
        report=getattr(exc,'deletion_report',None)
        if report is None:
            report=DeletionReport(removed,not_attempted=tuple(i.path for i in items),error=exc)
        return report if managed else (removed,str(exc))


def _delete_items(client,local,targets,items,check,managed,removed):
    current=None
    try:
        check()
        if prepare(client,local,targets,check)!=items:
            raise BrowserError('Contents changed since review. Review the deletion again.')
        directories={i.path:i for i in items if i.kind=='dir'}
        for item in items:
            current=item.path
            check()
            for parent in parents(item.path,local):
                if parent in directories and snapshot(client,local,parent)!=directories[parent]:
                    raise BrowserError('Parent folder changed: '+parent)
            if snapshot(client,local,item.path)!=item:
                raise BrowserError('Item changed since review: '+item.path)
            if local:
                if item.kind=='dir':Path(item.path).rmdir()
                else:Path(item.path).unlink()
            else:
                operate_managed(client,'delete',item.path,confirmation=item.path)
            removed.append(item.path)
        return DeletionReport(removed) if managed else (removed,None)
    except Exception as exc:
        result=getattr(exc,'result',None)
        mutation=getattr(result,'stopped',None)
        attempted=bool(mutation and mutation['consequential_submitted'])
        removed_set=set(removed)
        pending=tuple(i.path for i in items if i.path not in removed_set and
                      not (attempted and i.path==current))
        exc.deletion_report=DeletionReport(removed,current,mutation,pending,exc)
        raise
