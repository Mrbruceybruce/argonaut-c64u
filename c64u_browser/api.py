# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Shared FTP/REST transport layer, independent of the user interface."""
from dataclasses import dataclass
import ftplib
import json
import re
import urllib.request
import urllib.error
from urllib.parse import quote, urlencode
import socket
import ipaddress
from .diagnostics import operation_event, rest_target

class BrowserError(Exception):
    pass


class ConnectionFailure(BrowserError):
    def __init__(self, kind, message):
        self.kind = kind
        super().__init__(message)


def safe_argument(value):
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise BrowserError('Control characters are not allowed in connection arguments or paths.')
    return value


@dataclass(frozen=True)
class Entry:
    name: str
    kind: str
    size: int | None


def parse_list(line):
    # Ultimate upstream UNIX-style LIST; preserve spaces inside filenames.
    match = re.fullmatch(r'([d-])[rwx-]{9}\s+\d+\s+\S+\s+\S+\s+(\d+)\s+\S+\s+\d+\s+\S+ (.*)', line)
    if not match:
        raise BrowserError('Unrecognized FTP listing format; refusing to invent filenames.')
    return Entry(match[3], 'dir' if match[1] == 'd' else 'file', int(match[2]))


class UltimateClient:
    def __init__(self, host, password='', port=21, timeout=10, encoding='utf-8', http_port=80):
        safe_argument(host)
        if not host or any(c in host for c in '/@?#: '):
            raise BrowserError('Supply an IPv4 address or hostname, without a URL or port.')
        self.host, self.password = host, safe_argument(password)
        for value in (port, http_port):
            if type(value) is not int or not 1 <= value <= 65535:
                raise BrowserError("Ports must be between 1 and 65535.")
        self.port, self.timeout, self.encoding = port, timeout, encoding
        self.http_port = http_port

    def list_directory(self, path='/'):
        with operation_event('ftp', 'list_directory', 'directory'):
            return self._list_directory(path)

    def _list_directory(self, path):
        safe_argument(path)
        if not path.startswith('/'):
            raise BrowserError('Directory path must be absolute, beginning with /.')
        ftp = ftplib.FTP(timeout=self.timeout, encoding=self.encoding)
        try:
            ftp.connect(self.host, self.port)
            ftp.login('anonymous', self.password)
            ftp.set_pasv(True)
            ftp.cwd(path)
            actual = ftp.pwd()
            try:
                rows = list(ftp.mlsd())
                entries = []
                for name, facts in rows:
                    kind = facts.get('type', 'unknown')
                    if kind in ('cdir', 'pdir'):
                        continue
                    size = int(facts['size']) if 'size' in facts else None
                    entries.append(Entry(name, kind, size))
            except ftplib.error_perm as exc:
                if str(exc)[:3] not in ('500', '502', '504'):
                    raise
                lines = []
                ftp.retrlines('LIST', lines.append)
                entries = [parse_list(line) for line in lines]
            return actual, sorted(entries, key=lambda e: (e.kind != 'dir', e.name.casefold()))
        except UnicodeError as exc:
            raise BrowserError('Filename encoding failed. Retry with --encoding latin-1; byte mapping needs hardware verification.') from exc
        except (OSError, EOFError, ftplib.Error, ValueError) as exc:
            kind = 'authentication' if isinstance(exc, ftplib.error_perm) and str(exc).startswith('530') else ('network' if isinstance(exc, (OSError, EOFError)) else 'ftp')
            raise ConnectionFailure(kind, f'FTP browse failed ({self.host}:{self.port}): {exc}. Check address, FTP service, password and LAN connection.') from exc
        finally:
            ftp.close()

    def read_about(self, route):
        if route not in ('version', 'info'):
            raise BrowserError('Unsupported information route.')
        return self._get_json('/v1/' + route)

    def read_configuration(self, category=None):
        path = '/v1/configs'
        if category is not None:
            safe_argument(category)
            if not category or any(c in category for c in '/:*?'):
                raise BrowserError('Unsupported configuration category name.')
            path += '/' + quote(category, safe='') + '/*'
        return self._get_json(path)

    def read_drives(self):
        data=self._get_json('/v1/drives')
        if not isinstance(data.get('drives'),list):raise BrowserError('Unsupported drive status response.')
        result={}
        for row in data['drives']:
            if not isinstance(row,dict):raise BrowserError('Unsupported drive status entry.')
            for drive in ('a','b'):
                if drive in row:
                    info=row[drive]
                    if not isinstance(info,dict) or type(info.get('enabled')) is not bool:
                        raise BrowserError('Unsupported drive status fields.')
                    if any(key in info and not isinstance(info[key],str) for key in ('type','rom','image_file','image_path')):
                        raise BrowserError('Unsupported drive status fields.')
                    result[drive]=dict(info)
        return result

    @staticmethod
    def drive_route(drive, action):
        if drive not in ('a','b'):raise BrowserError('Choose Drive A or Drive B.')
        return '/v1/drives/'+drive+':'+action

    def drive_action(self, drive, action):
        if action not in ('reset','remove','on','off'):raise BrowserError('Unsupported drive action.')
        return self._request_json('PUT',self.drive_route(drive,action))

    def mount_disk(self, drive, path, mode='readonly'):
        safe_argument(path)
        if not path.startswith('/') or '..' in path.split('/'):
            raise BrowserError('Use an absolute C64U image path without parent traversal.')
        if path.rsplit('.',1)[-1].lower() not in ('d64','g64','d71','g71','d81'):
            raise BrowserError('Choose a D64, G64, D71, G71 or D81 image.')
        if mode not in ('readonly','readwrite','unlinked'):raise BrowserError('Unsupported disk write mode.')
        return self._request_json('PUT',self.drive_route(drive,'mount')+'?'+urlencode({'image':path,'mode':mode}))

    def create_d64(self, path, disk_name, tracks=35):
        """Ask supported C64U firmware to create a standard blank D64."""
        if not isinstance(path, str) or not isinstance(disk_name, str):
            raise BrowserError('Choose a C64U filename and disk name.')
        safe_argument(path)
        safe_argument(disk_name)
        parts = path.split('/')
        if (not path.startswith('/') or any(part in ('', '.', '..') for part in parts[1:])
                or not path.casefold().endswith('.d64')):
            raise BrowserError('Use an absolute C64U .d64 path without parent traversal.')
        if not disk_name.strip() or len(disk_name) > 16:
            raise BrowserError('Enter a C64 disk name of 1 to 16 characters.')
        if tracks != 35:
            raise BrowserError('Argonaut creates standard 35-track D64 images.')
        route = '/v1/files/' + quote(path.lstrip('/'), safe='/') + ':create_d64'
        return self._request_json(
            'PUT', route + '?' + urlencode({'tracks': tracks, 'diskname': disk_name}))

    def run_crt(self, path):
        """Start a CRT already present on C64U storage."""
        safe_argument(path)
        if (not path.startswith('/') or '..' in path.split('/')
                or not path.casefold().endswith('.crt')):
            raise BrowserError('Use an absolute C64U CRT path without parent traversal.')
        return self._request_json(
            'PUT', '/v1/runners:run_crt?' + urlencode({'file': path}))

    def run_crt_data(self, data, filename='game.crt'):
        """Start a supplied CRT without installing it on C64U storage."""
        if not isinstance(data, bytes) or not data:
            raise BrowserError('Choose non-empty CRT data.')
        safe_argument(filename)
        if (not filename or '/' in filename or '\\' in filename
                or not filename.casefold().endswith('.crt')):
            raise BrowserError('Use a simple CRT attachment filename.')
        return self._request_binary_json(
            '/v1/runners:run_crt', data, filename)

    def set_drive_type(self, drive, mode):
        if mode not in ('1541','1571','1581'):raise BrowserError('Unsupported drive type.')
        return self._request_json('PUT',self.drive_route(drive,'set_mode')+'?'+urlencode({'mode':mode}))

    def _get_json(self, path):
        return self._request_json('GET', path)

    def _request_json(self, method, path, payload=None):
        # Query values and dynamic route segments can contain private names.
        with operation_event('rest', method, rest_target(path)):
            return self._request_json_impl(method, path, payload)

    def _request_json_impl(self, method, path, payload=None):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        headers = {'X-Password': self.password, 'Accept': 'application/json'}
        if body is not None: headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(
            f'http://{self.host}:{self.http_port}{path}',
            data=body, headers=headers, method=method)
        try:
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('Response too large')
            data = json.loads(raw)
            if not isinstance(data, dict) or not isinstance(data.get('errors'), list):
                raise ValueError('Unexpected API response')
            if data['errors']:
                raise ValueError('Device reported an API error')
            return data
        except urllib.error.HTTPError as exc:
            if exc.code in (404,405,501):
                raise ConnectionFailure('api',f'This firmware does not support the requested operation (HTTP {exc.code}). Check the firmware version shown in Argonaut.') from exc
            kind = 'authentication' if exc.code in (401, 403) else 'api'
            if path.startswith('/v1/streams/') and kind == 'api':
                try:
                    errors=json.loads(exc.read(4096)).get('errors',[])
                    if 'No Operational Network Interface' in errors:
                        raise ConnectionFailure('api','C64U streaming requires an operational Ethernet connection. Connect its Ethernet cable, then connect Argonaut to the wired address.') from exc
                except (ValueError,AttributeError,OSError):
                    pass
            raise ConnectionFailure(kind, f'REST {"authentication failed" if kind == "authentication" else "request failed"} (HTTP {exc.code}).') from exc
        except urllib.error.URLError as exc:
            kind = 'host' if isinstance(exc.reason, socket.gaierror) else 'network'
            raise ConnectionFailure(kind, 'Hostname could not be resolved.' if kind == 'host' else 'Cannot reach the REST service; check address, port, power and network.') from exc
        except (OSError, TimeoutError) as exc:
            raise ConnectionFailure('network', 'REST connection timed out or failed.') from exc
        except (ValueError, BrowserError) as exc:
            raise ConnectionFailure('api', 'Invalid or unsupported REST response.') from exc

    def _request_binary_json(self, path, data, filename):
        """POST one bounded binary attachment and validate the JSON response."""
        with operation_event('rest', 'POST', rest_target(path)):
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), NoRedirect())
            request = urllib.request.Request(
                f'http://{self.host}:{self.http_port}{path}', data=data,
                headers={
                    'X-Password': self.password,
                    'Accept': 'application/json',
                    'Content-Type': 'application/octet-stream',
                    'Content-Disposition': f'attachment; filename="{filename}"',
                }, method='POST')
            try:
                with opener.open(request, timeout=self.timeout) as response:
                    raw = response.read(65537)
                if len(raw) > 65536:raise ValueError('Response too large')
                result = json.loads(raw)
                if (not isinstance(result, dict)
                        or not isinstance(result.get('errors'), list)):
                    raise ValueError('Unexpected API response')
                if result['errors']:raise ValueError('Device reported an API error')
                return result
            except urllib.error.HTTPError as exc:
                if exc.code in (404, 405, 501):
                    raise ConnectionFailure(
                        'api', 'This firmware does not support attached CRT launch '
                        f'(HTTP {exc.code}).') from exc
                kind = 'authentication' if exc.code in (401, 403) else 'api'
                raise ConnectionFailure(
                    kind, 'REST authentication failed.' if kind == 'authentication'
                    else f'REST request failed (HTTP {exc.code}).') from exc
            except urllib.error.URLError as exc:
                kind = 'host' if isinstance(exc.reason, socket.gaierror) else 'network'
                raise ConnectionFailure(
                    kind, 'Hostname could not be resolved.' if kind == 'host'
                    else 'The CRT launch response was not received.') from exc
            except (OSError, TimeoutError) as exc:
                raise ConnectionFailure(
                    'network', 'The CRT launch response was not received.') from exc
            except (ValueError, BrowserError) as exc:
                raise ConnectionFailure(
                    'api', 'Invalid or unsupported REST response.') from exc

    def apply_configuration(self, values):
        if not isinstance(values, dict) or not values:
            raise BrowserError('No configuration changes were staged.')
        return self._request_json('POST', '/v1/configs', values)

    def save_configuration(self):
        return self._request_json('PUT', '/v1/configs:save_to_flash')

    def machine_action(self, action):
        if action not in ('reset','reboot'):raise BrowserError('Unsupported machine action.')
        return self._request_json('PUT','/v1/machine:'+action)

    def run_prg(self, path):
        safe_argument(path)
        if (not isinstance(path, str) or not path.startswith('/')
                or any(part in ('.', '..') for part in path.split('/'))
                or not path.lower().endswith('.prg')):
            raise BrowserError('Use an absolute C64U path to a PRG file.')
        return self._request_json(
            'PUT', '/v1/runners:run_prg?' + urlencode({'file': path}))

    def write_memory(self, address, data):
        if (type(address) is not int or not 0 <= address <= 0xffff
                or not isinstance(data, bytes) or not 1 <= len(data) <= 128
                or address + len(data) > 0x10000):
            raise BrowserError('Use a valid C64 memory address and 1 to 128 bytes.')
        return self._request_json('PUT', '/v1/machine:writemem?' + urlencode({
            'address': f'{address:04X}', 'data': data.hex().upper(),
        }))

    @staticmethod
    def sid_parameters(path, song=None):
        if not isinstance(path,str):raise BrowserError('Choose a SID file on the C64U.')
        safe_argument(path)
        if not path.startswith('/') or '..' in path.split('/') or not path.lower().endswith('.sid'):
            raise BrowserError('Use an absolute C64U path to a .sid file, without parent traversal.')
        if song is not None and (type(song) is not int or not 1 <= song <= 65535):
            raise BrowserError('Song number must be a whole number from 1 to 65535, or use the file default.')
        parameters={'file':path}
        if song is not None:parameters['songnr']=song
        return parameters

    def play_sid(self, path, song=None):
        parameters=self.sid_parameters(path,song)
        return self._request_json('PUT','/v1/runners:sidplay?'+urlencode(parameters))

    def start_stream(self, stream, address, port):
        if stream not in ('video','audio'):raise BrowserError('Unsupported preview stream.')
        ip=ipaddress.IPv4Address(address)
        if ip.is_multicast or ip.is_unspecified or ip.is_loopback or int(ip)==0xffffffff:
            raise BrowserError('Use this workstation’s unicast LAN address.')
        if type(port) is not int or not 1024<=port<=65535:raise BrowserError('Invalid listening port.')
        return self._request_json('PUT','/v1/streams/'+stream+':start?'+urlencode({'ip':f'{ip}:{port}'}))

    def stop_stream(self, stream):
        if stream not in ('video','audio'):raise BrowserError('Unsupported preview stream.')
        return self._request_json('PUT','/v1/streams/'+stream+':stop')

    def info(self):
        return {route: self.read_about(route) for route in ('version', 'info')}

    def test_connection(self):
        result = self.info()
        info, version = result['info'], result['version']
        product = info.get('product')
        # Generic JSON, HTTP 200 and even /v1/version are insufficient identity.
        if (not isinstance(product, str) or product.casefold() not in
                {'c64 ultimate', 'commodore 64 ultimate', 'ultimate 64', 'ultimate 64 elite', 'ultimate 64 elite ii'}
                or not isinstance(info.get('firmware_version'), str)
                or not isinstance(version.get('version'), str)):
            raise ConnectionFailure('api', 'REST replied, but a supported Ultimate device could not be positively identified.')
        from .network_identity import peer_mac
        result['network_mac']=peer_mac(self.host)
        return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BrowserError('Device returned an unexpected HTTP redirect.')
