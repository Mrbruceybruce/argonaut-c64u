from .platform_support import publish_new
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Conservative transfers, separate from presentation and device controls."""
import ftplib
import hashlib
import os
from pathlib import Path
import posixpath
import tempfile
import uuid
from .api import BrowserError, safe_argument
from .storage import storage_root
from .diagnostics import operation_event


class UploadFailure(BrowserError):
    def __init__(self,message,partial_path=None):
        super().__init__(message);self.partial_path=partial_path

def remote_file(path):
    safe_argument(path)
    root=storage_root(path)
    if not root or path==root:
        raise BrowserError('Transfers require a file inside a USB or SD drive, without . or .. components.')
    return path


def connect(client):
    if getattr(client, 'credentials_encapsulated', False) is True:
        return client.open_ftp()
    ftp = ftplib.FTP(timeout=client.timeout, encoding=client.encoding)
    try:
        ftp.connect(client.host, client.port)
        ftp.login('anonymous', client.password)
        ftp.set_pasv(True)
        ftp.voidcmd('TYPE I')
        return ftp
    except BaseException:
        ftp.close()
        raise


def download(client, source, destination, progress=lambda n: None):
    with operation_event('ftp', 'download', 'file'):
        return _download(client, source, destination, progress)


def _download(client, source, destination, progress):
    check = getattr(progress, 'check', lambda:None)
    check()
    remote_file(source)
    destination = Path(destination).absolute()
    temporary = None
    ftp = None
    try:
        if os.path.lexists(destination):
            raise BrowserError('Destination already exists; nothing was overwritten.')
        ftp = connect(client)
        expected = ftp.size(source)
        if expected is None:
            raise BrowserError('Server did not provide a file size; download stopped.')
        digest = hashlib.sha256()
        count = 0
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.c64u-', delete=False) as output:
            temporary = output.name
            def receive(block):
                nonlocal count
                check()
                output.write(block)
                digest.update(block)
                count += len(block)
                progress(count)
            ftp.retrbinary('RETR ' + source, receive)
            output.flush()
            os.fsync(output.fileno())
        if count != expected or ftp.size(source) != expected:
            raise BrowserError('Remote size changed or transfer was incomplete; no destination published.')
        # Hard-link publication is atomic and refuses even a concurrently created destination.
        check()
        publish_new(temporary, destination)
        return {'path': str(destination), 'bytes': count, 'sha256': digest.hexdigest()}
    except (OSError, EOFError, ftplib.Error, ValueError) as exc:
        raise BrowserError(f'Download failed: {exc}') from exc
    finally:
        if ftp is not None:
            ftp.close()
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def upload_new_folder(client, source, parent='/USB2', progress=lambda n: None):
    """Never upload into an existing folder; leave uncertain results for inspection."""
    with operation_event('ftp', 'upload_new_folder', 'file'):
        return _upload_new_folder(client, source, parent, progress)


def _upload_new_folder(client, source, parent, progress):
    remote_file(parent + '/placeholder')
    source = Path(source)
    safe_argument(source.name)
    ftp = None
    folder = None
    try:
        with source.open('rb') as input_file:
            if not source.is_file() or os.fstat(input_file.fileno()).st_size == 0:
                raise BrowserError('Choose a nonempty regular file; empty uploads are not yet supported.')
            ftp = connect(client)
            ftp.cwd(parent)
            folder = posixpath.join(parent, 'c64u-transfer-' + uuid.uuid4().hex)
            ftp.mkd(folder)  # A failed creation aborts: never reuse an existing destination.
            ftp.cwd(folder)
            destination = folder + '/' + source.name
            digest = hashlib.sha256()
            count = 0
            def sent(block):
                nonlocal count
                digest.update(block)
                count += len(block)
                progress(count)
            ftp.storbinary('STOR ' + source.name, input_file, callback=sent)
            verified = hashlib.sha256()
            ftp.retrbinary('RETR ' + source.name, verified.update)
            if ftp.size(source.name) != count or digest.digest() != verified.digest():
                raise BrowserError('Upload verification failed.')
            return {'path': destination, 'bytes': count, 'sha256': digest.hexdigest(), 'verified': True}
    except (OSError, EOFError, ftplib.Error, ValueError, BrowserError) as exc:
        if getattr(exc,'cancelled',False):raise
        suffix = f' Inspect {folder!r}; partial files may remain. No automatic retry or deletion.' if folder else ''
        raise BrowserError(f'Upload failed: {exc}.{suffix}') from exc
    finally:
        if ftp is not None:
            ftp.close()


def upload(client, source, parent='/USB2', progress=lambda n: None):
    """Stage and verify a file, then rename into the requested directory."""
    with operation_event('ftp', 'upload', 'file'):
        return _upload(client, source, parent, progress)


def _upload(client, source, parent, progress):
    check = getattr(progress, 'check', lambda:None)
    from .files import child, inspect
    source = Path(source)
    destination = child(parent, source.name)
    temporary = child(parent, 'c64u-part-' + uuid.uuid4().hex)
    ftp = None
    started = False
    try:
        check()
        if inspect(client, destination) is not None:
            raise BrowserError('Destination already exists; upload refused.')
        if inspect(client, temporary) is not None:
            raise BrowserError('Temporary filename exists; upload refused.')
        with source.open('rb') as stream:
            if not source.is_file():
                raise BrowserError('Choose a regular file.')
            ftp = connect(client)
            digest = hashlib.sha256()
            count = 0
            def sent(block):
                nonlocal count
                digest.update(block)
                count += len(block)
                progress(count)
            started = True
            ftp.storbinary('STOR ' + temporary, stream, callback=sent)
            verified = hashlib.sha256()
            def verify(block):
                check()
                verified.update(block)
            ftp.retrbinary('RETR ' + temporary, verify)
            if ftp.size(temporary) != count or digest.digest() != verified.digest():
                raise BrowserError('Upload verification failed.')
            # Recheck immediately before publishing. FTP has no atomic no-replace rename.
            if inspect(client, destination) is not None:
                raise BrowserError('Destination appeared during transfer; publish refused.')
            check()
            ftp.rename(temporary, destination)
            return {'path': destination, 'bytes': count, 'sha256': digest.hexdigest(), 'verified': True}
    except (OSError, EOFError, ftplib.Error, ValueError, BrowserError) as exc:
        if getattr(exc,'cancelled',False):
            if started:setattr(exc,'partial_path',temporary)
            raise
        recovery = f' Inspect {temporary!r} and {destination!r}; no automatic retry or deletion.' if started else ''
        raise UploadFailure(f'Upload failed: {exc}.{recovery}',temporary if started else None) from exc
    finally:
        if ftp is not None: ftp.close()
