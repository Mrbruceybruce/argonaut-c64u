import unittest
from unittest.mock import Mock
from c64u_browser.api import Entry,BrowserError
from c64u_browser.storage import discover,initial_directory,storage_root
from c64u_browser.deletion import prepare

class Storage(unittest.TestCase):
 def client(self,names):
  client=Mock()
  client.list_directory.side_effect=lambda path:(path,[Entry(n,'dir',None) for n in names]+[Entry('USB9','file',4)] if path=='/' else [])
  return client
 def test_discovery_excludes_internal_and_files(self):
  client=self.client(['Flash','Temp','USB0','USB2','SD','USBbad'])
  self.assertEqual(discover(client),['/SD','/USB0','/USB2'])
  self.assertEqual(client.storage_roots,['/SD','/USB0','/USB2'])
 def test_initial_preference_and_fallback(self):
  self.assertEqual(initial_directory(self.client(['USB2','USB0']))[0],'/USB2')
  self.assertEqual(initial_directory(self.client(['USB2','USB0']),'/USB0')[0],'/USB0')
  self.assertEqual(initial_directory(self.client(['USB0']))[0],'/USB0')
  self.assertEqual(initial_directory(self.client(['Flash'])),('/',[]))
 def test_roots_cannot_be_deleted(self):
  client=Mock()
  for root in ('/','/USB0','/USB2','/SD'):
   with self.assertRaises(BrowserError):prepare(client,False,[root])
  client.list_directory.assert_not_called()
 def test_bad_roots(self):
  for path in ('/Flash/a','/USB0/../Flash/a','/USB0//a','/USB0/./a','USB0/a'):
   self.assertIsNone(storage_root(path))
