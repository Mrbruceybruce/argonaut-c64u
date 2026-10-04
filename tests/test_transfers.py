import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
from c64u_browser.simulated_ftp_reads import MemoryReads
from c64u_browser.api import BrowserError
from c64u_browser.transfers import download, remote_file

class Transfers(unittest.TestCase):
    def test_scope(self):
        for path in ['/USB0', '/SD', '/Flash/file', '/USB2/../Flash/file', '/USB2/a\nDELE b']:
            with self.assertRaises(BrowserError): remote_file(path)

    def test_other_storage(self):
        for path in ('/USB0/file', '/USB1/folder/file', '/SD/file'):
            self.assertEqual(remote_file(path), path)

    def test_download_success(self):
        with tempfile.TemporaryDirectory() as directory:
            peer = MemoryReads(files={b'/USB2/file': b'abc'})
            target = Path(directory)/'file'
            self.assertEqual(download(peer.attach(), '/USB2/file', target)['bytes'], 3)
            self.assertEqual(target.read_bytes(), b'abc')
            self.assertEqual([target], list(Path(directory).iterdir()))
            self.assertEqual((0, 1), (peer.active, peer.released))

    def test_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            peer = MemoryReads()
            target = Path(directory)/'file'
            target.write_bytes(b'keep')
            with self.assertRaises(BrowserError):download(peer.attach(), '/USB2/file', target)
            self.assertEqual(0, peer.acquired)
            self.assertEqual(target.read_bytes(), b'keep')

    def test_interrupted_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            peer = MemoryReads(files={b'/USB2/file': b'abc'}, interrupted=True)
            with self.assertRaises(BrowserError):download(peer.attach(), '/USB2/file', Path(directory)/'file')
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertEqual((0, 1), (peer.active, peer.released))

    def test_concurrent_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'file'
            peer = MemoryReads(files={b'/USB2/file': b'abc'}, after_read=lambda:target.write_bytes(b'keep'))
            with self.assertRaises(BrowserError):download(peer.attach(), '/USB2/file', target)
            self.assertEqual(target.read_bytes(), b'keep')
            self.assertEqual([target], list(Path(directory).iterdir()))

    def test_direct_upload(self):
        from c64u_browser.transfers import upload
        with tempfile.TemporaryDirectory() as directory, patch('c64u_browser.transfers.connect') as connect, patch('c64u_browser.files.inspect', return_value=None):
            source = Path(directory)/'test.txt'; source.write_bytes(b'abc')
            ftp = connect.return_value
            ftp.storbinary.side_effect = lambda cmd, stream, callback: callback(stream.read())
            ftp.retrbinary.side_effect = lambda cmd, cb: cb(b'abc')
            ftp.size.return_value = 3
            self.assertEqual(upload(Mock(), source, '/USB2/Utilities')['path'], '/USB2/Utilities/test.txt')
            ftp.mkd.assert_not_called()
            self.assertEqual(ftp.rename.call_args.args[1], '/USB2/Utilities/test.txt')
    def test_direct_upload_collision(self):
        from c64u_browser.transfers import upload
        with patch('c64u_browser.files.inspect', return_value=object()), patch('c64u_browser.transfers.connect') as connect:
            with self.assertRaises(BrowserError): upload(Mock(), 'test.txt')
            connect.assert_not_called()
    def test_destination_appears_during_upload(self):
        from c64u_browser.transfers import upload
        with tempfile.TemporaryDirectory() as directory, patch('c64u_browser.transfers.connect') as connect, patch('c64u_browser.files.inspect', side_effect=[None, None, object()]):
            source = Path(directory)/'test.txt'; source.write_bytes(b'abc')
            ftp = connect.return_value
            ftp.storbinary.side_effect = lambda cmd, stream, callback: callback(stream.read())
            ftp.retrbinary.side_effect = lambda cmd, cb: cb(b'abc')
            ftp.size.return_value = 3
            with self.assertRaisesRegex(BrowserError, 'appeared'): upload(Mock(), source)
            ftp.rename.assert_not_called()
