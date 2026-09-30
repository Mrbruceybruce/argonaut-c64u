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
from dataclasses import dataclass, replace
from .api import BrowserError, safe_argument
from .storage import storage_root
from .diagnostics import operation_event
from .ftp_reads import adapter_for


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


def download(client, source, destination, progress=lambda n: None, *, preserve_cleanup=False):
    with operation_event('ftp', 'download', 'file'):
        return _download(client, source, destination, progress, preserve_cleanup=preserve_cleanup)


def _download(client, source, destination, progress, *, preserve_cleanup=False):
    check = getattr(progress, 'check', lambda:None)
    check()
    remote_file(source)
    destination = Path(destination).absolute()
    temporary = None
    ftp = None
    try:
        if os.path.lexists(destination):
            raise BrowserError('Destination already exists; nothing was overwritten.')
        adapter = adapter_for(client)
        if adapter is not None:
            return _managed_download(adapter, source, destination, progress, check,
                                     preserve_cleanup=preserve_cleanup)
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
        failure = BrowserError('Download failed during local I/O.' if preserve_cleanup else f'Download failed: {exc}')
        if preserve_cleanup:
            for name in ('local_cleanup', 'download_observation', 'ftp_error'):
                if hasattr(exc, name):setattr(failure, name, getattr(exc, name))
        raise failure from exc
    finally:
        if ftp is not None:
            ftp.close()
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _managed_download(adapter, source, destination, progress, check, *, preserve_cleanup=False):
    temporary = None
    primary = None
    observation = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.c64u-', delete=False) as output:
            temporary = output.name
            def finish():
                output.flush()
                os.fsync(output.fileno())
            result = adapter.read_into(source, output, progress=progress, check=check, finish=finish)
        observation = dict(bytes=result.transferred, sha256=result.sha256)
        check()
        publish_new(temporary, destination)
        return dict(path=str(destination), **observation)
    except Exception as exc:
        primary = exc
        raise
    finally:
        if temporary is not None:
            try:
                if os.path.exists(temporary):os.unlink(temporary)
            except Exception:
                if not preserve_cleanup:raise
                cleanup = (dict(scope='download-staging', error_category='local-cleanup-failed'),)
                if primary is not None:
                    primary.local_cleanup = tuple(getattr(primary, 'local_cleanup', ())) + cleanup
                    if observation is not None:primary.download_observation = observation
                else:
                    failure = BrowserError('Managed download local staging cleanup failed.')
                    failure.local_cleanup = cleanup
                    failure.download_observation = observation
                    raise failure from None


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


# Explicit 3C entry: legacy upload() remains for deferred composite consumers.
@dataclass(frozen=True)
class UploadEvidence:
    phase: str
    staging: str
    destination: str
    expected_bytes: int | None = None
    stor: dict | None = None
    readback: str = 'unperformed'
    size: str = 'unperformed'
    publication: dict | None = None
    disposition: str = 'not-started'
    error_category: str | None = None
    error_code: str | None = None
    transport_error: dict | None = None

    def inspection_message(self):
        if self.disposition == 'location-unknown':
            return ('Publication was not confirmed. The uploaded file may be at '
                    f'{self.staging} or {self.destination}. Inspect before further action; '
                    'no retry or cleanup was attempted.')
        return ''


def upload_managed(client, source, parent='/USB2', progress=lambda n: None):
    """Core-only staged addition. Never retries or removes remote state."""
    from .files import child, inspect
    source = Path(source)
    destination = child(parent, source.name)
    temporary = child(parent, 'c64u-part-' + uuid.uuid4().hex)
    evidence = UploadEvidence('preflight', temporary, destination)
    check = getattr(progress, 'check', lambda: None)
    try:
        check()
        adapter = adapter_for(client)
        if adapter is None:
            raise BrowserError('Upload requires a Core-managed C64U session.')
        with operation_event('ftp', 'upload', 'file'), adapter.operation(check):
            if inspect(client, destination) is not None:
                raise BrowserError('Destination already exists; upload refused.')
            if inspect(client, temporary) is not None:
                raise BrowserError('Temporary filename exists; upload refused.')
            evidence = replace(evidence, phase='source')
            check()
            with source.open('rb') as stream:
                if not source.is_file():raise BrowserError('Choose a regular file.')
                expected = os.fstat(stream.fileno()).st_size
                evidence = replace(evidence, phase='stor', expected_bytes=expected)
                sent = adapter.write_from(temporary, stream, expected, progress)
                evidence = replace(evidence, stor=sent.transfer.as_dict(),
                                   disposition='staging-candidate', phase='source-close')
            evidence = replace(evidence, phase='readback', readback='pending')
            observed = adapter.readback(temporary, sent.transferred)
            if observed.sha256 != sent.sha256:
                evidence = replace(evidence, readback='failed')
                raise BrowserError('Upload readback hash verification failed.')
            evidence = replace(evidence, readback='passed', phase='size', size='pending')
            if adapter.size(temporary) != sent.transferred:
                evidence = replace(evidence, size='failed')
                raise BrowserError('Upload SIZE verification failed.')
            evidence = replace(evidence, size='passed', phase='destination-recheck')
            if inspect(client, destination) is not None:
                raise BrowserError('Destination appeared during transfer; publish refused.')
            evidence = replace(evidence, phase='publication')
            check()
            publication = adapter.mutate('rename', temporary, destination)
            evidence = replace(evidence, publication=publication, disposition='published', phase='complete')
            # No check after the acknowledged consequential rename, including context exit.
            return {'path': destination, 'bytes': sent.transferred, 'sha256': sent.sha256,
                    'verified': True, 'upload': evidence}
    except Exception as exc:
        wire = getattr(exc, 'ftp_error', None)
        stor = getattr(wire, 'transfer', None)
        mutation = getattr(wire, 'mutation', None)
        if evidence.phase == 'stor' and stor is not None:
            data = stor.as_dict()
            # A preliminary refusal does not establish creation of a staging file.
            refused = data['preliminary_reply'] is not None and data['preliminary_reply'] >= 400
            evidence = replace(evidence, stor=data, disposition=(
                'no-candidate' if refused else
                'staging-candidate' if data['submitted'] else 'not-started'))
        if evidence.phase == 'publication' and mutation is not None:
            data = mutation.as_dict()
            evidence = replace(evidence, publication=data)
            if data['consequential_submitted'] and data['outcome'] == 'unknown':
                evidence = replace(evidence, disposition='location-unknown')
        if evidence.readback == 'pending':evidence = replace(evidence, readback='failed')
        if evidence.size == 'pending':evidence = replace(evidence, size='failed')
        category = ('cancelled' if getattr(exc, 'cancelled', False) else
                    'transport' if wire is not None else
                    'verification' if evidence.phase in ('readback', 'size') else
                    'conflict' if evidence.phase in ('preflight', 'destination-recheck') else 'upload')
        if (wire is not None and wire.code.value == 'size-mismatch' and
                evidence.stor and evidence.stor['length_status'] in ('short', 'overlong')):
            category = 'source-length'
        code = wire.code.value if wire is not None else category
        evidence = replace(evidence, error_category=category, error_code=code,
                           transport_error=wire.as_dict() if wire is not None else None)
        partial = temporary if evidence.disposition == 'staging-candidate' else None
        if getattr(exc, 'cancelled', False):
            exc.upload_evidence = evidence
            exc.partial_path = partial
            raise
        message = evidence.inspection_message()
        if not message:
            message = (f'Upload stopped during {evidence.phase}: C64U FTP {code}. Inspect the recorded result.'
                       if wire is not None else str(exc) if isinstance(exc, BrowserError)
                       else 'Upload failed; inspect the recorded result.')
        failure = UploadFailure(message, partial)
        failure.upload_evidence = evidence
        failure.code = 'upload-' + category
        failure.retryable = False
        raise failure from None
