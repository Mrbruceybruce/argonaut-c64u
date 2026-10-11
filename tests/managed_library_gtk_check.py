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
        self.app=NS(core=self.core,preferences=NS(game_library_location=None),run_file_job=Mock())
        self.view=ManagedLibraryView(self.app)
        self.window=Gtk.Window();self.window.set_child(self.view.box);self.window.present();pump()

    def tearDown(self):self.view.close();self.window.destroy();pump()

    def children(self,widget):
        result=[];child=widget.get_first_child()
        while child:result.append(child);child=child.get_next_sibling()
        return result

    def test_no_library_is_not_empty_catalog_and_offers_only_explicit_creation(self):
        self.assertEqual('none',self.view.state.status)
        self.assertIn('not configured',self.view.message.get_text())
        self.assertEqual([],self.children(self.view.rows))
        labels=[c.get_label() for c in self.children(self.view.box) if isinstance(c,Gtk.Button)]
        self.assertEqual(['Load managed library','Create Library'],labels)
        self.core.load_managed_library.assert_not_called()

    def test_valid_empty_and_nonempty_manifest_only_catalog(self):
        for games in ([],[game()]):
            library=parse_manifest(manifest(games=games),'device',PATH)
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
        self.view.render(LibraryState('multiple','Copied UUID; choose location.',libraries,'one'))
        self.assertEqual(2,len(self.children(self.view.choices)))
        self.core.configure_game_library.assert_not_called()
        self.children(self.view.choices)[1].emit('clicked')
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
        with patch.object(app.core,'configure_game_library') as save:
            dialog=show_preferences(app);fixture.pump()
            entry=next(w for w in fixture.walk(dialog) if isinstance(w,Gtk.Entry)
                       and w.get_placeholder_text()=='/USB0/ARGONAUT_LIBRARY')
            entry.set_text(PATH)
            save_button=next(w for w in fixture.walk(dialog) if isinstance(w,Gtk.Button)
                             and w.get_label()=='Save location')
            save_button.emit('clicked');save.assert_called_once_with(PATH)
            dialog.response(Gtk.ResponseType.CLOSE);fixture.pump()
