import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from c64u_browser.configuration import Setting
from c64u_browser.backups import snapshot,differences,write_backup,read_backup
class BackupTests(unittest.TestCase):
 def test_roundtrip_and_exclusions(self):
  settings={'Test':[Setting('Speed','2','',value_type=int,minimum=1,maximum=4),Setting('Network Password','Hidden','',editable=False),Setting('C64U Model','Beige',''),Setting('Info','x','',editable=False)]}
  data=snapshot(settings,'test');self.assertEqual(data['settings'],{'Test':{'Speed':2}})
  with TemporaryDirectory() as d:
   p=Path(d)/'backup.json';write_backup(p,data);self.assertEqual(read_backup(p),data)
  self.assertEqual(differences(data,settings),([],0))
 def test_validate_against_target(self):
  settings={'Test':[Setting('Speed','1','',value_type=int,minimum=1,maximum=4),Setting('Mode','A','',choices=('A','B'))]}
  data={'settings':{'Test':{'Speed':2,'Mode':'invalid','Missing':'x','Network Password':'oops'}}}
  changes,skipped=differences(data,settings);self.assertEqual(len(changes),1);self.assertEqual(skipped,3)
  for value in ('2',False,9):
   self.assertEqual(differences({'settings':{'Test':{'Speed':value}}},settings),([],1))
 def test_invalid_file(self):
  with TemporaryDirectory() as d:
   p=Path(d)/'x.json'
   for text in ('{}','[]','{"format":"argonaut-settings","version":1,"settings":{"A":{"x":null}}}'):
    p.write_text(text)
    with self.assertRaises(ValueError):read_backup(p)
