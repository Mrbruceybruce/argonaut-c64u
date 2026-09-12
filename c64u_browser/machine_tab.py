# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Explicit C64 reset/reboot controls; commands are never automatically retried."""
from gi.repository import Gtk
from .api import ConnectionFailure


class MachineTab:
    def __init__(self, app):
        self.app=app;self.client=None
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        self.label=Gtk.Label(label='Connect to a C64 Ultimate.',xalign=0,wrap=True)
        self.box.append(self.label)
        self.actions=Gtk.Box(spacing=8);self.box.append(self.actions)
        app.button(self.actions,'Reset C64…',lambda:self.command('reset'))
        app.button(self.actions,'Reboot C64…',lambda:self.command('reboot'))
        self.box.append(Gtk.Label(label='Reset restarts the C64. Reboot also reinitializes its cartridge configuration. These are C64 controls, not a full power cycle of the Ultimate hardware.',xalign=0,wrap=True))
        self.box.append(Gtk.Label(label='Argonaut checks the connected device periodically. If it goes offline, it retries the same address and verifies its device ID before reconnecting. Disconnect stops retries.',xalign=0,wrap=True))
        self.bind(None)

    def bind(self, client):
        self.client=client;self.actions.set_sensitive(client is not None)
        self.label.set_text('Ready · '+client.host if client else 'C64U is disconnected or unavailable.')

    def command(self, action):
        if not self.client or self.app.busy:return
        client=self.client
        title='Reset C64' if action=='reset' else 'Reboot C64'
        dialog=Gtk.Dialog(title=title,transient_for=self.app.window,modal=True)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL);dialog.add_button(title,Gtk.ResponseType.OK)
        dialog.get_content_area().append(Gtk.Label(label=f'{title} on {client.host}?\nThe running program will stop and unsaved work may be lost.',wrap=True,xalign=0))
        def response(_,code):
            dialog.destroy()
            if code!=Gtk.ResponseType.OK or self.client is not client or self.app.busy:return
            def task():
                try:return client.machine_action(action)
                except Exception as exc:return exc
            def done(result):
                if self.client is not client:return
                if isinstance(result,Exception):
                    self.app.status.set_text(str(result))
                    if isinstance(result,ConnectionFailure) and result.kind in ('host','network'):
                        self.app.recovery.lost('Command outcome unknown. Checking the connection; the command will not be repeated.')
                    return
                self.app.recovery.lost(title+' acknowledged. Checking the connection…')
            self.app.run(task,done)
        dialog.connect('response',response);dialog.present()
        return dialog
