# SPDX-License-Identifier: GPL-3.0-or-later
"""D64 Mount & Run through the firmware's authenticated DMA service."""
import ftplib
import socket
import struct
from .api import BrowserError, safe_argument
from .transfers import connect
from .diagnostics import operation_event

# Standard 35/40/42-track D64 images, with or without error-byte tables.
D64_SIZES = frozenset((174848,175531,196608,197376,205312,206114))


class DmaLaunchError(BrowserError):
    """A sanitized DMA launch failure with explicit uncertainty."""
    def __init__(self, message, *, command_may_have_started=False):
        super().__init__(message)
        self.command_may_have_started = command_may_have_started
        self.code = ('launch-outcome-unknown' if command_may_have_started
                     else 'dma-rejection')


def validate_path(path):
    safe_argument(path)
    if not path.startswith('/') or any(p in ('.','..') for p in path.split('/')) or not path.lower().endswith('.d64'):
        raise BrowserError('Mount & Run requires an absolute C64U path to a D64 image.')


def receive_exact(connection, length):
    result=bytearray()
    while len(result)<length:
        chunk=connection.recv(length-len(result))
        if not chunk:raise BrowserError('DMA service closed the connection.')
        result.extend(chunk)
    return bytes(result)


def mount_and_run(client, path):
    with operation_event('dma', 'mount_and_run', 'disk'):
        return _mount_and_run(client, path)


def _mount_and_run(client, path):
    validate_path(path)
    image=bytearray()
    ftp=None
    sent=False
    try:
        ftp=connect(client)
        size=ftp.size(path)
        if size not in D64_SIZES:
            raise BrowserError('Unsupported D64 size; use a standard 35, 40 or 42-track image.')
        def collect(block):
            if len(image)+len(block)>size:
                raise BrowserError('Image changed during download; nothing was started.')
            image.extend(block)
        ftp.retrbinary('RETR '+path,collect)
        if len(image)!=size or ftp.size(path)!=size:
            raise BrowserError('Incomplete or changed image; nothing was started.')
        ftp.close();ftp=None
        sent=True
        run_image_bytes(client, bytes(image))
    except (OSError,EOFError,ftplib.Error,BrowserError) as exc:
        if isinstance(exc, DmaLaunchError):raise
        detail='Run may have started; check the C64U before retrying. ' if sent else 'Nothing was started. '
        raise BrowserError(detail+'Mount & Run failed: '+str(exc)+'. DMA service must be enabled on TCP port 64.') from exc
    finally:
        if ftp is not None:ftp.close()


def run_image_bytes(client, image):
    """Send one already-validated D64 image through RUN_IMG.

    A return means the firmware processed a following IDENTIFY command.  It is
    command acceptance evidence, not proof that software reached a playable
    screen.  Failures after RUN_IMG is sent are deliberately uncertain.
    """
    image = bytes(image)
    size = len(image)
    if size not in D64_SIZES:
        raise DmaLaunchError(
            'Unsupported D64 size; use a standard 35, 40 or 42-track image.')
    protected = getattr(client, 'credentials_encapsulated', False) is True
    connection = None
    sent = False
    try:
        connection = (client.open_dma() if protected else
                      socket.create_connection((client.host, 64),
                                               timeout=client.timeout))
        with connection:
            if not protected:
                password = client.password.encode('utf-8')
                if len(password) > 65535:
                    raise BrowserError('Network password is too long.')
                connection.sendall(
                    struct.pack('<HH', 0xff1f, len(password)) + password)
                if receive_exact(connection, 1) != b'\x01':
                    raise BrowserError(
                        'DMA authentication failed; check the network password.')
            # RUN_IMG has a three-byte little-endian length, unlike AUTH/IDENTIFY.
            sent = True
            connection.sendall(b'\x0b\xff' + size.to_bytes(3, 'little') + image)
            # A following IDENTIFY response proves command processing resumed;
            # firmware provides no disk-load success result, so do not claim one.
            connection.sendall(struct.pack('<HH', 0xff0e, 0))
            length = receive_exact(connection, 1)[0]
            if not length:
                raise BrowserError('DMA service returned an empty response.')
            receive_exact(connection, length)
    except (OSError, EOFError, BrowserError) as exc:
        if isinstance(exc, DmaLaunchError):raise
        detail = ('Run may have started; check the C64U before retrying. '
                  if sent else 'Nothing was started. ')
        raise DmaLaunchError(
            detail + 'Mount & Run failed: ' + str(exc)
            + '. DMA service must be enabled on TCP port 64.',
            command_may_have_started=sent) from exc
