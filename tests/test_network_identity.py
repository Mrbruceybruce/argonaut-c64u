import json
import unittest
from unittest.mock import patch
from c64u_browser.network_identity import peer_mac
from c64u_browser.profiles import Profile
from c64u_browser.api import ConnectionFailure
class MacTests(unittest.TestCase):
 def test_only_direct_verified_unicast_neighbor(self):
  route={'dst':'192.168.1.2','dev':'eth0'}
  peer={'dst':'192.168.1.2','lladdr':'02:15:41:01:02:03','state':['REACHABLE']}
  def lookup(r,p):
   with patch('c64u_browser.network_identity.socket.gethostbyname',return_value='192.168.1.2'),patch('c64u_browser.network_identity.subprocess.check_output',side_effect=[json.dumps([r]),json.dumps(p)]):return peer_mac('test')
  self.assertEqual(lookup(route,[peer]),peer['lladdr'])
  self.assertEqual(lookup({**route,'gateway':'192.168.1.1'},[peer]),'')
  self.assertEqual(lookup(route,[{**peer,'state':['FAILED']}]),'')
  self.assertEqual(lookup(route,[{**peer,'lladdr':'ff:ff:ff:ff:ff:ff'}]),'')
  self.assertEqual(lookup(route,[peer,peer]),'')
 def test_fallback_never_masks_changed_primary_id(self):
  p=Profile.new('test','test',device_id='abc123',device_mac='02:15:41:01:02:03')
  p.verify_identity({'info':{},'network_mac':p.device_mac},True)
  with self.assertRaises(ConnectionFailure):p.verify_identity({'info':{'unique_id':'different'},'network_mac':p.device_mac})
  with self.assertRaises(ConnectionFailure):p.verify_identity({'info':{},'network_mac':'02:15:41:01:02:04'})
  with self.assertRaises(ConnectionFailure):p.verify_identity({'info':{}})
  p.device_id='';p.verify_identity({'info':{},'network_mac':p.device_mac},True)
