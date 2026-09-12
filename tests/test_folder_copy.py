import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from types import SimpleNamespace
from c64u_browser.folder_copy import build_plan, execute_plan
from c64u_browser.api import BrowserError

class FolderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.src=self.root/'src'; self.dst=self.root/'dst'
        self.src.mkdir(); self.dst.mkdir()
        (self.src/'folder'/'nested').mkdir(parents=True)
        (self.src/'folder'/'empty').mkdir()
        (self.src/'folder'/'nested'/'a').write_text('new')
        (self.src/'folder'/'b').write_text('second')
    def plan(self): return build_plan(None,True,self.src,['folder'],True,self.dst)
    def test_nested_copy_empty_folder_and_merge_skip(self):
        report=execute_plan(None,self.plan(),True,True)
        self.assertFalse(report.error)
        self.assertEqual((self.dst/'folder'/'nested'/'a').read_text(),'new')
        self.assertTrue((self.dst/'folder'/'empty').is_dir())
        (self.src/'folder'/'nested'/'a').write_text('changed')
        (self.src/'folder'/'c').write_text('third')
        plan=self.plan(); self.assertEqual(set(plan.conflicts),{'folder/b','folder/nested/a'})
        report=execute_plan(None,plan,True,True)
        self.assertFalse(report.error)
        self.assertEqual((self.dst/'folder'/'nested'/'a').read_text(),'new')
        self.assertEqual((self.dst/'folder'/'c').read_text(),'third')
    def test_conflicting_folder_is_skipped_without_descendants(self):
        (self.dst/'folder').write_text('keep')
        plan=self.plan(); self.assertEqual(plan.conflicts,['folder']); self.assertFalse(plan.steps)
        self.assertEqual((self.dst/'folder').read_text(),'keep')
    def test_self_descendant_and_symlink_rejected(self):
        for dest in (self.src/'folder',self.src/'folder'/'nested'):
            with self.assertRaises(BrowserError): build_plan(None,True,self.src,['folder'],True,dest)
        (self.src/'folder'/'loop').symlink_to(self.src/'folder')
        with self.assertRaises(BrowserError): self.plan()
    def test_interruption_reports_completed_remaining_partial(self):
        plan=self.plan()
        with patch('c64u_browser.folder_copy.copy_files',return_value=('0 of 1 copied. interrupted','/USB2/partial')):
            report=execute_plan(None,plan,True,True)
        self.assertEqual(report.completed,['folder/'])
        self.assertEqual(report.remaining[0],'folder/b')
        self.assertEqual(report.partial,'/USB2/partial')
        self.assertIn('Unfinished',report.details())
    def test_new_conflict_and_changed_source_stop(self):
        plan=self.plan(); (self.dst/'folder').mkdir()
        report=execute_plan(None,plan,True,True)
        self.assertIn('appeared',report.error)
        self.assertFalse(report.completed)
        plan=self.plan(); (self.src/'folder'/'b').unlink()
        report=execute_plan(None,plan,True,True)
        self.assertIn('Source changed',report.error)
    def test_remote_planning_and_execution(self):
        tree={'/USB2':[('folder','dir')], '/USB2/folder':[('a','file'),('empty','dir')], '/USB2/folder/empty':[]}
        client=Mock()
        client.list_directory.side_effect=lambda path:(path,[SimpleNamespace(name=n,kind=k) for n,k in tree[path]])
        plan=build_plan(client,False,'/USB2',['folder'],True,self.dst)
        with patch('c64u_browser.folder_copy.copy_files',return_value=('Copied 1 file(s): a',None)) as copy:
            report=execute_plan(client,plan,False,True)
        self.assertFalse(report.error); self.assertTrue((self.dst/'folder'/'empty').is_dir())
        self.assertEqual(copy.call_args.args[2:4],('/USB2/folder',['a']))
    def test_case_collision_remote_destination_rejected(self):
        (self.src/'folder'/'B').write_text('collision')
        client=Mock(); client.list_directory.return_value=('/USB2',[])
        with self.assertRaises(BrowserError): build_plan(client,True,self.src,['folder'],False,'/USB2')
    def test_upload_creates_parent_directories_before_files(self):
        tree={'/USB2':[]}
        client=Mock()
        client.list_directory.side_effect=lambda path:(path,[SimpleNamespace(name=n,kind=k) for n,k in tree[path]])
        plan=build_plan(client,True,self.src,['folder'],False,'/USB2')
        def mkdir(c,action,path):
            self.assertEqual(action,'mkdir')
            parent,name=path.rsplit('/',1); tree[parent].append((name,'dir')); tree[path]=[]
        def copy(c,sl,parent,names,local,dest,progress):
            self.assertIn(dest,tree)
            tree[dest].append((names[0],'file'))
            return 'Copied 1 file(s): '+names[0],None
        with patch('c64u_browser.folder_copy.operate',side_effect=mkdir), patch('c64u_browser.folder_copy.copy_files',side_effect=copy):
            report=execute_plan(client,plan,True,False)
        self.assertFalse(report.error,report.error)
        self.assertIn(('a','file'),tree['/USB2/folder/nested'])
        self.assertIn('/USB2/folder/empty',tree)
    def test_destination_directory_replaced_with_link_stops(self):
        (self.dst/'folder').mkdir()
        plan=self.plan()
        (self.dst/'folder').rmdir(); (self.dst/'folder').symlink_to(self.src/'folder')
        report=execute_plan(None,plan,True,True)
        self.assertTrue(report.error)
        self.assertFalse(report.completed)
