# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Safe D64 loading and no-replace extraction boundaries."""
import os
from pathlib import Path
import posixpath
import tempfile

from .api import BrowserError
from .disk_image import D64Image, DiskDirectoryEntry
from .diagnostics import operation_event
from .native_files import read_remote
from .platform_support import publish_new
from .storage import storage_root


def read_local_d64(path):
    with operation_event('disk_image', 'open_local', 'd64'):
        path = Path(path)
        if path.suffix.casefold() != '.d64' or path.is_symlink() or not path.is_file():
            raise BrowserError('Choose a regular local D64 image.')
        # All recognized D64 forms are smaller than this fixed bound.
        with path.open('rb') as stream:
            data = stream.read(206115)
        image = D64Image(data)
        image.directory()
        return image


def read_remote_d64(client, path):
    with operation_event('disk_image', 'open_remote', 'd64'):
        if (not storage_root(path) or storage_root(path) == path
                or posixpath.splitext(path)[1].casefold() != '.d64'):
            raise BrowserError('Choose a D64 image inside a C64U USB or SD drive.')
        image = D64Image(read_remote(client, path))
        image.directory()
        return image


def suggested_name(entry):
    if not isinstance(entry, DiskDirectoryEntry):
        raise TypeError('entry must be a DiskDirectoryEntry')
    stem = ''.join(character if character.isalnum() or character in ' ._-' else '_'
                   for character in entry.name).strip(' .') or 'disk-file'
    suffix = '.' + entry.file_type.casefold() if entry.file_type in ('PRG', 'SEQ', 'USR', 'REL') else ''
    return stem + suffix


def extract_new(image, entry, destination):
    """Extract one CBM file atomically without replacing an existing host file."""
    with operation_event('disk_image', 'extract', 'file'):
        return _extract_new(image, entry, destination)


def _extract_new(image, entry, destination):
    if not isinstance(image, D64Image):
        raise TypeError('image must be a D64Image')
    destination = Path(destination).absolute()
    if not destination.parent.is_dir():
        raise BrowserError('Choose an existing destination folder.')
    data = image.read_file(entry)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix='.argonaut-disk-', delete=False) as stream:
            temporary = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            publish_new(temporary, destination)
        except FileExistsError as exc:
            raise BrowserError('Destination already exists; nothing was overwritten.') from exc
        return {'path': str(destination), 'bytes': len(data)}
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
