# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Files presentation adapters; GTK owns selection and keyboard navigation."""
from gi.repository import Gdk, Gio, GLib, Gtk


class ClickPolicy:
    """Optional, read-only Nautilus compatibility; not a global GTK setting."""
    def __init__(self):
        self.settings = None
        self.handler = None
        self.listeners = []
        self.value = 'double'
        try:
            source = Gio.SettingsSchemaSource.get_default()
            schema = source.lookup('org.gnome.nautilus.preferences', True) if source else None
            if schema is not None and schema.has_key('click-policy'):
                self.settings = Gio.Settings.new_full(schema, None, None)
                self.handler = self.settings.connect('changed::click-policy', self.changed)
        except (GLib.Error, TypeError, ValueError, RuntimeError):
            self.close()
        self.changed()

    def changed(self, *_):
        try:
            value = self.settings.get_string('click-policy') if self.settings else 'double'
        except (GLib.Error, TypeError, ValueError, RuntimeError):
            value = 'double'
        self.value = value if value in ('single', 'double') else 'double'
        for callback in self.listeners:
            callback()

    def close(self):
        if self.settings is not None and self.handler is not None:
            self.settings.disconnect(self.handler)
        self.handler = None
        self.settings = None
        self.listeners.clear()


class FileListActivation:
    """Qualify each pointer sequence before allowing GTK's native activation.

    GTK 4.18's single-click branch precedes modifier selection and has different
    multiple-selection semantics. Keep that property off: GTK processes every
    selection normally, then a qualified single/double release activates on the
    next UI turn. Native double-click activation on button-down is suppressed.
    This controller never claims events or computes toggle/range selection.
    """
    MODIFIERS = (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK |
                 Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.META_MASK |
                 Gdk.ModifierType.SUPER_MASK)

    def __init__(self, listing, policy, activate):
        self.listing, self.policy, self.activate = listing, policy, activate
        self.pointer = None
        self.expiry = None
        listing.set_activate_on_single_click(False)
        policy.listeners.append(self.cancel)
        self.click = Gtk.GestureClick(button=1)
        self.click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.click.connect('pressed', self.pressed)
        self.click.connect('released', self.released)
        self.click.connect('cancel', self.cancel)
        self.click.connect('stopped', self.cancel)
        listing.add_controller(self.click)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.key_pressed)
        listing.add_controller(keys)
        listing.connect('row-activated', self.activated)
        listing.connect('unmap', self.cancel)

    def cancel(self, *_):
        if self.expiry is not None:
            GLib.source_remove(self.expiry)
            self.expiry = None
        self.pointer = None
        self.listing.set_activate_on_single_click(False)

    def key_pressed(self, *_):
        self.cancel()
        return False

    def row_at(self, x, y):
        if 0 <= x < self.listing.get_width() and 0 <= y < self.listing.get_height():
            return self.listing.get_row_at_y(int(y))
        return None

    def pressed(self, gesture, count, x, y):
        self.cancel()
        plain = not gesture.get_current_event_state() & self.MODIFIERS
        self.pointer = (self.row_at(x, y), plain, x, y, count)

    def released(self, gesture, count, x, y):
        pointer = self.pointer
        if pointer is None:
            self.listing.set_activate_on_single_click(False)
            return
        row, plain, start_x, start_y, pressed_count = pointer
        valid = (plain and not gesture.get_current_event_state() & self.MODIFIERS
                 and self.row_at(x, y) is row
                 and not self.listing.drag_check_threshold(int(start_x), int(start_y), int(x), int(y)))
        valid = valid and count == pressed_count
        self.pointer = (row, valid, start_x, start_y, count)
        if valid and row is None and 0 <= x < self.listing.get_width() and 0 <= y < self.listing.get_height():
            self.listing.unselect_all()
        # Let GTK finish native selection before dispatching one activation.
        self.expiry = GLib.idle_add(self.expire)

    def expire(self):
        self.expiry = None
        pointer = self.pointer
        self.cancel()
        if pointer is not None:
            row, valid, _, _, count = pointer
            required_count = 1 if self.policy.value == 'single' else 2
            if (valid and count == required_count and row is not None
                    and row.get_parent() is self.listing and row.get_mapped()
                    and row.is_sensitive() and row.get_activatable()):
                root = self.listing.get_root()
                focus = root.get_focus() if root is not None else None
                if focus is row or (focus is not None and focus.is_ancestor(row)):
                    self.activate(row)
        return GLib.SOURCE_REMOVE

    def activated(self, _, row):
        # GTK emits native double-click activation on the second button-down.
        # Only released() may authorize pointer activation: a drag can still
        # begin after this signal. Keyboard activation has no pointer record
        # (key_pressed clears it) and remains synchronous, as does accessibility.
        if self.pointer is None:
            self.activate(row)
