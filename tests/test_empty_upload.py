from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from c64u_browser.transfers import upload_managed,UploadFailure
from c64u_browser.folder_copy import build_plan,execute_plan
from c64u_browser.simulated_ftp_reads import MemoryFilesystem

class EmptyUploadTests(TestCase):
    def test_empty_file_verified_then_batch_continues(self):
        peer=MemoryFilesystem();client=peer.attach()
        with TemporaryDirectory() as d:
            root=Path(d);(root/'empty').touch();(root/'next').write_bytes(b'data')
            plan=build_plan(client,True,root,['empty','next'],False,'/USB2')
            report=execute_plan(client,plan,True,False)
        self.assertFalse(report.error,report.error)
        self.assertEqual(report.completed,['empty','next'])
        self.assertEqual(peer.files,{b'/USB2/empty':b'',b'/USB2/next':b'data'})
        self.assertEqual([c[2] for c in peer.calls if c[0]=='rename'],[b'/USB2/empty',b'/USB2/next'])
        self.assertEqual(0,peer.active)

    def test_bad_empty_size_never_publishes(self):
        peer=MemoryFilesystem()
        with TemporaryDirectory() as d,patch.object(peer,'size',return_value=1):
            p=Path(d)/'empty';p.touch()
            with self.assertRaises(UploadFailure):upload_managed(peer.attach(),p)
        self.assertFalse(any(c[0]=='rename' for c in peer.calls))
        self.assertEqual(0,peer.active)
