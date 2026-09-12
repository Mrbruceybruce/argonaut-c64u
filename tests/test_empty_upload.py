from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock,patch
from c64u_browser.transfers import upload,UploadFailure
from c64u_browser.folder_copy import build_plan,execute_plan

class EmptyUploadTests(TestCase):
    def test_empty_file_verified_then_batch_continues(self):
        with TemporaryDirectory() as d:
            root=Path(d);(root/'empty').touch();(root/'next').write_bytes(b'data')
            client=Mock();client.list_directory.return_value=('/USB2',[])
            plan=build_plan(client,True,root,['empty','next'],False,'/USB2')
            ftp=Mock();stored={}
            def store(cmd,stream,callback):
                stored[cmd[5:]]=stream.read()
                if stored[cmd[5:]]:callback(stored[cmd[5:]])
            ftp.storbinary.side_effect=store
            ftp.retrbinary.side_effect=lambda cmd,cb: cb(stored[cmd[5:]]) if stored[cmd[5:]] else None
            ftp.size.side_effect=lambda path:len(stored[path])
            with patch('c64u_browser.transfers.connect',return_value=ftp),patch('c64u_browser.files.inspect',return_value=None):
                report=execute_plan(client,plan,True,False)
            self.assertFalse(report.error,report.error)
            self.assertEqual(report.completed,['empty','next'])
            self.assertEqual([call.args[1] for call in ftp.rename.call_args_list],['/USB2/empty','/USB2/next'])
    def test_bad_empty_size_never_publishes(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'empty';p.touch();ftp=Mock();ftp.size.return_value=1
            with patch('c64u_browser.transfers.connect',return_value=ftp),patch('c64u_browser.files.inspect',return_value=None):
                with self.assertRaises(UploadFailure):upload(Mock(),p)
            ftp.rename.assert_not_called()
