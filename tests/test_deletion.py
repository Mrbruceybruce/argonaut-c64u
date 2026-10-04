from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
from types import SimpleNamespace
from c64u_browser.deletion import prepare, delete_reviewed

class DeletionTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'folder';self.folder.mkdir()
        (self.folder/'nested').mkdir();(self.folder/'nested'/'a').write_text('a')
        (self.folder/'b').write_text('b')
    def test_recursive_multiple_and_links(self):
        outside=self.root/'outside';outside.write_text('keep')
        (self.folder/'link').symlink_to(outside)
        second=self.root/'second';second.write_text('second')
        targets=[self.folder,second]
        items=prepare(None,True,targets)
        removed,error=delete_reviewed(None,True,targets,items)
        self.assertIsNone(error);self.assertEqual(len(removed),len(items))
        self.assertFalse(self.folder.exists());self.assertFalse(second.exists());self.assertEqual(outside.read_text(),'keep')
    def test_new_content_aborts_before_any_delete(self):
        items=prepare(None,True,[self.folder]);(self.folder/'new').write_text('new')
        removed,error=delete_reviewed(None,True,[self.folder],items)
        self.assertFalse(removed);self.assertIn('changed',error);self.assertTrue((self.folder/'b').exists())
    def test_replaced_folder_link_aborts(self):
        items=prepare(None,True,[self.folder])
        moved=self.root/'moved';self.folder.rename(moved);self.folder.symlink_to(moved)
        removed,error=delete_reviewed(None,True,[self.folder],items)
        self.assertFalse(removed);self.assertTrue(error);self.assertTrue((moved/'b').exists())
    def test_remote_children_before_parent_and_failure_stops(self):
        from c64u_browser.simulated_ftp_reads import MemoryFilesystem
        peer=MemoryFilesystem(files={b'/USB2/folder/a':b'a',b'/USB2/folder/b':b'b'},directories=(b'/USB2/folder',))
        client=peer.attach();items=prepare(client,False,['/USB2/folder'])
        def fail(verb,path,destination):
            if path.endswith(b'/b'):raise OSError('offline')
        peer.before_mutation=fail
        result=delete_reviewed(client,False,['/USB2/folder'],items)
        self.assertEqual(result.removed,['/USB2/folder/a'])
        self.assertEqual(2,len([c for c in peer.calls if c[0]=='delete']))
        self.assertIn('offline',str(result.error))
        self.assertIn(b'/USB2/folder/b',peer.files)
        self.assertEqual(0,peer.active)
