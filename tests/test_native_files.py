import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import Mock,patch
from c64u_browser.api import BrowserError,Entry
from c64u_browser.native_files import (parse_cfg,config_backup,read_remote,
                                       read_remote_game,upload_flash,
                                       validate_upload)
from c64u_browser.configuration import Setting
from c64u_browser.config_history import history_path,save_before_apply,read_previous
from c64u_browser.profiles import Preferences,Profile

class NativeTests(unittest.TestCase):
 def test_game_library_has_scoped_64_mib_remote_read(self):
  data=b'x'*(16*1024*1024+1);events=[]
  class FTP:
   def size(self,path):return len(data)
   def retrbinary(self,cmd,callback):
    callback(data[:1024]);callback(data[1024:])
   def close(self):events.append('closed')
  with patch('c64u_browser.native_files.connect',return_value=FTP()):
   with self.assertRaises(BrowserError):
    read_remote(Mock(),'/USB1/game.crt',17*1024*1024)
   value=read_remote_game(Mock(),'/USB1/game.crt',64*1024*1024,
                          lambda completed,total:events.append((completed,total)))
  self.assertEqual(data,value)
  self.assertEqual((len(data),len(data)),events[-2])
  self.assertEqual('closed',events[-1])
 def test_parser_and_conversion(self):
  data=b'[Test]\nNumber=4\nMode= on \nText=001\nPassword=secret\nMissing=x\n'
  settings={'Test':[Setting('Number','3','',value_type=int),Setting('Mode','Off','',choices=('Off','On')),Setting('Text','abc',''),Setting('Password','Hidden','',editable=False)]}
  converted,skipped=config_backup(data,settings)
  self.assertEqual(converted,{'settings':{'Test':{'Number':4,'Mode':'On','Text':'001'}}});self.assertEqual(skipped,2)
  for malformed in (b'X=1\n',b'[A]\nX=1\nX=2\n',b'[A]\n'+b'x'*128+b'\n',b''):
   with self.assertRaises(BrowserError):parse_cfg(malformed)
 def test_targets_and_file_validation(self):
  for folder,name,data in [('/Flash/html','a.bin',b'a'),('/Flash/roms','../a.bin',b'a'),('/Flash/configs','a.cfg',b'not a config'),('/Flash/carts','a.crt',b'bad')]:
   with self.assertRaises(BrowserError):validate_upload(folder,name,data)
  validate_upload('/Flash/roms','a.bin',b'1234')
  validate_upload('/Flash/configs','a.cfg',b'[A]\nX=1\n')
 def test_verified_upload_no_overwrite_and_corruption(self):
  for corrupt in (False,True):
   files={};folders={'roms'}
   class FTP:
    def storbinary(self,cmd,stream):files[cmd[5:]]=stream.read()
    def retrbinary(self,cmd,callback):callback(b'wrong' if corrupt else files[cmd[5:]])
    def size(self,path):return len(files[path])
    def rename(self,src,dst):files[dst]=files.pop(src)
    def close(self):pass
    def mkd(self,path):folders.add(path.rsplit('/',1)[-1])
   client=Mock()
   client.list_directory.side_effect=lambda path:(path,[Entry(n,'dir',None) for n in folders] if path=='/Flash' else [Entry(p.rsplit('/',1)[-1],'file',len(v)) for p,v in files.items()])
   with patch('c64u_browser.native_files.connect',return_value=FTP()):
    if corrupt:
     with self.assertRaisesRegex(BrowserError,'verification'):upload_flash(client,'/Flash/roms','a.bin',b'new')
     self.assertNotIn('/Flash/roms/a.bin',files)
    else:
     self.assertEqual(upload_flash(client,'/Flash/roms','a.bin',b'new'),'/Flash/roms/a.bin')
     with self.assertRaisesRegex(BrowserError,'already exists'):upload_flash(client,'/Flash/roms','a.bin',b'other')
     self.assertEqual(files,{'/Flash/roms/a.bin':b'new'})
 def test_rollback_scoped_to_profile_and_changed_fields(self):
  with TemporaryDirectory() as d:
   prefs=Preferences(Path(d)/'prefs.json');p=Profile.new('one','host');q=Profile.new('two','host')
   client=Mock();client.host='host'
   path=history_path(prefs,p,client);self.assertNotEqual(path,history_path(prefs,q,client))
   settings={'Test':[Setting('Count','3','',value_type=int),Setting('Other','keep','')]}
   save_before_apply(path,settings,{'Test':{'Count':4}},'host')
   self.assertEqual(read_previous(path)['settings'],{'Test':{'Count':3}})
