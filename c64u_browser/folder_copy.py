from .platform_support import parents, contains_path
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Read-only recursive planning followed by conservative, sequential copying."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import posixpath
from .api import BrowserError
from .files import child, operate
from .file_copy import copy_files
from .replacement import signature, replace_file

@dataclass
class Step:
    relative: str
    source: object
    destination: object
    directory: bool
    existed: bool = False
    signature: object = None

@dataclass
class Plan:
    steps: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    replacements: list = field(default_factory=list)

@dataclass
class Report:
    completed: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    remaining: list = field(default_factory=list)
    error: str = ''
    partial: str = None
    cancelled: bool = False

    @property
    def message(self):
        return f'{len(self.completed)} items completed; {len(self.skipped)} skipped; {len(self.remaining)} unfinished.' + (' Stopped: ' + self.error if self.error else '')

    def details(self):
        return self.message + ''.join('\n\n'+title+':\n'+'\n'.join(items) for title,items in
            [('Completed',self.completed),('Skipped',self.skipped),('Unfinished (first item failed)',self.remaining)] if items) + ('\n\nPartial upload: '+self.partial if self.partial else '')


def completed_roots(requested, completed):
    """Return requested top-level names that have a completed copy step."""
    roots = {relative.rstrip('/').split('/', 1)[0] for relative in completed}
    return tuple(name for name in requested if name in roots)


def kind(client, local, path):
    if local:
        path = Path(path)
        if path.is_symlink(): return 'unsupported'
        if not os.path.lexists(path): return None
        return 'dir' if path.is_dir() else 'file' if path.is_file() else 'unsupported'
    parent, name = posixpath.split(path)
    _, entries = client.list_directory(parent)
    entry = next((e for e in entries if e.name.casefold()==name.casefold()),None)
    if entry is None: return None
    # Do not merge into a differently cased remote directory.
    return entry.kind if entry.name==name else 'unsupported'


def build_plan(client, source_local, parent, names, local, destination, check=lambda:None):
    plan = Plan()
    destination = Path(destination).resolve() if local else destination
    parent = Path(parent).resolve() if source_local else parent
    seen = set()
    def visit(source, dest, relative, destination_parent_exists=True, depth=0):
        check()
        if depth > 64 or len(plan.steps)+len(plan.conflicts) >= 10000:
            raise BrowserError('Folder copy exceeds the limit of 10,000 items or 64 levels; select smaller folders.')
        source_kind = kind(client,source_local,source)
        if source_kind not in ('dir','file'):
            raise BrowserError(f'Source is missing or unsupported (links are not copied): {source}')
        if source_kind == 'dir' and source_local == local:
            src = str(Path(source).resolve()) if local else str(source).casefold()
            dst = str(destination) if local else str(destination).casefold()
            if (contains_path(src,dst) if local else dst == src or dst.startswith(src.rstrip('/')+'/')):
                raise BrowserError('A folder cannot be copied into itself or one of its subfolders.')
        key = str(dest) if local else str(dest).casefold()
        if key in seen: raise BrowserError('Two source names map to the same destination: '+str(dest))
        seen.add(key)
        target_kind = kind(client,local,dest) if destination_parent_exists else None
        if target_kind is not None and not (source_kind == target_kind == 'dir'):
            plan.conflicts.append(relative)
            if source_kind==target_kind=='file':
                same=(Path(source).resolve()==Path(dest).resolve()) if local and source_local else (str(source).casefold()==str(dest).casefold() if not local and not source_local else False)
                if not same:plan.replacements.append(Step(relative,source,dest,False,True,signature(client,local,dest)))
            return
        plan.steps.append(Step(relative,source,dest,source_kind=='dir',target_kind is not None))
        if source_kind == 'dir':
            if source_local:
                children = sorted(p.name for p in Path(source).iterdir())
            else:
                _, entries = client.list_directory(source)
                children = sorted(e.name for e in entries)
            for name in children:
                child('/USB2',name)
                visit(Path(source)/name if source_local else child(source,name),
                      Path(dest)/name if local else child(dest,name),relative+'/'+name,
                      target_kind == 'dir',depth+1)
    for name in names:
        child('/USB2',name)
        visit(Path(parent)/name if source_local else child(parent,name),
              destination/name if local else child(destination,name),name)
    return plan


def execute_plan(client, plan, source_local, local, progress=lambda n:None):
    report = Report(skipped=list(plan.conflicts))
    checked_directories = set()
    for index,step in enumerate(plan.steps):
        try:
            getattr(progress, 'check', lambda:None)()
            if kind(client,source_local,step.source) != ('dir' if step.directory else 'file'):
                raise BrowserError('Source changed since the copy was prepared: '+str(step.source))
            # Recheck every destination ancestor used by this plan, so a changed
            # directory cannot redirect later writes through a local symlink.
            for ancestor in parents(step.destination,local):
                if ancestor in checked_directories and kind(client,local,ancestor) != 'dir':
                    raise BrowserError('Destination folder changed: '+ancestor)
            target_kind = kind(client,local,step.destination)
            if step.signature is not None:
                replace_file(client,step,source_local,local,progress)
            elif step.directory:
                if step.existed:
                    if target_kind != 'dir': raise BrowserError('Destination folder changed: '+str(step.destination))
                elif target_kind is not None:
                    raise BrowserError('Destination appeared after review: '+str(step.destination))
                elif local: Path(step.destination).mkdir()
                else: operate(client,'mkdir',step.destination)
                checked_directories.add(str(step.destination))
            else:
                if target_kind is not None: raise BrowserError('Destination appeared after review: '+str(step.destination))
                parent = Path(step.source).parent if source_local else posixpath.dirname(step.source)
                dest_parent = Path(step.destination).parent if local else posixpath.dirname(step.destination)
                name = Path(step.source).name if source_local else posixpath.basename(step.source)
                message, partial = copy_files(client,source_local,parent,[name],local,dest_parent,progress)
                if not message.startswith('Copied 1 file(s):'):
                    report.partial = partial
                    raise BrowserError(message)
            report.completed.append(step.relative + ('/' if step.directory else ''))
        except Exception as exc:
            report.error = str(exc)
            report.cancelled = bool(getattr(exc,'cancelled',False))
            if report.cancelled:
                report.partial=getattr(exc,'partial_path',report.partial)
            report.remaining = [s.relative for s in plan.steps[index:]]
            break
    return report
