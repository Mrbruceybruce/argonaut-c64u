# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""USB/SD directory operations with validated paths."""
import ftplib
import posixpath
import uuid
from .api import BrowserError, safe_argument
from .transfers import connect, remote_file
from .diagnostics import operation_event


def child(parent, name):
    safe_argument(name)
    if not name or name in ('.', '..') or any(c in name for c in '/\\:*?') or name.endswith((' ', '.')):
        raise BrowserError('Use a single ordinary filename without slash, wildcard, or trailing dot/space.')
    return remote_file(parent + '/' + name)


def inspect(client, path):
    remote_file(path)
    parent, name = posixpath.split(path)
    _, entries = client.list_directory(parent)
    return next((e for e in entries if e.name.casefold() == name.casefold()), None)


def operate(client, action, path, new_name=None, confirmation=None):
    logged_action = action if action in ('mkdir', 'rename', 'delete') else 'unknown'
    with operation_event('ftp', 'file_' + logged_action, 'entry'):
        return _operate(client, action, path, new_name, confirmation)


def _operate(client, action, path, new_name, confirmation):
    remote_file(path)
    parent, name = posixpath.split(path)
    child(parent, name)
    if action == 'delete' and confirmation != path:
        raise BrowserError('Deletion requires confirmation of the exact path, including letter case.')
    entry = inspect(client, path)
    destination = None
    case_only = False
    temporary = None
    if action == 'mkdir':
        if entry is not None:
            raise BrowserError('That name already exists.')
    elif action in ('rename', 'delete'):
        if entry is None or entry.name != name or entry.kind not in ('file', 'dir'):
            raise BrowserError('Entry changed or is unsupported; refresh before continuing.')
        if action == 'rename':
            destination = child(parent, new_name or '')
            if destination == path:
                return path
            case_only = name.casefold() == new_name.casefold()
            _, siblings = client.list_directory(parent)
            conflicts = [e for e in siblings if e.name.casefold() == new_name.casefold()
                         and not (case_only and e.name == name)]
            if conflicts:
                raise BrowserError('Destination already exists; rename refused.')
            if case_only:
                temporary = child(parent, 'c64u-rename-' + uuid.uuid4().hex)
                if inspect(client, temporary) is not None:
                    raise BrowserError('Temporary rename name exists; retry after refreshing.')
        else:
            if confirmation != path:
                raise BrowserError('Deletion requires confirmation of the exact path.')
            if entry.kind == 'dir' and client.list_directory(path)[1]:
                raise BrowserError('Folder is not empty; recursive deletion is disabled.')
    else:
        raise BrowserError('Unknown file operation.')
    ftp = None
    try:
        ftp = connect(client)
        if action == 'mkdir': ftp.mkd(path)
        elif action == 'rename':
            if case_only:
                # A distinct intermediate name avoids case-insensitive self-renames.
                ftp.rename(path, temporary)
                ftp.rename(temporary, destination)
                _, entries = client.list_directory(parent)
                if not any(e.name == new_name for e in entries):
                    raise BrowserError('Server did not report the requested letter case. Refresh to inspect the resulting name.')
            else:
                ftp.rename(path, destination)
        elif entry.kind == 'dir': ftp.rmd(path)
        else: ftp.delete(path)
        return destination or path
    except (OSError, EOFError, ftplib.Error) as exc:
        raise BrowserError(f'{action} failed: {exc}. Refresh to check the result before retrying.'
                           + (f' The item may be named {temporary!r} or {destination!r}; no automatic rollback was attempted.' if temporary else '')) from exc
    finally:
        if ftp is not None: ftp.close()
