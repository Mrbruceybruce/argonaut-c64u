# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""SID playback requests for files already stored on the active device."""
import posixpath
from gi.repository import Gtk
from .api import UltimateClient, BrowserError, ConnectionFailure


class MediaTab:
    def __init__(self, app):
        self.app=app;self.client=None;self.generation=0
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        self.device=Gtk.Label(xalign=0,wrap=True);self.box.append(self.device)
        self.controls=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);self.box.append(self.controls)
        self.controls.append(Gtk.Label(label='SID file on the C64U',xalign=0))
        self.path=Gtk.Entry(hexpand=True,placeholder_text='/USB2/Music/tune.sid');self.controls.append(self.path)
        row=Gtk.Box(spacing=8);self.controls.append(row)
        app.button(row,'Use selected C64U file',self.use_selected)
        self.default_song=Gtk.CheckButton(label='Use file’s default song',active=True);row.append(self.default_song)
        row.append(Gtk.Label(label='Song number'))
        self.song=Gtk.Entry(text='1',width_chars=6,max_width_chars=6,sensitive=False)
        row.append(self.song)
        self.default_song.connect('toggled',lambda *_:self.song.set_sensitive(not self.default_song.get_active()))
        app.button(row,'Play SID…',self.play)
        self.controls.append(Gtk.Label(label='Select a SID file on the C64U side of Files, then use it here. You can also right-click it and choose Open in SID/Media. Upload local files first.',xalign=0,wrap=True))
        self.controls.append(Gtk.Label(label='Songs count from 1; available song numbers depend on the file. Audio plays through the C64U’s outputs.',xalign=0,wrap=True))
        self.status=Gtk.Label(xalign=0,wrap=True,selectable=True);self.box.append(self.status)
        self.bind(None)

    def bind(self, client):
        self.generation+=1;self.client=client
        self.controls.set_sensitive(client is not None)
        self.path.set_text('');self.default_song.set_active(True);self.song.set_text('1')
        self.device.set_text('Active C64U · '+client.host if client else 'Connect to a C64 Ultimate to play a SID file.')
        self.status.set_text('No playback requested in this session.' if client else 'Playback status unavailable while disconnected.')

    def select_file(self, path):
        if not self.client or self.app.busy:return False
        try:UltimateClient.sid_parameters(path)
        except BrowserError as exc:self.status.set_text(str(exc));return False
        self.path.set_text(path);self.default_song.set_active(True);self.song.set_text('1')
        self.status.set_text('File selected. Choose its default song or enter a song number, then Play SID.')
        return True

    def use_selected(self):
        rows=self.app.rlist.get_selected_rows()
        if len(rows)!=1 or rows[0].item[1] or rows[0].item[0]=='..':
            self.status.set_text('Select one .sid file on the C64U side of Files.');return
        self.select_file(posixpath.join(self.app.remote,rows[0].item[0]))

    def play(self):
        if not self.client or self.app.busy:return
        path=self.path.get_text()
        try:
            song=None if self.default_song.get_active() else int(self.song.get_text())
            UltimateClient.sid_parameters(path,song)
        except (ValueError,BrowserError) as exc:
            self.status.set_text(str(exc) if isinstance(exc,BrowserError) else 'Enter a whole song number, or use the file default.');return
        client=self.client;generation=self.generation
        song_label='file default' if song is None else str(song)
        dialog=Gtk.Dialog(title='Play SID',transient_for=self.app.window,modal=True)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL);dialog.add_button('Play SID',Gtk.ResponseType.OK)
        dialog.get_content_area().append(Gtk.Label(label=f'Play on {client.host}\n{path}\nSong: {song_label}\n\nThe SID player takes over the C64. Its current program will stop, and unsaved work may be lost.',wrap=True,xalign=0))
        def response(_,code):
            dialog.destroy()
            if code!=Gtk.ResponseType.OK or generation!=self.generation or self.app.busy:return
            def task():
                try:return client.play_sid(path,song)
                except Exception as exc:return exc
            def done(result):
                if generation!=self.generation:return
                if isinstance(result,Exception):
                    message='Playback was not confirmed. Check the file and song number. '+str(result)
                    if isinstance(result,ConnectionFailure) and result.kind in ('host','network','authentication'):
                        self.app.recovery.lost('SID playback outcome unknown. Checking the connection; playback will not be retried.')
                        if result.kind=='authentication':self.app.recovery.paused=True
                    self.status.set_text(message);self.app.status.set_text(message)
                    return
                message=f'C64U accepted playback: {path} · Song: {song_label}'
                self.status.set_text(message+'\nThis records the last request; live playback progress is not monitored.')
                self.app.status.set_text(message)
            self.app.run(task,done)
        dialog.connect('response',response);dialog.present()
        return dialog
