import ftplib
import unittest
from unittest.mock import patch
from c64u_browser.api import UltimateClient, BrowserError, parse_list

class Tests(unittest.TestCase):
    def test_spaces(self):
        self.assertEqual(parse_list('-rw-rw-rw- 1 user ftp 123 Sep 07 12:30 My  game.d64').name, 'My  game.d64')
    def test_unknown_format(self):
        with self.assertRaises(BrowserError): parse_list('garbage')
    def test_injection(self):
        with patch('c64u_browser.api.ftplib.FTP') as factory:
            with self.assertRaises(BrowserError): UltimateClient('device').list_directory('/\r\nDELE file')
            factory.assert_not_called()
    def test_mlsd(self):
        with patch('c64u_browser.api.ftplib.FTP') as factory:
            ftp = factory.return_value
            ftp.mlsd.return_value = [('game', {'type':'file','size':'12'}), ('Usb1', {'type':'dir'})]
            self.assertEqual(UltimateClient('device').list_directory()[1][0].name, 'Usb1')
            ftp.close.assert_called_once()
    def test_fallback(self):
        with patch('c64u_browser.api.ftplib.FTP') as factory:
            ftp = factory.return_value
            ftp.mlsd.side_effect = ftplib.error_perm('502 Unsupported')
            ftp.retrlines.side_effect = lambda cmd, cb: cb('drw-rw-rw- 1 user ftp 0 Sep 07 2026 Usb1')
            self.assertEqual(UltimateClient('device').list_directory()[1][0].name, 'Usb1')
    def test_denied(self):
        with patch('c64u_browser.api.ftplib.FTP') as factory:
            ftp = factory.return_value
            ftp.mlsd.side_effect = ftplib.error_perm('550 Denied')
            with self.assertRaises(BrowserError): UltimateClient('device').list_directory()
            ftp.retrlines.assert_not_called()
            ftp.close.assert_called_once()
    def test_run_prg_validates_and_encodes_path(self):
        client=UltimateClient('device')
        with patch.object(client,'_request_json',return_value={'errors':[]}) as request:
            client.run_prg('/USB2/Argonaut AI.prg')
        request.assert_called_once_with(
            'PUT','/v1/runners:run_prg?file=%2FUSB2%2FArgonaut+AI.prg')
        for path in ('relative.prg','/USB2/../bad.prg','/USB2/readme.txt'):
            with self.subTest(path=path),self.assertRaises(BrowserError):
                client.run_prg(path)
    def test_write_memory_is_bounded_and_encoded(self):
        client=UltimateClient('device')
        with patch.object(client,'_request_json',return_value={'errors':[]}) as request:
            client.write_memory(0x0277,b'A\r')
        request.assert_called_once_with(
            'PUT','/v1/machine:writemem?address=0277&data=410D')
        for address,data in ((-1,b'A'),(0xffff,b'AB'),(0x0277,b''),
                             (0x0277,b'A'*129),(0x0277,'A')):
            with self.subTest(address=address,data=data),self.assertRaises(BrowserError):
                client.write_memory(address,data)
