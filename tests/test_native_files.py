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
  from c64u_browser.simulated_ftp_reads import MemoryReads
  peer=MemoryReads(files={b'/USB1/game.crt':data});client=peer.attach()
  with self.assertRaises(BrowserError):read_remote(client,'/USB1/game.crt',17*1024*1024)
  value=read_remote_game(client,'/USB1/game.crt',64*1024*1024,
                         lambda completed,total:events.append((completed,total)))
  self.assertEqual(data,value)
  self.assertEqual((len(data),len(data)),events[-1])
  self.assertEqual((0,1),(peer.active,peer.released))
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
  # R6 wire verification lives in test_r6_flash; raw clients must now refuse.
  with patch('ftplib.FTP',side_effect=AssertionError('raw factory')):
   with self.assertRaises(BrowserError) as caught:
    upload_flash(Mock(),'/Flash/roms','a.bin',b'new')
  self.assertEqual('not-started',caught.exception.flash_evidence.upload.disposition)
 def test_rollback_scoped_to_profile_and_changed_fields(self):
  with TemporaryDirectory() as d:
   prefs=Preferences(Path(d)/'prefs.json');p=Profile.new('one','host');q=Profile.new('two','host')
   client=Mock();client.host='host'
   path=history_path(prefs,p,client);self.assertNotEqual(path,history_path(prefs,q,client))
   settings={'Test':[Setting('Count','3','',value_type=int),Setting('Other','keep','')]}
   save_before_apply(path,settings,{'Test':{'Count':4}},'host')
   self.assertEqual(read_previous(path)['settings'],{'Test':{'Count':3}})
