import struct
import unittest
import threading
from unittest.mock import Mock,patch
from urllib.parse import parse_qs,urlsplit
from c64u_browser.streaming import VideoDecoder,AudioDecoder,StreamSession,rgb_frame,RGB
from c64u_browser.api import UltimateClient,BrowserError

def packet(frame,line,height=272,value=0x21):
 return struct.pack('<HHHHBBH',line//4,frame,line|(0x8000 if line+4==height else 0),384,4,4,0)+bytes([value])*768

class DecodeTests(unittest.TestCase):
 def test_reordered_frame(self):
  d=VideoDecoder();result=None
  for line in reversed(range(0,272,4)):result=d.feed(packet(1,line)) or result
  self.assertEqual(result,(272,bytes([0x21])*(192*272)))
  self.assertEqual(rgb_frame(b'\x21'),RGB[1]+RGB[2])
  self.assertIsNone(d.feed(packet(1,0)))
 def test_incomplete_and_wrap(self):
  d=VideoDecoder()
  for line in range(4,272,4):self.assertIsNone(d.feed(packet(65535,line)))
  for line in range(0,240,4):result=d.feed(packet(0,line,240,0x43))
  self.assertEqual(result,(240,bytes([0x43])*(192*240)))
  self.assertEqual(d.incomplete,1)
  self.assertIsNone(d.feed(packet(65535,0)))
 def test_malformed(self):
  d=VideoDecoder()
  for p in (b'',packet(1,0)[:-1],packet(1,272)):self.assertIsNone(d.feed(p))
  self.assertEqual(d.invalid,3)
 def test_audio(self):
  d=AudioDecoder();pcm=bytes(768)
  for seq in (65535,0,2):self.assertEqual(d.feed(struct.pack('<H',seq)+pcm),pcm)
  self.assertEqual(d.missing,1)
  for seq in (2,1):self.assertIsNone(d.feed(struct.pack('<H',seq)+pcm))
  self.assertIsNone(d.feed(b'invalid'))

class StreamTests(unittest.TestCase):
 def test_routes(self):
  c=UltimateClient('test')
  with patch.object(c,'_request_json') as request:
   c.start_stream('video','192.168.68.80',11000)
   method,url=request.call_args.args
   self.assertEqual(method,'PUT');self.assertEqual(urlsplit(url).path,'/v1/streams/video:start')
   self.assertEqual(parse_qs(urlsplit(url).query),{'ip':['192.168.68.80:11000']})
   c.stop_stream('audio');request.assert_called_with('PUT','/v1/streams/audio:stop')
   request.reset_mock()
   for stream,address,port in [('debug','192.168.1.1',11000),('video','224.0.0.1',11000),('audio','0.0.0.0',11001),('audio','192.168.1.1',True)]:
    with self.assertRaises(BrowserError):c.start_stream(stream,address,port)
   request.assert_not_called()
 def test_partial_failure_cleanup(self):
  c=Mock();c.start_stream.side_effect=[{},RuntimeError('start failed')];r=Mock(address='192.168.68.80')
  with patch('c64u_browser.streaming.Receiver',return_value=r):s=StreamSession(c);s.thread.join(2)
  self.assertFalse(s.thread.is_alive());r.close.assert_called_once()
  self.assertEqual([call.args[0] for call in c.stop_stream.call_args_list],['audio','video'])
  self.assertIn('start failed',s.message)
 def test_stop_during_start(self):
  entered=threading.Event();release=threading.Event();c=Mock()
  c.start_stream.side_effect=lambda *args:(entered.set(),release.wait(2));r=Mock(address='192.168.68.80')
  with patch('c64u_browser.streaming.Receiver',return_value=r):
   s=StreamSession(c);self.assertTrue(entered.wait(1));s.stop();release.set();s.thread.join(2)
  c.stop_stream.assert_called_once_with('video');r.close.assert_called_once()
 def test_failed_stop_reported(self):
  c=Mock();c.start_stream.side_effect=RuntimeError('start failed');c.stop_stream.side_effect=RuntimeError('offline')
  with patch('c64u_browser.streaming.Receiver',return_value=Mock(address='192.168.68.80')):s=StreamSession(c);s.thread.join(2)
  self.assertIn('Remote stop was not confirmed',s.message)
