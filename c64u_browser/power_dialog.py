# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Global machine controls using the reviewed one-shot Core command path."""
from gi.repository import Gtk, Pango
from .api import BrowserError, ConnectionFailure


def _content(dialog, response):
    """Spacing for these three native dialogs; retain GTK response handling."""
    dialog.set_default_size(480, -1)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    for side in ('top', 'start', 'end'):
        getattr(box, 'set_margin_' + side)(20)
    box.set_margin_bottom(16)
    dialog.get_content_area().append(box)
    footer = dialog.get_widget_for_response(response).get_parent()
    footer.set_spacing(8)
    footer.set_halign(Gtk.Align.END)
    for side in ('bottom', 'start', 'end'):
        getattr(footer, 'set_margin_' + side)(20)
    return box


def _text(text):
    label = Gtk.Label(label=text, xalign=0, wrap=True,
                      width_chars=1, max_width_chars=54)
    label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    return label


class UltimatePower:
    def __init__(self, app):
        self.app=app;self.client=None;self.dialog=None

    def show(self):
        if self.app.busy:return
        if self.dialog is not None:
            self.dialog.present();return self.dialog
        dialog=Gtk.Dialog(title='Ultimate Power',transient_for=self.app.window,modal=True)
        self.dialog=dialog
        dialog.add_button('Close',Gtk.ResponseType.CLOSE)
        box = _content(dialog, Gtk.ResponseType.CLOSE)
        box.append(Gtk.Label(label='C64',xalign=0))
        self.label=_text('');box.append(self.label)
        self.actions=Gtk.Box(spacing=8, homogeneous=True, halign=Gtk.Align.START);box.append(self.actions)
        self.app.button(self.actions,'Reset C64…',lambda:self.command('reset'))
        self.app.button(self.actions,'Reboot C64…',lambda:self.command('reboot'))
        box.append(_text('Reset restarts the C64. Reboot also reinitializes its cartridge configuration. These are C64 controls, not a full power cycle of the Ultimate hardware.'))
        box.append(_text('Argonaut verifies the same device when reconnecting. Disconnect stops retries.'))
        self.app.busy_controls.append(box)
        def closed(*_):
            if box in self.app.busy_controls:self.app.busy_controls.remove(box)
            self.dialog=None
            dialog.destroy()
            return True
        dialog.connect('close-request',closed)
        dialog.connect('response',closed)
        self.bind(self.client)
        dialog.present()
        return dialog

    def bind(self, client):
        self.client=client
        if self.dialog is not None:
            self.actions.set_sensitive(client is not None)
            self.label.set_text('Ready · '+client.host if client else 'C64U is disconnected or unavailable.')

    def command(self, action):
        if not self.client or self.app.busy:return
        if self.app.recovery and self.app.recovery.inflight:
            self.app.status.set_text('Connection check running. Action was not sent.')
            return
        try:
            target = self.app.core.prepare_machine_command(action)
        except BrowserError as exc:
            self.app.status.set_text(str(exc))
            return
        title='Reset C64' if action=='reset' else 'Reboot C64'
        dialog=Gtk.Dialog(title=title,transient_for=self.app.window,modal=True)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL);dialog.add_button(title,Gtk.ResponseType.OK)
        box = _content(dialog, Gtk.ResponseType.CANCEL)
        box.append(_text(f'{title} on {target.host}?'))
        box.append(_text('The running program will stop and unsaved work may be lost.'))
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.get_widget_for_response(Gtk.ResponseType.CANCEL).grab_focus()
        responded = False
        def response(_,code):
            nonlocal responded
            if responded:return
            responded = True
            try:
                dialog.destroy()
                if code!=Gtk.ResponseType.OK:
                    self.app.core.discard_machine_command(target)
                    return
                if self.app.busy or (self.app.recovery and self.app.recovery.inflight):
                    self.app.core.discard_machine_command(target)
                    self.app.status.set_text('Connection or device operation running. Action was not sent.')
                    return
                def task():
                    try:return self.app.core.execute_machine_command(target)
                    except Exception as exc:return exc
                def done(result):
                    self.app.core.discard_machine_command(target)
                    if isinstance(result,Exception):
                        self.app.status.set_text(str(result))
                        if (isinstance(result,ConnectionFailure) and result.kind in ('host','network')
                                and self.app.core.device_session() == target.session):
                            self.app.recovery.lost('Command outcome unknown. Checking the connection; the command will not be repeated.')
                        return
                    if self.app.core.device_session() != target.session:
                        self.app.status.set_text(title+' acknowledged for the previous connection.')
                        return
                    self.app.recovery.lost(title+' acknowledged. Checking the connection…')
                if self.app.run(task,done) is False:
                    self.app.core.discard_machine_command(target)
                    self.app.status.set_text(title+' was not sent. Could not start the operation.')
            except Exception:
                self.app.core.discard_machine_command(target)
                self.app.status.set_text(
                    'Could not complete '+title+' submission. No automatic retry.')
        dialog.connect('response',response);dialog.present()
        return dialog
