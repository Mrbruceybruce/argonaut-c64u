import unittest
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
from c64u_browser.api import UltimateClient,BrowserError


class MediaTests(unittest.TestCase):
 def test_default_and_numbered_song_routes(self):
  client=UltimateClient('test')
  path='/USB2/Music/A & B #1?.SID'
  with patch.object(client,'_request_json') as request:
   client.play_sid(path)
   method,route=request.call_args.args
   self.assertEqual(method,'PUT')
   self.assertEqual(urlsplit(route).path,'/v1/runners:sidplay')
   self.assertEqual(parse_qs(urlsplit(route).query),{'file':[path]})
   client.play_sid(path,2)
   self.assertEqual(parse_qs(urlsplit(request.call_args.args[1]).query),{'file':[path],'songnr':['2']})
 def test_invalid_inputs_never_play(self):
  client=UltimateClient('test')
  with patch.object(client,'_request_json') as request:
   for path in ('','relative.sid','/USB2/../x.sid','/USB2/game.prg','/USB2/x\n.sid'):
    with self.assertRaises(BrowserError):client.play_sid(path)
   for song in (0,-1,65536,True,1.5,'2'):
    with self.assertRaises(BrowserError):client.play_sid('/USB2/x.sid',song)
   request.assert_not_called()
 def test_attached_sid_default_and_numbered_song_routes(self):
  client=UltimateClient('test')
  with patch.object(client,'_request_binary_json') as request:
   client.play_sid_data(b'PSID data')
   request.assert_called_with('/v1/runners:sidplay',b'PSID data',
                              'argonaut.sid','SID playback')
   client.play_sid_data(b'PSID data',3,'music.sid')
   request.assert_called_with('/v1/runners:sidplay?songnr=3',b'PSID data',
                              'music.sid','SID playback')
 def test_invalid_attached_sid_inputs_never_post(self):
  client=UltimateClient('test')
  with patch.object(client,'_request_binary_json') as request:
   for data in (b'',bytearray(b'PSID')):
    with self.assertRaises(BrowserError):client.play_sid_data(data)
   for song in (0,257,True,'2'):
    with self.assertRaises(BrowserError):client.play_sid_data(b'PSID',song)
   for filename in ('','../x.sid','x.prg','x\n.sid'):
    with self.assertRaises(BrowserError):
     client.play_sid_data(b'PSID',filename=filename)
   request.assert_not_called()
