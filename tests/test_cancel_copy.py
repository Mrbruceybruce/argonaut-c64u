from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock,patch
from c64u_browser.api import BrowserError
from c64u_browser.transfers import upload, download, UploadFailure
from c64u_browser.file_copy import local_copy
from c64u_browser.folder_copy import build_plan, execute_plan

class CancelTests(TestCase):
    def check(self):raise BrowserError('Transfer cancelled by user.')
    def test_local_cleanup_and_between_files(self):
        with TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.write_bytes(b'a'*2000000)
            def progress(n):self.check()
            with self.assertRaises(BrowserError):local_copy(source,root/'dest',progress)
            self.assertEqual(list(root.iterdir()),[source])
            folder=root/'folder';folder.mkdir()
            plan=build_plan(None,True,root,['source'],True,folder)
            progress.check=self.check
            report=execute_plan(None,plan,True,True,progress)
            self.assertTrue(report.error);self.assertEqual(report.remaining,['source']);self.assertFalse(report.completed)
    def test_download_cancellation_removes_temp(self):
        with TemporaryDirectory() as d:
            ftp=Mock();ftp.size.return_value=4
            ftp.retrbinary.side_effect=lambda cmd,receive:receive(b'data')
            def progress(n):self.check()
            with patch('c64u_browser.transfers.connect',return_value=ftp):
                with self.assertRaises(BrowserError):download(Mock(),'/USB2/a',Path(d)/'a',progress)
            self.assertFalse(list(Path(d).iterdir()));ftp.close.assert_called_once()
    def test_upload_cancel_verification_retains_partial_without_publish(self):
        with TemporaryDirectory() as d:
            source=Path(d)/'a';source.write_bytes(b'data')
            ftp=Mock();ftp.size.return_value=4
            ftp.storbinary.side_effect=lambda cmd,stream,callback:callback(stream.read())
            cancelled=[False]
            def progress(n):cancelled[0]=True
            def check():
                if cancelled[0]:self.check()
            progress.check=check
            ftp.retrbinary.side_effect=lambda cmd,receive:receive(b'data')
            with patch('c64u_browser.transfers.connect',return_value=ftp),patch('c64u_browser.files.inspect',return_value=None):
                with self.assertRaises(UploadFailure) as caught:upload(Mock(),source,'/USB2',progress)
            self.assertTrue(caught.exception.partial_path.startswith('/USB2/c64u-part-'))
            ftp.rename.assert_not_called();ftp.close.assert_called_once()
    def test_cancel_preparation_does_not_write(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(BrowserError):build_plan(None,True,d,['folder'],True,d,self.check)
            self.assertFalse(list(Path(d).iterdir()))
