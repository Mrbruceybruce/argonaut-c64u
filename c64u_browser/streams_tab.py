# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Live C64 video and optional audio, with explicit session ownership."""
import time
from datetime import datetime
from pathlib import Path
from gi.repository import Gtk,Gdk,GLib,Gio
from .streaming import StreamSession
from .media_session import MediaDelivery


class StreamsTab:
    def __init__(self,app):
        self.app=app;self.client=None;self.session=None;self.media=None;self.timer=None
        self.capture_window=None;self.last_frame=None;self.diagnostics_dialog=None;self.last_stats={}
        self.replace_prompt=None
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
        capture_row=Gtk.Box(spacing=8);self.box.append(capture_row)
        self.open_capture=Gtk.Button(label='Open capture window');capture_row.append(self.open_capture)
        self.open_capture.connect('clicked',self.show_capture)
        self.integer_capture=Gtk.CheckButton(label='Integer scaling',active=True,halign=Gtk.Align.START)
        self.integer_capture.set_tooltip_text('Clean view only: nearest-neighbor scaling with the native pixel aspect ratio. Small windows fit the whole picture.')
        capture_row.append(self.integer_capture)
        self.integer_capture.connect('toggled',self.capture_scale)
        capture_row.append(Gtk.Label(label='Native pixels',xalign=0))
        diagnostics=Gtk.Button(label='Diagnostics…');capture_row.append(diagnostics)
        diagnostics.connect('clicked',self.show_diagnostics)
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
        self.record_chooser=None
        keyboard=Gtk.Box(spacing=8);self.box.append(keyboard)
        self.text_input=Gtk.Entry(placeholder_text='Text for the C64 BASIC READY prompt',hexpand=True,max_length=160)
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
        running=(self.session is not None and self.session.thread.is_alive()) or (self.media is not None and self.media.thread.is_alive())
        self.start_button.set_sensitive(self.client is not None and not running)
        self.stop_button.set_sensitive(running)
        self.audio.set_sensitive(not running)

    def start(self,*_):
        if not self.client or (self.session and self.session.thread.is_alive()) or (self.media and self.media.thread.is_alive()):return
        self.app.preferences.app_options['preview_audio']=self.audio.get_active();self.app.save_app_preferences()
        self.picture.set_paintable(None);self.capture_button.set_sensitive(False)
        self.fps_time=time.monotonic();self.fps_frames=0;self.fps=0.0
        self.session=StreamSession(self.client,self.audio.get_active())
        self.media=MediaDelivery(self.session,cairo_fallback=not hasattr(Gtk.Snapshot,'append_scaled_texture'))
        self.last_stats={};self.last_frame=None
        self.status.set_text('Starting preview…');self.update_buttons()
        if self.timer is None:self.timer=GLib.timeout_add(33,self.tick)

    def stop(self,*_):
        if self.media:self.media.stop()
        self.record_button.set_sensitive(False)
        if self.session and self.session.thread.is_alive():
            self.session.stop();self.status.set_text('Stopping preview…')
        self.blank_picture()

    def blank_picture(self):
        self.last_frame=None;self.picture.set_paintable(None);self.capture_button.set_sensitive(False)
        if self.capture_window:self.capture_window.canvas.set_frame(None)

    def tick(self):
        session=self.session;media=self.media
        if not session or not media:self.timer=None;return False
        receiver=session.receiver;state=media.snapshot()
        if receiver and not session.stopping.is_set() and session.thread.is_alive():
            stats=receiver.snapshot();self.last_stats=stats
            frame=media.take_frame()
            if frame:
                height,rgb,surface=frame
                texture=Gdk.MemoryTexture.new(384,height,Gdk.MemoryFormat.R8G8B8,GLib.Bytes.new(rgb),384*3)
                self.last_frame=(texture,surface)
                self.picture.set_paintable(texture)
                if self.capture_window:self.capture_window.canvas.set_frame(texture,surface)
                if height!=self.preview_height:self.preview_height=height;self.scale_preview()
                self.capture_button.set_sensitive(self.capture_chooser is None)
            if (stats.get('video_age') or 0)>2:self.blank_picture()
            if receiver.frames:
                audio=' · Audio receiving' if receiver.last_audio and time.monotonic()-receiver.last_audio<2 else (' · Waiting for audio' if session.with_audio else '')
                stale=' · Waiting for video' if time.monotonic()-receiver.last_video>2 else ''
                now=time.monotonic();interval=now-self.fps_time
                if interval>=1:
                    self.fps=max(0,receiver.frames-self.fps_frames)/interval
                    self.fps_time=now;self.fps_frames=receiver.frames
                seconds=max(0,int(now-receiver.started))
                self.status.set_text(f'Live preview · {self.fps:.1f} FPS · {seconds} s'+audio+stale)
            else:self.status.set_text(session.message)
        self.record_tick()
        if not session.thread.is_alive():
            media.stop();self.blank_picture();self.status.set_text(state['error'] or session.message)
            if not media.thread.is_alive():
                self.record_tick();self.session=None;self.timer=None;self.update_buttons();return False
        self.update_buttons()
        return True

    def record(self,*_):
        media=self.media;session=self.session;texture=self.picture.get_paintable()
        if not media:return
        if media.snapshot()['recording_state'] in ('starting','recording','finishing'):
            media.stop_recording();return
        if not session or not texture or self.record_chooser:return
        chooser=Gtk.FileChooserNative.new('Save recording',self.app.window,Gtk.FileChooserAction.SAVE,'Record','Cancel')
        self.record_chooser=chooser;self.record_button.set_sensitive(False)
        folder=self.app.preferences.recording_folder
        if folder and Path(folder).is_dir():chooser.set_current_folder(Gio.File.new_for_path(folder))
        chooser.set_current_name(datetime.now().strftime('c64u-%Y%m%d-%H%M%S.webm'))
        def response(_,code):
            file=chooser.get_file();chooser.destroy();self.record_chooser=None
            if code!=Gtk.ResponseType.ACCEPT or not file:return
            if self.session is not session or session.stopping.is_set() or not session.thread.is_alive():return
            path=file.get_path()
            if not path:self.record_status.set_text('Choose a local recording file.');return
            from .recording import destination_signature
            try:expected=destination_signature(path)
            except Exception as exc:self.record_status.set_text(str(exc));return
            def begin():
                if self.session is not session or session.stopping.is_set() or self.media is not media:return
                if media.start_recording(path,texture.get_height(),expected):
                    self.app.preferences.recording_folder=str(Path(path).parent)
                    try:self.app.preferences.save()
                    except Exception:pass
            if expected is None:begin()
            else:
                dialog=Gtk.Dialog(title='Replace recording?',transient_for=self.app.window,modal=True)
                self.replace_prompt=dialog
                dialog.add_button('Cancel',Gtk.ResponseType.CANCEL);dialog.add_button('Replace',Gtk.ResponseType.OK)
                dialog.get_content_area().append(Gtk.Label(label='Replace this file only after the new recording finishes successfully?\n'+path,wrap=True))
                def replace(_,code):
                    dialog.destroy();self.replace_prompt=None
                    if code==Gtk.ResponseType.OK:begin()
                dialog.connect('response',replace);dialog.present()
        chooser.connect('response',response);chooser.show()

    def record_tick(self):
        if not self.media:return
        state=self.media.snapshot();mode=state['recording_state']
        active=mode in ('starting','recording','finishing')
        self.record_button.set_label('Stop recording' if active else 'Start recording…')
        running=self.session is not None and self.session.thread.is_alive() and not self.session.stopping.is_set()
        self.record_button.set_sensitive((mode=='recording') or (not active and running and self.picture.get_paintable() is not None and self.record_chooser is None and self.replace_prompt is None))
        if mode=='recording':
            seconds=max(0,int(time.monotonic()-state['record_started']))
            self.record_status.set_text(f'Recording {seconds//60:02}:{seconds%60:02}'+(' · With audio' if self.session.with_audio else ' · Video only'))
        elif mode in ('starting','finishing'):self.record_status.set_text('Starting recording…' if mode=='starting' else 'Finishing recording…')
        else:self.record_status.set_text(state['record_message'])

    def show_capture(self,*_):
        if self.capture_window:self.capture_window.present();return
        from .capture_window import CaptureWindow
        self.capture_window=CaptureWindow(self.app,lambda:setattr(self,'capture_window',None))
        self.capture_scale()
        if self.last_frame:self.capture_window.canvas.set_frame(*self.last_frame)
        self.capture_window.present()

    def capture_scale(self,*_):
        if self.capture_window:
            self.capture_window.canvas.integer=self.integer_capture.get_active()
            self.capture_window.canvas.queue_draw()

    def show_diagnostics(self,*_):
        if self.diagnostics_dialog:self.diagnostics_dialog.present();return
        from .stream_diagnostics import report
        dialog=Gtk.Dialog(title='Stream diagnostics',transient_for=self.app.window,default_width=680,default_height=600)
        self.diagnostics_dialog=dialog
        box=dialog.get_content_area()
        addresses=Gtk.CheckButton(label='Include network addresses',halign=Gtk.Align.START)
        box.append(addresses)
        view=Gtk.TextView(editable=False,cursor_visible=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True);scroll.set_child(view);box.append(scroll)
        dialog.add_button('Copy report',Gtk.ResponseType.APPLY);dialog.add_button('Close',Gtk.ResponseType.CLOSE)
        def refresh():
            if self.diagnostics_dialog is not dialog:return False
            stats=dict(self.last_stats)
            stats.update(connected=self.client is not None,running=self.session is not None and self.session.thread.is_alive() and not self.session.stopping.is_set())
            if self.session and self.session.receiver:stats.update(self.session.receiver.snapshot())
            if self.media:
                # Formatter ignores free-form error text and recording paths.
                stats.update(self.media.snapshot())
            view.get_buffer().set_text(report(stats,addresses.get_active()))
            return True
        refresh();timer=GLib.timeout_add(500,refresh)
        def response(_,code):
            if code==Gtk.ResponseType.APPLY:
                refresh();buf=view.get_buffer();dialog.get_clipboard().set(buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False))
            else:
                GLib.source_remove(timer);self.diagnostics_dialog=None;dialog.destroy()
        dialog.connect('response',response);dialog.present()

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
        if self.replace_prompt:self.replace_prompt.destroy();self.replace_prompt=None
        if self.diagnostics_dialog:self.diagnostics_dialog.response(Gtk.ResponseType.CLOSE)
        if self.capture_window:self.capture_window.close()
        self.stop()
        pending=(self.media is not None and self.media.thread.is_alive()) or (self.session is not None and self.session.thread.is_alive())
        if not pending and self.timer is not None:GLib.source_remove(self.timer);self.timer=None
        return bool(pending)

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
            self.text_status.set_text(str(result) if isinstance(result,Exception) else f'Sent {result} bytes. Check the C64U screen.')
        self.app.run(task,done)

    def scale_preview(self,*_):
        factor=self.preview_percent/100
        self.picture.set_size_request(round(384*factor),round(self.preview_height*factor))

    def apply_scale(self,*_):
        self.preview_percent=int(self.zoom.get_text().rstrip('%'))
        self.scale_preview()
