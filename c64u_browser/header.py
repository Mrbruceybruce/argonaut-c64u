# SPDX-License-Identifier: GPL-3.0-or-later
"""Native header presentation. Core/Browser retain all connection authority."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango


def refresh_header(app):
    header = getattr(app, 'header_view', None)
    if header is not None:
        header.refresh()


def begin_connection(app, phase):
    header = getattr(app, 'header_view', None)
    return header.begin(phase) if header is not None else None


def end_connection(app, token):
    header = getattr(app, 'header_view', None)
    if header is not None:
        header.end(token)


class ConnectionHeader:
    def __init__(self, app, box):
        self.app = app
        self.closed = False
        self.phase = self.token = None
        identity = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                           hexpand=True)
        box.append(identity)
        self.title = Gtk.Label(xalign=0, hexpand=True, width_chars=1,
                               ellipsize=Pango.EllipsizeMode.END)
        self.title.add_css_class('heading')
        self.metadata = Gtk.Label(xalign=0, wrap=True, width_chars=1)
        self.metadata.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.metadata.add_css_class('dim-label')
        self.notice = Gtk.Label(xalign=0, wrap=True, width_chars=1, selectable=True)
        self.notice.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        for label in (self.title, self.metadata, self.notice):
            identity.append(label)
        self.actions = Gtk.Box(spacing=8, valign=Gtk.Align.START)
        box.append(self.actions)
        self.primary = app.button(self.actions, 'Connect…', self.activate)

    def begin(self, phase):
        if self.closed:
            return None
        self.token = object()
        self.phase = phase
        self.refresh()
        return self.token

    def end(self, token):
        if token is not None and token is self.token:
            self.token = self.phase = None
            self.refresh()

    def close(self):
        self.closed = True
        self.token = self.phase = None
        self.primary.set_sensitive(False)

    def blocked(self):
        app = self.app
        return (self.closed or self.phase is not None or app.busy or
                (app.recovery is not None and app.recovery.inflight) or
                app.foreground.token is not None)

    def activate(self):
        if self.blocked():
            return
        if self.app.active_profile is not None:
            self.app.disconnect_device()
        elif self.app.reconnect_available():
            # This existing route uses connect_selected(require_bound=True)
            # when disconnected; it never adopts an editor-only selection.
            self.app.reconnect_device()
        else:
            self.app.open_connections()

    def refresh(self):
        if self.closed:
            return
        app = self.app
        selected = app.core.selected_profile()
        active = app.active_profile
        profile = active or selected
        recovery = app.recovery
        offline = bool(active and app.offline_message)
        state = 'Offline' if offline else 'Connected' if active else 'Disconnected'
        if self.phase is not None:
            state = self.phase
        elif offline and recovery is not None:
            state += ' · retries paused' if recovery.paused else ' · recovering'
        title = state + ' · ' + (profile.name if profile else 'No device selected')
        self.title.set_text(title)
        self.title.set_tooltip_text(title)
        metadata = f'{profile.host}:{profile.http_port}' if profile else ''
        if active and app.device_info:
            info = app.device_info
            metadata += (f" · Firmware {info['info']['firmware_version']}"
                         f" · API {info['version']['version']}")
        if active and selected and selected.id != active.id:
            metadata += f'\nSelected for next connection: {selected.name}'
        self.metadata.set_text(metadata)
        self.metadata.set_tooltip_text(metadata or None)
        self.metadata.set_visible(bool(metadata))
        # Essential diagnostics remain fully wrapped and never dimmed/ellipsized.
        self.notice.set_text(app.offline_message or '')
        self.notice.set_visible(bool(app.offline_message))
        label = self.phase or ('Disconnect' if active else
                              'Connect' if app.reconnect_available() else 'Connect…')
        self.primary.set_label(label)
        self.primary.set_tooltip_text(
            'Disconnect and stop automatic recovery' if active else
            'Connect to the selected saved device' if app.reconnect_available() else
            'Open Settings → Device details to select and verify a connection')
        self.primary.set_sensitive(not self.blocked())
