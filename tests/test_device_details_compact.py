"""UI-DD.1 native GTK sections, lifecycle and measured allocations; offline only."""
from unittest.mock import Mock, patch
from types import SimpleNamespace
import unittest
from itertools import product
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from c64u_browser.discovery import Candidate
import test_uc1b_presentation as uc1b


class IndependentSections(unittest.TestCase):
    def setUp(self):
        self.f = uc1b.HardwarePresentation(); self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.d = self.f.d

    def test_eight_states_preserve_data_and_do_not_contact_or_dirty(self):
        d = self.d
        d.fields['http'].set_text('8080');d.fields['ftp'].set_text('2121')
        before = d.snapshot()
        candidate = Candidate('192.0.2.42')
        d.add_candidate(candidate)
        d.subnet.set_text('192.0.2.0/24')
        d.scan_progress.set_fraction(.5)
        d.scan_progress.set_text('Existing scan feedback')
        d.app.core.discover = Mock(side_effect=AssertionError('Automatic discovery'))
        d.app.core.read_model = Mock(side_effect=AssertionError('Automatic read'))
        d.app.core._credential_for = Mock(side_effect=AssertionError('Credential access'))
        for advanced, hardware, discovery in product((False, True), repeat=3):
            d.advanced_expander.set_expanded(advanced)
            d.hardware_expander.set_expanded(hardware)
            d.discovery_expander.set_expanded(discovery)
            self.f.pump()
            self.assertEqual(advanced, d.advanced_expander.get_expanded())
            self.assertEqual((hardware, discovery), (d.hardware_expander.get_expanded(), d.discovery_expander.get_expanded()))
            self.assertEqual(before, d.snapshot())
            self.assertEqual(('8080','2121'),(d.fields['http'].get_text(),d.fields['ftp'].get_text()))
            self.assertEqual('192.0.2.0/24', d.subnet.get_text())
            self.assertEqual(.5, d.scan_progress.get_fraction())
            self.assertEqual('Existing scan feedback', d.scan_progress.get_text())
            self.assertEqual(1, len(d._candidate_rows))
        self.assertEqual([], self.f.futures)
        d.app.core.discover.assert_not_called(); d.app.core.read_model.assert_not_called()
        d.app.core.inspect_profile.assert_not_called(); d.app.core._credential_for.assert_not_called()

    def test_collapse_does_not_cancel_or_restart_inspection(self):
        d = self.d
        d.hardware_expander.set_expanded(True); d.inspect_compatibility()
        d.hardware_expander.set_expanded(False); d.discovery_expander.set_expanded(True)
        self.assertTrue(d._inspection_inflight)
        self.assertEqual(1, len(self.f.futures))
        self.f.finish()
        d.hardware_expander.set_expanded(True)
        self.assertIn('REST interface recognized', d.compatibility_status.get_text())
        self.assertEqual(1, len(self.f.futures))

    def test_discovery_collapse_and_closed_completion(self):
        d = self.d
        work = []
        d.app.run = lambda task, done: work.append((task, done))
        d.app.core.discover = Mock(return_value=((), (), ()))
        d.discovery_expander.set_expanded(True); d.scan(False)
        d.discovery_expander.set_expanded(False); d.discovery_expander.set_expanded(True)
        self.assertEqual(1, len(work)); self.assertTrue(d._scanning)
        d.window.destroy(); self.f.pump()
        before = d.status.get_text()
        task, done = work[0]; done(task())
        self.assertEqual(before, d.status.get_text())
        self.assertTrue(d._closed)
        d.app.core.discover.assert_called_once_with(subnet='')


class SettingsSectionLifecycle(unittest.TestCase):
    def test_keep_editing_and_save_discard_reopen(self):
        import test_preferences_ui
        from c64u_browser.app_preferences import show_preferences
        from c64u_browser.profiles import Profile
        for target in ('socket.socket.connect', 'socket.socket.sendto', 'ftplib.FTP'):
            guard=patch(target, side_effect=AssertionError('Network forbidden'))
            guard.start(); self.addCleanup(guard.stop)
        fixture = test_preferences_ui.PreferencesUI(); fixture.setUp()
        self.addCleanup(fixture.doCleanups); self.addCleanup(fixture.tearDown)
        app = fixture.app
        app.core.discovery_networks = Mock(return_value=())
        app.preferences.profiles=[Profile.new('Selected', '192.0.2.20')]
        app.preferences.selected_id=app.preferences.profiles[0].id
        for response in (Gtk.ResponseType.REJECT, Gtk.ResponseType.OK):
            dialog=show_preferences(app, page=1); fixture.pump()
            d=dialog.connections
            self.assertFalse(d.advanced_expander.get_expanded())
            self.assertFalse(d.hardware_expander.get_expanded())
            self.assertFalse(d.discovery_expander.get_expanded())
            d.discovery_expander.set_expanded(True)
            d.advanced_expander.set_expanded(True)
            d.fields['notes'].set_text('An edit ' + str(response))
            show_preferences(app, page=2); show_preferences(app, page=1)
            self.assertTrue(d.discovery_expander.get_expanded())
            self.assertTrue(d.advanced_expander.get_expanded())
            self.assertFalse(d.hardware_expander.get_expanded())
            dialog.close(); fixture.pump()
            dialog.unsaved_prompt.response(Gtk.ResponseType.CANCEL); fixture.pump()
            self.assertTrue(d.discovery_expander.get_expanded()); self.assertFalse(d._closed)
            self.assertTrue(d.advanced_expander.get_expanded())
            dialog.close(); fixture.pump()
            # Keep production Save semantics, make only worker delivery deterministic.
            app.run=lambda task,done:done(task())
            dialog.unsaved_prompt.response(response); fixture.pump()
            self.assertTrue(d._closed)
            self.assertIsNone(app.preferences_dialog)


class GeometryAndKeyboard(unittest.TestCase):
    def setUp(self):
        import test_preferences_ui
        import test_core
        from c64u_browser.app_preferences import show_preferences
        from c64u_browser.profiles import Profile
        for target in ('socket.socket.connect', 'socket.socket.sendto', 'socket.create_connection', 'ftplib.FTP'):
            guard=patch(target, side_effect=AssertionError('Network forbidden before construction'))
            guard.start(); self.addCleanup(guard.stop)
        self.f = test_preferences_ui.PreferencesUI(); self.f.setUp()
        self.addCleanup(self.f.doCleanups); self.addCleanup(self.f.tearDown)
        self.app = self.f.app
        self.app.core.discovery_networks=Mock(return_value=())
        credentials=test_core.FakeCredentials();credentials.exists=lambda _:False
        self.app.core._credentials=credentials
        profile=Profile.new('Ethernet', '192.0.2.20')
        self.app.preferences.profiles=[profile];self.app.preferences.selected_id=profile.id
        self.dialog=show_preferences(self.app, 1);self.f.pump();self.d=self.dialog.connections
        self.settings=Gtk.Settings.get_default()
        self.font=self.settings.get_property('gtk-font-name')
        self.dark=self.settings.get_property('gtk-application-prefer-dark-theme')
        self.addCleanup(self.restore_settings)
        self.settings.set_property('gtk-font-name','Sans 10')

    def restore_settings(self):
        self.settings.set_property('gtk-font-name',self.font)
        self.settings.set_property('gtk-application-prefer-dark-theme',self.dark)

    def frame(self):
        from gtk_layout_fixture import allocated_frame
        for _ in range(3):allocated_frame(self.dialog,self.d.page)

    def bounds(self, widget):
        ok,rect=widget.compute_bounds(self.d.page)
        self.assertTrue(ok)
        return rect

    def report(self, scenario):
        import json
        d=self.d
        result={'scenario':scenario, 'window':[self.dialog.get_width(),self.dialog.get_height()],
            'viewport':[d.page.get_width(),d.page.get_height()],
            'content':[d.controls.get_width(),d.controls.get_height()],
            'vertical_extent':d.page.get_vadjustment().get_upper(),
            'vertical_page':d.page.get_vadjustment().get_page_size(),
            'device_page_minimum_width':d.page.measure(Gtk.Orientation.HORIZONTAL,-1)[0],
            'test_connect_bottom':round(self.bounds(d.connection_actions).get_y()+self.bounds(d.connection_actions).get_height())}
        print('GEOMETRY '+json.dumps(result),flush=True)
        return result

    def visible_controls(self):
        d=self.d
        widgets=[d.saved,d.password,d.auto,d.remember,d.forget_button,d.retry_credential_button,
                 *(d.fields[k] for k in ('name','host','http','ftp'))]
        for box in (d.profile_actions,d.connection_actions):
            child=box.get_first_child()
            while child is not None:widgets.append(child);child=child.get_next_sibling()
        return [w for w in widgets if w.get_mapped()]

    def assert_horizontal_fit(self, widgets):
        for widget in widgets:
            rect=self.bounds(widget)
            self.assertGreaterEqual(rect.get_x(),-1,type(widget).__name__)
            self.assertLessEqual(rect.get_x()+rect.get_width(),self.d.page.get_width()+1,type(widget).__name__)

    def test_default_controls_fit_viewport(self):
        self.dialog.set_default_size(740,680);self.frame()
        self.assertEqual((740,680),(self.dialog.get_width(),self.dialog.get_height()))
        self.assertFalse(self.d.hardware_expander.get_expanded());self.assertFalse(self.d.discovery_expander.get_expanded())
        self.assert_horizontal_fit(self.visible_controls())
        for widget in self.visible_controls():
            rect=self.bounds(widget)
            self.assertGreaterEqual(rect.get_y(),0)
            self.assertLessEqual(rect.get_y()+rect.get_height(),self.d.page.get_height())
        labels=list(self.d.form_labels.values())
        self.assertEqual(1,self.d.form_labels['name'].get_layout().get_line_count())
        self.assertEqual(1,len({label.get_width() for label in labels}))
        self.assertEqual(1,len({round(self.bounds(label).get_x()) for label in labels}))
        self.assertEqual('Hardware & REST Information',self.d.hardware_expander.get_label())
        self.assertFalse(self.d.advanced_expander.get_expanded())
        self.report('default-740x680-normal')

    def test_narrow_controls_reachable_by_vertical_scroll(self):
        self.dialog.set_default_size(520,480);self.frame()
        self.assertEqual(520,self.dialog.get_width())
        # Existing non-scrolling Game Library page sets the shared dialog's height floor.
        self.assertLessEqual(self.dialog.get_height(),500)
        self.assert_horizontal_fit(self.visible_controls())
        adjustment=self.d.page.get_vadjustment()
        self.assertGreater(adjustment.get_upper(),adjustment.get_page_size())
        for widget in self.visible_controls():
            rect=self.bounds(widget)
            adjustment.set_value(adjustment.get_value()+rect.get_y())
            self.frame()
            rect=self.bounds(widget)
            self.assertGreaterEqual(rect.get_y(),-1)
            self.assertLessEqual(rect.get_y()+rect.get_height(),self.d.page.get_height()+1)
        action=self.dialog.get_widget_for_response(Gtk.ResponseType.CLOSE)
        self.assertTrue(action.get_mapped());self.assertTrue(action.grab_focus())
        adjustment.set_value(0);self.frame();self.report('narrow-520x480-normal')

    def test_enlarged_long_content_light_dark(self):
        d=self.d
        self.settings.set_property('gtk-font-name','Sans 18')
        self.dialog.set_default_size(520,480)
        self.app.preferences.profiles[0].name='Long saved profile '+('abcdefghijklmnop'*15)
        d.reload();d.fields['name'].set_text('Long connection '+('C'*200));d.fields['host'].set_text('a'*60+'.example.test')
        d.credential_status.set_text('Unable to determine saved-password status. Retry credential check before saving this profile.')
        d.retry_credential_button.set_visible(True)
        d.advanced_expander.set_expanded(True);d.hardware_expander.set_expanded(True);d.discovery_expander.set_expanded(True)
        result=uc1b.HardwarePresentation.result()
        from dataclasses import replace
        identity=dict(result.identity);identity.update(product='Product'+('P'*200),firmware_version='Firmware'+('F'*200))
        d.compatibility_status.set_text(d.compact_compatibility(replace(result,identity=tuple(identity.items()))))
        d.subnet_validation.set_text('Discovery feedback '+('N'*200))
        d.add_candidate(Candidate('192.0.2.88',info={'info':{'hostname':'H'*200}}))
        for dark in (False,True):
            self.settings.set_property('gtk-application-prefer-dark-theme',dark);self.frame()
            # Native notebook tabs and the existing Library page impose shared minima at 18pt.
            self.assertLessEqual(self.dialog.get_width(),700)
            self.assertLessEqual(self.dialog.get_height(),760)
            self.assertLessEqual(d.page.measure(Gtk.Orientation.HORIZONTAL,-1)[0],520)
            self.assert_horizontal_fit(self.visible_controls()+list(d.form_labels.values())+[d.inspection_target,d.compatibility_status,d.subnet_validation,d.devices])
            self.assertGreater(d.compatibility_status.get_layout().get_line_count(),8)
            self.report('18pt-long-content-'+('dark' if dark else 'light'))

    def test_tab_reverse_tab_and_collapsed_focus_exclusion(self):
        from c0_gtk_input import Input
        d=self.d;self.frame()
        keyboard=Input(self.dialog);self.addCleanup(keyboard.close)
        self.assertTrue(d.saved.grab_focus())
        visited=[]
        for modifier in (None, 'Shift_L'):
            for _ in range(22):
                keyboard.press('Tab',modifier)
                focus=self.dialog.get_focus()
                if focus is not None:
                    self.assertFalse(focus.is_ancestor(d.ports_row))
                    self.assertFalse(focus.is_ancestor(d.details_page))
                    self.assertFalse(focus.is_ancestor(d.discovery_section))
                    visited.append(focus)
        for widget in (d.password,d.fields['host'],d.auto):
            self.assertTrue(any(f is widget or f.is_ancestor(widget) for f in visited),type(widget).__name__)
        with patch.object(d,'connect') as connect,patch.object(d,'save') as save:
            d.password.grab_focus();keyboard.press('Return')
            connect.assert_called_once();save.assert_not_called()
        self.assertIsNone(self.dialog.get_default_widget())

    def test_expander_keyboard_and_collapse_returns_focus(self):
        d=self.d
        for expander,child,box in ((d.advanced_expander,d.fields['http'],d.ports_row),
                                   (d.hardware_expander,d.inspect_button,d.details_page),
                                   (d.discovery_expander,d.subnet,d.discovery_section)):
            self.assertTrue(expander.grab_focus());self.assertTrue(expander.activate());self.frame()
            self.assertTrue(expander.get_expanded());self.assertTrue(child.grab_focus())
            expander.set_expanded(False);self.frame()
            focus=self.dialog.get_focus()
            self.assertIsNotNone(focus)
            self.assertFalse(focus.is_ancestor(box))
            self.assertTrue(focus.get_mapped())

    def test_focus_after_inspection_discovery_and_closure(self):
        d=self.d
        d.hardware_expander.set_expanded(True);self.frame();d.inspect_button.grab_focus()
        self.app.core.inspect_profile=Mock(return_value=uc1b.HardwarePresentation.result())
        with patch.object(d,'_background',side_effect=lambda task,done:done(task())):d.inspect_compatibility()
        self.assertTrue(d.page.child_focus(Gtk.DirectionType.TAB_FORWARD))
        d.discovery_expander.set_expanded(True);self.frame()
        self.app.core.discover=Mock(return_value=((),(),()))
        self.app.run=lambda task,done:done(task())
        d.scan(False)
        self.assertTrue(d.page.child_focus(Gtk.DirectionType.TAB_BACKWARD))
        self.dialog.close();self.f.pump()
        self.assertTrue(d._closed);self.assertTrue(self.app.window.get_visible())
        self.assertIsNotNone(self.app.window.get_focus())
