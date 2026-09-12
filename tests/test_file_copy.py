import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from c64u_browser.file_copy import conflicts, copy_files, local_copy
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

    def test_conflicts_include_directories_and_broken_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'dir').mkdir(); (root/'broken').symlink_to(root/'missing')
            self.assertEqual(conflicts(None, ['dir','broken','new'], True, root), ('dir','broken'))
        client=Mock(); client.list_directory.return_value=('/USB2',[SimpleNamespace(name='FILE')])
        self.assertEqual(conflicts(client, ['file','new'],False,'/USB2'), ('file',))

    @patch('c64u_browser.file_copy.upload')
    @patch('c64u_browser.file_copy.download')
    def test_remote_to_remote_and_temp_cleanup(self, download, upload):
        upload.return_value={'path':'/USB2/dst/a'}
        message, partial=copy_files('client',False,'/USB2/src',['a'],False,'/USB2/dst')
        staged=download.call_args.args[2]
        self.assertEqual(download.call_args.args[:2],('client','/USB2/src/a'))
        self.assertEqual(upload.call_args.args[1],staged)
        self.assertFalse(staged.parent.exists())
        self.assertIsNone(partial)
        self.assertIn('Copied 1', message)

    @patch('c64u_browser.file_copy.upload')
    def test_batch_stops_and_exposes_partial(self, upload):
        upload.side_effect=[{'path':'/USB2/a'},UploadFailure('interrupted','/USB2/c64u-part-123')]
        message, partial=copy_files('client',True,Path('/tmp'),['a','b','c'],False,'/USB2')
        self.assertEqual(upload.call_count,2)
        self.assertEqual(partial,'/USB2/c64u-part-123')
        self.assertIn('1 of 3',message)
