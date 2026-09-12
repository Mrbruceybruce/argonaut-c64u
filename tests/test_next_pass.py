import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import Mock,patch
from c64u_browser.profiles import Profile,Preferences
from c64u_browser.configuration import Configuration
from c64u_browser.api import ConnectionFailure,BrowserError
from c64u_browser.folder_copy import build_plan,execute_plan
from c64u_browser.settings_sections import section_entries

class IdentityTests(unittest.TestCase):
 def test_saved_identity_and_mismatch(self):
  p=Profile.new('test','192.168.1.2',device_id='abc123')
  self.assertEqual(p.verify_identity({'info':{'unique_id':'ABC123'}}),'ABC123')
  for value in ('xyz123','',None,'Default'):
   with self.assertRaises(ConnectionFailure):p.verify_identity({'info':{'unique_id':value}})
  with TemporaryDirectory() as d:
   prefs=Preferences(Path(d)/'p.json');prefs.profiles=[p];prefs.save()
   self.assertEqual(Preferences(prefs.path).load().profiles[0].device_id,'abc123')
 def test_legacy_requires_manual_confirmation(self):
  with self.assertRaises(ConnectionFailure):Profile.new('old','test').verify_identity({'info':{'unique_id':'abc123'}},True)

class SchemaTests(unittest.TestCase):
 def test_presets_unknown_metadata_model_and_actual_id(self):
  client=Mock();client.test_connection.return_value={'info':{'unique_id':'123ABC'}}
  client.read_configuration.return_value={'Network Settings':{'Unique ID':{'current':'Default','presets':['','Default']},'New format':{'unfamiliar':1}}}
  rows=Configuration(client).settings('Network Settings')
  self.assertEqual(rows[0].presets,('','Default'));self.assertEqual(rows[0].parse('manual'),'manual')
  self.assertFalse(rows[1].editable);self.assertEqual(rows[2].current,'123ABC');self.assertFalse(rows[2].editable)
  client.read_configuration.return_value={'U64 Specific Settings':{'C64U Model':{'current':'Starlight Edition'}}}
  rows=Configuration(client).settings('U64 Specific Settings');self.assertFalse(rows[0].editable)
  self.assertIn('System Information',section_entries({'U64 Specific Settings':rows}))

class ReplacementTests(unittest.TestCase):
 def test_replace_skip_changed_and_cancel(self):
  with TemporaryDirectory() as d:
   root=Path(d);src=root/'src';dst=root/'dst';src.mkdir();dst.mkdir()
   (src/'a').write_text('new');(dst/'a').write_text('old')
   def plan():return build_plan(None,True,src,['a'],True,dst)
   reviewed=plan();self.assertEqual(len(reviewed.replacements),1)
   execute_plan(None,reviewed,True,True);self.assertEqual((dst/'a').read_text(),'old')
   reviewed.steps.extend(reviewed.replacements);reviewed.conflicts=[]
   report=execute_plan(None,reviewed,True,True);self.assertFalse(report.error);self.assertEqual((dst/'a').read_text(),'new')
   reviewed=plan();reviewed.steps.extend(reviewed.replacements)
   (dst/'a').write_text('changed since review')
   self.assertIn('changed',execute_plan(None,reviewed,True,True).error)
   self.assertEqual((dst/'a').read_text(),'changed since review')
   reviewed=plan();reviewed.steps.extend(reviewed.replacements)
   progress=Mock();progress.check.side_effect=BrowserError('cancelled')
   self.assertIn('cancelled',execute_plan(None,reviewed,True,True,progress).error)
   self.assertEqual((dst/'a').read_text(),'changed since review')
 def test_self_copy_not_replaceable(self):
  with TemporaryDirectory() as d:
   root=Path(d);(root/'a').write_text('keep')
   self.assertFalse(build_plan(None,True,root,['a'],True,root).replacements)

class RemoteReplacementTests(unittest.TestCase):
 def test_verified_publish_and_failure_preserves_original_backup(self):
  from types import SimpleNamespace
  from c64u_browser.folder_copy import Step
  from c64u_browser.replacement import replace_file
  for fail_publish in (False,True):
   data={'/USB2/a':b'old'};calls=[]
   def inspect(_,path):
    return SimpleNamespace(name=path.rsplit('/',1)[-1],kind='file',size=len(data[path])) if path in data else None
   class FTP:
    def retrbinary(self,command,callback):callback(data[command[5:]])
    def rename(self,source,dest):
     calls.append((source,dest))
     if fail_publish and 'c64u-replace-' in source:raise OSError('lost connection')
     data[dest]=data.pop(source)
    def delete(self,path):del data[path]
    def rmd(self,path):pass
    def close(self):pass
   def copy(client,source_local,parent,names,local,folder,progress):
    data[folder+'/a']=b'new';return 'Copied 1 file(s): a',None
   with patch('c64u_browser.replacement.inspect',side_effect=inspect),patch('c64u_browser.replacement.operate'),patch('c64u_browser.replacement.connect',return_value=FTP()),patch('c64u_browser.replacement.copy_files',side_effect=copy):
    step=Step('a',Path('/source/a'),'/USB2/a',False,True,('a',3))
    if fail_publish:
     with self.assertRaisesRegex(BrowserError,'original backup'):replace_file(Mock(),step,True,False,lambda n:None)
     self.assertIn(b'old',data.values());self.assertIn(b'new',data.values())
    else:
     replace_file(Mock(),step,True,False,lambda n:None)
     self.assertEqual(data,{'/USB2/a':b'new'})
