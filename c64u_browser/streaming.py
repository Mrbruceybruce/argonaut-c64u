# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Bounded UDP reception and decoding for Ultimate VIC and PCM streams."""
from collections import deque
import select
import socket
import struct
import threading
import time

# Fixed preview palette; streamed color indices do not carry a custom VPL palette.
PALETTE = ('000000','ffffff','68372b','70a4b2','6f3d86','588d43','352879','b8c76f',
           '6f4f25','433900','9a6759','444444','6c6c6c','9ad284','6c5eb5','959595')
RGB=tuple(bytes.fromhex(c) for c in PALETTE)
PIXELS=tuple(RGB[n&15]+RGB[n>>4] for n in range(256))

def rgb_frame(packed):
    return b''.join(PIXELS[n] for n in packed)

class VideoDecoder:
    def __init__(self):
        self.frame=None;self.rows=set();self.height=None;self.emitted=False
        self.buffer=bytearray(384*272//2);self.invalid=0;self.incomplete=0

    def feed(self, data):
        if len(data)<12:self.invalid+=1;return
        seq,frame,line,width,lines,bits,encoding=struct.unpack_from('<HHHHBBH',data)
        last=bool(line&0x8000);line &= 0x7fff
        if width!=384 or bits!=4 or encoding!=0 or not 1<=lines<=4 or line+lines>272 or len(data)!=12+width*lines//2:
            self.invalid+=1;return
        if self.frame!=frame:
            if self.frame is not None:
                if ((frame-self.frame)&0xffff) >= 0x8000:return
                if not self.emitted:self.incomplete+=1
            self.frame=frame;self.rows=set();self.height=None;self.emitted=False
        if self.emitted:return
        offset=line*192;self.buffer[offset:offset+len(data)-12]=data[12:]
        self.rows.update(range(line,line+lines))
        if last:
            if line+lines not in (240,272):self.invalid+=1;return
            self.height=line+lines
        if self.height and all(row in self.rows for row in range(self.height)):
            self.emitted=True
            return self.height,bytes(self.buffer[:192*self.height])

class AudioDecoder:
    def __init__(self):self.sequence=None;self.missing=0;self.invalid=0;self.resets=0;self.late=0
    def feed(self,data):
        if len(data)!=770:self.invalid+=1;return
        sequence=struct.unpack_from('<H',data)[0]
        if self.sequence is not None:
            delta=(sequence-self.sequence)&0xffff
            if delta==0:return
            if sequence==0 and 4096 < self.sequence < 65000:
                self.resets+=1
            elif delta>=0x8000:
                self.late+=1;return
            elif delta>4096:
                self.resets+=1
            else:self.missing+=delta-1
        self.sequence=sequence
        return data[2:]

class Receiver:
    def __init__(self, host, audio=True):
        self.peer=socket.gethostbyname(host)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as route:
            route.connect((self.peer,80));self.address=route.getsockname()[0]
        self.sockets={};self.stopping=threading.Event();self.lock=threading.Lock()
        self.video=VideoDecoder();self.audio=AudioDecoder();self.latest=None
        self.samples=deque(maxlen=24);self.frames=0;self.audio_packets=0
        self.video_packets=0;self.video_superseded=0;self.audio_evictions=0;self.with_audio=audio
        self.last_video=0;self.last_audio=0;self.error='';self.started=time.monotonic()
        try:
            for name,port in [('video',11000)]+([('audio',11001)] if audio else []):
                sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                self.sockets[sock]=name
                sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1048576)
                sock.bind((self.address,port))
        except Exception:
            self.close();raise
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def run(self):
        try:
            while not self.stopping.is_set():
                ready,_,_=select.select(list(self.sockets),[],[],.1)
                for sock in ready:
                    data,peer=sock.recvfrom(2048)
                    if peer[0]!=self.peer:continue
                    name=self.sockets[sock]
                    with self.lock:
                        if name=='video':
                            self.video_packets+=1
                            frame=self.video.feed(data)
                            if frame:
                                if self.latest is not None:self.video_superseded+=1
                                self.latest=frame;self.frames+=1;self.last_video=time.monotonic()
                        else:
                            pcm=self.audio.feed(data)
                            if pcm:
                                if len(self.samples)==self.samples.maxlen:self.audio_evictions+=1
                                self.samples.append(pcm);self.audio_packets+=1;self.last_audio=time.monotonic()
        except (OSError,ValueError) as exc:
            if not self.stopping.is_set():self.error=str(exc)

    def take(self):
        with self.lock:
            frame=self.latest;self.latest=None
            samples=list(self.samples);self.samples.clear()
        return frame,samples

    def snapshot(self):
        with self.lock:
            now=time.monotonic()
            return dict(peer=self.peer,address=self.address,frames=self.frames,
                video_packets=self.video_packets,audio_packets=self.audio_packets,
                invalid_video=self.video.invalid,incomplete_video=self.video.incomplete,
                invalid_audio=self.audio.invalid,missing_audio=self.audio.missing,
                audio_resets=self.audio.resets,audio_evictions=self.audio_evictions,
                video_superseded=self.video_superseded,with_audio=self.with_audio,
                video_age=now-self.last_video if self.last_video else None,
                audio_age=now-self.last_audio if self.last_audio else None)

    def close(self):
        self.stopping.set()
        thread=getattr(self,'thread',None)
        if thread:thread.join(timeout=.5)
        for sock in self.sockets:sock.close()

class AudioOutput:
    def __init__(self):
        import gi
        gi.require_version('Gst','1.0')
        from gi.repository import Gst
        self.Gst=Gst;Gst.init(None);self.dropped=0
        self.pipeline=Gst.parse_launch('appsrc name=source is-live=true format=time do-timestamp=true block=false max-bytes=8192 caps="audio/x-raw,format=S16LE,rate=48000,channels=2,layout=interleaved" ! queue max-size-buffers=24 max-size-bytes=0 max-size-time=0 leaky=downstream ! audioconvert ! audioresample ! autoaudiosink sync=false')
        self.source=self.pipeline.get_by_name('source')
        self.pipeline.set_state(Gst.State.PLAYING)

    def push(self, chunks):
        Gst=self.Gst
        message=self.pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR)
        if message:
            error,_=message.parse_error();raise RuntimeError(error.message)
        for chunk in chunks:
            if self.source.get_property('current-level-bytes')>8192:
                self.dropped+=1;continue
            buffer=Gst.Buffer.new_allocate(None,len(chunk),None);buffer.fill(0,chunk)
            self.source.emit('push-buffer',buffer)

    def close(self):self.pipeline.set_state(self.Gst.State.NULL)


class StreamSession:
    """Own receiver and remote streams together, including partial-start cleanup."""
    def __init__(self,client,audio=True):
        self.client=client;self.with_audio=audio;self.receiver=None
        self.stopping=threading.Event();self.message='Starting preview…';self.stop_reason=''
        self.thread=threading.Thread(target=self.run)
        self.thread.start()

    def stop(self):self.stopping.set()

    def run(self):
        attempted=[];receiver=None;failure=''
        try:
            receiver=Receiver(self.client.host,self.with_audio)
            self.receiver=receiver
            for name,port in [('video',11000)]+([('audio',11001)] if self.with_audio else []):
                if self.stopping.is_set():break
                attempted.append(name)
                self.client.start_stream(name,receiver.address,port)
            self.message='Waiting for video…'
            began=time.monotonic()
            while not self.stopping.wait(.1):
                if receiver.error:raise RuntimeError(receiver.error)
                if time.monotonic()-(receiver.last_video or began)>8:
                    raise RuntimeError('No complete video frames received for 8 seconds. Check Ethernet and the firewall rule for UDP 11000–11001.')
        except Exception as exc:failure=str(exc)
        finally:
            self.message='Stopping preview…'
            if receiver:receiver.close()
            errors=[]
            for name in reversed(attempted):
                try:self.client.stop_stream(name)
                except Exception as exc:errors.append(name+': '+str(exc))
            self.message=failure or self.stop_reason or 'Preview stopped.'
            if errors:self.message+=' Remote stop was not confirmed; stop streams on the C64U if necessary. '+'; '.join(errors)
