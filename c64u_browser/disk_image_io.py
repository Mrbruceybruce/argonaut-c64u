# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Safe D64 loading and no-replace extraction boundaries."""
import os
from pathlib import Path
import posixpath
import tempfile

from .api import BrowserError
from .disk_image import D64Image, D71Image, D81Image, DiskDirectoryEntry
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


def create_remote_blank_d64(client, path, disk_name):
    """Create via the C64U API, then read back and validate the exact result."""
    from .files import inspect
    if inspect(client, path) is not None:
        raise BrowserError(
            'That filename already exists on the C64U. Choose another filename; '
            'nothing was overwritten.')
    client.create_d64(path, disk_name)
    try:
        image = read_remote_d64(client, path)
        directory = image.directory()
        validation = image.validate()
        if (len(image.source_bytes) != 174848 or directory.entries
                or directory.blocks_free != 664
                or not validation.standard_compatible):
            raise BrowserError('The created image did not pass blank-D64 validation.')
        return image
    except Exception as exc:
        raise BrowserError(
            'The C64U reported success, but the new image could not be validated. '
            'Inspect it before retrying. ' + str(exc)) from exc


def read_local_d71(path):
    with operation_event('disk_image', 'open_local', 'd71'):
        path = Path(path)
        if path.suffix.casefold() != '.d71' or path.is_symlink() or not path.is_file():
            raise BrowserError('Choose a regular local D71 image.')
        with path.open('rb') as stream:
            data = stream.read(351063)
        image = D71Image(data)
        image.directory()
        return image


def read_remote_d71(client, path):
    with operation_event('disk_image', 'open_remote', 'd71'):
        if (not storage_root(path) or storage_root(path) == path
                or posixpath.splitext(path)[1].casefold() != '.d71'):
            raise BrowserError('Choose a D71 image inside a C64U USB or SD drive.')
        image = D71Image(read_remote(client, path))
        image.directory()
        return image


def read_local_d81(path):
    with operation_event('disk_image', 'open_local', 'd81'):
        path = Path(path)
        if path.suffix.casefold() != '.d81' or path.is_symlink() or not path.is_file():
            raise BrowserError('Choose a regular local D81 image.')
        with path.open('rb') as stream:
            data = stream.read(822401)
        image = D81Image(data)
        image.directory()
        return image


def read_remote_d81(client, path):
    with operation_event('disk_image', 'open_remote', 'd81'):
        if (not storage_root(path) or storage_root(path) == path
                or posixpath.splitext(path)[1].casefold() != '.d81'):
            raise BrowserError('Choose a D81 image inside a C64U USB or SD drive.')
        image = D81Image(read_remote(client, path))
        image.directory()
        return image


def read_local_disk_image(path):
    suffix = Path(path).suffix.casefold()
    if suffix == '.d64':
        return read_local_d64(path)
    if suffix == '.d71':
        return read_local_d71(path)
    if suffix == '.d81':
        return read_local_d81(path)
    raise BrowserError('Choose a supported D64, D71 or D81 disk image.')


def read_remote_disk_image(client, path):
    suffix = posixpath.splitext(path)[1].casefold()
    if suffix == '.d64':
        return read_remote_d64(client, path)
    if suffix == '.d71':
        return read_remote_d71(client, path)
    if suffix == '.d81':
        return read_remote_d81(client, path)
    raise BrowserError('Choose a supported D64, D71 or D81 disk image.')


def read_host_file_for_d64(path):
    """Read one bounded regular host file for a staged D64 import."""
    return read_host_file_for_disk(path, 174848)


def read_host_file_for_disk(path, maximum_size):
    """Read one bounded regular host file for a staged disk-image import."""
    with operation_event('disk_image', 'import_host_file', 'file'):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise BrowserError('Choose a regular local file to add to the disk copy.')
        if path.stat().st_size > maximum_size:
            raise BrowserError('The selected file is too large for this disk image.')
        return path.read_bytes()


def suggested_import_type(path, data):
    """Choose a conservative Commodore disk type for one host file.

    Text BASIC source is not a loadable PRG merely because its host suffix is
    ``.bas``.  A tokenized C64 BASIC program normally carries the $0801 load
    address; other .bas files default to SEQ and remain editable in the review
    dialog before anything is staged.
    """
    suffix = Path(path).suffix.casefold()
    if suffix == '.seq':
        return 'SEQ'
    if suffix == '.usr':
        return 'USR'
    if suffix == '.bas':
        return 'PRG' if len(data) >= 2 and data[:2] == b'\x01\x08' else 'SEQ'
    return 'PRG'


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


def save_edited_copy(session, destination):
    """Validate and atomically publish a staged image under a new local name."""
    from .disk_image_edit import D64EditSession
    if not isinstance(session, D64EditSession):
        raise TypeError('session must be a supported disk edit session')
    with operation_event('disk_image', 'save_copy', session.format_name.casefold()):
        if not session.dirty:
            raise BrowserError('Stage at least one disk change before saving a copy.')
        destination = Path(destination).absolute()
        if destination.suffix.casefold() != session.extension:
            raise BrowserError(
                f'Save the edited disk copy with a {session.extension} filename.')
        if not destination.parent.is_dir():
            raise BrowserError('Choose an existing destination folder.')
        data = session.validated_bytes()
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
                raise BrowserError('Destination already exists; the original and staged image were unchanged.') from exc
            session.mark_saved()
            return {'path': str(destination), 'bytes': len(data),
                    'changes': len(session.changes)}
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)


def create_blank_d64(destination, disk_name, disk_id):
    """Create and atomically publish one validated standard D64 without replacement."""
    from .disk_image_edit import create_blank_d64_image
    destination = Path(destination).absolute()
    with operation_event('disk_image', 'publish_blank', 'd64'):
        if destination.suffix.casefold() != '.d64':
            raise BrowserError('Save the new disk with a .d64 filename.')
        if not destination.parent.is_dir():
            raise BrowserError('Choose an existing destination folder.')
        image = create_blank_d64_image(disk_name, disk_id)
        data = image.source_bytes
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
            return {'path': str(destination), 'bytes': len(data), 'image': image}
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
