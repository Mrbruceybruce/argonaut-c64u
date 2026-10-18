# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""One job-bound cancellation decision; deliberately no cleanup submission."""
from gi.repository import Gtk, Gdk, GLib, Pango


class UploadCancelDialog:
    KEEP = 1
    DELETE = 2

    def __init__(self, app, job, token):
        self.app, self.job, self.token = app, job, token
        self.responded = False
        self.dialog = Gtk.Dialog(title='Cancel Upload?', transient_for=app.window, modal=True)
        self.dialog.set_default_size(480, -1)
        self.continue_button = self.dialog.add_button('Continue Upload', Gtk.ResponseType.CANCEL)
        self.keep_button = self.dialog.add_button('Cancel & Keep', self.KEEP)
        self.delete_button = self.dialog.add_button('Cancel & Clean Up', self.DELETE)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ('top', 'start', 'end'):
            getattr(self.content, 'set_margin_' + side)(20)
        self.content.set_margin_bottom(16)
        self.dialog.get_content_area().append(self.content)
        for text in (
            'The upload continues while this dialog is open. Cancellation is cooperative; the upload stops when it can safely respond.',
            'Cancel & Keep retains incomplete staging files. Cancel & Clean Up attempts cleanup once, after the upload stops, only for this upload’s verified incomplete staging file. Cleanup may fail if the C64U has not finished updating the file. Completed files are kept.',
        ):
            label = Gtk.Label(label=text, xalign=0, wrap=True, width_chars=1, max_width_chars=54)
            label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            self.content.append(label)
        self.footer = self.keep_button.get_parent()
        self.footer.set_spacing(8)
        self.footer.set_halign(Gtk.Align.END)
        for side in ('start', 'end', 'bottom'):
            getattr(self.footer, 'set_margin_' + side)(20)
        self.dialog.set_default_response(self.KEEP)
        self.dialog.connect('response', self.response)
        self.dialog.connect('close-request', self._close_requested)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._key_pressed)
        self.dialog.add_controller(keys)
        self.keys = keys
        # Core/job callbacks may run off the GTK thread. Late idle deliveries
        # are harmless after the response latch is consumed.
        self._remove_job = job.add_listener(lambda event: GLib.idle_add(self.validate))
        self._remove_core = app.core.add_listener(lambda event: GLib.idle_add(self.validate))

    def show(self):
        if self.validate_current():
            self.dialog.present()
            self.keep_button.grab_focus()
        else:self.dismiss()

    def validate_current(self):
        return (not self.responded and
                self.app.foreground.owns(self.token, self.job) and
                self.app.transfer_job is self.job and
                self.app.operation.matches(self.job, self.token) and
                self.app.operation.view.cancel_available and
                self.app.core.files._upload_cancel_eligible(self.job))

    def validate(self):
        if not self.responded and not self.validate_current():self.dismiss()
        return False

    def _key_pressed(self, controller, key, code, state):
        if key == Gdk.KEY_Escape:
            self.dismiss()
            return True
        return False

    def _close_requested(self, *_):
        self.dismiss()
        return True

    def dismiss(self):
        self.response(self.dialog, Gtk.ResponseType.CANCEL)

    def response(self, dialog, code):
        if self.responded:return
        valid = self.validate_current()
        self.responded = True  # Before destruction, notifications, or reentry.
        self._remove_job()
        self._remove_core()
        if self.app.upload_cancel_dialog is self:self.app.upload_cancel_dialog = None
        self.dialog.destroy()
        if valid and code in (self.KEEP, self.DELETE):
            decision = 'keep' if code == self.KEEP else 'delete'
            self.app.operation.request_cancel(self.job, self.token,
                lambda:self.app.core.files._request_upload_cancel(self.job, decision))
        # Restore to a live control, including when B5 has hidden Cancel.
        if self.app.cancel_button.get_visible() and self.app.cancel_button.is_sensitive():
            self.app.cancel_button.grab_focus()
        elif not self.app.tabs.child_focus(Gtk.DirectionType.TAB_FORWARD):
            self.app.status_label.grab_focus()
