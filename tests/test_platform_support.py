import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from c64u_browser.platform_support import parents,publish_new,contains_path,config_base
class Platform(unittest.TestCase):
 def test_remote_parents(self):self.assertEqual(list(parents('/USB2/folder/file',False)),['/USB2/folder','/USB2'])
 def test_local_parents_terminate(self):
  p=Path.home()/'folder'/'file';self.assertEqual(list(parents(p,True)),[str(x) for x in p.parents if x.parent!=x])
 def test_contains(self):
  self.assertTrue(contains_path(Path.home(),Path.home()/'folder'))
  self.assertFalse(contains_path(Path.home()/'a',Path.home()/'ab'))
 def test_publish_no_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   source=Path(d)/'source';dest=Path(d)/'dest';source.write_bytes(b'new');dest.write_bytes(b'old')
   with self.assertRaises(FileExistsError):publish_new(source,dest)
   self.assertEqual(dest.read_bytes(),b'old');dest.unlink();publish_new(source,dest);self.assertEqual(dest.read_bytes(),b'new')
