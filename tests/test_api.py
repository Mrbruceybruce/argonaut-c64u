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
