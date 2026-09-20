"""Opt-in real GTK checks: ARGONAUT_UI_TESTS=1 on a disposable display."""
import os,tempfile,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch

@unittest.skipUnless(os.environ.get('ARGONAUT_UI_TESTS')=='1','Opt-in GTK display test')
class PreferencesUI(unittest.TestCase):
    def setUp(self):
        import gi
        gi.require_version('Gtk','4.0')
        from gi.repository import Gtk,Gio,GLib
        from c64u_browser.gui import Browser
        from c64u_browser.profiles import Preferences
        self.Gtk=Gtk;self.GLib=GLib;self.Gio=Gio
        self.env=patch.dict(os.environ,{'ARGONAUT_DEVELOPMENT':'1'});self.env.start()
        self.temp=tempfile.TemporaryDirectory()
        self.app=Browser();self.app.preferences=Preferences(Path(self.temp.name)/'config.json')
        self.app.set_application_id('org.local.Argonaut.Test'+uuid.uuid4().hex)
        self.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);self.app.register(None);self.app.activate()
    def tearDown(self):
        dialog=getattr(self.app,'preferences_dialog',None)
        if dialog:dialog.response(self.Gtk.ResponseType.CANCEL)
        self.app.window.close();self.temp.cleanup();self.env.stop()
    def pump(self):
        for _ in range(20):
            while self.GLib.MainContext.default().pending():self.GLib.MainContext.default().iteration(False)
            time.sleep(.01)
    def walk(self,widget):
        yield widget
        child=widget.get_first_child()
        while child:
            yield from self.walk(child);child=child.get_next_sibling()
    def test_scale_bounds_session_only_and_scroll_without_resize(self):
        tab=self.app.streams_tab
        self.assertTrue(tab.text_return.get_active());self.assertIsInstance(tab.zoom,self.Gtk.Label)
        buttons=[w for w in self.walk(tab.box) if isinstance(w,self.Gtk.Button)]
        plus=next(w for w in buttons if w.get_label()=='+');minus=next(w for w in buttons if w.get_label()=='−')
        self.app.tabs.set_current_page(5);self.pump()
        before=(self.app.window.get_width(),self.app.window.get_height())
        for _ in range(6):plus.emit('clicked')
        self.assertEqual(tab.zoom.get_text(),'300%');self.assertFalse(plus.get_sensitive())
        self.assertEqual(self.app.preferences.app_options['preview_scale'],150)
        self.app.preferences.save()
        from c64u_browser.profiles import Preferences
        self.assertEqual(Preferences(self.app.preferences.path).load().app_options['preview_scale'],150)
        self.pump()
        self.assertEqual(before,(self.app.window.get_width(),self.app.window.get_height()))
        v=tab.preview_scroll.get_vadjustment();self.assertGreater(v.get_upper(),v.get_page_size())
        for _ in range(8):minus.emit('clicked')
        self.assertEqual(tab.zoom.get_text(),'100%');self.assertFalse(minus.get_sensitive())
    def test_preferences_auto_save_undo_close_and_checkbox_extent(self):
        from c64u_browser.app_preferences import show_preferences
        from c64u_browser.profiles import Preferences
        dialog=show_preferences(self.app);self.pump()
        self.assertEqual(dialog.pages.get_n_pages(),3)
        general=dialog.pages.get_nth_page(0)
        checks=[w for w in self.walk(general) if isinstance(w,self.Gtk.CheckButton)]
        for w in checks:
            self.assertEqual(w.get_halign(),self.Gtk.Align.START)
            self.assertLess(w.get_width(),general.get_width()-80)
        labels=[w.get_label() for w in self.walk(dialog)
                if isinstance(w,self.Gtk.Button)]
        self.assertIn('Close',labels);self.assertIn('Undo',labels)
        self.assertIn('Restore defaults…',labels)
        self.assertNotIn('Save preferences',labels)
        hidden=next(w for w in checks
                    if w.get_label()=='Show hidden local files and folders')
        self.assertFalse(hidden.get_active())
        with patch.object(self.app,'refresh_local') as refresh:
            hidden.set_active(True)
            refresh.assert_called_once_with()
        self.assertTrue(Preferences(self.app.preferences.path).load().app_options[
            'show_hidden_local'])
        plus=next(w for w in self.walk(general) if isinstance(w,self.Gtk.Button) and w.get_label()=='+')
        plus.emit('clicked')
        self.assertEqual(self.app.preferences.app_options['preview_scale'],175)
        self.assertEqual(Preferences(self.app.preferences.path).load().app_options['preview_scale'],175)
        undo=next(w for w in self.walk(general) if isinstance(w,self.Gtk.Button) and w.get_label()=='Undo')
        undo.emit('clicked')
        self.assertEqual(self.app.preferences.app_options['preview_scale'],150)
        self.assertEqual(Preferences(self.app.preferences.path).load().app_options['preview_scale'],150)
        plus.emit('clicked')
        restore=next(w for w in self.walk(general)
                     if isinstance(w,self.Gtk.Button) and
                     w.get_label()=='Restore defaults…')
        restore.emit('clicked')
        dialog.restore_prompt.response(self.Gtk.ResponseType.CANCEL)
        self.assertEqual(self.app.preferences.app_options['preview_scale'],175)
        restore.emit('clicked')
        dialog.restore_prompt.response(self.Gtk.ResponseType.OK)
        self.assertEqual(self.app.preferences.app_options['preview_scale'],150)
        plus.emit('clicked');dialog.response(self.Gtk.ResponseType.CLOSE)
        self.assertIsNone(self.app.preferences_dialog)
        self.assertEqual(Preferences(self.app.preferences.path).load().app_options['preview_scale'],175)

    def test_instant_replay_is_an_explicit_saved_opt_in(self):
        from c64u_browser.app_preferences import show_preferences
        from c64u_browser.profiles import Preferences
        dialog=show_preferences(self.app);self.pump()
        general=dialog.pages.get_nth_page(0)
        replay=next(w for w in self.walk(general)
                    if isinstance(w,self.Gtk.CheckButton) and
                    w.get_label()=='Keep a 30-second instant replay while previewing')
        self.assertFalse(replay.get_active())
        self.assertIn('off',self.app.streams_tab.replay_status.get_text())
        replay.set_active(True);self.pump()
        self.assertTrue(Preferences(self.app.preferences.path).load().app_options[
            'replay_enabled'])
        self.assertIn('enabled',self.app.streams_tab.replay_status.get_text())
        dialog.response(self.Gtk.ResponseType.CLOSE)

    def test_preview_feeds_replay_and_normal_recording_together(self):
        import threading
        from unittest.mock import Mock
        tab=self.app.streams_tab
        self.app.preferences.app_options['replay_enabled']=True
        receiver=Mock()
        packed=bytes(384*240//2);samples=[bytes(768)]
        receiver.take.return_value=((240,packed),samples)
        receiver.frames=1;receiver.last_audio=time.monotonic()
        receiver.last_video=time.monotonic();receiver.started=time.monotonic()
        session=Mock(receiver=receiver,stopping=threading.Event(),with_audio=True)
        session.thread.is_alive.return_value=True
        tab.session=session
        recorder=Mock(finishing=False);tab.recorder=recorder
        replay=Mock(height=240,seconds=30,audio=True,retained_seconds=1.0)
        with patch('c64u_browser.replay_buffer.ReplayBuffer',return_value=replay):
            self.assertTrue(tab.tick())
        recorder.feed.assert_called_once()
        replay.feed.assert_called_once()
        self.assertEqual(recorder.feed.call_args.args[1],samples)
        self.assertEqual(replay.feed.call_args.args[1],samples)
        self.assertEqual(recorder.feed.call_args.args[0][0],240)
        self.assertEqual(replay.feed.call_args.args[0],recorder.feed.call_args.args[0])
        tab.recorder=None;tab.replay=None;tab.session=None

    def test_unchanged_missing_legacy_folder_does_not_trap_preferences(self):
        from c64u_browser.app_preferences import show_preferences
        missing=str(Path(self.temp.name)/'removed-screenshot-folder')
        self.app.preferences.screenshot_folder=missing
        self.app.preferences.save()
        dialog=show_preferences(self.app);self.pump()
        dialog.response(self.Gtk.ResponseType.CLOSE);self.pump()
        self.assertIsNone(self.app.preferences_dialog)
        self.assertEqual(self.app.preferences.screenshot_folder,missing)

        dialog=show_preferences(self.app);self.pump()
        general=dialog.pages.get_nth_page(0)
        entry=next(w for w in self.walk(general)
                   if isinstance(w,self.Gtk.Entry) and w.get_text()==missing)
        entry.set_text(str(Path(self.temp.name)/'new-missing-folder'))
        dialog.response(self.Gtk.ResponseType.CLOSE);self.pump()
        self.assertIs(self.app.preferences_dialog,dialog)
        self.assertEqual(dialog.pages.get_current_page(),0)

    def test_invalid_folder_message_is_visibly_marked_as_an_error(self):
        from c64u_browser.app_preferences import show_preferences
        dialog=show_preferences(self.app);self.pump()
        general=dialog.pages.get_nth_page(0)
        entries=[w for w in self.walk(general) if isinstance(w,self.Gtk.Entry)]
        entries[0].set_text(str(Path(self.temp.name)/'does-not-exist'))
        entries[0].emit('activate');self.pump()
        self.assertIn('Choose an existing folder',dialog.general_message.get_text())
        self.assertTrue(dialog.general_message.has_css_class(
            'argonaut-error-message'))

    def test_c64_visible_text_entries_show_uppercase_before_submission(self):
        tab=self.app.streams_tab
        tab.text_input.set_text('print "hello"')
        self.assertEqual(tab.text_input.get_text(),'PRINT "HELLO"')
        dialog=self.app.new_d64()
        _,disk_name,disk_id=self.app.d64_create_entries
        self.assertEqual(disk_id.get_text(),'')
        disk_name.set_text('new disk');disk_id.set_text('a1')
        self.assertEqual((disk_name.get_text(),disk_id.get_text()),
                         ('NEW DISK','A1'))
        dialog.response(self.Gtk.ResponseType.CANCEL)

    def test_local_d64_visible_conflict_is_rejected_before_submission(self):
        conflict=Path(self.temp.name)/'new-disk.d64'
        conflict.write_bytes(b'existing')
        self.app.local=Path(self.temp.name);self.app.refresh_local()
        dialog=self.app.new_d64();self.pump()
        buttons=[w for w in self.walk(dialog) if isinstance(w,self.Gtk.Button)]
        create=next(w for w in buttons if w.get_label()=='Create disk')
        self.assertFalse(create.get_sensitive())
        messages=[w for w in self.walk(dialog)
                  if isinstance(w,self.Gtk.Label) and 'already exists' in w.get_text()]
        self.assertEqual(len(messages),1)
        self.assertTrue(messages[0].has_css_class('argonaut-error-message'))
        entries=[w for w in self.walk(dialog) if isinstance(w,self.Gtk.Entry)]
        entries[0].set_text('another-disk');self.pump()
        self.assertTrue(create.get_sensitive())
        self.assertEqual(messages[0].get_text(),'')
        dialog.response(self.Gtk.ResponseType.CANCEL)

    def test_local_d64_late_conflict_stays_in_dialog_with_clear_feedback(self):
        from c64u_browser.api import BrowserError
        self.app.local=Path(self.temp.name);self.app.refresh_local()
        self.app.run=lambda task,done:done(task())
        with patch('c64u_browser.disk_image_io.create_blank_d64',
                   side_effect=BrowserError(
                       'That filename already exists; choose another name.')):
            dialog=self.app.new_d64()
            dialog.response(self.Gtk.ResponseType.OK);self.pump()
        self.assertIs(self.app.d64_create_prompt,dialog)
        messages=[w for w in self.walk(dialog)
                  if isinstance(w,self.Gtk.Label) and 'already exists' in w.get_text()]
        self.assertEqual(len(messages),1)
        self.assertTrue(messages[0].has_css_class('argonaut-error-message'))
        dialog.response(self.Gtk.ResponseType.CANCEL)

    def test_remote_d64_conflict_stays_in_dialog_with_clear_feedback(self):
        from unittest.mock import Mock
        from c64u_browser.api import BrowserError
        self.app.client=Mock();self.app.remote='/USB2'
        self.app.run=lambda task,done:done(task())
        with patch('c64u_browser.disk_image_io.create_remote_blank_d64',
                   side_effect=BrowserError(
                       'That filename already exists on the C64U; choose another name.')):
            dialog=self.app.new_remote_d64()
            dialog.response(self.Gtk.ResponseType.OK);self.pump()
        self.assertIs(self.app.remote_d64_create_prompt,dialog)
        messages=[w for w in self.walk(dialog)
                  if isinstance(w,self.Gtk.Label) and 'already exists' in w.get_text()]
        self.assertEqual(len(messages),1)
        self.assertTrue(messages[0].has_css_class('argonaut-error-message'))
        dialog.response(self.Gtk.ResponseType.CANCEL)

    def test_remote_d64_visible_conflict_is_rejected_before_submission(self):
        from unittest.mock import Mock
        self.app.client=Mock();self.app.remote='/USB2'
        self.app.populate(self.app.rlist,[('new-disk.d64',False,174848)])
        dialog=self.app.new_remote_d64();self.pump()
        buttons=[w for w in self.walk(dialog) if isinstance(w,self.Gtk.Button)]
        create=next(w for w in buttons if w.get_label()=='Create disk')
        self.assertFalse(create.get_sensitive())
        messages=[w for w in self.walk(dialog)
                  if isinstance(w,self.Gtk.Label) and 'already exists' in w.get_text()]
        self.assertEqual(len(messages),1)
        self.assertTrue(messages[0].has_css_class('argonaut-error-message'))
        entries=[w for w in self.walk(dialog) if isinstance(w,self.Gtk.Entry)]
        entries[0].set_text('another-disk');self.pump()
        self.assertTrue(create.get_sensitive())
        self.assertEqual(messages[0].get_text(),'')
        dialog.response(self.Gtk.ResponseType.CANCEL)
    def test_device_details_follow_profile_and_save_box_model(self):
        from c64u_browser.app_preferences import show_preferences
        from c64u_browser.profiles import Profile,Preferences
        one=Profile.new('First','first.local',case_edition='Existing case')
        two=Profile.new('Second','second.local',case_edition='Second case')
        self.app.preferences.profiles=[one,two];self.app.preferences.selected_id=one.id
        dialog=show_preferences(self.app,1);c=dialog.connections
        labels=[w.get_label() for w in self.walk(c.page)
                if isinstance(w,self.Gtk.Button)]
        self.assertIn('Save device profile',labels)
        self.assertNotIn('Save profile details',labels)
        self.assertEqual(c.fields['case_edition'].get_text(),'Existing case')
        self.assertTrue(c.fields['case_edition'].get_editable());self.assertFalse(c.model.get_editable())
        c.saved.set_active_id(two.id);c.fields['case_edition'].set_text('New box');c.fields['serial_number'].set_text('SN2')
        self.app.run=lambda task,done:done(task())
        c.save()
        loaded=Preferences(self.app.preferences.path).load()
        self.assertEqual(loaded.profiles[0].case_edition,'Existing case')
        self.assertEqual(loaded.profiles[1].case_edition,'New box');self.assertEqual(loaded.profiles[1].serial_number,'SN2')

    def test_close_prompt_keeps_profile_edits_while_general_is_already_saved(self):
        from c64u_browser.app_preferences import show_preferences
        from c64u_browser.profiles import Profile,Preferences
        profile=Profile.new('Test','test.local')
        self.app.preferences.profiles=[profile];self.app.preferences.selected_id=profile.id
        dialog=show_preferences(self.app)
        self.assertEqual([dialog.pages.get_tab_label_text(dialog.pages.get_nth_page(i)) for i in range(3)],['General','Device details','About'])
        general=dialog.pages.get_nth_page(0)
        plus=next(w for w in self.walk(general) if isinstance(w,self.Gtk.Button) and w.get_label()=='+')
        plus.emit('clicked');dialog.connections.fields['case_edition'].set_text('Test box')
        dialog.close();self.pump()
        dialog.unsaved_prompt.response(self.Gtk.ResponseType.CANCEL)
        self.assertIs(self.app.preferences_dialog,dialog)
        self.assertEqual(self.app.preferences.app_options['preview_scale'],175)
        self.app.run=lambda task,done:done(task())
        dialog.response(self.Gtk.ResponseType.CLOSE)
        dialog.unsaved_prompt.response(self.Gtk.ResponseType.OK)
        self.assertIsNone(self.app.preferences_dialog)
        stored=Preferences(self.app.preferences.path).load()
        self.assertEqual(stored.app_options['preview_scale'],175)
        self.assertEqual(stored.profiles[0].case_edition,'Test box')

    def test_enter_sends_text_once_and_respects_busy_guard(self):
        from c64u_browser.api import BrowserError
        from unittest.mock import Mock
        tab=self.app.streams_tab;tab.client=Mock();tab.text_input.set_text('PRINT "HELLO"')
        self.app.tabs.set_current_page(5);self.pump()
        self.app.run=lambda task,done:done(task())
        with patch('c64u_browser.keyboard_input.send_text',return_value=14) as send, \
                patch.object(tab.text_input, 'grab_focus',
                             wraps=tab.text_input.grab_focus) as focus:
            tab.text_input.emit('activate')
            send.assert_called_once_with(tab.client,'PRINT "HELLO"',True)
            self.assertEqual(tab.text_input.get_text(),'')
            focus.assert_called_once_with()
            self.assertEqual(tab.text_status.get_text(),
                             'Sent 14 bytes. Ready for the next line.')
            tab.text_input.set_text('RUN')
            self.app.busy=True;tab.text_input.emit('activate');self.assertEqual(send.call_count,1)
        self.app.busy=False
        with patch('c64u_browser.keyboard_input.send_text',
                   side_effect=BrowserError('Send failed')):
            tab.text_input.emit('activate')
        self.assertEqual(tab.text_input.get_text(),'RUN')
        self.assertEqual(tab.text_status.get_text(),'Send failed')

    def test_test_lab_bridge_setup_state_is_non_secret_and_actionable(self):
        tab=self.app.test_lab_tab
        self.assertIsInstance(tab.box,self.Gtk.ScrolledWindow)
        self.assertIs(tab.content.get_ancestor(self.Gtk.ScrolledWindow),tab.box)
        self.assertEqual(tab.box.get_policy()[1],self.Gtk.PolicyType.ALWAYS)
        self.assertEqual(tab.ai_scroll.get_policy()[1],
                         self.Gtk.PolicyType.ALWAYS)
        self.assertFalse(tab.box.get_overlay_scrolling())
        self.assertFalse(tab.ai_scroll.get_overlay_scrolling())
        self.assertEqual(tab.latest_action.get_text(), 'Action: None yet')
        self.assertIn('No test has run', tab.latest_deterministic.get_text())
        self.assertEqual(tab.latest_ai.get_text(),
                         'AI analysis: Not requested.')
        tab.update_latest(
            'Local AI simulation',
            'PASS — expected simulated failure was detected.',
            'UNAVAILABLE — enter a downloaded model name.')
        self.assertEqual(tab.latest_action.get_text(),
                         'Action: Local AI simulation')
        self.assertIn('PASS', tab.latest_deterministic.get_text())
        self.assertIn('UNAVAILABLE', tab.latest_ai.get_text())
        self.assertTrue(tab.latest_status_path.is_file())
        self.app.tabs.set_current_page(6);self.pump()
        for check in (tab.schedule_check,tab.auto_analyze,tab.unattended_ai):
            self.assertEqual(check.get_halign(),self.Gtk.Align.START)
            self.assertLess(check.get_width(),tab.content.get_width()-80)
        self.assertIn('Setup needed',tab.bridge_status.get_text())
        self.assertNotIn('token',tab.bridge_status.get_text().casefold())
        self.assertEqual(tab.pair_bridge_button.get_label(),
                         'Set up & install C64 AI')
        self.assertFalse(tab.activate_bridge_button.get_sensitive())
        self.assertFalse(tab.probe_bridge_button.get_sensitive())
        self.assertFalse(tab.pair_bridge_button.get_sensitive())
        self.assertTrue(tab.health_status.get_text())
        self.assertNotIn('token', tab.health_status.get_text().casefold())
        self.assertEqual(tab.health_button.get_label(), 'Enable alerts')
        from c64u_browser.c64_ai_bridge_control import HealthMonitorStatus
        tab.show_health_status(HealthMonitorStatus(
            'ready','On · checks every 5 minutes'))
        self.assertEqual(tab.health_button.get_label(),'Stop alerts')
        self.assertTrue(tab.health_button.get_sensitive())
        tab.show_health_status(HealthMonitorStatus(
            'disabled','Off · no alerts are scheduled'))
        self.assertEqual(tab.health_button.get_label(),'Enable alerts')
        self.assertEqual(tab.ai_test_result_button.get_label(),
                         'View latest result')
        self.assertTrue(tab.background_status.get_text())
        self.assertIn(tab.background_button.get_label(),
                      ('Enable checks', 'Stop checks'))

    def test_test_lab_presents_probe_failure_as_expected_fixture(self):
        from c64u_browser.test_lab_probe import run_diagnosis_probe
        tab=self.app.test_lab_tab
        tab.report=run_diagnosis_probe();tab.comparison=None
        tab.probe_mode=True;tab.loaded_from_history=True
        tab.saved_context=('Expected simulated failure. No C64U was contacted '
                           'and this probe was not saved.')
        tab.render()
        self.assertIn('Expected simulation failure',tab.summary.get_text())
        row=tab.checks.get_row_at_index(0)
        self.assertTrue(row.get_child().get_text().startswith(
            '✓  Expected fixture:'))

    def test_stable_developer_mode_is_opt_in_and_builds_test_lab_after_restart(self):
        from c64u_browser.gui import Browser
        from c64u_browser.profiles import Preferences
        from unittest.mock import patch
        prefs = Preferences(Path(self.temp.name) / 'stable/config.json')
        prefs.app_options['developer_mode'] = True
        prefs.save()
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT': '0'}), patch(
                'c64u_browser.gui.Preferences', return_value=prefs):
            stable = Browser()
            stable.set_application_id('org.local.Argonaut.StableTest' + uuid.uuid4().hex)
            stable.set_flags(self.Gio.ApplicationFlags.NON_UNIQUE)
            stable.register(None)
            stable.activate()
            try:
                self.assertTrue(hasattr(stable, 'test_lab_tab'))
                labels = [stable.tabs.get_tab_label_text(
                    stable.tabs.get_nth_page(index))
                    for index in range(stable.tabs.get_n_pages())]
                self.assertIn('Test Lab', labels)
                self.assertIsInstance(stable.test_lab_tab.box,
                                      self.Gtk.ScrolledWindow)
                self.assertEqual(
                    stable.test_lab_tab.box.get_policy()[1],
                    self.Gtk.PolicyType.ALWAYS)
            finally:
                stable.window.close()
