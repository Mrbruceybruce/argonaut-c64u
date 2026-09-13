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

    def test_occupied_buffer_times_out(self):
        with patch('c64u_browser.keyboard_input.buffer_count',return_value=3),patch('c64u_browser.keyboard_input.time.monotonic',side_effect=[0,6]):
            with self.assertRaisesRegex(BrowserError,'not consumed'):wait_empty(UltimateClient('test'))
