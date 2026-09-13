# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Bounded live WebM writer with asynchronous EOS finalization."""
import os
import tempfile
import threading
import time
from pathlib import Path
from .platform_support import publish_new
import gi
gi.require_version('Gst','1.0')
from gi.repository import Gst

def destination_signature(path):
 p=Path(path)
 if not os.path.lexists(p):return None
 if p.is_symlink() or not p.is_file():raise RuntimeError('Recording destination is not a regular file.')
 st=p.stat();return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)

class Recorder:
 def __init__(self,path,height,audio=True,expected=None):
  Gst.init(None)
  if destination_signature(path)!=expected:raise RuntimeError('Recording destination changed or already exists; choose a new file.')
  self.expected=expected;self.frames=0
  self.path=path;self.height=height;self.audio=audio;self.started=time.monotonic()
  self.finishing=False;self.done=False;self.error='';self.audio_pts=None;self.last_video=-1
  fd,self.temporary=tempfile.mkstemp(prefix='.argonaut-recording-',suffix='.webm',dir=Path(path).parent);os.close(fd)
  self.pipeline=None
  try:
   pipeline='webmmux name=mux ! filesink name=file appsrc name=video is-live=true format=time block=false max-bytes=4194304 ! queue ! videoconvert ! vp8enc deadline=1 cpu-used=8 ! queue ! mux. '
   if audio:pipeline+='appsrc name=audio is-live=true format=time block=false max-bytes=262144 ! queue ! audioconvert ! audioresample ! vorbisenc ! queue ! mux.'
   self.pipeline=Gst.parse_launch(pipeline);self.pipeline.get_by_name('file').set_property('location',self.temporary)
   self.video=self.pipeline.get_by_name('video');self.video.set_property('caps',Gst.Caps.from_string(f'video/x-raw,format=RGB,width=384,height={height},framerate=30/1'))
   self.sound=self.pipeline.get_by_name('audio') if audio else None
   if self.sound:self.sound.set_property('caps',Gst.Caps.from_string('audio/x-raw,format=S16LE,rate=48000,channels=2,layout=interleaved'))
   if self.pipeline.set_state(Gst.State.PLAYING)==Gst.StateChangeReturn.FAILURE:raise RuntimeError('Recording pipeline could not start.')
  except Exception:
   if self.pipeline:self.pipeline.set_state(Gst.State.NULL)
   os.unlink(self.temporary);raise
 def push(self,source,data,pts,duration):
  if source.get_property('current-level-bytes')>source.get_property('max-bytes'):raise RuntimeError('Recording could not keep up with incoming data.')
  buffer=Gst.Buffer.new_allocate(None,len(data),None);buffer.fill(0,data);buffer.pts=pts;buffer.duration=duration
  if source.emit('push-buffer',buffer)!=Gst.FlowReturn.OK:raise RuntimeError('Recording input failed.')
 def feed(self,frame,samples):
  if self.finishing:return
  message=self.pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR)
  if message:raise RuntimeError(message.parse_error()[0].message)
  now=int((time.monotonic()-self.started)*Gst.SECOND)
  if frame:
   height,rgb=frame
   if height!=self.height:raise RuntimeError('Video mode changed; start a new recording for the new mode.')
   pts=max(now,self.last_video+1);self.last_video=pts
   self.push(self.video,rgb,pts,Gst.SECOND//30);self.frames+=1
  if self.sound and samples:
   duration=len(samples)*192*Gst.SECOND//48000
   if self.audio_pts is None:self.audio_pts=max(0,now-duration)
   # Re-anchor after a gap instead of allowing sound to drift behind video.
   if now-self.audio_pts>250000000:self.audio_pts=max(0,now-duration)
   for sample in samples:
    length=192*Gst.SECOND//48000
    self.push(self.sound,sample,self.audio_pts,length);self.audio_pts+=length
 def stop(self,reason=''):
  if self.finishing:return
  self.finishing=True;self.error=reason
  self.thread=threading.Thread(target=self.finish);self.thread.start()
 def finish(self):
  try:
   self.video.emit('end-of-stream')
   if self.sound:self.sound.emit('end-of-stream')
   message=self.pipeline.get_bus().timed_pop_filtered(10*Gst.SECOND,Gst.MessageType.EOS|Gst.MessageType.ERROR)
   if not message:raise RuntimeError('Timed out finalizing recording.')
   if message.type==Gst.MessageType.ERROR:raise RuntimeError(message.parse_error()[0].message)
   self.pipeline.set_state(Gst.State.NULL)
   if destination_signature(self.path)!=self.expected:raise RuntimeError('Recording destination changed; the new recording was not published.')
   if self.expected is None:
    publish_new(self.temporary,self.path)
    if os.path.exists(self.temporary):os.unlink(self.temporary)
   else:os.replace(self.temporary,self.path)
  except Exception as exc:self.error=(self.error+' '+str(exc)).strip()+f' Partial file: {self.temporary}'
  finally:self.pipeline.set_state(Gst.State.NULL);self.done=True
