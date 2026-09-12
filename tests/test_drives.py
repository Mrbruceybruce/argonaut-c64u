import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
from c64u_browser.api import UltimateClient,BrowserError

class DrivesTests(unittest.TestCase):
 def test_machine_routes_are_bounded(self):
  client=UltimateClient('test')
  with patch.object(client,'_request_json') as request:
   client.machine_action('reset');request.assert_called_with('PUT','/v1/machine:reset')
   client.machine_action('reboot');request.assert_called_with('PUT','/v1/machine:reboot')
   with self.assertRaises(BrowserError):client.machine_action('poweroff')
 def test_mount_encoding_and_mode(self):
  client=UltimateClient('test')
  path='/USB2/A & B/#1?.d64'
  with patch.object(client,'_request_json') as request:
   client.mount_disk('b',path)
   method,route=request.call_args.args
   self.assertEqual(method,'PUT')
   self.assertEqual(urlsplit(route).path,'/v1/drives/b:mount')
   self.assertEqual(parse_qs(urlsplit(route).query),{'image':[path],'mode':['readonly']})
 def test_invalid_arguments_never_send(self):
  client=UltimateClient('test')
  with patch.object(client,'_request_json') as request:
   for drive,path,mode in [('c','/a.d64','readonly'),('a','/../a.d64','readonly'),('a','local.d64','readonly'),('a','/a.prg','readonly'),('a','/a.d64','unknown')]:
    with self.assertRaises(BrowserError):client.mount_disk(drive,path,mode)
   with self.assertRaises(BrowserError):client.drive_action('a','reboot')
   with self.assertRaises(BrowserError):client.set_drive_type('a','1582')
   request.assert_not_called()
 def test_drive_status_and_routes(self):
  client=UltimateClient('test')
  with patch.object(client,'_get_json',return_value={'drives':[{'a':{'enabled':True,'image_file':''}},{'Printer Emulation':{'enabled':True}}]}) as get:
   self.assertEqual(set(client.read_drives()),{'a'});get.assert_called_once_with('/v1/drives')
  with patch.object(client,'_request_json') as request:
   client.drive_action('a','remove');request.assert_called_with('PUT','/v1/drives/a:remove')
   client.set_drive_type('b','1581');request.assert_called_with('PUT','/v1/drives/b:set_mode?mode=1581')
  with patch.object(client,'_get_json',return_value={'drives':[{'a':{'enabled':'yes'}}]}):
   with self.assertRaises(BrowserError):client.read_drives()
