# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""USB/SD directory operations with validated paths."""
import posixpath
import uuid
from dataclasses import dataclass
from .ftp_reads import adapter_for
from .api import BrowserError, safe_argument
from .transfers import remote_file
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


def _operate(client, action, path, new_name, confirmation, managed):
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
    return managed(entry, destination, case_only, temporary, parent)


@dataclass(frozen=True)
class MutationResult:
    operation: str
    source: str
    destination: str | None = None
    temporary: str | None = None
    completed: tuple[dict, ...] = ()
    stopped: dict | None = None
    verification: str = 'not-required'


def operate_managed(client, action, path, new_name=None, confirmation=None, check=None):
    """Validate and mutate only within an explicit managed operation."""
    adapter = adapter_for(client)
    if adapter is None:
        raise BrowserError('This operation requires a Core-managed C64U session.')
    completed = []
    destination = temporary = None
    verification = 'not-required'

    def execute(entry, target, case_only, intermediate, parent):
        nonlocal destination, temporary, verification
        destination, temporary = target, intermediate
        if action == 'rename':
            if case_only:
                verification = 'unperformed'
                with adapter.defer_cancellation():
                    completed.append(adapter.mutate('rename', path, temporary))
                    completed.append(adapter.mutate('rename', temporary, destination))
                _, entries = client.list_directory(parent)
                if not any(e.name == new_name for e in entries):
                    verification = 'failed'
                    raise BrowserError('Server did not report the requested letter case. Refresh to inspect the resulting name.')
                verification = 'passed'
            else:completed.append(adapter.mutate('rename', path, destination))
        else:
            verb = 'mkdir' if action == 'mkdir' else 'rmdir' if entry.kind == 'dir' else 'delete'
            completed.append(adapter.mutate(verb, path))
        return destination or path

    with operation_event('ftp', 'file_' + action, 'entry'):
        try:
            with adapter.operation(check):
                result = _operate(client, action, path, new_name, confirmation, managed=execute)
            return MutationResult(action, path, destination or result, temporary,
                                  tuple(completed), verification=verification)
        except Exception as exc:
            error = getattr(exc, 'ftp_error', None)
            evidence = getattr(error, 'mutation', None)
            exc.result = MutationResult(action, path, destination, temporary,
                tuple(completed), evidence.as_dict() if evidence is not None else None,
                verification)
            raise
