import unittest
from unittest.mock import Mock, patch
from c64u_browser.api import Entry, BrowserError
from c64u_browser.files import operate_managed, child

class Files(unittest.TestCase):
    def test_invalid_names(self):
        for name in ['..', 'a/b', 'a\\b', 'x*', 'name.', '']:
            with self.assertRaises(BrowserError): child('/USB2', name)
    def peer(self, files=None, directories=()):
        from c64u_browser.simulated_ftp_reads import MemoryFilesystem
        peer=MemoryFilesystem(files=files,directories=directories)
        self.addCleanup(lambda:self.assertEqual(0,peer.active))
        return peer,peer.attach()

    def test_existing_case_insensitive_rename(self):
        peer,client=self.peer({b'/USB2/a':b'a',b'/USB2/B':b'b'})
        with self.assertRaises(BrowserError):operate_managed(client,'rename','/USB2/a','b')
        self.assertFalse(any(c[0]=='rename' for c in peer.calls))
    def test_confirmation(self):
        peer,client=self.peer({b'/USB2/a':b'a'})
        with self.assertRaises(BrowserError):operate_managed(client,'delete','/USB2/a',confirmation='yes')
        self.assertEqual([],peer.calls)
    def test_nonempty_folder(self):
        peer,client=self.peer({b'/USB2/a/b':b'b'},(b'/USB2/a',))
        with self.assertRaises(BrowserError):operate_managed(client,'delete','/USB2/a',confirmation='/USB2/a')
        self.assertFalse(any(c[0]=='rmdir' for c in peer.calls))
    def test_delete_file(self):
        peer,client=self.peer({b'/USB2/a':b'a'})
        result=operate_managed(client,'delete','/USB2/a',confirmation='/USB2/a')
        self.assertEqual({},peer.files)
        self.assertEqual('completed',result.completed[0]['outcome'])
        self.assertFalse(any(c[0]=='rmdir' for c in peer.calls))
    def test_mkdir(self):
        peer,client=self.peer()
        operate_managed(client,'mkdir','/USB2/new')
        self.assertIn(b'/USB2/new',peer.directories)
    def test_case_only_rename(self):
        peer,client=self.peer(directories=(b'/USB2/Test',))
        result=operate_managed(client,'rename','/USB2/Test','test')
        calls=[c for c in peer.calls if c[0]=='rename']
        self.assertEqual(result.destination,'/USB2/test')
        self.assertEqual(len(calls),2)
        temporary=calls[0][2]
        self.assertTrue(temporary.startswith(b'/USB2/c64u-rename-'))
        self.assertEqual(calls[0][1],b'/USB2/Test')
        self.assertEqual(calls[1][1:],(temporary,b'/USB2/test'))
        self.assertEqual('passed',result.verification)
    def test_case_only_second_step_failure(self):
        peer,client=self.peer({b'/USB2/Test':b'a'})
        def fail(verb,path,destination):
            if verb=='rename' and destination==b'/USB2/test':raise BrowserError('connection lost')
        peer.before_mutation=fail
        with self.assertRaises(BrowserError) as caught:operate_managed(client,'rename','/USB2/Test','test')
        result=caught.exception.result
        self.assertEqual(1,len(result.completed))
        self.assertIn(result.temporary.encode(),peer.files)
        self.assertEqual(2,len([c for c in peer.calls if c[0]=='rename']))
        self.assertFalse(any(c[0]=='delete' for c in peer.calls))
    def test_same_name_noop(self):
        peer,client=self.peer(directories=(b'/USB2/Test',))
        result=operate_managed(client,'rename','/USB2/Test','Test')
        self.assertEqual(result.destination,'/USB2/Test')
        self.assertFalse(result.completed)
        self.assertFalse(any(c[0]=='rename' for c in peer.calls))
