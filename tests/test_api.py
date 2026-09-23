import ftplib
import unittest
from unittest.mock import patch
from c64u_browser.api import (UltimateClient, BrowserError, IdentityEntry,
                              parse_list)

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

    def test_identity_listing_preserves_filename_octets_and_sorts_raw_bytes(self):
        with patch('c64u_browser.api.ftplib.FTP') as factory:
            ftp = factory.return_value
            ftp.pwd.return_value = '/USB1/games/s'
            ftp.mlsd.return_value = [
                ('Schatzj\x84ger [Side 2] [Ariolasoft] [TWG].d64',
                 {'type':'file','size':'174848'}),
                ('ASCII.d64', {'type':'file','size':'174848'}),
                ('Schatzj\x84ger [Side 1] [Ariolasoft] [TWG].d64',
                 {'type':'file','size':'174848'}),
                ('.', {'type':'cdir'}),
            ]
            actual, entries = UltimateClient('device').list_directory_identity(
                b'/USB1/games/s')
        factory.assert_called_once_with(timeout=10, encoding='latin-1')
        self.assertEqual(b'/USB1/games/s', actual)
        self.assertEqual([
            b'ASCII.d64',
            b'Schatzj\x84ger [Side 1] [Ariolasoft] [TWG].d64',
            b'Schatzj\x84ger [Side 2] [Ariolasoft] [TWG].d64',
        ], [entry.name for entry in entries])
        self.assertTrue(all(isinstance(entry, IdentityEntry)
                            for entry in entries))

    def test_identity_listing_fallback_preserves_non_utf8_octet(self):
        with patch('c64u_browser.api.ftplib.FTP') as factory:
            ftp = factory.return_value
            ftp.pwd.return_value = '/USB1'
            ftp.mlsd.side_effect = ftplib.error_perm('502 Unsupported')
            ftp.retrlines.side_effect = lambda _cmd, callback: callback(
                '-rw-rw-rw- 1 user ftp 174848 Sep 07 2026 Schatzj\x84ger.d64')
            actual, entries = UltimateClient('device').list_directory_identity(
                b'/USB1')
        self.assertEqual(b'/USB1', actual)
        self.assertEqual(b'Schatzj\x84ger.d64', entries[0].name)

    def test_identity_listing_rejects_text_and_control_path(self):
        client = UltimateClient('device')
        for path in ('/USB1', b'/USB1\rDELE'):
            with self.subTest(path=path), self.assertRaises(BrowserError):
                client.list_directory_identity(path)
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

    def test_create_d64_uses_native_encoded_route(self):
        client=UltimateClient('device')
        with patch.object(client,'_request_json',return_value={'errors':[]}) as request:
            client.create_d64('/USB2/My disks/New disk.d64','MY DISK')
        request.assert_called_once_with(
            'PUT','/v1/files/USB2/My%20disks/New%20disk.d64:create_d64?tracks=35&diskname=MY+DISK')

    def test_create_d64_rejects_unsafe_or_nonstandard_arguments(self):
        client=UltimateClient('device')
        cases=(('relative.d64','DISK',35),('/USB2/../bad.d64','DISK',35),
               ('/USB2/not-d64.txt','DISK',35),('/USB2/new.d64','',35),
               ('/USB2/new.d64','X'*17,35),('/USB2/new.d64','DISK',40))
        for path,name,tracks in cases:
            with self.subTest(path=path,name=name,tracks=tracks),self.assertRaises(BrowserError):
                client.create_d64(path,name,tracks)

    def test_run_crt_supports_resident_and_attached_routes(self):
        client=UltimateClient('device')
        with patch.object(client,'_request_json',return_value={'errors':[]}) as request:
            client.run_crt('/USB2/Games/My cart.crt')
        request.assert_called_once_with(
            'PUT','/v1/runners:run_crt?file=%2FUSB2%2FGames%2FMy+cart.crt')
        with patch.object(client,'_request_binary_json',return_value={'errors':[]}) as request:
            client.run_crt_data(b'C64 CARTRIDGE data','My cart.crt')
        request.assert_called_once_with(
            '/v1/runners:run_crt',b'C64 CARTRIDGE data','My cart.crt')
        for path in ('relative.crt','/USB2/../bad.crt','/USB2/game.d64'):
            with self.subTest(path=path),self.assertRaises(BrowserError):
                client.run_crt(path)
        for data,name in ((b'','game.crt'),(b'x','../game.crt'),
                          (b'x','game.d64')):
            with self.subTest(name=name),self.assertRaises(BrowserError):
                client.run_crt_data(data,name)
