# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Live C64 video and optional audio, with explicit session ownership."""
import time
from datetime import datetime
from pathlib import Path
from gi.repository import Gtk,Gdk,GLib,Gio
from .streaming import StreamSession,AudioOutput,rgb_frame


class StreamsTab:
    def __init__(self,app):
        self.app=app;self.client=None;self.session=None;self.output=None;self.timer=None
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        header=Gtk.Box(spacing=12);self.box.append(header)
        self.device=Gtk.Label(xalign=0,wrap=True,hexpand=True);header.append(self.device)
        self.status=Gtk.Label(xalign=1,wrap=True,max_width_chars=55);header.append(self.status)
        self.status.set_tooltip_text('FPS counts complete video frames received; seconds are elapsed preview time.')
        self.fps_time=0;self.fps_frames=0;self.fps=0.0
        row=Gtk.Box(spacing=8);self.box.append(row)
        self.start_button=Gtk.Button(label='Start preview');row.append(self.start_button)
        self.start_button.connect('clicked',self.start)
        self.stop_button=Gtk.Button(label='Stop preview',sensitive=False);row.append(self.stop_button)
        self.stop_button.connect('clicked',self.stop)
        self.capture_button=Gtk.Button(label='Save screenshot…',sensitive=False);row.append(self.capture_button)
        self.capture_button.connect('clicked',self.capture)
        self.capture_chooser=None
        self.record_button=Gtk.Button(label='Start recording…',sensitive=False);row.append(self.record_button)
        self.record_button.connect('clicked',self.record)
        self.audio=Gtk.CheckButton(label='Play audio on this computer',active=app.preferences.app_options['preview_audio']);row.append(self.audio)
        zoomrow=Gtk.Box(spacing=8);self.box.append(zoomrow)
        zoomrow.append(Gtk.Label(label='Preview scale'))
        self.preview_percent=app.preferences.app_options['preview_scale']
        from .app_preferences import scale_control
        control,self.zoom,self.set_zoom=scale_control(self.preview_percent,self.apply_scale)
        zoomrow.append(control)
        self.preview_height=240
        self.picture=Gtk.Picture(can_shrink=True,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
        self.preview_scroll=Gtk.ScrolledWindow(hexpand=True,vexpand=True,min_content_height=200)
        self.preview_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC)
        self.preview_scroll.set_propagate_natural_width(False);self.preview_scroll.set_propagate_natural_height(False)
        self.preview_scroll.set_overlay_scrolling(False)
        self.preview_scroll.set_child(self.picture);self.box.append(self.preview_scroll)
        self.scale_preview()
        self.capture_status=Gtk.Label(xalign=0,wrap=True,selectable=True);self.box.append(self.capture_status)
        self.record_status=Gtk.Label(xalign=0,wrap=True);self.box.append(self.record_status)
        self.recorder=None;self.record_chooser=None
        keyboard=Gtk.Box(spacing=8);self.box.append(keyboard)
        self.text_input=Gtk.Entry(placeholder_text='Text for the C64 BASIC READY prompt',hexpand=True,max_length=160)
        from .text_input import uppercase_entry
        self.text_input.connect('changed', uppercase_entry)
        keyboard.append(self.text_input)
        self.text_return=Gtk.CheckButton(label='Append Return',active=True);keyboard.append(self.text_return)
        self.text_send=Gtk.Button(label='Send text',sensitive=False);keyboard.append(self.text_send)
        self.text_send.connect('clicked',self.send_text)
        self.text_input.connect('activate',self.send_text)
        self.text_status=Gtk.Label(xalign=0,wrap=True)
        self.box.append(self.text_status)
        self.bind(None)

    def bind(self,client):
        self.stop();self.client=client;self.picture.set_paintable(None);self.capture_button.set_sensitive(False)
        self.device.set_text('Active C64U · '+client.host if client else 'Connect to a C64 Ultimate to preview video and audio.')
        self.text_send.set_sensitive(client is not None)
        self.text_input.set_text('')
        self.update_buttons()

    def update_buttons(self):
        running=self.session is not None and self.session.thread.is_alive()
        self.start_button.set_sensitive(self.client is not None and not running)
        self.stop_button.set_sensitive(running)
        self.audio.set_sensitive(not running)

    def start(self,*_):
        if not self.client or (self.session and self.session.thread.is_alive()):return
        self.app.preferences.app_options['preview_audio']=self.audio.get_active();self.app.save_app_preferences()
        self.picture.set_paintable(None);self.capture_button.set_sensitive(False)
        try:self.output=AudioOutput() if self.audio.get_active() else None
        except Exception as exc:
            self.status.set_text('Audio could not start: '+str(exc)+'. Turn off audio to preview video only.');return
        self.fps_time=time.monotonic();self.fps_frames=0;self.fps=0.0
        self.session=StreamSession(self.client,self.audio.get_active())
        self.status.set_text('Starting preview…');self.update_buttons()
        if self.timer is None:self.timer=GLib.timeout_add(33,self.tick)

    def stop(self,*_):
        if self.recorder:self.recorder.stop()
        self.record_button.set_sensitive(False)
        if self.session and self.session.thread.is_alive():
            self.session.stop();self.status.set_text('Stopping preview…')
        if self.output:self.output.close();self.output=None
        self.picture.set_paintable(None);self.capture_button.set_sensitive(False)

    def tick(self):
        session=self.session
        if not session:return False
        receiver=session.receiver
        if receiver and not session.stopping.is_set() and session.thread.is_alive():
            frame,samples=receiver.take()
            if frame:
                height,packed=frame
                rgb=rgb_frame(packed)
                texture=Gdk.MemoryTexture.new(384,height,Gdk.MemoryFormat.R8G8B8,GLib.Bytes.new(rgb),384*3)
                self.picture.set_paintable(texture)
                if height!=self.preview_height:
                    self.preview_height=height;self.scale_preview()
                self.capture_button.set_sensitive(self.capture_chooser is None)
            if self.recorder and not self.recorder.finishing:
                try:self.recorder.feed((height,rgb) if frame else None,samples)
                except Exception as exc:self.recorder.stop(str(exc))
            if not self.recorder:self.record_button.set_sensitive(bool(self.picture.get_paintable()) and self.record_chooser is None)
            if self.output:
                try:self.output.push(samples)
                except Exception as exc:
                    self.output.close();self.output=None
                    session.stop_reason='Audio output failed: '+str(exc);self.stop()
            if receiver.frames:
                audio=' · Audio receiving' if receiver.last_audio and time.monotonic()-receiver.last_audio<2 else (' · Waiting for audio' if session.with_audio else '')
                stale=' · Waiting for video' if time.monotonic()-receiver.last_video>2 else ''
                now=time.monotonic()
                interval=now-self.fps_time
                if interval>=1:
                    self.fps=max(0,receiver.frames-self.fps_frames)/interval
                    self.fps_time=now;self.fps_frames=receiver.frames
                seconds=max(0,int(now-receiver.started))
                self.status.set_text(f'Live preview · {self.fps:.1f} FPS · {seconds} s'+audio+stale)
            else:self.status.set_text(session.message)
        if not session.thread.is_alive():
            if self.recorder:self.recorder.stop()
            self.record_button.set_sensitive(False)
            if self.output:self.output.close();self.output=None
            self.picture.set_paintable(None);self.capture_button.set_sensitive(False);self.status.set_text(session.message)
            self.session=None;self.timer=None;self.update_buttons();return False
        return True

    def record(self,*_):
        if self.recorder:
            self.recorder.stop();return
        session=self.session;texture=self.picture.get_paintable()
        if not session or not texture or self.record_chooser:return
        chooser=Gtk.FileChooserNative.new('Save recording',self.app.window if self.app else None,Gtk.FileChooserAction.SAVE,'Record','Cancel')
        self.record_chooser=chooser;self.record_button.set_sensitive(False)
        folder=self.app.preferences.recording_folder if self.app else ''
        if folder and Path(folder).is_dir():chooser.set_current_folder(Gio.File.new_for_path(folder))
        chooser.set_current_name(datetime.now().strftime('c64u-%Y%m%d-%H%M%S.webm'))
        def response(_,code):
            file=chooser.get_file();chooser.destroy();self.record_chooser=None
            if code!=Gtk.ResponseType.ACCEPT or not file:return
            if self.session is not session or session.stopping.is_set() or not session.thread.is_alive():return
            path=file.get_path()
            if not path:self.record_status.set_text('Choose a local recording file.');return
            try:
                from .recording import Recorder
                self.recorder=Recorder(path,texture.get_height(),session.with_audio)
                self.record_button.set_label('Stop recording');self.record_button.set_sensitive(True)
                GLib.timeout_add(200,self.record_tick)
                if self.app:
                    self.app.preferences.recording_folder=str(Path(path).parent)
                    try:self.app.preferences.save()
                    except Exception:pass
            except Exception as exc:self.record_status.set_text('Could not start recording: '+str(exc))
        chooser.connect('response',response);chooser.show()

    def record_tick(self):
        recorder=self.recorder
        if not recorder:return False
        if recorder.done:
            self.record_status.set_text(('Recording stopped: '+recorder.error) if recorder.error else 'Recording saved: '+recorder.path)
            self.recorder=None;self.record_button.set_label('Start recording…')
            self.record_button.set_sensitive(self.picture.get_paintable() is not None)
            return False
        seconds=int(time.monotonic()-recorder.started)
        self.record_status.set_text('Finishing recording…' if recorder.finishing else f'Recording {seconds//60:02}:{seconds%60:02}'+(' · With audio' if recorder.audio else ' · Video only'))
        self.record_button.set_sensitive(not recorder.finishing)
        return True

    def capture(self,*_):
        texture=self.picture.get_paintable()
        if texture is None or self.capture_chooser is not None:return
        # Hold this immutable frame while the live preview keeps updating.
        chooser=Gtk.FileChooserNative.new('Save C64 screenshot',self.app.window if self.app else None,Gtk.FileChooserAction.SAVE,'Save','Cancel')
        self.capture_chooser=chooser;self.capture_button.set_sensitive(False)
        folder=self.app.preferences.screenshot_folder if self.app else ''
        if folder and Path(folder).is_dir():chooser.set_current_folder(Gio.File.new_for_path(folder))
        chooser.set_current_name(datetime.now().strftime('c64u-%Y%m%d-%H%M%S.png'))
        def response(_,code):
            file=chooser.get_file();chooser.destroy();self.capture_chooser=None
            self.capture_button.set_sensitive(self.picture.get_paintable() is not None)
            if code!=Gtk.ResponseType.ACCEPT or not file:return
            path=file.get_path()
            if not path:self.capture_status.set_text('Choose a local file for the screenshot.');return
            try:
                if not texture.save_to_png(path):raise OSError('Could not write the image.')
                self.capture_status.set_text('Screenshot saved: '+path)
                if self.app:
                    self.app.preferences.screenshot_folder=str(Path(path).parent)
                    try:self.app.preferences.save()
                    except Exception:self.capture_status.set_text('Screenshot saved: '+path+' · Could not remember the folder for next launch.')
            except Exception as exc:self.capture_status.set_text('Screenshot could not be saved: '+str(exc))
        chooser.connect('response',response);chooser.show()
        return chooser

    def close(self):
        if self.record_chooser:self.record_chooser.destroy();self.record_chooser=None
        if self.capture_chooser:self.capture_chooser.destroy();self.capture_chooser=None
        self.stop()
        if self.timer is not None:GLib.source_remove(self.timer);self.timer=None

    def send_text(self,*_):
        if not self.client or self.app.busy:return
        from .keyboard_input import send_text,encode_text
        client=self.client;text=self.text_input.get_text();enter=self.text_return.get_active()
        try:encode_text(text,enter)
        except Exception as exc:
            self.text_status.set_text(str(exc));return
        self.text_status.set_text('Sending text… Keep the C64U at BASIC READY; do not type on its keyboard during sending.')
        def task():
            try:return send_text(client,text,enter)
            except Exception as exc:return exc
        def done(result):
            if self.client is not client:return
            if isinstance(result,Exception):
                self.text_status.set_text(str(result))
                return
            # Keep newly typed text if the user managed to edit the field while
            # the asynchronous send was finishing.
            if self.text_input.get_text() == text:
                self.text_input.set_text('')
            self.text_input.grab_focus()
            self.text_status.set_text(f'Sent {result} bytes. Ready for the next line.')
        self.app.run(task,done)

    def scale_preview(self,*_):
        factor=self.preview_percent/100
        self.picture.set_size_request(round(384*factor),round(self.preview_height*factor))

    def apply_scale(self,*_):
        self.preview_percent=int(self.zoom.get_text().rstrip('%'))
        self.scale_preview()
