import unittest
from unittest.mock import Mock,patch
from c64u_browser.api import UltimateClient,BrowserError
from c64u_browser.keyboard_input import encode_text,send_text,wait_empty

class KeyboardTests(unittest.TestCase):
    def test_encoding_and_explicit_return(self):
        self.assertEqual(encode_text('print "hello"'),b'PRINT "HELLO"')
        self.assertEqual(encode_text('run',True),b'RUN\r')
        self.assertEqual(encode_text('a\r\nb\n',True),b'A\rB\r')
        for text in ('','a'*161,'π','a\t'):
            with self.assertRaises(BrowserError):encode_text(text)

    def test_chunks_stay_inside_ten_byte_buffer(self):
        sock=Mock();sock.__enter__=Mock(return_value=sock);sock.__exit__=Mock(return_value=False)
        sock.recv.side_effect=[b'\1',b'\1',b'X',b'\1',b'X']
        with patch('c64u_browser.keyboard_input.wait_empty') as empty,patch('c64u_browser.keyboard_input.socket.create_connection',return_value=sock):
            self.assertEqual(send_text(UltimateClient('test'),'abcdefghijk'),11)
        packets=[c.args[0] for c in sock.sendall.call_args_list]
        self.assertEqual(packets[1],b'\3\xff\x0a\0ABCDEFGHIJ')
        self.assertEqual(packets[3],b'\3\xff\1\0K')
        self.assertEqual(empty.call_count,5)

    def test_auth_rejection_does_not_send_text(self):
        sock=Mock();sock.__enter__=Mock(return_value=sock);sock.__exit__=Mock(return_value=False)
        sock.recv.return_value=b'\0'
        with patch('c64u_browser.keyboard_input.wait_empty'),patch('c64u_browser.keyboard_input.socket.create_connection',return_value=sock):
            with self.assertRaisesRegex(BrowserError,'up to 0 bytes'):send_text(UltimateClient('test'),'run')
        self.assertEqual(sock.sendall.call_count,1)

    def test_refused_dma_uses_bounded_rest_keyboard_buffer(self):
        client=Mock(timeout=10)
        with patch('c64u_browser.keyboard_input.wait_empty') as empty,patch(
                'c64u_browser.keyboard_input.socket.create_connection',
                side_effect=ConnectionRefusedError):
            self.assertEqual(send_text(client,'abcdefghijk',True),12)
        self.assertEqual(client.write_memory.call_args_list,[
            unittest.mock.call(0x0277,b'ABCDEFGHIJ'),
            unittest.mock.call(0x00c6,b'\x0a'),
            unittest.mock.call(0x0277,b'K\r'),
            unittest.mock.call(0x00c6,b'\x02'),
        ])
        self.assertEqual(empty.call_count,6)

    def test_timed_out_dma_quickly_uses_rest_before_queuing_text(self):
        client=Mock(timeout=10)
        with patch('c64u_browser.keyboard_input.wait_empty'),patch(
                'c64u_browser.keyboard_input.socket.create_connection',
                side_effect=TimeoutError) as connect:
            self.assertEqual(send_text(client,'run',True),4)
        connect.assert_called_once_with((client.host,64),timeout=3)
        self.assertEqual(client.write_memory.call_args_list,[
            unittest.mock.call(0x0277,b'RUN\r'),
            unittest.mock.call(0x00c6,b'\x04'),
        ])

    def test_rest_fallback_never_retries_uncertain_chunk(self):
        client=Mock(timeout=10)
        client.write_memory.side_effect=[{},BrowserError('uncertain response')]
        with patch('c64u_browser.keyboard_input.wait_empty'),patch(
                'c64u_browser.keyboard_input.socket.create_connection',
                side_effect=ConnectionRefusedError):
            with self.assertRaisesRegex(BrowserError,'up to 10 bytes'):
                send_text(client,'abcdefghijk')
        self.assertEqual(client.write_memory.call_count,2)

    def test_occupied_buffer_times_out(self):
        with patch('c64u_browser.keyboard_input.buffer_count',return_value=3),patch('c64u_browser.keyboard_input.time.monotonic',side_effect=[0,6]):
            with self.assertRaisesRegex(BrowserError,'not consumed'):wait_empty(UltimateClient('test'))
