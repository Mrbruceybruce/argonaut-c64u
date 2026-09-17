import http.client
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from c64u_browser.c64_ai_chat import (
    C64ChatGateway, decode_prompt, encode_reply,
)
from c64u_browser.c64_ai_client import render_chat_client, render_link_probe
from c64u_browser.c64_ai_bridge_config import (
    C64BridgeConfig, load_bridge_config, save_bridge_config,
)
from c64u_browser.c64_ai_service import (
    loopback_server, paired_c64_server, paired_lan_server,
)


TOKEN = 'A' * 40


class C64AIBridgeTests(unittest.TestCase):
    def test_private_bridge_config_round_trip_and_validation(self):
        config = C64BridgeConfig('gemma3:4b', '192.0.2.1', 6464,
                                 ('192.0.2.10', '192.0.2.11'), 'C' * 64)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bridge.json'
            save_bridge_config(path, config)
            self.assertEqual(load_bridge_config(path), config)
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            save_bridge_config('/unused', C64BridgeConfig(
                'gemma3:4b', '0.0.0.0', 6464, ('192.0.2.10',), 'C' * 64))

    def test_private_link_probe_source_is_bounded_and_tokenized(self):
        token = 'B' * 64
        source = render_link_probe('192.0.2.1', 6464, token)
        self.assertIn('h$="192.0.2.1":p=6464', source)
        self.assertIn('argonaut/1 ' + token.lower() + ' 33', source)
        self.assertIn('chr$(3)+chr$(7)', source)
        self.assertIn('chr$(3)+chr$(17)', source)
        self.assertIn('chr$(3)+chr$(16)', source)
        self.assertIn('chr$(3)+chr$(9)', source)
        self.assertLess(max(map(len, source.splitlines())), 255)
        with self.assertRaises(ValueError):
            render_link_probe('0.0.0.0', 80, token)
        with self.assertRaises(ValueError):
            render_link_probe('192.0.2.1', 6464, 'short')

    def test_interactive_client_prompts_and_reconnects(self):
        source = render_chat_client('192.0.2.1', 6464, 'B' * 64)
        self.assertIn('40 q$="":input "ask argonaut (blank exits)";q$', source)
        self.assertIn('45 if len(q$)>80', source)
        self.assertIn('+mid$(str$(len(q$)),2)+chr$(10)+q$', source)
        self.assertIn('900 goto 40', source)
        self.assertLess(max(map(len, source.splitlines())), 255)

    def test_text_contract_rejects_controls_and_bounds_reply(self):
        self.assertEqual(decode_prompt(b'  What is a SID?  '), 'What is a SID?')
        for body in (b'', b'Hello\nworld', b'\x00cmd', b'\xff', b'x' * 241):
            with self.subTest(body=body[:10]), self.assertRaises(ValueError):
                decode_prompt(body)
        reply = encode_reply('Caf\N{LATIN SMALL LETTER E WITH ACUTE} ' + 'x' * 600)
        self.assertLessEqual(len(reply), 512)
        self.assertTrue(reply.startswith(b'Cafe '))
        self.assertTrue(reply.endswith(b'...'))
        self.assertTrue(reply.isascii())

    def test_chat_adapter_has_no_device_or_test_lab_inputs(self):
        with patch('c64u_browser.c64_ai_chat._post_json') as post:
            post.return_value = {'done': True, 'message': {'content': 'A SID makes sound.'}}
            reply = C64ChatGateway('gemma3:4b')('What is a SID?')
        self.assertEqual(reply, b'A SID makes sound.')
        url, payload = post.call_args.args[:2]
        self.assertEqual(url, 'http://127.0.0.1:11434/api/chat')
        self.assertEqual(payload['messages'][1]['content'], 'What is a SID?')
        self.assertNotIn('failures', str(payload))
        self.assertFalse(payload['stream'])

    def test_loopback_http_requires_token_and_limits_question(self):
        gateway = Mock(return_value=b'Use the SID chip.')
        server = loopback_server(gateway, TOKEN)
        self.assertEqual(server.server_address[0], '127.0.0.1')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]

            def ask(body, headers):
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                conn.request('POST', '/v1/chat', body=body, headers=headers)
                result = conn.getresponse()
                answer = result.read()
                status = result.status
                conn.close()
                return status, answer

            headers = {'Content-Type': 'text/plain'}
            self.assertEqual(ask(b'What is SID?', headers)[0], 401)
            gateway.assert_not_called()
            headers['Authorization'] = 'Bearer ' + TOKEN
            self.assertEqual(ask(b'x' * 241, headers)[0], 413)
            self.assertEqual(ask(b'bad\x00input', headers)[0], 400)
            gateway.assert_not_called()
            self.assertEqual(ask(b'What is SID?', headers),
                             (200, b'Use the SID chip.'))
            gateway.assert_called_once_with('What is SID?')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_paired_server_validates_binding_and_client(self):
        with self.assertRaises(ValueError):
            paired_lan_server(Mock(), TOKEN, '0.0.0.0', '192.0.2.10')
        with self.assertRaises(ValueError):
            paired_lan_server(Mock(), TOKEN, '127.0.0.1', '192.0.2.10', 80)

        gateway = Mock(return_value=b'answer')
        server = paired_lan_server(gateway, TOKEN, '127.0.0.1',
                                   '192.0.2.10', 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection(
                '127.0.0.1', server.server_address[1], timeout=2)
            conn.request('POST', '/v1/chat', body=b'Question?', headers={
                'Authorization': 'Bearer ' + TOKEN,
                'Content-Type': 'text/plain',
            })
            result = conn.getresponse()
            self.assertEqual((result.status, result.read()),
                             (403, b'Client is not paired.'))
            conn.close()
            gateway.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_compact_c64_protocol_authenticates_and_returns_plain_text(self):
        gateway = Mock(return_value=b'A SID makes sound.')
        server = paired_c64_server(gateway, TOKEN, '127.0.0.1',
                                   '127.0.0.1', 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            address = server.server_address
            with socket.create_connection(address, timeout=2) as client:
                client.sendall(b'ARGONAUT/1 wrong 9\nQuestion?')
                self.assertEqual(client.recv(100), b'ERR AUTH\n')
            gateway.assert_not_called()
            with socket.create_connection(address, timeout=2) as client:
                client.sendall(('ARGONAUT/1 ' + TOKEN + ' 12\n').encode()
                               + b'What is SID?')
                self.assertEqual(client.recv(100),
                                 b'OK 18\nA SID MAKES SOUND.')
            gateway.assert_called_once_with('What is SID?')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
