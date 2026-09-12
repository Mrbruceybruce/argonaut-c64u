import unittest
from unittest.mock import Mock
from c64u_browser.configuration import Configuration,READ_ONLY_FIELDS
from c64u_browser.backups import snapshot,differences
class SIDReadOnlyTests(unittest.TestCase):
 def test_menu_readonly_overrides_missing_api_flag(self):
  names=[name for category,name in READ_ONLY_FIELDS if category=='SID Sockets Configuration']
  metadata={name:{'current':'A','values':['A','B']} for name in names+['SID Socket 1','SID Socket 1 1K Ohm Resistor']}
  client=Mock();client.read_configuration.return_value={'SID Sockets Configuration':metadata}
  settings=Configuration(client).settings('SID Sockets Configuration')
  for setting in settings:
   if setting.name in names:
    self.assertFalse(setting.editable)
    with self.assertRaises(ValueError):setting.parse('B')
   else:self.assertTrue(setting.editable)
  model={'SID Sockets Configuration':settings}
  data=snapshot(model,'test')
  self.assertEqual(set(data['settings']['SID Sockets Configuration']),{'SID Socket 1','SID Socket 1 1K Ohm Resistor'})
  self.assertEqual(differences({'settings':{'SID Sockets Configuration':{name:'B' for name in names}}},model),([],4))
