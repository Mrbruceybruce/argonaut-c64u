# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Offline REST/FTP fixtures for the Test Lab; no device or network access."""
import ftplib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import urllib.error
from urllib.parse import urlsplit
from unittest.mock import patch

from .api import BrowserError, ConnectionFailure, UltimateClient
from .hardware_checks import run_hardware_checks
from .profiles import Profile
from .test_lab import Check, require
from .transfers import download, upload, UploadFailure


class _Response:
    def __init__(self, value):
        self.body = json.dumps(value).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limit):
        require(limit == 65537, 'REST response limit differed')
        return self.body


class _RestOpener:
    def __init__(self, response=None, failure=None):
        self.response, self.failure = response, failure
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.failure is not None:
            raise self.failure
        return _Response(self.response)


class _RouteOpener(_RestOpener):
    def __init__(self, responses):
        super().__init__()
        self.responses = responses

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return _Response(self.responses[urlsplit(request.full_url).path])


class _FTP:
    def __init__(self, rows=(), listing=(), mlsd_error=None, login_error=None):
        self.rows, self.listing = rows, listing
        self.mlsd_error, self.login_error = mlsd_error, login_error
        self.commands = []

    def connect(self, host, port):
        self.commands.append(('connect', host, port))

    def login(self, user, password):
        self.commands.append(('login', user, password))
        if self.login_error:
            raise self.login_error

    def set_pasv(self, enabled):
        self.commands.append(('set_pasv', enabled))

    def cwd(self, path):
        self.commands.append(('cwd', path))

    def pwd(self):
        return '/Usb1'

    def mlsd(self):
        self.commands.append(('mlsd',))
        if self.mlsd_error:
            raise self.mlsd_error
        return self.rows

    def retrlines(self, command, callback):
        self.commands.append(('retrlines', command))
        for line in self.listing:
            callback(line)

    def close(self):
        self.commands.append(('close',))


class _TransferFTP:
    def __init__(self, files=None, fail_download=False):
        self.files = dict(files or {})
        self.fail_download = fail_download
        self.commands = []

    def connect(self, host, port):
        self.commands.append(('connect', host, port))

    def login(self, user, password):
        self.commands.append(('login', user, password))

    def set_pasv(self, enabled):
        self.commands.append(('set_pasv', enabled))

    def voidcmd(self, command):
        self.commands.append(('voidcmd', command))

    def size(self, path):
        self.commands.append(('size', path))
        return len(self.files[path]) if path in self.files else None

    def retrbinary(self, command, callback):
        self.commands.append(('retrbinary', command))
        if self.fail_download:
            callback(b'a')
            raise OSError('simulated connection loss')
        callback(self.files[command[5:]])

    def storbinary(self, command, stream, callback=None):
        self.commands.append(('storbinary', command))
        data = stream.read()
        self.files[command[5:]] = data
        if callback:
            callback(data)

    def rename(self, source, destination):
        self.commands.append(('rename',))
        self.files[destination] = self.files.pop(source)

    def close(self):
        self.commands.append(('close',))


def _rest_success():
    opener = _RestOpener({'errors': [], 'version': '1.1.0'})
    with patch('urllib.request.build_opener', return_value=opener):
        result = UltimateClient('fixture.invalid', password='private').read_about('version')
    require(result['version'] == '1.1.0', 'REST version differed')
    request, timeout = opener.requests[0]
    require((request.get_method(), request.full_url, timeout) == (
        'GET', 'http://fixture.invalid:80/v1/version', 10), 'REST request differed')
    require(len(opener.requests) == 1, 'REST request count differed')


def _rest_malformed_response():
    opener = _RestOpener({'errors': 'not a list'})
    with patch('urllib.request.build_opener', return_value=opener):
        try:
            UltimateClient('fixture.invalid').read_about('info')
        except ConnectionFailure as exc:
            require(exc.kind == 'api', 'Malformed response category differed')
        else:
            raise AssertionError('Malformed response was accepted')
    require(len(opener.requests) == 1, 'REST request count differed')


def _rest_authentication_failure():
    error = urllib.error.HTTPError('http://fixture.invalid/v1/info', 403,
                                   'Forbidden', {}, io.BytesIO())
    opener = _RestOpener(failure=error)
    with patch('urllib.request.build_opener', return_value=opener):
        try:
            UltimateClient('fixture.invalid').read_about('info')
        except ConnectionFailure as exc:
            require(exc.kind == 'authentication', 'REST authentication category differed')
        else:
            raise AssertionError('Authentication failure was accepted')
    require(len(opener.requests) == 1, 'REST request count differed')


def _ftp_mlsd_listing():
    ftp = _FTP(rows=(('game.d64', {'type': 'file', 'size': '12'}),
                     ('Usb1', {'type': 'dir'})))
    with patch('ftplib.FTP', return_value=ftp):
        actual, entries = UltimateClient('fixture.invalid').list_directory('/Usb1')
    require(actual == '/Usb1', 'FTP actual directory differed')
    require([(entry.name, entry.kind) for entry in entries] == [
        ('Usb1', 'dir'), ('game.d64', 'file')], 'FTP entries differed')
    require(('cwd', '/Usb1') in ftp.commands, 'FTP did not change directory')
    require(ftp.commands[-1] == ('close',), 'FTP connection was not closed')


def _ftp_list_fallback():
    ftp = _FTP(mlsd_error=ftplib.error_perm('502 Unsupported'), listing=(
        '-rw-rw-rw- 1 user ftp 12 Sep 07 12:30 My game.d64',))
    with patch('ftplib.FTP', return_value=ftp):
        _, entries = UltimateClient('fixture.invalid').list_directory('/Usb1')
    require(entries[0].name == 'My game.d64', 'FTP LIST filename differed')
    require(('retrlines', 'LIST') in ftp.commands, 'FTP LIST fallback did not run')
    require(ftp.commands[-1] == ('close',), 'FTP connection was not closed')


def _ftp_authentication_failure():
    ftp = _FTP(login_error=ftplib.error_perm('530 Denied'))
    with patch('ftplib.FTP', return_value=ftp):
        try:
            UltimateClient('fixture.invalid', password='private').list_directory('/Usb1')
        except ConnectionFailure as exc:
            require(exc.kind == 'authentication', 'FTP authentication category differed')
        else:
            raise AssertionError('FTP authentication failure was accepted')
    require(('mlsd',) not in ftp.commands, 'FTP listed after authentication failed')
    require(ftp.commands[-1] == ('close',), 'FTP connection was not closed')


def _rest_wrong_device_identity():
    opener = _RouteOpener({
        '/v1/version': {'errors': [], 'version': 'v1'},
        '/v1/info': {'errors': [], 'product': 'C64 Ultimate',
                     'firmware_version': '1.1.0', 'unique_id': 'other-device'},
    })
    profile = Profile.new('Expected device', 'fixture.invalid',
                          device_id='expected-device', device_mac='02:15:41:01:02:03')
    with patch('urllib.request.build_opener', return_value=opener), patch(
            'c64u_browser.network_identity.peer_mac', return_value='02:15:41:04:05:06'):
        report = run_hardware_checks(UltimateClient('fixture.invalid'), profile)
    require([check['status'] for check in report['checks']] ==
            ['fail', 'skip', 'skip', 'skip'],
            'Wrong-device identity did not block dependent checks')
    require(report['checks'][0]['error_kind'] == 'identity',
            'Wrong-device failure category differed')
    require([urlsplit(request.full_url).path for request, _ in opener.requests] ==
            ['/v1/version', '/v1/info'],
            'Wrong-device test made dependent device reads')


def _complete_read_only_hardware_suite():
    opener = _RouteOpener({
        '/v1/version': {'errors': [], 'version': 'v1'},
        '/v1/info': {'errors': [], 'product': 'C64 Ultimate',
                     'firmware_version': '1.1.0', 'unique_id': 'expected-device'},
        '/v1/drives': {'errors': [], 'drives': [
            {'a': {'enabled': True, 'type': '1541'}},
            {'b': {'enabled': False, 'type': '1571'}},
        ]},
    })
    ftp = _FTP(rows=(('Usb1', {'type': 'dir'}),
                     ('game.d64', {'type': 'file', 'size': '12'})))
    profile = Profile.new('Expected device', 'fixture.invalid',
                          device_id='expected-device', device_mac='02:15:41:01:02:03')
    with patch('urllib.request.build_opener', return_value=opener), patch(
            'ftplib.FTP', return_value=ftp), patch(
            'c64u_browser.network_identity.peer_mac', return_value=profile.device_mac):
        report = run_hardware_checks(UltimateClient('fixture.invalid'), profile)
    require(report['status'] == 'pass' and
            [check['status'] for check in report['checks']] == ['pass'] * 4,
            'Complete simulated hardware run did not pass')
    require([len(check['operations']) for check in report['checks']] == [2, 1, 1, 1],
            'Complete hardware operation count differed')
    require([urlsplit(request.full_url).path for request, _ in opener.requests] ==
            ['/v1/version', '/v1/info', '/v1/drives', '/v1/version'],
            'Complete hardware REST sequence differed')
    require(('cwd', '/') in ftp.commands and ('mlsd',) in ftp.commands and
            ftp.commands[-1] == ('close',),
            'Complete hardware FTP listing differed')


def _transfer_download_complete():
    data = b'verified fixture payload'
    ftp = _TransferFTP({'/USB2/private-game.d64': data})
    with tempfile.TemporaryDirectory() as directory, patch('ftplib.FTP', return_value=ftp):
        destination = Path(directory) / 'private-download.d64'
        result = download(UltimateClient('fixture.invalid', password='private'),
                          '/USB2/private-game.d64', destination)
        require(destination.read_bytes() == data and result['bytes'] == len(data),
                'FTP download bytes differed')
        require(result['sha256'] == hashlib.sha256(data).hexdigest(),
                'FTP download digest differed')
        require(len(list(Path(directory).iterdir())) == 1,
                'FTP download left a staged file')
    require(('voidcmd', 'TYPE I') in ftp.commands and
            ('retrbinary', 'RETR /USB2/private-game.d64') in ftp.commands and
            ftp.commands[-1] == ('close',),
            'FTP download did not use and close the binary connection')


def _transfer_download_interrupt():
    ftp = _TransferFTP({'/USB2/private-game.d64': b'abc'}, fail_download=True)
    with tempfile.TemporaryDirectory() as directory, patch('ftplib.FTP', return_value=ftp):
        destination = Path(directory) / 'private-download.d64'
        try:
            download(UltimateClient('fixture.invalid'),
                     '/USB2/private-game.d64', destination)
        except BrowserError:
            pass
        else:
            raise AssertionError('Interrupted FTP download was accepted')
        require(not destination.exists() and not list(Path(directory).iterdir()),
                'Interrupted FTP download published or left a staged file')
    require(ftp.commands[-1] == ('close',),
            'Interrupted FTP download did not close the connection')


def _transfer_upload_verified():
    data = b'verified upload payload'
    ftp = _TransferFTP()
    with tempfile.TemporaryDirectory() as directory, patch(
            'ftplib.FTP', return_value=ftp), patch(
            'c64u_browser.files.inspect', return_value=None):
        source = Path(directory) / 'private-upload.bin'
        source.write_bytes(data)
        result = upload(UltimateClient('fixture.invalid', password='private'),
                        source, '/USB2/Private')
    require(result['verified'] and result['bytes'] == len(data),
            'FTP upload verification differed')
    require(ftp.files == {'/USB2/Private/private-upload.bin': data},
            'FTP upload did not publish only the verified file')
    require(any(command[0] == 'rename' for command in ftp.commands) and
            ftp.commands[-1] == ('close',),
            'FTP upload did not publish and close the connection')


def _transfer_upload_collision():
    with patch('c64u_browser.files.inspect', return_value=object()), patch(
            'ftplib.FTP') as create_ftp:
        try:
            upload(UltimateClient('fixture.invalid'), 'private-upload.bin', '/USB2')
        except UploadFailure:
            pass
        else:
            raise AssertionError('Colliding FTP upload was accepted')
    create_ftp.assert_not_called()


SIMULATED_CHECKS = (
    Check('sim.rest.success', 'REST valid response', _rest_success),
    Check('sim.rest.malformed', 'REST malformed response', _rest_malformed_response),
    Check('sim.rest.authentication', 'REST authentication failure', _rest_authentication_failure),
    Check('sim.ftp.mlsd', 'FTP MLSD listing', _ftp_mlsd_listing),
    Check('sim.ftp.list_fallback', 'FTP LIST fallback', _ftp_list_fallback),
    Check('sim.ftp.authentication', 'FTP authentication failure', _ftp_authentication_failure),
    Check('sim.identity.wrong_device', 'Wrong C64U identity blocks dependent reads',
          _rest_wrong_device_identity),
    Check('sim.hardware.complete', 'Complete read-only C64U check simulation',
          _complete_read_only_hardware_suite),
    Check('sim.transfer.download', 'Verified FTP download simulation',
          _transfer_download_complete),
    Check('sim.transfer.interrupted', 'Interrupted FTP download cleanup simulation',
          _transfer_download_interrupt),
    Check('sim.transfer.upload', 'Verified FTP upload simulation',
          _transfer_upload_verified),
    Check('sim.transfer.collision', 'FTP upload collision refusal simulation',
          _transfer_upload_collision),
)
