"""Real SettingsTab construction with injected Core transport; never launches Browser."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

if os.environ.get('ARGONAUT_GATE_A_NETNS') != os.readlink('/proc/self/ns/net'):
    raise RuntimeError('Use run_gate_a.py: verified isolation is mandatory')

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from c64u_browser.settings_tab import SettingsTab
from c64u_browser.core import ArgonautCore
from c64u_browser.profiles import Preferences, Profile
from c64u_browser.config_history import history_path
from c64u_browser.settings_sections import display_name, subsection_for
from test_configuration_dependencies import RecordingClient, CATEGORIES, metadata
from test_core import FakeCredentials
from gtk_layout_fixture import allocated_frame


def children(widget):
    child = widget.get_first_child()
    while child:
        yield child
        child = child.get_next_sibling()


def descendants(widget):
    for child in children(widget):
        yield child
        yield from descendants(child)


class MenuFixture:
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='menu-fixture-'); self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.core = ArgonautCore(preferences=Preferences(self.temp / 'prefs.json'),
                                credentials=FakeCredentials(), client_factory=RecordingClient)
        self.addCleanup(self.core.close)
        self.profile = Profile.new('Synthetic', '192.0.2.20', device_id='ABC123')
        self.core.connect(self.profile, initial_browse=False)
        self.client = self.core._client
        for category in ('Ethernet Settings', 'WiFi settings'):
            self.client.metadata[category] = {
                'Use DHCP': {'current': 'Enabled', 'values': ['Disabled', 'Enabled']},
                'Static IP': {'current': '192.0.2.1'}}
        self.ops = self.core.device_operations
        self.history = history_path(self.core.preferences, self.profile, self.ops)
        self.history.parent.mkdir(parents=True); self.history.write_bytes(b'prior-history')
        self.window = Gtk.Window(title='Offline Ultimate Menu fixture')
        self.window.set_default_size(1100, 850)
        self.addCleanup(self.destroy_windows)
        def button(box, label, callback):
            control = Gtk.Button(label=label)
            control.connect('clicked', lambda *_: callback()); box.append(control)
            return control
        self.app = SimpleNamespace(window=self.window, busy=False, status=Gtk.Label(),
                                   preferences=self.core.preferences, active_profile=self.profile,
                                   button=button, run=lambda task, done: done(task()))
        self.tab = SettingsTab(self.app)
        self.window.set_child(self.tab.box)
        self.tab.bind(self.ops); self.tab.reload()
        self.window.present(); self.show_section('LED Lighting')

    def destroy_windows(self):
        for window in list(Gtk.Window.get_toplevels()):
            window.destroy()

    def show_section(self, section):
        row = next(r for r in children(self.tab.categories) if r.category == section)
        self.tab.categories.select_row(row)
        allocated_frame(self.window, self.tab.rows)

    def expander(self, category, name):
        group = None
        for row in children(self.tab.rows):
            if isinstance(row, Gtk.Label):
                group = row.get_text()
            elif group == subsection_for(self.tab.category, category, name):
                for item in children(row):
                    if isinstance(item, Gtk.Expander) and item.get_label().startswith(display_name(category, name) + ' — '):
                        return item
        raise AssertionError(f'Missing rendered row: {category}/{name}')

    def editor(self, category, name):
        expander = self.expander(category, name)
        expander.set_expanded(True)
        allocated_frame(self.window, expander)
        editors = [w for w in descendants(expander.get_child()) if isinstance(w, (Gtk.ComboBoxText, Gtk.Entry))]
        self.assertEqual(len(editors), 1, (category, name))
        return editors[0]

    def choose(self, category, name, value):
        editor = self.editor(category, name)
        self.assertTrue(editor.is_sensitive())
        if isinstance(editor, Gtk.ComboBoxText):
            setting = next(s for s in self.tab.all_settings[category] if s.name == name)
            editor.set_active(setting.choices.index(value))
        else:
            editor.set_text(str(value))
        allocated_frame(self.window, self.tab.rows)

    def no_writes(self):
        self.assertEqual(self.client.writes, [])
        self.assertEqual(self.history.read_bytes(), b'prior-history')

    def reviewed(self):
        dialog = self.tab.apply()
        self.assertIsInstance(dialog, Gtk.Dialog)
        allocated_frame(dialog)
        return dialog
