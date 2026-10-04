import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from c64u_browser.file_copy import copy_files, local_copy
from c64u_browser.transfers import UploadFailure

class CopyTests(unittest.TestCase):
    def test_local_copy_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'source'; target=root/'target'
            source.write_bytes(b'content'*1000)
            local_copy(source, target, lambda _: None)
            self.assertEqual(target.read_bytes(), source.read_bytes())
            source.write_bytes(b'changed')
            with self.assertRaises(Exception): local_copy(source, target, lambda _: None)
            self.assertEqual(target.read_bytes(), b'content'*1000)
            self.assertEqual(set(p.name for p in root.iterdir()), {'source','target'})

    def test_concurrent_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source'; target=root/'target'
            source.write_bytes(b'new')
            with self.assertRaises(FileExistsError):
                local_copy(source, target, lambda _: target.write_bytes(b'existing'))
            self.assertEqual(target.read_bytes(), b'existing')
            self.assertEqual(len(list(root.iterdir())), 2)


    def test_remote_to_remote_and_temp_cleanup(self):
        from c64u_browser.simulated_ftp_reads import MemoryFilesystem
        from c64u_browser.folder_copy import build_plan,execute_plan
        peer=MemoryFilesystem(files={b'/USB2/src/a':b'content'},directories=(b'/USB2/src',b'/USB2/dst'))
        client=peer.attach();plan=build_plan(client,False,'/USB2/src',['a'],False,'/USB2/dst')
        from c64u_browser.transfers import download
        with patch('c64u_browser.folder_steps.download',wraps=download) as copied:
            result=execute_plan(client,plan,False,False)
        staged=Path(copied.call_args.args[2])
        self.assertFalse(staged.exists())
        self.assertFalse(staged.parent.exists())
        self.assertFalse(result.error,result.error)
        self.assertEqual(peer.files,{b'/USB2/src/a':b'content',b'/USB2/dst/a':b'content'})
        self.assertEqual((),result.folder_steps[0].local_cleanup)
        self.assertEqual(0,peer.active)

    def test_batch_stops_and_exposes_partial(self):
        from c64u_browser.simulated_ftp_reads import MemoryFilesystem
        from c64u_browser.folder_copy import build_plan,execute_plan
        peer=MemoryFilesystem();client=peer.attach()
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('a','b','c'):(Path(tmp)/name).write_bytes(name.encode())
            plan=build_plan(client,True,tmp,['a','b','c'],False,'/USB2')
            reads=[0]
            def fail(path):
                reads[0]+=1
                if reads[0]==2:peer.interrupted=True
            peer.before_read=fail
            result=execute_plan(client,plan,True,False)
        self.assertEqual(result.completed,['a'])
        self.assertEqual(result.remaining,['b','c'])
        self.assertIn(result.partial.encode(),peer.files)
        self.assertTrue(result.partial.startswith('/USB2/c64u-part-'))
        self.assertEqual(0,peer.active)
