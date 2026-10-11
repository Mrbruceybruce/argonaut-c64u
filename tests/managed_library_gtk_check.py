"""Explicit offline GTK managed-library state and settings checks."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
from c64u_browser.managed_library import LibraryState,parse_manifest
from c64u_browser.managed_library_view import ManagedLibraryView
from c64u_browser.scheduler import DeviceSession
from tests.test_managed_library import manifest,game,PATH
from c0_gtk_input import pump


class ManagedViewGtk(unittest.TestCase):
    def setUp(self):
        self.session=DeviceSession('device','one');self.listeners=[]
        self.core=NS(device_session=lambda:self.session,
            add_listener=lambda callback:(self.listeners.append(callback) or (lambda:self.listeners.remove(callback))),
            configure_game_library=Mock(),load_managed_library=Mock())
        self.app=NS(core=self.core,preferences=NS(game_library_location=None),run_file_job=Mock(),busy=False)
        self.view=ManagedLibraryView(self.app)
        self.window=Gtk.Window();self.app.window=self.window;self.window.set_child(self.view.box);self.window.present();pump()

    def tearDown(self):self.view.close();self.window.destroy();pump()

    def children(self,widget):
        result=[];child=widget.get_first_child()
        while child:result.append(child);child=child.get_next_sibling()
        return result

    def test_no_library_is_not_empty_catalog_and_offers_only_explicit_creation(self):
        self.assertEqual('none',self.view.state.status)
        self.assertIn('No Game Library Configured',self.view.main_message.get_text())
        self.assertEqual([],self.children(self.view.rows))
        labels=[c.get_label() for c in self.children(self.view.box) if isinstance(c,Gtk.Button) and c.get_visible()]
        self.assertEqual(['Go to Settings'],labels)
        self.assertEqual('Discover Libraries',self.view.refresh_button.get_label())
        self.core.load_managed_library.assert_not_called()

    def test_valid_empty_and_nonempty_manifest_only_catalog(self):
        for games in ([],[game()]):
            library=parse_manifest(manifest(games=games),'device',PATH)
            self.app.preferences.game_library_location=library.identity.preference()
            self.view.render(LibraryState('valid','Manifest loaded; content not verified.',(library,),'one'))
            self.assertEqual(len(games),len(self.children(self.view.rows)))
            self.assertIn(PATH,self.view.message.get_text())
            self.assertNotIn('not configured',self.view.message.get_text())

    def test_unavailable_clears_rows_and_does_not_switch(self):
        library=parse_manifest(manifest(games=[game()]),'device',PATH)
        self.view.render(LibraryState('valid','Loaded',(library,),'one'))
        self.view.render(LibraryState('unavailable','Configured library unavailable.'))
        self.assertEqual([],self.children(self.view.rows))
        self.core.load_managed_library.assert_not_called()

    def test_multiple_copied_libraries_need_explicit_choice(self):
        libraries=tuple(parse_manifest(manifest(),'device',path) for path in (PATH,'/USB0/ARGONAUT_LIBRARY'))
        self.view.discover();done=self.app.run_file_job.call_args.args[1]
        done(NS(state='succeeded',result=LibraryState('multiple','Copied UUID; choose location.',libraries,'one')))
        self.assertEqual(2,len(self.children(self.view.choices)))
        self.core.configure_game_library.assert_not_called()
        self.assertEqual('none',self.view.state.status)
        self.view.choices.select_row(self.children(self.view.choices)[1]);self.view.select_available()
        factory,done=self.app.run_file_job.call_args.args
        factory()
        self.core.load_managed_library.assert_called_once_with(selection=libraries[1].identity,expected_session=self.session)
        self.core.configure_game_library.assert_not_called()
        done(NS(state='succeeded',result=LibraryState('valid','Loaded',(libraries[1],),'one')))
        self.core.configure_game_library.assert_called_once_with('/USB0/ARGONAUT_LIBRARY',
            identity=libraries[1].identity,expected_session=self.session)

    def test_stale_completion_and_location_change_are_discarded(self):
        library=parse_manifest(manifest(),'device',PATH)
        self.view.load();done=self.app.run_file_job.call_args.args[1]
        self.session=DeviceSession('device','two')
        done(NS(state='succeeded',result=LibraryState('valid','Loaded',(library,),'one')))
        self.assertNotEqual('valid',self.view.state.status)
        self.view.load();done=self.app.run_file_job.call_args.args[1]
        self.app.preferences.game_library_location=library.identity.preference()
        done(NS(state='succeeded',result=LibraryState('valid','Loaded',(library,),'two')))
        self.assertEqual('unavailable',self.view.state.status)

    def test_connection_event_invalidates_visible_state(self):
        library=parse_manifest(manifest(),'device',PATH)
        self.view.render(LibraryState('valid','Loaded',(library,),'one'))
        self.listeners[0](NS(kind='disconnected'));pump()
        self.assertNotEqual('valid',self.view.state.status)
        self.assertEqual([],self.children(self.view.rows))

    def test_load_uses_foreground_factory_and_cancel_is_explicit(self):
        self.view.load()
        self.core.load_managed_library.assert_not_called()
        self.assertIs(self.core.load_managed_library,self.app.run_file_job.call_args.args[0])
        self.app.run_file_job.call_args.args[1](NS(state='cancelled'))
        self.assertIn('cancelled',self.view.message.get_text())


    def loaded(self,configured=False):
        library=parse_manifest(manifest(games=[game()]),'device',PATH)
        if configured:self.app.preferences.game_library_location=library.identity.preference()
        self.view.render(LibraryState('valid','Loaded',(library,),'one'))
        return library

    def test_forget_loaded_discovered_and_configured_library(self):
        for configured in (False,True):
            library=self.loaded(configured)
            self.assertTrue(self.view.forget_button.get_visible())
            self.assertFalse(self.view.create_button.get_visible())
            self.view.forget()
            text=self.view.forget_confirmation.get_content_area().get_first_child().get_text()
            for value in (PATH,library.identity.library_id,'device','does not delete files'):
                self.assertIn(value,text)
            def clear(path,**kwargs):
                self.assertEqual('',path);self.app.preferences.game_library_location=None
            self.core.configure_game_library.side_effect=clear
            self.view.forget_confirmation.response(Gtk.ResponseType.OK);pump()
            self.core.configure_game_library.assert_called_with('',expected_session=self.session)
            self.assertIsNone(self.app.preferences.game_library_location)
            self.assertEqual('none',self.view.state.status)
            self.assertEqual((),self.view.state.libraries)
            self.assertEqual([],self.children(self.view.rows))
            self.assertEqual([],self.children(self.view.choices))
            self.assertTrue(self.view.create_button.get_visible())
            self.assertFalse(self.view.forget_button.get_visible())
            self.core.load_managed_library.assert_not_called()
            self.app.run_file_job.assert_not_called()

    def test_forget_cancel_preserves_selection(self):
        self.loaded(True);before=self.view.state
        self.view.forget();self.view.forget_confirmation.response(Gtk.ResponseType.CANCEL);pump()
        self.core.configure_game_library.assert_not_called()
        self.assertEqual(before,self.view.state)
        self.assertIsNotNone(self.app.preferences.game_library_location)

    def test_forget_refuses_active_operation_before_and_after_confirmation(self):
        self.loaded(True);self.app.busy=True;self.view.forget()
        self.assertIsNone(self.view.forget_confirmation)
        self.app.busy=False;self.view.forget();self.app.busy=True
        self.view.forget_confirmation.response(Gtk.ResponseType.OK);pump()
        self.core.configure_game_library.assert_not_called()
        self.assertEqual('valid',self.view.state.status)

    def test_forget_stale_connection_or_preference_does_not_clear(self):
        for change in ('disconnect','reconnect','location'):
            self.session=DeviceSession('device','one');self.loaded(True);self.view.forget()
            if change=='location':self.app.preferences.game_library_location['library_id']='changed'
            else:self.session=DeviceSession('','') if change=='disconnect' else DeviceSession('device','two')
            self.view.forget_confirmation.response(Gtk.ResponseType.OK);pump()
            self.core.configure_game_library.assert_not_called()

    def test_forget_connection_event_closes_confirmation(self):
        self.loaded(True);self.view.forget()
        self.listeners[0](NS(kind='disconnected'));pump()
        self.assertIsNone(self.view.forget_confirmation)
        self.core.configure_game_library.assert_not_called()
        self.assertTrue(self.view.forget_button.get_visible())
        self.assertEqual('unavailable',self.view.state.status)

    def test_forget_invalidates_old_load_and_reconnect_does_not_autoload(self):
        self.loaded();self.view.load();done=self.app.run_file_job.call_args.args[1]
        old=self.view.state;self.view.forget()
        self.view.forget_confirmation.response(Gtk.ResponseType.OK);pump()
        done(NS(state='succeeded',result=old))
        self.assertEqual('none',self.view.state.status)
        self.listeners[0](NS(kind='reconnected'));pump()
        self.assertEqual('none',self.view.state.status)
        self.assertTrue(self.view.create_button.get_visible())
        self.assertEqual(1,self.app.run_file_job.call_count)

    def test_forget_save_failure_keeps_view_and_association(self):
        self.loaded(True);before=self.view.state
        self.core.configure_game_library.side_effect=OSError('save failed')
        self.view.forget();self.view.forget_confirmation.response(Gtk.ResponseType.OK);pump()
        self.assertEqual(before,self.view.state)
        self.assertIsNotNone(self.app.preferences.game_library_location)
        self.assertIn('save failed',self.view.message.get_text())


class ManagedSettingsGtk(unittest.TestCase):
    def test_real_settings_and_managed_notebook_preserve_legacy(self):
        from tests.test_preferences_ui import PreferencesUI
        from c64u_browser.app_preferences import show_preferences
        fixture=PreferencesUI();fixture.setUp()
        self.addCleanup(fixture.doCleanups);self.addCleanup(fixture.tearDown)
        app=fixture.app
        self.assertGreaterEqual(app.tabs.page_num(app.managed_library_view.box),0)
        self.assertEqual(-1,app.tabs.page_num(app.game_library_tab.box))
        self.assertIsNotNone(app.game_library_tab.client)
        self.assertIn(app.managed_library_view.forget_button,app.busy_controls)
        from c64u_browser.app_preferences import GAME_LIBRARY_PAGE
        app.managed_library_view.settings_button.emit('clicked');fixture.pump()
        dialog=app.preferences_dialog
        self.assertEqual(GAME_LIBRARY_PAGE,dialog.pages.get_current_page())
        self.assertIs(app.managed_library_view.settings_box,dialog.pages.get_nth_page(GAME_LIBRARY_PAGE))
        self.assertEqual('Game Library',dialog.pages.get_tab_label_text(app.managed_library_view.settings_box))
        general=dialog.pages.get_nth_page(0)
        self.assertFalse(any(isinstance(w,Gtk.Entry) and w.get_placeholder_text()=='/USB0/ARGONAUT_LIBRARY'
                             for w in fixture.walk(general)))
        main_labels=[w.get_label() for w in fixture.walk(app.managed_library_view.box) if isinstance(w,Gtk.Button)]
        self.assertEqual(['Go to Settings'],main_labels)
        library=parse_manifest(manifest(),'device',PATH)
        app.managed_library_view.render(LibraryState('valid','Loaded',(library,),'one'))
        app.managed_library_view.forget()
        prompt=app.managed_library_view.forget_confirmation
        self.assertIs(dialog,prompt.get_transient_for())
        prompt.response(Gtk.ResponseType.CANCEL);fixture.pump()
        dialog.response(Gtk.ResponseType.CLOSE);fixture.pump()
        self.assertIsNone(app.managed_library_view.settings_box.get_parent())
        self.assertIsNone(app.managed_library_view.settings_dialog)
        reopened=app.managed_library_view.open_settings();fixture.pump()
        self.assertIs(app.managed_library_view.settings_box,reopened.pages.get_nth_page(GAME_LIBRARY_PAGE))
        reopened.response(Gtk.ResponseType.CLOSE);fixture.pump()


class SettingsSelectionGtk(unittest.TestCase):
    setUp=ManagedViewGtk.setUp
    tearDown=ManagedViewGtk.tearDown
    children=ManagedViewGtk.children
    loaded=ManagedViewGtk.loaded
    def candidates(self,libraries):
        self.view.discover();factory,done=self.app.run_file_job.call_args.args
        factory();self.core.load_managed_library.assert_called_with(discover=True)
        done(NS(state='succeeded',result=LibraryState('multiple' if len(libraries)>1 else
            'valid' if libraries else 'none','Discovery complete.',tuple(libraries),'one')))

    def test_zero_and_one_discovery_never_adopt(self):
        library=parse_manifest(manifest(),'device',PATH)
        for libraries in ([],[library]):
            self.candidates(libraries)
            self.assertEqual(len(libraries),len(self.children(self.view.choices)))
            self.assertEqual('none',self.view.state.status)
            self.assertIsNone(self.app.preferences.game_library_location)
            self.assertTrue(self.view.create_button.get_visible())
        self.core.configure_game_library.assert_not_called()

    def test_selection_saves_before_render_and_event_keeps_selected_view(self):
        library=parse_manifest(manifest(),'device',PATH);self.candidates([library])
        self.core.active_profile=NS(name='C64 Founders')
        def save(path,identity,expected_session):
            self.assertEqual('none',self.view.state.status)
            self.app.preferences.game_library_location=identity.preference()
            self.listeners[0](NS(kind='library-location-changed'))
        self.core.configure_game_library.side_effect=save
        self.view.choices.select_row(self.choices_first());self.view.select_available()
        done=self.app.run_file_job.call_args.args[1]
        done(NS(state='succeeded',result=LibraryState('valid','Validated.',(library,),'one')));pump()
        self.assertEqual('valid',self.view.state.status)
        for text in ('C64 Founders','/SD',PATH,library.identity.library_id,'Revision 0','0 games','Valid'):
            self.assertIn(text,self.view.main_message.get_text())
        self.assertIn('Selected library',self.choices_first().get_child().get_last_child().get_text())

    def choices_first(self):return self.view.choices.get_first_child()

    def test_selection_validation_and_save_failures_preserve_old_selection(self):
        old=self.loaded(True);new=parse_manifest(manifest(),'device','/USB1/ARGONAUT_LIBRARY')
        self.view.available=(new,);self.view.available_session=self.session;self.view.render_available()
        before=self.view.state
        self.view.select(new.identity,self.session)
        done=self.app.run_file_job.call_args.args[1]
        done(NS(state='succeeded',result=LibraryState('unavailable','UUID changed.')))
        self.core.configure_game_library.assert_not_called();self.assertEqual(before,self.view.state)
        self.view.select(new.identity,self.session)
        self.core.configure_game_library.side_effect=OSError('disk full')
        self.app.run_file_job.call_args.args[1](NS(state='succeeded',result=LibraryState('valid','Loaded',(new,),'one')))
        self.assertEqual(before,self.view.state)
        self.assertEqual(old.identity.preference(),self.app.preferences.game_library_location)
        self.assertIn('not saved',self.view.discovery_message.get_text())

    def test_busy_and_stale_candidate_selection_refused(self):
        library=parse_manifest(manifest(),'device',PATH);self.candidates([library])
        self.app.run_file_job.reset_mock();self.app.busy=True
        self.view.select(library.identity,self.session);self.view.discover();self.view.choose_creation()
        self.app.run_file_job.assert_not_called()
        self.app.busy=False;old=self.session;self.session=DeviceSession('device','two')
        self.view.select(library.identity,old);self.app.run_file_job.assert_not_called()
        self.assertIn('stale',self.view.discovery_message.get_text())

    def test_reconnect_during_selection_validation_does_not_save(self):
        library=parse_manifest(manifest(),'device',PATH);self.candidates([library])
        self.view.select(library.identity,self.session);done=self.app.run_file_job.call_args.args[1]
        self.session=DeviceSession('other','two')
        done(NS(state='succeeded',result=LibraryState('valid','Loaded',(library,),'one')))
        self.core.configure_game_library.assert_not_called();self.assertEqual('none',self.view.state.status)

    def test_unavailable_configured_location_never_switches_to_candidate(self):
        old=self.loaded(True);other=parse_manifest(manifest(),'device','/USB1/ARGONAUT_LIBRARY')
        self.candidates([other])
        # Discovery then loads the saved location independently, including nested paths.
        self.app.run_file_job.call_args.args[1](NS(state='succeeded',result=LibraryState('unavailable','Missing manifest.')))
        self.assertIn('Game Library Unavailable',self.view.main_message.get_text())
        self.assertIn(PATH,self.view.main_message.get_text())
        self.assertIn('Missing manifest',self.view.main_message.get_text())
        self.assertEqual(old.identity.preference(),self.app.preferences.game_library_location)
        self.core.configure_game_library.assert_not_called()

    def test_settings_keyboard_focus_and_native_library_row(self):
        self.window.set_child(self.view.settings_box)
        library=parse_manifest(manifest(),'device',PATH);self.candidates([library]);pump()
        self.assertTrue(self.view.refresh_button.grab_focus())
        self.assertTrue(self.view.settings_box.child_focus(Gtk.DirectionType.TAB_FORWARD))
        self.view.choices.select_row(self.choices_first())
        self.assertTrue(self.view.select_button.get_sensitive())
        self.assertTrue(self.view.select_button.grab_focus())
        self.assertEqual(Gtk.AccessibleRole.LIST_ITEM,self.choices_first().get_accessible_role())
        self.assertIn(library.identity.library_id,self.choices_first().get_child().get_last_child().get_text())
        self.assertEqual(root_icon('SD'),self.choices_first().get_child().get_first_child().get_icon_name())


    def test_settings_actions_and_rows_fit_resized_window(self):
        self.window.set_child(self.view.settings_box)
        library=parse_manifest(manifest(),'device',PATH);self.candidates([library])
        for width in (600,900):
            self.window.set_default_size(width,750);pump(.15)
            self.assertGreater(self.view.settings_box.get_width(),0)
            for button in (self.view.refresh_button,self.view.select_button,self.view.create_button):
                self.assertGreater(button.get_width(),0)
                self.assertLessEqual(button.get_width(),self.view.settings_box.get_width())
            self.assertLessEqual(self.choices_first().get_width(),self.view.settings_box.get_width())



def root_icon(name):
    from c64u_browser.storage import root_presentation
    return root_presentation('/'+name)[1]
