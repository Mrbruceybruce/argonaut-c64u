from .platform_support import publish_new
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""File-only copies; remote work shares the verified transfer implementation."""
import hashlib
import os
from pathlib import Path
import tempfile
from .api import BrowserError
from .files import child
from .transfers import download, upload, UploadFailure


def conflicts(client, names, local, destination):
    if local:
        return tuple(name for name in names if os.path.lexists(Path(destination) / name))
    _, entries = client.list_directory(destination)
    existing = {entry.name.casefold() for entry in entries}
    return tuple(name for name in names if name.casefold() in existing)


def local_copy(source, destination, progress):
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise BrowserError('The source must still be a regular file.')
    if os.path.lexists(destination):
        raise BrowserError('Destination already exists; nothing was overwritten.')
    temporary = None
    try:
        with source.open('rb') as input_file, tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.c64u-', delete=False) as output:
            temporary = output.name
            before = os.fstat(input_file.fileno())
            digest = hashlib.sha256()
            count = 0
            while block := input_file.read(1024 * 1024):
                output.write(block); digest.update(block)
                count += len(block); progress(count)
            output.flush(); os.fsync(output.fileno())
            after = os.fstat(input_file.fileno())
        if count != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise BrowserError('Source changed during copy; no destination published.')
        verified = hashlib.sha256()
        with open(temporary, 'rb') as check:
            while block := check.read(1024 * 1024):
                getattr(progress, 'check', lambda:None)()
                verified.update(block)
        if verified.digest() != digest.digest():
            raise BrowserError('Copy verification failed.')
        getattr(progress, 'check', lambda:None)()
        publish_new(temporary, destination)
        return {'path': str(destination)}
    finally:
        if temporary is not None and os.path.exists(temporary): os.unlink(temporary)


def copy_files(client, source_local, parent, names, local, destination, progress=lambda n: None):
    results = []
    for name in names:
        try:
            child('/USB2', name)
            if source_local and local:
                result = local_copy(Path(parent) / name, Path(destination) / name, progress)
            elif source_local:
                result = upload(client, Path(parent) / name, destination, progress)
            elif local:
                result = download(client, child(parent, name), Path(destination) / name, progress)
            else:
                # Remote-to-remote uses a verified upload after downloading locally.
                with tempfile.TemporaryDirectory(prefix='argonaut-copy-') as folder:
                    staged = Path(folder) / name
                    download(client, child(parent, name), staged, progress)
                    result = upload(client, staged, destination, progress)
            results.append(result['path'])
        except Exception as exc:
            return (f'{len(results)} of {len(names)} copied. Stopped at {name!r}: {exc}. Completed paths: {results}',
                    exc.partial_path if isinstance(exc, UploadFailure) else None)
    return f'Copied {len(results)} file(s): ' + ', '.join(results), None
