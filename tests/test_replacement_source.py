"""Exercise real copy/upload/download code against an in-memory FTP peer."""
import posixpath
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock,patch
from c64u_browser.api import Entry
from c64u_browser.folder_copy import build_plan,execute_plan

class ReplacementSourceTests(unittest.TestCase):
 def test_distinct_source_parent_for_local_and_remote_replacements(self):
  for source_local in (True,False):
   with self.subTest(source_local=source_local),TemporaryDirectory() as tmp:
    source=Path(tmp)/'a.png';source.write_bytes(b'new content')
    data={'/USB2/dest/a.png':b'old content','/USB2/source/a.png':b'new content'}
    folders={'/USB2','/USB2/dest','/USB2/source'}
    class FTP:
     def storbinary(self,command,stream,callback):
      value=stream.read();data[command[5:]]=value;callback(value)
     def retrbinary(self,command,callback):callback(data[command[5:]])
     def size(self,path):return len(data[path])
     def rename(self,source,dest):
      assert dest not in data
      data[dest]=data.pop(source)
     def delete(self,path):del data[path]
     def rmd(self,path):folders.remove(path)
     def close(self):pass
    def listing(path):
     rows=[Entry(posixpath.basename(p),'file',len(v)) for p,v in data.items() if posixpath.dirname(p)==path]
     rows += [Entry(posixpath.basename(p),'dir',None) for p in folders if posixpath.dirname(p)==path]
     return path,rows
    client=Mock();client.list_directory.side_effect=listing
    def operate(client,action,path):
     self.assertEqual(action,'mkdir');self.assertNotIn(path,folders);folders.add(path)
    parent=Path(tmp) if source_local else '/USB2/source'
    plan=build_plan(client,source_local,parent,['a.png'],False,'/USB2/dest')
    plan.steps.extend(plan.replacements);plan.conflicts=[]
    with patch('c64u_browser.replacement.connect',side_effect=lambda client:FTP()),patch('c64u_browser.transfers.connect',side_effect=lambda client:FTP()),patch('c64u_browser.replacement.operate',side_effect=operate):
     result=execute_plan(client,plan,source_local,False)
    self.assertEqual(result.error,'')
    self.assertEqual(data['/USB2/dest/a.png'],b'new content')
    self.assertEqual(data['/USB2/source/a.png'],b'new content')
    self.assertEqual(source.read_bytes(),b'new content')
    self.assertEqual(folders,{'/USB2','/USB2/dest','/USB2/source'})
    self.assertEqual(set(data),{'/USB2/dest/a.png','/USB2/source/a.png'})
