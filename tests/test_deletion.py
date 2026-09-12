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
        tree={'/USB2':[('folder','dir')],'/USB2/folder':[('a','file'),('b','file')]}
        client=Mock();client.list_directory.side_effect=lambda p:(p,[SimpleNamespace(name=n,kind=k,size=1) for n,k in tree[p]])
        items=prepare(client,False,['/USB2/folder'])
        def remove(c,action,path,confirmation):
            self.assertEqual(path,confirmation)
            if path.endswith('/b'):raise OSError('offline')
            parent,name=path.rsplit('/',1);tree[parent]=[(n,k) for n,k in tree[parent] if n!=name]
        with patch('c64u_browser.deletion.operate',side_effect=remove) as op:
            removed,error=delete_reviewed(client,False,['/USB2/folder'],items)
        self.assertEqual(removed,['/USB2/folder/a']);self.assertEqual(op.call_count,2);self.assertIn('offline',error)
