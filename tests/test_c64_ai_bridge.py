import http.client
import threading
import unittest
from unittest.mock import Mock, patch

from c64u_browser.c64_ai_chat import (
    C64ChatGateway, decode_prompt, encode_reply,
)
from c64u_browser.c64_ai_service import loopback_server


TOKEN = 'a' * 40


class C64AIBridgeTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
