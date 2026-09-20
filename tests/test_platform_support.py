import stat,unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from c64u_browser.platform_support import parents,publish_new,contains_path,config_base,local_hidden
class Platform(unittest.TestCase):
 def test_remote_parents(self):self.assertEqual(list(parents('/USB2/folder/file',False)),['/USB2/folder','/USB2'])
 def test_local_parents_terminate(self):
  p=Path.home()/'folder'/'file';self.assertEqual(list(parents(p,True)),[str(x) for x in p.parents if x.parent!=x])
 def test_contains(self):
  self.assertTrue(contains_path(Path.home(),Path.home()/'folder'))
  self.assertFalse(contains_path(Path.home()/'a',Path.home()/'ab'))
 def test_dot_names_are_hidden(self):
  self.assertTrue(local_hidden(Path('/tmp/.secret')))
  self.assertFalse(local_hidden(Path('/tmp/ordinary')))
 def test_windows_hidden_attribute_is_recognized(self):
  hidden=SimpleNamespace(st_file_attributes=stat.FILE_ATTRIBUTE_HIDDEN)
  with patch.object(Path,'lstat',return_value=hidden):
   self.assertTrue(local_hidden(Path('/tmp/ordinary')))
 def test_publish_no_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   source=Path(d)/'source';dest=Path(d)/'dest';source.write_bytes(b'new');dest.write_bytes(b'old')
   with self.assertRaises(FileExistsError):publish_new(source,dest)
   self.assertEqual(dest.read_bytes(),b'old');dest.unlink();publish_new(source,dest);self.assertEqual(dest.read_bytes(),b'new')
 def test_portable_preferences_and_credentials(self):
  import sys
  from c64u_browser.credentials import Credentials
  from c64u_browser.profiles import Preferences
  with tempfile.TemporaryDirectory() as d,patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(Path(d)/'Argonaut.exe')):
   (Path(d)/'portable.flag').touch()
   self.assertEqual(Preferences().path,Path(d).resolve()/'Data'/'argonaut'/'config.json')
   creds=Credentials();self.assertTrue(creds.session_only);self.assertEqual(creds.get('id'),'')
   from c64u_browser.api import BrowserError
   with self.assertRaises(BrowserError):creds.set('id','secret')
   creds.delete('id')
 def test_nonportable_does_not_use_application_folder(self):
  import sys
  from c64u_browser.platform_support import portable_root
  with tempfile.TemporaryDirectory() as d,patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(Path(d)/'Argonaut.exe')):
   self.assertIsNone(portable_root())
