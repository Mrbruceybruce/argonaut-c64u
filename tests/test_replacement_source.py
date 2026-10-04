"""Exercise real copy/upload/download code against an in-memory FTP peer."""
import posixpath
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock,patch
from c64u_browser.api import Entry
from c64u_browser.simulated_ftp_reads import MemoryReads
from c64u_browser.folder_copy import build_plan,execute_plan

class ReplacementSourceTests(unittest.TestCase):
 def test_distinct_source_parent_for_local_and_remote_replacements(self):
  for source_local in (True,False):
   with self.subTest(source_local=source_local),TemporaryDirectory() as tmp:
    source=Path(tmp)/'a.png';source.write_bytes(b'new content')
    from c64u_browser.simulated_ftp_reads import MemoryFilesystem
    peer=MemoryFilesystem(files={b'/USB2/dest/a.png':b'old content',b'/USB2/source/a.png':b'new content'},
                          directories=(b'/USB2/dest',b'/USB2/source'))
    client=peer.attach()
    parent=Path(tmp) if source_local else '/USB2/source'
    plan=build_plan(client,source_local,parent,['a.png'],False,'/USB2/dest')
    plan.steps.extend(plan.replacements);plan.conflicts=[]
    result=execute_plan(client,plan,source_local,False)
    self.assertEqual(result.error,'')
    self.assertEqual(peer.files[b'/USB2/dest/a.png'],b'new content')
    self.assertEqual(peer.files[b'/USB2/source/a.png'],b'new content')
    self.assertEqual(source.read_bytes(),b'new content')
    self.assertEqual(peer.directories,{b'/',b'/USB2',b'/USB2/dest',b'/USB2/source'})
    self.assertEqual(set(peer.files),{b'/USB2/dest/a.png',b'/USB2/source/a.png'})
    self.assertEqual(0,peer.active)
