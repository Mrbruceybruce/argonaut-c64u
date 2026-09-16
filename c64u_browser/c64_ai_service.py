# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Loopback-only HTTP prototype for a later UCI TCP C64 client."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import ipaddress

from .c64_ai_chat import MAX_PROMPT_BYTES, MAX_REPLY_BYTES, decode_prompt
from .ai_gateway import GatewayError


def make_handler(gateway, token, allowed_client=None):
    if not isinstance(token, str) or len(token) < 32 or not token.isascii():
        raise ValueError('A strong bridge token is required.')
    if allowed_client is not None:
        allowed_client = str(ipaddress.IPv4Address(allowed_client))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            # Requests can contain private questions; do not write access logs.
            pass

        def _send(self, status, body):
            self.send_response(status)
            self.send_header('Content-Type', 'text/plain; charset=us-ascii')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if (allowed_client is not None
                    and self.client_address[0] != allowed_client):
                self._send(403, b'Client is not paired.')
                return
            if self.path != '/v1/chat':
                self._send(404, b'Not found.')
                return
            supplied = self.headers.get('Authorization', '')
            if not supplied.isascii() or not hmac.compare_digest(
                    supplied, 'Bearer ' + token):
                self._send(401, b'Unauthorized.')
                return
            if self.headers.get('Content-Type', '').lower() != 'text/plain':
                self._send(415, b'Use text/plain.')
                return
            raw_length = self.headers.get('Content-Length', '')
            if (not raw_length.isascii() or not raw_length.isdecimal()
                    or len(raw_length) > 5):
                self._send(400, b'Invalid request length.')
                return
            length = int(raw_length)
            if not 1 <= length <= MAX_PROMPT_BYTES:
                self._send(413, b'Question is too long.')
                return
            body = self.rfile.read(length)
            if len(body) != length:
                self._send(400, b'Incomplete question.')
                return
            try:
                answer = gateway(decode_prompt(body))
                if (not isinstance(answer, bytes) or not answer.isascii()
                        or not 1 <= len(answer) <= MAX_REPLY_BYTES):
                    raise GatewayError('response', 'Invalid answer.')
            except ValueError:
                self._send(400, b'Use one printable ASCII question.')
            except GatewayError:
                self._send(502, b'Local AI is unavailable.')
            else:
                self._send(200, answer)

        def do_GET(self):
            self._send(404, b'Not found.')

    return Handler


def loopback_server(gateway, token, port=0):
    """Bind only this computer; LAN exposure requires a separate deployment step."""
    return HTTPServer(('127.0.0.1', port), make_handler(gateway, token))


def paired_lan_server(gateway, token, host, allowed_client, port=6464):
    """Bind one LAN address and accept chat only from one paired IPv4 client."""
    host = str(ipaddress.IPv4Address(host))
    client = str(ipaddress.IPv4Address(allowed_client))
    if (ipaddress.IPv4Address(host).is_unspecified
            or ipaddress.IPv4Address(host).is_multicast
            or ipaddress.IPv4Address(client).is_unspecified
            or ipaddress.IPv4Address(client).is_multicast):
        raise ValueError('Use unicast LAN addresses for the bridge.')
    if type(port) is not int or (port != 0 and not 1024 <= port <= 65535):
        raise ValueError('Use a bridge port from 1024 to 65535.')
    return HTTPServer((host, port), make_handler(gateway, token, client))
