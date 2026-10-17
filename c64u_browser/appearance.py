# SPDX-License-Identifier: GPL-3.0-or-later
"""Portal-first appearance following on the GTK main thread, without polling.

GTK 4.8 has no gtk-interface-color-scheme. Use the compatible dark-variant
property (deprecated, but still available, in GTK 4.20+) without changing the
GTK theme name or CSS providers. No preference restores the initial GTK value
unless GNOME supplies an explicit preference. No user preference is persisted.
"""
import os
import sys
from gi.repository import Gio, GLib, Gtk


class AppearanceFollower:
    def __init__(self, display):
        self.closed = False
        self.display = display
        self.settings = None
        self.proxy = None
        self.gnome = None
        self.handlers = []
        self.revision = 0
        self.portal_value = None
        self.cancel = Gio.Cancellable()
        if display is None or display.is_closed():
            self.closed = True
            return
        self.settings = Gtk.Settings.get_for_display(display)
        self.initial = self.settings.get_property('gtk-application-prefer-dark-theme')
        self.listen(display, 'closed', lambda *_: self.close())
        if sys.platform != 'linux':
            return  # Preserve native platform appearance on other backends.
        desktops = os.environ.get('XDG_CURRENT_DESKTOP', '').upper().split(':')
        if 'GNOME' in desktops:
            source = Gio.SettingsSchemaSource.get_default()
            schema = source.lookup('org.gnome.desktop.interface', True) if source else None
            if schema is not None and schema.has_key('color-scheme'):
                try:
                    self.gnome = Gio.Settings.new_full(schema, None, None)
                    self.listen(self.gnome, 'changed::color-scheme', lambda *_: self.apply())
                except GLib.Error:
                    self.gnome = None
        self.apply()
        try:
            Gio.DBusProxy.new_for_bus(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                None, 'org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                'org.freedesktop.portal.Settings', self.cancel, self.proxy_ready, None)
        except GLib.Error:
            pass  # Session bus setup may fail synchronously as well.

    def listen(self, obj, signal, callback):
        self.handlers.append((obj, obj.connect(signal, callback)))

    @staticmethod
    def preference(value):
        while isinstance(value, GLib.Variant):
            value = value.unpack()
        if type(value) is int:
            return {1: True, 2: False}.get(value)
        return None

    def apply(self):
        if self.closed or self.display.is_closed():
            return
        value = self.portal_value
        if value is None and self.gnome is not None:
            try:
                value = {'prefer-dark': True, 'prefer-light': False}.get(
                    self.gnome.get_string('color-scheme'))
            except GLib.Error:
                pass
        self.settings.set_property('gtk-application-prefer-dark-theme',
                                   self.initial if value is None else value)

    def proxy_ready(self, _source, result, _data):
        try:
            proxy = Gio.DBusProxy.new_for_bus_finish(result)
        except GLib.Error:
            return  # Fallback/initial value is already in place.
        if self.closed:
            return
        self.proxy = proxy
        self.listen(proxy, 'g-signal', self.changed)
        self.listen(proxy, 'notify::g-name-owner', lambda *_: self.read())
        self.read()

    def read(self):
        if self.closed:
            return
        self.revision += 1
        revision = self.revision
        self.portal_value = None
        self.apply()
        if not self.proxy.get_name_owner():
            return
        self.proxy.call('Read', GLib.Variant('(ss)',
            ('org.freedesktop.appearance', 'color-scheme')),
            Gio.DBusCallFlags.NONE, 2000, self.cancel, self.read_done, revision)

    def read_done(self, proxy, result, revision):
        try:
            reply = proxy.call_finish(result)
        except GLib.Error:
            return
        if self.closed or revision != self.revision:
            return
        values = reply.unpack()
        self.portal_value = self.preference(values[0]) if len(values) == 1 else None
        self.apply()

    def changed(self, _proxy, _sender, signal, parameters):
        if self.closed or signal != 'SettingChanged':
            return
        values = parameters.unpack()
        if len(values) != 3 or values[:2] != ('org.freedesktop.appearance', 'color-scheme'):
            return
        self.revision += 1  # A late initial Read must not overwrite a newer signal.
        self.portal_value = self.preference(values[2])
        self.apply()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancel.cancel()
        for obj, handler in reversed(self.handlers):
            obj.disconnect(handler)
        self.handlers.clear()
        self.proxy = self.gnome = self.settings = None
