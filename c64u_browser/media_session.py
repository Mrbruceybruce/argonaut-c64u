# SPDX-License-Identifier: GPL-3.0-or-later
"""One worker consumes stream data for audio, recording and independent views."""
import queue
import threading
import time
import sys
from .streaming import rgb_frame, AudioOutput

class MediaDelivery:
    def __init__(self, session, output_factory=AudioOutput, recorder_factory=None, cairo_fallback=False):
        self.session=session;self.output_factory=output_factory;self.cairo_fallback=cairo_fallback
        self.recorder_factory=recorder_factory
        self.lock=threading.Lock();self.stopping=threading.Event()
        self.commands=queue.Queue(maxsize=2)
        self.latest=None;self.display_superseded=0;self.displayed=0
        self.recorded=0;self.monitor_drops=0;self.error=''
        self.state='idle';self.record_message='';self.record_started=0
        self.done=False;self.recorder=None;self.output=None
        self.max_cycle_gap_ms=0;self.max_processing_ms=0
        self.thread=threading.Thread(target=self.run,name='Argonaut media')
        self.thread.start()

    def start_recording(self,path,height,expected=None):
        with self.lock:
            if self.state in ('starting','recording','finishing') or self.stopping.is_set() or self.done:return False
            self.state='starting';self.record_message='Starting recording…'
            self.commands.put_nowait((path,height,expected))
        return True

    def stop_recording(self):
        with self.lock:
            if self.state in ('starting','recording'):self.state='finishing'

    def stop(self):
        self.stopping.set();self.stop_recording()
        with self.lock:self.latest=None

    def take_frame(self):
        with self.lock:
            frame=self.latest;self.latest=None
            if frame:self.displayed+=1
            return frame

    def snapshot(self):
        with self.lock:
            return dict(recording_state=self.state,record_message=self.record_message,
                        record_started=self.record_started,recorded=self.recorded,
                        display_superseded=self.display_superseded,displayed=self.displayed,
                        monitor_drops=self.monitor_drops,error=self.error,done=self.done,
                        max_cycle_gap_ms=self.max_cycle_gap_ms,max_processing_ms=self.max_processing_ms)

    def run(self):
        try:
            if self.session.with_audio:self.output=self.output_factory()
            # Audio has its own shorter service cadence. Video still targets
            # the existing 30 fps policy. Subtract processing time from the
            # wait so work does not accumulate on top of every interval.
            next_cycle=time.monotonic();last_cycle=None;next_video=next_cycle
            while not self.stopping.wait(max(0,next_cycle-time.monotonic())):
                cycle_started=time.monotonic()
                with self.lock:
                    if last_cycle is not None:self.max_cycle_gap_ms=max(self.max_cycle_gap_ms,round((cycle_started-last_cycle)*1000))
                last_cycle=cycle_started
                next_cycle=cycle_started+.008
                if not self.session.thread.is_alive():break
                try:command=self.commands.get_nowait()
                except queue.Empty:command=None
                if command:
                    with self.lock:cancelled=self.state=='finishing'
                    if cancelled:
                        with self.lock:self.state='idle';self.record_message='Recording cancelled before starting.'
                    else:
                        try:
                            factory=self.recorder_factory
                            if factory is None:
                                from .recording import Recorder
                                factory=Recorder
                            path,height,expected=command
                            self.recorder=factory(path,height,self.session.with_audio,expected=expected)
                            with self.lock:
                                self.record_started=self.recorder.started;self.recorded=0
                                if self.state!='finishing':self.state='recording'
                        except Exception as exc:
                            with self.lock:self.state='failed';self.record_message='Could not start recording: '+str(exc)
                with self.lock:finish=self.state=='finishing'
                if self.recorder and finish:self.recorder.stop()
                receiver=self.session.receiver
                if receiver and not self.session.stopping.is_set():
                    video_due=cycle_started>=next_video
                    frame,samples=receiver.take(video=video_due)
                    # Deliver already-received sound before converting a frame.
                    if self.output:
                        self.output.push(samples)
                        with self.lock:self.monitor_drops=self.output.dropped
                    if frame:next_video=cycle_started+1/30
                    converted=(frame[0],rgb_frame(frame[1])) if frame else None
                    if converted:
                        surface=None
                        if self.cairo_fallback:
                            rgb=converted[1];surface=bytearray(len(rgb)//3*4)
                            if sys.byteorder=='little':
                                surface[0::4]=rgb[2::3];surface[1::4]=rgb[1::3];surface[2::4]=rgb[0::3]
                            else:
                                surface[1::4]=rgb[0::3];surface[2::4]=rgb[1::3];surface[3::4]=rgb[2::3]
                        with self.lock:
                            if self.latest is not None:self.display_superseded+=1
                            self.latest=(*converted,surface)
                    if self.recorder and not self.recorder.finishing:
                        try:self.recorder.feed(converted,samples)
                        except Exception as exc:self.recorder.stop(str(exc))
                self.update_recording()
                if next_video>cycle_started:next_cycle=min(next_cycle,next_video)
                with self.lock:self.max_processing_ms=max(self.max_processing_ms,round((time.monotonic()-cycle_started)*1000))
        except Exception as exc:
            with self.lock:self.error='Media output failed: '+str(exc)
            self.session.stop_reason=self.error;self.session.stop()
        finally:
            if self.output:
                try:self.output.close()
                except Exception:
                    with self.lock:self.error='Audio output cleanup failed.'
            if self.recorder:
                self.recorder.stop()
                with self.lock:self.state='finishing'
                # Recorder owns a bounded EOS timeout. Never join on the GTK thread.
                self.recorder.thread.join()
                self.update_recording()
            with self.lock:
                self.latest=None;self.done=True
                if self.state in ('starting','finishing'):self.state='idle';self.record_message='Recording cancelled: preview stopped.'

    def update_recording(self):
        r=self.recorder
        if not r:return
        with self.lock:
            self.recorded=r.frames
            if r.done:
                self.state='failed' if r.error else 'saved'
                self.record_message=('Recording stopped: '+r.error) if r.error else 'Recording saved: '+str(r.path)
                self.recorder=None
            elif r.finishing:self.state='finishing'
