"""Real codec/mux/demux checks; no C64U or desktop is used."""
import os,tempfile,time,unittest
from pathlib import Path
try:
 from c64u_browser.recording import Recorder,destination_signature,Gst
 Gst.init(None)
 AVAILABLE=all(Gst.ElementFactory.find(n) for n in ['vp8enc','vorbisenc','webmmux','matroskademux','vp8dec','vorbisdec'])
except (ImportError,ValueError):AVAILABLE=False

@unittest.skipUnless(AVAILABLE,'GStreamer recording codecs unavailable')
class Recording(unittest.TestCase):
 def finish(self,r):
  r.stop();r.thread.join(12)
  self.assertTrue(r.done)
 def feed(self,r):
  for _ in range(12):
   r.feed((240,bytes([70,140,220])*(384*240)),[bytes(768)]*8 if r.audio else [])
   time.sleep(.033)
 def decode(self,path,audio):
  pipeline=Gst.parse_launch('uridecodebin name=source source. ! queue ! videoconvert ! video/x-raw,format=RGB ! fakesink name=video signal-handoffs=true sync=false'+(' source. ! queue ! audioconvert ! audio/x-raw,format=S16LE ! fakesink name=audio signal-handoffs=true sync=false' if audio else ''))
  pipeline.get_by_name('source').set_property('uri',Path(path).as_uri())
  counts={'video':0,'audio':0};pts={'video':[],'audio':[]}
  def got(s,b,p,key):counts[key]+=b.get_size();pts[key].append(b.pts)
  for key in ['video']+(['audio'] if audio else []):pipeline.get_by_name(key).connect('handoff',got,key)
  pipeline.set_state(Gst.State.PLAYING)
  try:
   msg=pipeline.get_bus().timed_pop_filtered(8*Gst.SECOND,Gst.MessageType.ERROR|Gst.MessageType.EOS)
   self.assertIsNotNone(msg);self.assertEqual(msg.type,Gst.MessageType.EOS)
   self.assertGreater(counts['video'],0)
   if audio:self.assertGreater(counts['audio'],0)
   for values in pts.values():self.assertEqual(values,sorted(values))
  finally:pipeline.set_state(Gst.State.NULL)
 def test_webm_roundtrip_with_and_without_audio(self):
  with tempfile.TemporaryDirectory() as folder:
   for audio in [False,True]:
    path=str(Path(folder)/f'{audio}.webm');r=Recorder(path,240,audio)
    self.feed(r);self.finish(r);self.assertEqual(r.error,'');self.decode(path,audio)
 def test_destination_appearing_during_recording_is_not_replaced(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'clip.webm';r=Recorder(str(path),240,False)
   self.feed(r);path.write_bytes(b'keep');self.finish(r)
   self.assertEqual(path.read_bytes(),b'keep');self.assertIn('Partial file',r.error)
 def test_explicit_replacement_and_changed_target(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'clip.webm';path.write_bytes(b'old')
   with self.assertRaises(RuntimeError):Recorder(str(path),240,False)
   r=Recorder(str(path),240,False,expected=destination_signature(path))
   self.feed(r);self.finish(r);self.assertEqual(r.error,'');self.decode(str(path),False)
   r=Recorder(str(path),240,False,expected=destination_signature(path));self.feed(r)
   path.write_bytes(b'changed');self.finish(r);self.assertEqual(path.read_bytes(),b'changed')
 def test_mode_change_finalizes_previous_frames(self):
  with tempfile.TemporaryDirectory() as folder:
   path=str(Path(folder)/'clip.webm');r=Recorder(path,240,False);self.feed(r)
   with self.assertRaisesRegex(RuntimeError,'mode changed'):r.feed((272,bytes(384*272*3)),[])
   self.finish(r);self.decode(path,False)

@unittest.skipUnless(AVAILABLE,'GStreamer runtime unavailable')
class RecordingTiming(unittest.TestCase):
 def test_thirty_minutes_of_nominal_audio_and_video_have_monotonic_pts(self):
  from unittest.mock import Mock,patch
  r=Recorder.__new__(Recorder)
  r.finishing=False;r.started=0;r.audio_pts=None;r.last_video=-1;r.height=240;r.frames=0
  r.pipeline=Mock();r.pipeline.get_bus.return_value.pop_filtered.return_value=None
  r.video=object();r.sound=object();last={'audio':-1,'video':-1};max_offset=0
  def push(source,data,pts,duration):
   key='video' if source is r.video else 'audio'
   self.assertGreater(pts,last[key]);last[key]=pts
  r.push=push
  # Accelerated 30-minute test of the current nominal clock policy, not hardware sync.
  with patch('c64u_browser.recording.time.monotonic') as clock:
   for n in range(1,56251):
    clock.return_value=n*.032
    r.feed((240,b''),[bytes(768)]*8)
    max_offset=max(max_offset,abs(r.audio_pts-r.last_video))
  self.assertLessEqual(max_offset,1)
 def test_gap_reanchors_audio_and_encoder_failure_is_explicit(self):
  from unittest.mock import Mock,patch
  r=Recorder.__new__(Recorder)
  r.finishing=False;r.started=0;r.audio_pts=0;r.last_video=-1;r.height=240;r.frames=0
  r.pipeline=Mock();r.pipeline.get_bus.return_value.pop_filtered.return_value=None
  r.video=object();r.sound=object();r.push=Mock()
  with patch('c64u_browser.recording.time.monotonic',return_value=2):r.feed((240,b''),[bytes(768)])
  self.assertEqual(r.audio_pts,2*Gst.SECOND)
  source=Mock();source.get_property.side_effect=[100,10]
  with self.assertRaisesRegex(RuntimeError,'keep up'):Recorder.push(r,source,b'',0,1)
