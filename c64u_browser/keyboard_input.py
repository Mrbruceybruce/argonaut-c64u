# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded text injection into the standard C64 KERNAL keyboard buffer."""
import socket
import struct
import time
import urllib.request
from .api import BrowserError, NoRedirect
from .disk_run import receive_exact
from .diagnostics import operation_event


def encode_text(text, enter=False):
    # Start deliberately small: no Unicode substitutions or BASIC abbreviations.
    text=text.replace('\r\n','\n').replace('\r','\n')
    if not text or len(text)>160:
        raise BrowserError('Enter between 1 and 160 characters.')
    if any(c!='\n' and not 32<=ord(c)<=126 for c in text):
        raise BrowserError('Use plain ASCII text; unsupported characters were not sent.')
    if any(c in text for c in ('\\','^','_','`','{','|','}','~')):
        raise BrowserError('This symbol needs PETSCII mapping and is not supported yet.')
    result=text.upper().replace('\n','\r').encode('ascii')
    return result+(b'\r' if enter and not result.endswith(b'\r') else b'')


def buffer_count(client):
    with operation_event('rest', 'GET', '/v1/machine:readmem'):
        return _buffer_count(client)


def _buffer_count(client):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    request=urllib.request.Request(f'http://{client.host}:{client.http_port}/v1/machine:readmem?address=00C6&length=1',
        headers={'X-Password':client.password,'Accept':'application/octet-stream'})
    with opener.open(request,timeout=client.timeout) as response:
        data=response.read(2)
    if len(data)!=1 or data[0]>10:
        raise BrowserError('Standard keyboard buffer is unavailable. Use Send Text at the BASIC READY prompt.')
    return data[0]


def wait_empty(client):
    deadline=time.monotonic()+5
    while buffer_count(client):
        if time.monotonic()>=deadline:
            raise BrowserError('Keyboard buffer was not consumed. Return to BASIC READY before retrying.')
        time.sleep(.05)


def send_text(client, text, enter=False):
    with operation_event('dma', 'send_text', 'keyboard'):
        return _send_text(client, text, enter)


def _send_text_rest(client, data):
    queued = 0
    try:
        wait_empty(client)
        for offset in range(0, len(data), 10):
            wait_empty(client)
            chunk = data[offset:offset + 10]
            client.write_memory(0x0277, chunk)
            queued = offset + len(chunk)
            client.write_memory(0x00C6, bytes((len(chunk),)))
            wait_empty(client)
    except (OSError, BrowserError) as exc:
        raise BrowserError(
            f'REST Send Text stopped; up to {queued} bytes may have been sent. '
            f'Check the C64U before retrying. {exc}') from exc
    return len(data)


def _send_text(client, text, enter=False):
    data=encode_text(text,enter)
    queued=0
    try:
        wait_empty(client)
        with socket.create_connection((client.host,64),timeout=client.timeout) as connection:
            password=client.password.encode('utf-8')
            if len(password)>65535:raise BrowserError('Network password is too long.')
            connection.sendall(struct.pack('<HH',0xff1f,len(password))+password)
            if receive_exact(connection,1)!=b'\1':raise BrowserError('DMA authentication failed.')
            for offset in range(0,len(data),10):
                wait_empty(client)
                chunk=data[offset:offset+10]
                # Mark uncertain bytes before sending: a failed send may be partial.
                queued=offset+len(chunk)
                connection.sendall(struct.pack('<HH',0xff03,len(chunk))+chunk)
                connection.sendall(struct.pack('<HH',0xff0e,0))
                length=receive_exact(connection,1)[0]
                if not length:raise BrowserError('DMA service returned an empty response.')
                receive_exact(connection,length)
                wait_empty(client)
    except ConnectionRefusedError as exc:
        if queued == 0:
            return _send_text_rest(client, data)
        raise BrowserError(
            f'Send Text stopped; up to {queued} bytes may have been sent. '
            f'Check the C64U before retrying. {exc}') from exc
    except (OSError,BrowserError) as exc:
        raise BrowserError(f'Send Text stopped; up to {queued} bytes may have been sent. Check the C64U before retrying. {exc}') from exc
    return len(data)
