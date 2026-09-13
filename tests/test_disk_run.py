import unittest
from unittest.mock import Mock, patch
from c64u_browser.api import UltimateClient, BrowserError
from c64u_browser.disk_run import mount_and_run

class DiskRunTests(unittest.TestCase):
    def setUp(self):
        self.client=UltimateClient('test',password='secret')
        self.image=b'\0'*174848
        self.ftp=Mock();self.ftp.size.return_value=len(self.image)
        self.ftp.retrbinary.side_effect=lambda command,cb:cb(self.image)
        self.sock=Mock();self.sock.recv.side_effect=[b'\1',b'\2',b'O',b'K']
        self.sock.__enter__=Mock(return_value=self.sock)
        self.sock.__exit__=Mock(return_value=False)

    def run_image(self):
        with patch('c64u_browser.disk_run.connect',return_value=self.ftp),patch('c64u_browser.disk_run.socket.create_connection',return_value=self.sock):
            mount_and_run(self.client,'/USB2/game.d64')

    def test_wire_format_and_processing_barrier(self):
        self.run_image()
        messages=[c.args[0] for c in self.sock.sendall.call_args_list]
        self.assertEqual(messages,[b'\x1f\xff\x06\x00secret',b'\x0b\xff'+len(self.image).to_bytes(3,'little')+self.image,b'\x0e\xff\0\0'])
        self.ftp.close.assert_called_once()

    def test_auth_failure_never_runs_image(self):
        self.sock.recv.side_effect=[b'\0']
        with self.assertRaisesRegex(BrowserError,'Nothing was started.*authentication'):
            self.run_image()
        self.assertEqual(self.sock.sendall.call_count,1)

    def test_incomplete_download_never_connects_dma(self):
        self.ftp.retrbinary.side_effect=lambda command,cb:cb(b'short')
        with patch('c64u_browser.disk_run.connect',return_value=self.ftp),patch('c64u_browser.disk_run.socket.create_connection') as dma:
            with self.assertRaisesRegex(BrowserError,'Incomplete'):mount_and_run(self.client,'/USB2/game.d64')
            dma.assert_not_called()
        self.ftp.close.assert_called_once()

    def test_invalid_paths_never_download(self):
        with patch('c64u_browser.disk_run.connect') as ftp:
            for path in ('','game.d64','/USB2/../game.d64','/USB2/game.d81','/USB2/game.d64\n'):
                with self.assertRaises(BrowserError):mount_and_run(self.client,path)
            ftp.assert_not_called()

    def test_failure_after_send_reports_uncertainty(self):
        self.sock.recv.side_effect=[b'\1',b'']
        with self.assertRaisesRegex(BrowserError,'Run may have started'):self.run_image()
