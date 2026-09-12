import unittest
from c64u_browser.configuration import Setting
from c64u_browser.dependencies import enabled, NETWORK_CATEGORIES, STATIC_FIELDS
from c64u_browser.backups import snapshot

class DHCPTests(unittest.TestCase):
 def test_each_network_uses_its_own_current_and_pending_dhcp(self):
  settings={c:[Setting('Use DHCP','Enabled','')] for c in NETWORK_CATEGORIES}
  for category in NETWORK_CATEGORIES:
   pending={(category,'Use DHCP'):'Disabled'}
   for other in NETWORK_CATEGORIES:
    for field in STATIC_FIELDS:
     self.assertFalse(enabled(other,field,settings,{}))
     self.assertEqual(enabled(other,field,settings,pending),other==category)
   self.assertTrue(enabled(category,'Use DHCP',settings,{}))
 def test_enabled_override_and_unknown_state(self):
  for category in NETWORK_CATEGORIES:
   settings={category:[Setting('Use DHCP','Disabled','')]}
   for field in STATIC_FIELDS:
    self.assertTrue(enabled(category,field,settings,{}))
    self.assertFalse(enabled(category,field,settings,{(category,'Use DHCP'):'Enabled'}))
    self.assertFalse(enabled(category,field,{},{}))
 def test_saved_static_values_remain_in_backups(self):
  for category in NETWORK_CATEGORIES:
   settings={category:[Setting('Use DHCP','Enabled',''),Setting('Static IP','192.168.2.64','')]}
   self.assertEqual(snapshot(settings,'test')['settings'][category]['Static IP'],'192.168.2.64')

 def test_wifi_status_is_read_only_when_supplied(self):
  from unittest.mock import Mock
  from c64u_browser.configuration import Configuration, WIRED_STATUS_FIELDS
  client=Mock()
  client.read_configuration.return_value={'WiFi settings':{name:{'current':'example'} for name in WIRED_STATUS_FIELDS}}
  rows=Configuration(client).settings('WiFi settings')
  self.assertEqual(len(rows),3)
  self.assertTrue(all(not row.editable for row in rows))
