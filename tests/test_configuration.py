import unittest
from unittest.mock import Mock,patch
from c64u_browser.configuration import Configuration
from c64u_browser.settings_sections import section_entries, visible_entries, subsection_for
from c64u_browser.configuration import Setting
from c64u_browser.api import UltimateClient,BrowserError

class ConfigurationTests(unittest.TestCase):
 def test_edit_types_and_bounds(self):
  client=Mock();client.read_configuration.return_value={'Test':{
   'Count':{'current':3,'min':1,'max':8},'Text':{'current':'001'},
   'Choice':{'current':1,'values':[1,2]},'Flag':{'current':True}}}
  count,text,choice,flag=Configuration(client).settings('Test')
  self.assertEqual(count.parse('8'),8)
  for invalid in ('0','9','1.5','nan',''):
   with self.assertRaises(ValueError):count.parse(invalid)
  self.assertEqual(text.parse('002'),'002')
  self.assertIsInstance(choice.parse('2'),int)
  self.assertIs(flag.parse('false'),False)
  with self.assertRaises(ValueError):choice.parse('3')

 def test_shared_roms_keep_identity_and_search_deduplicates(self):
  rom=Setting('ROM for 1541 mode','1541.rom','')
  data={'Drive A Settings':[rom]}
  groups=section_entries(data)
  self.assertEqual(groups['Memory & ROMs'],groups['Built-in Drive A'])
  self.assertIs(groups['Memory & ROMs'][0][1],rom)
  self.assertEqual(len(visible_entries(data,'Memory & ROMs','1541')),1)
  self.assertEqual(len(visible_entries(data,'Memory & ROMs',favorites={('Drive A Settings',rom.name)})),1)

 def test_native_order_aliases_and_subsections(self):
  data={'C64 and Cartridge Settings':[Setting(n,'Off','') for n in ('Command Interface','Char ROM','Map Ultimate Audio $DF20-DFFF','Kernal ROM')]}
  rows=section_entries(data)['Memory & ROMs']
  self.assertEqual([s.name for _,s in rows],['Kernal ROM','Char ROM','Command Interface','Map Ultimate Audio $DF20-DFFF'])
  self.assertEqual(visible_entries(data,'Video Setup','Character ROM')[0][1].name,'Char ROM')
  self.assertEqual(subsection_for('Network Services & Timezone','Network Settings','TimeZone'),'Time Synchronization')
  self.assertEqual(subsection_for('Built-in Drive A','Drive A Settings','Extra RAM'),'Advanced')

 def test_categories_are_grouped_without_loss(self):
  settings={c:[Setting('Example','On','')] for c in ['Drive A Settings','SID Addressing','New Firmware Category','Network Settings']}
  groups=section_entries(settings)
  self.assertEqual(list(groups),['Audio Setup','Network Services & Timezone','Built-in Drive A','Additional Settings'])
  self.assertEqual({c for rows in groups.values() for c,_ in rows},set(settings))

 def test_split_categories_and_global_search(self):
  settings={'U64 Specific Settings':[Setting(n,'On','') for n in ['CPU Speed','HDMI Scan lines','Joystick Swapper','Unknown new item']],
            'SID Addressing':[Setting('Paddle Override','On',''),Setting('SID Socket 1 Address','$D400','')]}
  groups=section_entries(settings)
  self.assertEqual(len(groups['Joystick & Controllers']),2)
  self.assertEqual(len(visible_entries(settings,'Turbo Boost')),1)
  self.assertEqual(visible_entries(settings,'Turbo Boost','HDMI')[0][1].name,'HDMI Scan lines')
  key=('SID Addressing','SID Socket 1 Address')
  self.assertEqual(visible_entries(settings,'Turbo Boost',favorites={key})[0][0],key[0])
  self.assertEqual(sum(map(len,groups.values())),7)

 def test_metadata_and_secrets(self):
  client=Mock();client.read_configuration.return_value={'Network Settings':{'Mode':{'current':'On','default':'Off','values':['Off','On']},'Network Password':{'current':'secret123','default':'secret456'}}}
  rows=Configuration(client).settings('Network Settings')
  self.assertIn('Allowed values',rows[0].details)
  self.assertEqual(rows[1].current,'Hidden');self.assertNotIn('secret123',repr(rows));self.assertNotIn('secret456',repr(rows))
 def test_bad_responses(self):
  client=Mock();model=Configuration(client)
  for data in [{},{'categories':'bad'},{'categories':[123]}]:
   client.read_configuration.return_value=data
   with self.assertRaises(BrowserError):model.categories()
  for data in [{}]:
   client.read_configuration.return_value=data
   with self.assertRaises(BrowserError):model.settings('Test')
 def test_read_routes(self):
  client=UltimateClient('test')
  with patch.object(client,'_get_json') as get:
   client.read_configuration();get.assert_called_with('/v1/configs')
   client.read_configuration('SID Sockets Configuration');get.assert_called_with('/v1/configs/SID%20Sockets%20Configuration/*')
   for name in ['*','../machine:reset','configs:save_to_flash']:
    with self.assertRaises(BrowserError):client.read_configuration(name)

 def test_all_settings_reads_each_category(self):
  client=Mock();client.read_configuration.side_effect=lambda category=None: {category:{'Value':{'current':'On'}}}
  rows=Configuration(client).all_settings(['SID','Drive'])
  self.assertEqual(set(rows),{'SID','Drive'})
  self.assertEqual(client.read_configuration.call_count,2)

 def test_write_methods_use_documented_routes(self):
  client=UltimateClient('test')
  with patch.object(client,'_request_json') as request:
   client.apply_configuration({'SID Sockets Configuration': {'SID Socket 1':'Enabled'}})
   request.assert_called_with('POST','/v1/configs',{'SID Sockets Configuration': {'SID Socket 1':'Enabled'}})
   client.save_configuration()
   request.assert_called_with('PUT','/v1/configs:save_to_flash')
