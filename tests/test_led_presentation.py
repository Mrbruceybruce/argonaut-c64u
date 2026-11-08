"""Synthetic snapshots only; no hardware, sockets, or configuration operations."""
import copy
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from c64u_browser.configuration import Setting
from c64u_browser.led_presentation import Evidence, present_led, SOURCE_REVISION

STRIP = 'LED Strip Settings'
KEYBOARD = 'Keyboard Lighting'
POWER = 'U64 Specific Settings'
SCOPE = ('synthetic-device', 'qualified-build')
FIRMWARE = Evidence(SOURCE_REVISION, 'synthetic source equivalence', *SCOPE, '2026-11-07')


def snapshot(mode='Fixed Color'):
    result = {}
    for category in (STRIP, KEYBOARD):
        modes = ('Off', 'Fixed Color', 'SID Music', 'Rainbow', 'Rainbow Sparkle')
        if category == STRIP:modes += ('Sparkle',)
        modes += ('Default',)
        patterns = (('SingleColor', 'Left to Right', 'Right to Left', 'Serpentine', 'Outward')
                    if category == STRIP else
                    ('Single Color', 'Left to Right', 'Right to Left', 'Outward', 'Circular'))
        result[category] = [
            Setting('Color tint', 'Pure', '', ('Pure', 'Bright', 'Pastel', 'Whisper')),
            Setting('Fixed Color', 'Royal Blue', '', ('Royal Blue', 'Red')),
            Setting('Strip Intensity', '10', '', value_type=int, minimum=0, maximum=31),
            Setting('LedStrip Pattern', 'Outward', '', patterns),
            Setting('LedStrip Auto SID Mode', 'Enabled', '', ('Disabled', 'Enabled')),
            Setting('LedStrip Mode', mode, '', modes),
            Setting('LedStrip SID Select', 'UltiSID1-A', '', ('UltiSID1-A',)),
            Setting('Future field', 'opaque retained', ''),
        ]
    result[POWER] = [Setting('LED Select Bot', 'Drive B', '', ('Drive B',)),
                     Setting('LED Select Top', 'Power', '', ('Power',)),
                     Setting('C64U Model', 'Founders Edition', '')]
    return result


def qualified(settings, detected=True, **kwargs):
    return present_led(settings, scope=SCOPE, firmware=FIRMWARE,
                       controller=Evidence(detected, 'synthetic detector', *SCOPE), **kwargs)


class LEDPresentationTests(unittest.TestCase):
    def test_qualified_layouts_and_exact_order(self):
        settings = snapshot()
        view = qualified(settings)
        self.assertEqual([g.heading for g in view.groups], [
            'Power LED (if installed)', 'Case Lights', 'REST details — LED Strip Settings',
            'Keyboard Lights', 'REST details — Keyboard Lighting'])
        self.assertEqual([r.label for r in view.groups[0].rows], ['Output 1', 'Output 2'])
        self.assertEqual([r.name for r in view.groups[0].rows], ['LED Select Top', 'LED Select Bot'])
        for group in (view.groups[1], view.groups[3]):
            self.assertEqual([r.label for r in group.rows],
                             ['Mode', 'Music Detect', 'Pattern', 'Brightness', 'Color', 'Tint'])
        beige = qualified(settings, False, installed=(Evidence(False, 'operator: no strip', *SCOPE),))
        self.assertEqual([g.heading for g in beige.groups], ['Power LED', 'LED Strip (if installed)',
                         'REST details — LED Strip Settings', 'REST details — Keyboard Lighting'])
        self.assertEqual(len(beige.groups[-1].rows), 8)
        self.assertTrue(all(r.availability == 'Native availability unknown' for r in beige.groups[-1].rows))

    def test_unknown_hardware_never_infers_layout_from_model_or_advertisement(self):
        for model in ('Founders Edition', 'BASIC Beige', 'Starlight Edition', 'Retrofit', 'Unknown'):
            settings = snapshot()
            settings[POWER][-1] = Setting('C64U Model', model, '')
            view = present_led(settings)
            self.assertEqual(view.layout, 'Native layout unknown')
            self.assertEqual([g.heading for g in view.groups if not g.heading.startswith('REST')],
                             [POWER, STRIP, KEYBOARD])
            self.assertTrue(all(r.availability == 'Native availability unknown' for g in view.groups for r in g.rows))

    def test_missing_stale_conflicting_wrong_scope_or_version_evidence_stays_unknown(self):
        detector = Evidence(True, 'detector', *SCOPE)
        for evidence in (None, replace(FIRMWARE, value='1.1.0'), replace(FIRMWARE, value='1.1.0s2'),
                         replace(FIRMWARE, current=False), replace(FIRMWARE, conflicting=True),
                         replace(FIRMWARE, device='other'), replace(FIRMWARE, build='other'),
                         replace(FIRMWARE, source='')):
            view = present_led(snapshot(), scope=SCOPE, firmware=evidence, controller=detector)
            self.assertEqual(view.layout, 'Native layout unknown')
        for evidence in (None, replace(detector, current=False), replace(detector, conflicting=True),
                         replace(detector, device='other'), replace(detector, value='Founders Edition'),
                         replace(detector, value=1)):
            view = present_led(snapshot(), scope=SCOPE, firmware=FIRMWARE, controller=evidence)
            self.assertEqual(view.layout, 'Native layout unknown')
        self.assertEqual(present_led(snapshot(), firmware=FIRMWARE, controller=detector).layout,
                         'Native layout unknown')

    def test_all_modes_native_status_and_values_retained_without_mutation(self):
        flags = {'Off': (0,0,0,0), 'Default': (0,1,0,0), 'Fixed Color': (0,1,1,1),
                 'SID Music': (1,1,0,0), 'Rainbow': (1,1,0,1),
                 'Rainbow Sparkle': (1,1,0,1), 'Sparkle': (0,1,0,0)}
        for mode, expected in flags.items():
            settings = snapshot(mode)
            before = copy.deepcopy(settings)
            view = qualified(settings)
            for group in (view.groups[1], view.groups[3]):
                if mode == 'Sparkle' and group.heading == 'Keyboard Lights':
                    self.assertTrue(all(r.availability == 'Native availability unknown' for r in group.rows))
                    continue
                self.assertEqual([r.availability == 'Native active' for r in group.rows[2:]], list(map(bool, expected)))
                self.assertEqual([r.value for r in group.rows[2:]], ['Outward', '10', 'Royal Blue', 'Pure'])
                self.assertEqual([r.availability for r in group.rows[:2]], ['Native active'] * 2)
            self.assertEqual(settings, before)

    def test_missing_fields_remain_missing_without_source_defaults(self):
        settings = snapshot()
        settings[STRIP] = [s for s in settings[STRIP] if s.name not in ('LedStrip Mode', 'Fixed Color')]
        del settings[KEYBOARD]
        view = qualified(settings)
        rows = view.groups[1].rows
        self.assertEqual(rows[0].value, 'Not reported')
        self.assertIsNone(rows[0].setting)
        self.assertEqual(rows[4].value, 'Not reported')
        self.assertTrue(all(r.availability == 'Native availability unknown' for r in rows))
        self.assertNotIn('Keyboard Lights', [g.heading for g in view.groups])
        self.assertEqual(present_led({}).groups, ())

    def test_conflicting_metadata_and_unknown_mode_fail_neutral(self):
        for name, updates in (('LedStrip Mode', {'current':'Future'}),
                              ('LedStrip Mode', {'choices':('Fixed Color', 'Future')}),
                              ('LedStrip Pattern', {'choices':('Outward','Circular')}),
                              ('Strip Intensity', {'maximum':255}),
                              ('Strip Intensity', {'current':'Unavailable'}),
                              ('Color tint', {'choices':()}),
                              ('Fixed Color', {'current':'Ultraviolet', 'choices':('Ultraviolet',)})):
            settings = snapshot()
            settings[STRIP] = [replace(s, **updates) if s.name == name else s for s in settings[STRIP]]
            rows = qualified(settings).groups[1].rows
            self.assertTrue(all(r.availability == 'Native availability unknown' for r in rows))

    def test_rest_only_identities_and_evidence_provenance_are_preserved(self):
        settings = snapshot()
        view = qualified(settings, installed=(Evidence(False, 'historical operator', *SCOPE, '2026-11-01', current=False),))
        for group in (view.groups[2],view.groups[4]):
            self.assertEqual([r.name for r in group.rows], ['LedStrip SID Select', 'Future field'])
            self.assertEqual([r.value for r in group.rows], ['UltiSID1-A', 'opaque retained'])
            self.assertTrue(all(r.setting in settings[r.category] for r in group.rows))
        text = '\n'.join(view.provenance)
        for expected in (SOURCE_REVISION, 'synthetic-device', 'qualified-build', '2026-11-01',
                         'current=False', 'historical operator', 'Auto SID', 'exposure only'):
            self.assertIn(expected, text)

    def test_malformed_power_metadata_stays_unknown(self):
        for changes in ({'choices':()}, {'current':'Unavailable'}, {'value_type':int}):
            settings = snapshot()
            settings[POWER][1] = replace(settings[POWER][1], **changes)
            view = qualified(settings)
            self.assertEqual(view.groups[0].rows[0].availability, 'Native availability unknown')
            self.assertEqual(view.groups[0].rows[0].value, settings[POWER][1].current)

    def test_presentation_never_bypasses_whole_batch_led_refusal(self):
        from c64u_browser.api import UltimateClient
        from c64u_browser.configuration_policy import ConfigurationRefused
        client = UltimateClient('192.0.2.20')
        for view in (present_led(snapshot()), qualified(snapshot())):
            for group in view.groups:
                for row in group.rows:
                    if row.category == POWER:continue
                    payload = {row.category:{row.name:row.value}, 'Other':{'Value':'new'}}
                    for entries in (list(payload.items()), list(reversed(list(payload.items())))):
                        with patch.object(client, '_request_json', side_effect=AssertionError('transport')) as request:
                            with self.assertRaises(ConfigurationRefused):
                                client.apply_configuration(dict(entries))
                            request.assert_not_called()


class Widget:
    def __init__(self, **kwargs):
        self.text = kwargs.get('label', '')
        self.children = []
        self.callbacks = []
    def append(self, child):self.children.append(child)
    def set_child(self, child):self.children.append(child)
    def connect(self, event, callback):self.callbacks.append((event,callback))
    def set_text(self, text):self.text=text
    def set_tooltip_text(self, text):pass
    def get_first_child(self):return self.children[0] if self.children else None
    def remove(self, child):self.children.remove(child)


def walk(widget):
    yield widget
    for child in widget.children:yield from walk(child)


class LEDPresentationUITests(unittest.TestCase):
    def test_settings_search_favorites_are_read_only_and_preserve_drafts(self):
        from c64u_browser import settings_tab
        gtk = SimpleNamespace(Label=Widget, Box=Widget, Button=Widget, Expander=Widget)
        tab = settings_tab.SettingsTab.__new__(settings_tab.SettingsTab)
        tab.all_settings = snapshot()
        tab.favorites = {(STRIP, 'Fixed Color')}
        tab.pending = {(STRIP,'Fixed Color'):'Red'}
        tab.drafts = {(STRIP,'Fixed Color'):'Red'}
        tab.errors = {}
        tab.rows = Widget(); tab.heading = Widget(); tab.category = 'LED Lighting'
        tab.app = SimpleNamespace(status=Mock())
        tab.update_edit_buttons = Mock()
        before = copy.deepcopy((tab.all_settings,tab.pending,tab.drafts,tab.errors))
        from c64u_browser.settings_sections import visible_entries
        with patch.object(settings_tab, 'Gtk', gtk):
            for query, favorites in (('',False),('color',False),('',True),('output',False)):
                matches=visible_entries(tab.all_settings,tab.category,query,tab.favorites if favorites else None)
                tab.show_results(matches,query,favorites)
                widgets = list(walk(tab.rows))
                text = '\n'.join(w.text for w in widgets)
                self.assertIn('Native layout unknown', text)
                self.assertIn('Read-only — safety qualification pending', text)
                self.assertTrue(all(event == 'clicked' for w in widgets for event,_ in w.callbacks))
                if query != 'output':self.assertIn('Retained local draft: Red (not applied)', text)
        self.assertEqual((tab.all_settings,tab.pending,tab.drafts,tab.errors),before)

    def test_render_uses_loaded_snapshot_and_stale_gate(self):
        from c64u_browser.settings_tab import SettingsTab
        tab = SettingsTab.__new__(SettingsTab)
        tab.loaded=False;tab.show_results=Mock()
        tab.render();tab.show_results.assert_not_called()
        tab.loaded=True;tab.all_settings=snapshot();tab.category='LED Lighting'
        tab.search=Mock();tab.search.get_text.return_value=''
        tab.favorite_filter=Mock();tab.favorite_filter.get_active.return_value=False
        tab.render();tab.show_results.assert_called_once()
        tab.rows=Mock();tab.update_edit_buttons=Mock()
        tab.pending={(STRIP,'Fixed Color'):'Red'}
        tab.require_fresh_settings()
        tab.rows.set_sensitive.assert_called_once_with(False)
        self.assertEqual(tab.pending,{(STRIP,'Fixed Color'):'Red'})
        tab.show_results.reset_mock();tab.render();tab.show_results.assert_not_called()
