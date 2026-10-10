# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Storage discovery is independent of USB/SD operation authorization."""
import re


def recognized_root(path):
    """Exact Files browsing paths; never an authorization to mutate or launch."""
    if not isinstance(path, str) or not path.startswith('/'):
        return None
    parts = path.split('/')[1:]
    if not parts or not re.fullmatch(r'USB[0-9]+|SD|Flash|Temp', parts[0]):
        return None
    if any(p in ('', '.', '..') or '\\' in p or
           any(ord(c) < 32 or ord(c) == 127 for c in p) for p in parts):
        return None
    return '/' + parts[0]


def storage_root(path):
    """Legacy USB/SD operation gate. Visibility must never widen this contract."""
    root = recognized_root(path)
    return root if root and root not in ('/Flash', '/Temp') else None


def require_file_operation(path, *, parent=False):
    """Authorize generic file operations; native Flash keeps its separate route."""
    from .api import BrowserError
    root = storage_root(path)
    if root is None or (not parent and path == root):
        raise BrowserError('This operation requires a file or folder inside USB/SD storage. '
                           'Flash and Temp support browsing only in Files.')
    return path


def root_presentation(path):
    root = recognized_root(path)
    if root == '/Flash':
        return ('Flash', 'drive-harddisk-solidstate-symbolic',
                'Flash — Internal Memory · Browsing only in Files; validated additions remain in Ultimate Menu → Flash files.')
    if root == '/Temp':
        return ('Temp', 'argonaut-ram-symbolic',
                'Temp — RAM Disk · Temporary storage; keep important files elsewhere. Browsing only in Files.')
    if root == '/SD':
        return ('SD', 'argonaut-sd-symbolic', '')
    if root:
        return (root[1:], 'argonaut-usb-symbolic', '')
    return ('', '', '')


def browse_directory(client, path):
    """Use the existing managed listing; reject traversal and redirected paths."""
    from .api import BrowserError
    if recognized_root(path) is None:
        raise BrowserError('Choose an exact USB, SD, Flash or Temp storage path.')
    from .api import ConnectionFailure
    try:
        actual, entries = client.list_directory(path)
    except ConnectionFailure:
        raise  # Preserve Browser's existing connection-recovery classification.
    except BrowserError as exc:
        raise BrowserError('Storage unavailable at '+path+': '+str(exc)) from exc
    if actual != path:
        raise BrowserError('Storage path changed or is unavailable: ' + path)
    return actual, entries


def discover(client):
    from .api import BrowserError
    actual, entries = client.list_directory('/')
    if actual != '/':
        raise BrowserError('C64U storage discovery returned a different root.')
    roots = sorted({'/' + e.name for e in entries
                    if e.kind == 'dir' and recognized_root('/' + e.name) == '/' + e.name
                    and '/' not in e.name})
    client.storage_roots = roots
    return roots


def initial_directory(client, preferred='/USB2'):
    roots = discover(client)
    if recognized_root(preferred) in roots and preferred not in roots:
        from .api import BrowserError
        try:
            return browse_directory(client, preferred)
        except BrowserError:
            from .ftp_reads import end_read_attempt
            end_read_attempt(client)
            preferred = recognized_root(preferred)
    # Preserve the existing USB/SD fallback ahead of newly visible locations.
    candidates = [r for r in roots if storage_root(r)] + [r for r in roots if not storage_root(r)]
    target = preferred if preferred in roots else next(iter(candidates), None)
    return browse_directory(client, target) if target else ('/', [])
