"""Opt-in real GTK checks: ARGONAUT_UI_TESTS=1 on a disposable display."""
import json,os,tempfile,time,unittest,uuid
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
        appearance=patch('c64u_browser.gui.AppearanceFollower',autospec=True)
        self.appearance_factory=appearance.start();self.addCleanup(appearance.stop)
        self.env=patch.dict(os.environ,{'ARGONAUT_DEVELOPMENT':'1'});self.env.start()
        self.temp=tempfile.TemporaryDirectory()
        from c64u_browser.c64_ai_bridge_control import HealthMonitorStatus
        health=patch('c64u_browser.test_lab_tab.health_monitor_status',
                     return_value=HealthMonitorStatus(
                         'disabled', 'Off · no health alerts are scheduled'))
        health.start();self.addCleanup(health.stop)
        from c64u_browser.core import ArgonautCore
        core=ArgonautCore(preferences=Preferences(Path(self.temp.name)/'config.json'))
        with patch('c64u_browser.gui.ArgonautCore', return_value=core):
            self.app=Browser()
        self.assertIs(self.app.preferences, self.app.core.preferences)
        self.app.set_application_id('org.local.Argonaut.Test'+uuid.uuid4().hex)
        self.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);self.app.register(None);self.app.activate()
    def owned_windows(self):
        def owned(window):
            seen=set()
            while window is not None and window not in seen:
                if window is self.app.window or window.get_application() is self.app:
                    return True
                seen.add(window);window=window.get_transient_for()
            return False
        return [w for w in self.Gtk.Window.list_toplevels() if owned(w)]

    def drain_events(self):
        context=self.GLib.MainContext.default()
        for _ in range(10000):
            if not context.pending():return
            context.iteration(False)
        self.fail('GTK event queue did not become idle during fixture cleanup')

    def tearDown(self):
        try:
            # Normal close may correctly refuse invalid edits or open a prompt.
            # Dispose only this fixture's windows; never enumerate-and-close all.
            self.drain_events()
            owned=self.owned_windows()
            for window in owned:
                if window is not self.app.window:window.destroy()
            self.app.preferences_dialog=None
            self.drain_events()
            self.app.window.close()
            self.drain_events()
            self.assertFalse([w for w in self.owned_windows() if w.get_modal()],
                             'Fixture leaked a modal window')
            self.assertFalse(self.owned_windows(), 'Fixture leaked a window')
        finally:
            self.temp.cleanup();self.env.stop()
    def pump(self):
        for _ in range(20):
            while self.GLib.MainContext.default().pending():self.GLib.MainContext.default().iteration(False)
            time.sleep(.01)
    def pump_for(self, seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            while self.GLib.MainContext.default().pending():
                self.GLib.MainContext.default().iteration(False)
            time.sleep(.01)
    def walk(self,widget):
        yield widget
        child=widget.get_first_child()
        while child:
            yield from self.walk(child);child=child.get_next_sibling()
    @staticmethod
    def type_text(entry,text):
        position=len(entry.get_text())
        entry.insert_text(text,position)
        entry.set_position(position+len(text))
    def test_scale_bounds_session_only_and_scroll_without_resize(self):
        tab=self.app.streams_tab
        self.assertTrue(tab.text_return.get_active());self.assertIsInstance(tab.zoom,self.Gtk.Label)
        buttons=[w for w in self.walk(tab.box) if isinstance(w,self.Gtk.Button)]
        plus=next(w for w in buttons if w.get_label()=='+');minus=next(w for w in buttons if w.get_label()=='−')
        self.app.tabs.set_current_page(self.app.tabs.page_num(self.app.streams_tab.box));self.pump()
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

    def test_game_library_tab_constructs_with_useful_empty_state(self):
        labels=[self.app.tabs.get_tab_label_text(
            self.app.tabs.get_nth_page(index))
            for index in range(self.app.tabs.get_n_pages())]
        self.assertIn('Game Library',labels)
        tab=self.app.game_library_tab
        tab.search.set_text('no-match-'+uuid.uuid4().hex)
        tab.search.emit('activate');self.pump()
        self.assertIn('no games match',tab.library_state.get_text().casefold())
        self.assertFalse(tab.launch_button.get_sensitive())
        self.assertEqual('Select a game to view its details.',
                         tab.detail_heading.get_text())

    def test_game_library_search_debounce_and_immediate_actions(self):
        tab=self.app.game_library_tab
        self.pump()
        with patch.object(tab,'refresh',wraps=tab.refresh) as refresh:
            self.type_text(tab.search,'a');first=tab._search_source
            self.pump_for(.06)
            self.type_text(tab.search,'s');second=tab._search_source
            self.pump_for(.06)
            self.type_text(tab.search,'tro');third=tab._search_source
            self.assertTrue(first and second and third)
            self.assertNotEqual(first,second);self.assertNotEqual(second,third)
            self.assertEqual(0,refresh.call_count)
            self.pump_for(.36)
            self.assertEqual(1,refresh.call_count)

            self.assertEqual('astro',tab.client.query)

            refresh.reset_mock()
            self.type_text(tab.search,'l')
            self.pump_for(.20)
            self.type_text(tab.search,'abe')
            self.pump_for(.18)
            self.assertEqual(0,refresh.call_count)
            self.pump_for(.16)
            self.assertEqual(1,refresh.call_count)
            self.assertEqual('astrolabe',tab.client.query)

            refresh.reset_mock()
            tab.search.set_text('')
            refresh.reset_mock()
            self.type_text(tab.search,'return query')
            tab.search.emit('activate');self.pump()
            self.assertEqual(1,refresh.call_count)
            self.assertEqual('return query',tab.client.query)
            self.pump_for(.20)
            self.assertEqual(1,refresh.call_count)

            refresh.reset_mock()
            tab.search.set_text('')
            refresh.reset_mock()
            self.type_text(tab.search,'pending clear')
            tab.search.set_text('');self.pump()
            self.assertEqual(1,refresh.call_count)
            self.assertEqual('',tab.client.query)
            self.pump_for(.20)
            self.assertEqual(1,refresh.call_count)

            refresh.reset_mock()
            self.type_text(tab.search,'favorite query')
            tab.favorites.set_active(True);self.pump()
            self.assertEqual(1,refresh.call_count)
            self.assertEqual('favorite query',tab.client.query)
            self.assertTrue(tab.client.favorites_only)
            self.pump_for(.20)
            self.assertEqual(1,refresh.call_count)

    def test_slow_core_verification_keeps_gtk_heartbeat_responsive(self):
        from threading import Event
        from c64u_browser.jobs import CoreJob,JobProgress
        from c64u_browser.scheduler import CoreScheduler,JobBinding
        entered=Event();admitted=Event();release=Event();finished=[];ticks=[]
        scheduler=CoreScheduler(lambda:None);self.addCleanup(scheduler.close)
        def verify(job):
            entered.set()
            if not admitted.wait(5):raise AssertionError('Presentation was not admitted')
            job.report(JobProgress(
                'storage-fingerprint',4,None,'directories','ignored',
                (('entries_observed',40),)))
            if not release.wait(5):raise AssertionError('GTK did not release the worker')
            job.check_cancel();return 'verified'
        submit=lambda:scheduler.submit(CoreJob('game-library.launch-preview',verify),
                             JobBinding.core_host())
        loop=self.GLib.MainLoop();condition=[lambda:False]
        def beat():
            ticks.append(time.monotonic())
            if condition[0]():loop.quit()
            return True
        heartbeat=self.GLib.timeout_add(20,beat)
        def until(predicate):
            # Observe events, not how many fit into a short rendering-dependent
            # sampling window. The deadline only detects a blocked GTK loop.
            if predicate():return
            condition[0]=predicate;expired=[]
            def timeout():expired.append(True);loop.quit();return False
            deadline=self.GLib.timeout_add(3000,timeout)
            try:loop.run()
            finally:
                if not expired:self.GLib.source_remove(deadline)
                condition[0]=lambda:False
            self.assertFalse(expired,'GTK event delivery deadline expired')
            self.assertTrue(predicate())
        try:
            self.app.run_file_job(submit,finished.append)
            admitted.set()
            self.assertTrue(entered.wait(1))
            until(lambda:len(ticks)>=5 and
                  'directories checked' in self.app.status.get_text())
            self.assertTrue(self.app.busy)
            self.assertFalse(finished)
            release.set();until(lambda:bool(finished))
            self.assertFalse(self.app.busy)
        finally:
            admitted.set();release.set();self.GLib.source_remove(heartbeat)

    def test_game_library_search_debounce_rejects_stale_client_and_teardown(self):
        from unittest.mock import Mock
        tab=self.app.game_library_tab;original=tab.client
        self.pump()
        with patch.object(tab,'refresh',wraps=tab.refresh) as refresh:
            self.type_text(tab.search,'old client query')
            replacement=Mock();replacement.query='replacement query'
            tab.client=replacement
            self.pump_for(.36)
            self.assertEqual('replacement query',replacement.query)
            self.assertEqual(0,refresh.call_count)
            tab.client=original

            self.type_text(tab.search,' teardown query')
            self.assertIsNotNone(tab._search_source)
            tab.close()
            self.assertIsNone(tab._search_source)
            self.pump_for(.36)
            self.assertEqual(0,refresh.call_count)

    def test_sid_jukebox_tab_constructs_with_empty_state_and_manual_duration(self):
        labels=[self.app.tabs.get_tab_label_text(
            self.app.tabs.get_nth_page(index))
            for index in range(self.app.tabs.get_n_pages())]
        self.assertIn('SID Jukebox',labels);self.assertNotIn('SID/Media',labels)
        tab=self.app.sid_jukebox_tab
        tab.search.set_text('no-match-'+uuid.uuid4().hex);self.pump()
        self.assertIn('no sid tunes match',tab.library_state.get_text().casefold())
        self.assertEqual('Duration: Unknown',tab.duration.get_text())
        self.assertFalse(tab.play_button.get_sensitive())

    def test_sid_jukebox_two_column_hierarchy_keeps_player_visible(self):
        tab=self.app.sid_jukebox_tab
        page=next(index for index in range(self.app.tabs.get_n_pages())
            if self.app.tabs.get_tab_label_text(self.app.tabs.get_nth_page(index))
            =='SID Jukebox')
        self.app.tabs.set_current_page(page);self.pump()
        right=tab.playlist_section.get_parent();children=[];child=right.get_first_child()
        while child:children.append(child);child=child.get_next_sibling()
        self.assertLess(children.index(tab.playlist_section),
                        children.index(tab.now_playing_section))
        self.assertIs(tab.transport_row.get_parent(),tab.playlist_section)
        self.assertTrue(tab.library_scroll.get_vexpand())
        self.assertTrue(tab.playlist_scroll.get_vexpand())
        self.assertIsInstance(tab.library_scroll,self.Gtk.ScrolledWindow)
        self.assertIsInstance(tab.playlist_scroll,self.Gtk.ScrolledWindow)
        self.assertIs(tab.library_summary.get_parent(),tab.library_column)
        self.assertTrue(tab.transport_row.get_mapped())
        self.assertTrue(tab.now_playing_section.get_mapped())
        self.assertGreater(tab.transport_row.get_height(),0)
        self.assertGreater(tab.now_playing_section.get_height(),0)
        button_labels={widget.get_label() for widget in self.walk(tab.box)
            if isinstance(widget,self.Gtk.Button)}
        self.assertNotIn('Play now…',button_labels)
        self.assertIn('Add to active playlist',button_labels)
        self.assertIn('Details…',button_labels)

    def test_sid_playback_preparation_has_immediate_feedback_and_cancel(self):
        from unittest.mock import Mock,patch
        tab=self.app.sid_jukebox_tab;job=Mock()
        with patch.object(tab.client,'can_play_playlist',return_value=True), \
             patch.object(tab.client,'prepare_playlist_play',return_value=job), \
             patch.object(tab,'_run_job',side_effect=lambda submit,done,**kwargs:submit()) as run:
            tab.play()
        run.assert_called_once()
        self.assertTrue(callable(run.call_args.args[0]))
        self.assertEqual(tab._play_prepared,run.call_args.args[1])
        self.assertEqual('Preparing SID playback…',tab.message.get_text())
        self.assertEqual('Preparing SID playback…',self.app.status.get_text())

    def test_sid_playlist_create_select_add_refresh_and_action_sensitivity(self):
        from unittest.mock import Mock
        from c64u_browser.sid_jukebox import SidCatalogService,SidSource
        from c64u_browser.sid_jukebox_client import SidJukeboxClient
        from tests.test_sid_format import sid_bytes
        store=Path(self.temp.name)/'sid-playlist-ui.json'
        service=SidCatalogService(store).load();self.addCleanup(service.close)
        first=Path(self.temp.name)/'astrolabe.sid'
        second=Path(self.temp.name)/'second.sid'
        first.write_bytes(sid_bytes(title='Astrolabe (Mono)',songs=3,start=1))
        second.write_bytes(sid_bytes(title='Second Tune',songs=2,start=1))
        first_tune=service.add(SidSource.core_host(first)).wait(5).result.tune
        second_tune=service.add(SidSource.core_host(second)).wait(5).result.tune
        playback=Mock();playback.current_playback.return_value=Mock(
            playlist_authorized=False,shuffle=False)
        tab=self.app.sid_jukebox_tab
        tab.client=SidJukeboxClient(service,playback);tab.refresh(False)
        tab.refresh_playlists();self.pump()
        self.assertFalse(tab.add_item_button.get_sensitive())

        tab._show('Playback cancelled before sending a command.')
        dialog=tab.new_playlist()
        entry=next(w for w in self.walk(dialog) if isinstance(w,self.Gtk.Entry))
        entry.set_text('Acceptance Test');dialog.response(self.Gtk.ResponseType.OK)
        self.pump()
        playlist=service.list_playlists()[0]
        self.assertEqual(playlist.id,tab.playlist_choice.get_active_id())
        self.assertEqual(playlist.id,tab.client.playlist_id)
        self.assertEqual('Playlist created.',tab.message.get_text())

        tab.list.select_row(tab.rows[first_tune.id]);self.pump()
        self.assertTrue(tab.add_item_button.get_sensitive())
        tab.subtune.set_value(2);self.pump()
        self.assertTrue(tab.add_item_button.get_sensitive())
        tab.add_item_button.emit('clicked');self.pump()
        self.assertEqual(1,len(service.get_playlist(playlist.id).items))
        self.assertEqual(1,len(tab.playlist_rows))
        self.assertTrue(tab.remove_item_button.get_sensitive())
        self.assertFalse(tab.up_button.get_sensitive())
        self.assertFalse(tab.down_button.get_sensitive())

        tab.list.unselect_all();tab.list.select_row(tab.rows[second_tune.id]);self.pump()
        self.assertTrue(tab.add_item_button.get_sensitive())
        tab.subtune.set_value(2);tab.add_item_button.emit('clicked');self.pump()
        self.assertEqual(2,len(service.get_playlist(playlist.id).items))
        self.assertIn(tab.client.playlist_item_id,tab.playlist_rows)
        self.assertTrue(tab.remove_item_button.get_sensitive())
        self.assertTrue(tab.up_button.get_sensitive())
        self.assertFalse(tab.down_button.get_sensitive())

        other=service.create_playlist('Other')
        tab.refresh_playlists();tab.playlist_choice.set_active_id(other.id);self.pump()
        self.assertEqual(other.id,tab.client.playlist_id)
        self.assertEqual(0,len(tab.playlist_rows))
        self.assertTrue(tab.add_item_button.get_sensitive())
        self.assertFalse(tab.remove_item_button.get_sensitive())
        tab.playlist_choice.set_active(-1);self.pump()
        self.assertIsNone(tab.client.playlist_id)
        self.assertTrue(tab.add_item_button.get_sensitive())

        tab.client.playlist_id=playlist.id;tab.refresh_playlists();self.pump()
        self.assertEqual(playlist.id,tab.playlist_choice.get_active_id())
        self.assertEqual(2,len(tab.playlist_rows))
        reloaded=SidCatalogService(store).load();self.addCleanup(reloaded.close)
        self.assertEqual(2,len(reloaded.get_playlist(playlist.id).items))

    def test_sid_library_add_defaults_multiselect_and_double_click_never_play(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from c64u_browser.sid_jukebox import SidCatalogService,SidSource
        from c64u_browser.sid_jukebox_client import SidJukeboxClient
        from tests.test_sid_format import sid_bytes
        service=SidCatalogService(Path(self.temp.name)/'sid-add-ui.json').load()
        self.addCleanup(service.close)
        first_path=Path(self.temp.name)/'first.sid';second_path=Path(self.temp.name)/'second.sid'
        first_path.write_bytes(sid_bytes(title='First',author='Zulu',songs=3,start=1))
        second_path.write_bytes(sid_bytes(title='Second',author='Able',songs=2,start=1))
        first=service.add(SidSource.core_host(first_path)).wait(5).result.tune
        second=service.add(SidSource.core_host(second_path)).wait(5).result.tune
        playback=Mock();playback.current_playback.return_value=SimpleNamespace(
            tune_id='',selected_subtune=None,playlist_authorized=False,
            playlist_id='',playlist_item_id='',shuffle=False)
        tab=self.app.sid_jukebox_tab;tab.client=SidJukeboxClient(service,playback)
        tab.refresh(False);tab.refresh_playlists();self.pump()

        tab.list.select_row(tab.rows[first.id]);tab.subtune.set_value(2);self.pump()
        tab.list.emit('row-activated',tab.rows[first.id]);self.pump()
        playlist=service.list_playlists()[0]
        self.assertEqual('Playlist 1',playlist.title)
        self.assertEqual((first.id,2),(playlist.items[0].tune_id,playlist.items[0].subtune))
        playback.prepare_play.assert_not_called()
        tab.subtune.set_value(3);self.pump()
        self.assertEqual(2,service.get_playlist(playlist.id).items[0].subtune)

        tab.list.unselect_all();tab.list.select_row(tab.rows[first.id])
        tab.list.select_row(tab.rows[second.id]);self.pump()
        self.assertEqual(2,len(tab.list.get_selected_rows()))
        tab.add_item_button.emit('clicked');self.pump()
        items=service.get_playlist(playlist.id).items
        self.assertEqual(3,len(items))
        self.assertEqual(((first.id,1),(second.id,1)),
                         tuple((item.tune_id,item.subtune) for item in items[1:]))
        playback.prepare_play.assert_not_called()
        tab.sort_choice.set_active_id('author');self.pump()
        first_visible=tab.list.get_row_at_index(0)
        self.assertEqual(second.id,first_visible.tune_id)

    def test_sid_library_playlist_and_now_playing_remain_distinct(self):
        from types import SimpleNamespace
        from unittest.mock import Mock,patch
        from c64u_browser.sid_jukebox import SidCatalogService,SidSource
        from c64u_browser.sid_jukebox_client import SidJukeboxClient
        from tests.test_sid_format import sid_bytes
        service=SidCatalogService(Path(self.temp.name)/'sid-state-ui.json').load()
        self.addCleanup(service.close)
        first_path=Path(self.temp.name)/'first.sid';second_path=Path(self.temp.name)/'second.sid'
        first_path.write_bytes(sid_bytes(title='Playlist Target',songs=3,start=1))
        second_path.write_bytes(sid_bytes(title='Library Browse',songs=2,start=1))
        first=service.add(SidSource.core_host(first_path)).wait(5).result.tune
        second=service.add(SidSource.core_host(second_path)).wait(5).result.tune
        playlist=service.create_playlist('Authoritative queue')
        first_item=service.add_playlist_item(playlist.id,first.id,2)
        second_item=service.add_playlist_item(playlist.id,second.id,1)
        idle=SimpleNamespace(tune_id='',selected_subtune=None,playlist_authorized=False,
            playlist_id='',playlist_item_id='',shuffle=False)
        playback=Mock();playback.current_playback.return_value=idle
        playback.prepare_play.return_value=Mock()
        tab=self.app.sid_jukebox_tab;tab.client=SidJukeboxClient(service,playback)
        tab.connected=True;tab.client.playlist_id=playlist.id
        tab.refresh(False);tab.refresh_playlists();tab._sync_playback_state();self.pump()
        initial=tab.now_playing_heading.get_text()
        self.assertIn('No SID command',initial)

        tab.list.select_row(tab.rows[second.id]);self.pump()
        tab.subtune.set_value(1);self.pump()
        self.assertEqual(2,service.get_playlist(playlist.id).items[0].subtune)
        self.assertEqual(initial,tab.now_playing_heading.get_text())
        tab.playlist_list.select_row(tab.playlist_rows[first_item.id]);self.pump()
        self.assertEqual(second.id,tab.client.selected_id)
        self.assertEqual(initial,tab.now_playing_heading.get_text())

        with patch.object(tab,'_run_job',side_effect=lambda submit,done,**kwargs:submit()) as run:
            tab.play()
        run.assert_called_once()
        args=playback.prepare_play.call_args.args
        self.assertEqual((first.id,2,playlist.id,first_item.id),
            (args[0],args[1],args[2].playlist_id,args[2].item_id))

        accepted=SimpleNamespace(tune_id=first.id,selected_subtune=2,
            playlist_authorized=True,playlist_id=playlist.id,
            playlist_item_id=first_item.id,shuffle=False)
        playback.current_playback.return_value=accepted
        tab._sync_playback_state();self.pump()
        self.assertIn('Playlist Target · Subtune 2',tab.now_playing_heading.get_text())
        self.assertTrue(tab.playlist_rows[first_item.id].playing)
        self.assertTrue(tab.playlist_rows[first_item.id].get_child().get_text().startswith('▶'))
        now_playing=tab.now_playing_heading.get_text()
        tab.list.select_row(tab.rows[second.id]);self.pump()
        tab.playlist_list.select_row(tab.playlist_rows[second_item.id]);self.pump()
        self.assertEqual(now_playing,tab.now_playing_heading.get_text())
        self.assertTrue(tab.playlist_rows[first_item.id].playing)
        self.assertFalse(tab.playlist_rows[second_item.id].playing)

    def test_sid_playlist_multiselect_move_keyboard_remove_and_persistence(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from gi.repository import Gdk
        from c64u_browser.sid_jukebox import SidCatalogService,SidSource
        from c64u_browser.sid_jukebox_client import SidJukeboxClient
        from tests.test_sid_format import sid_bytes
        store=Path(self.temp.name)/'sid-edit-ui.json'
        service=SidCatalogService(store).load();self.addCleanup(service.close)
        tunes=[]
        for index,title in enumerate(('Alpha','Bravo','Charlie','Delta','Echo')):
            path=Path(self.temp.name)/f'{index}.sid';path.write_bytes(sid_bytes(title=title))
            tunes.append(service.add(SidSource.core_host(path)).wait(5).result.tune)
        playlist=service.create_playlist('Editable')
        items=tuple(service.add_playlist_item(playlist.id,tune.id,1) for tune in tunes)
        playback=Mock();playback.current_playback.return_value=SimpleNamespace(
            tune_id='',selected_subtune=None,playlist_authorized=False,
            playlist_id='',playlist_item_id='',shuffle=False)
        tab=self.app.sid_jukebox_tab;tab.client=SidJukeboxClient(service,playback)
        tab.client.playlist_id=playlist.id;tab.refresh(False);tab.refresh_playlists();self.pump()

        tab.playlist_list.select_row(tab.playlist_rows[items[1].id])
        tab.playlist_list.select_row(tab.playlist_rows[items[3].id]);self.pump()
        self.assertEqual((items[1].id,items[3].id),tab._selected_playlist_ids())
        tab._open_playlist_context_menu(tab.playlist_rows[items[3].id]);self.pump()
        menu_labels={widget.get_label() for widget in self.walk(tab.playlist_menu)
                     if isinstance(widget,self.Gtk.Button)}
        self.assertIn('Remove selected',menu_labels)
        self.assertIn('Move to top',menu_labels)
        tab.playlist_menu.popdown();self.pump()
        tab.move_playlist_items(-1);self.pump()
        self.assertEqual((items[1].id,items[0].id,items[3].id,items[2].id,items[4].id),
            tuple(item.id for item in service.get_playlist(playlist.id).items))
        self.assertEqual((items[1].id,items[3].id),tab._selected_playlist_ids())

        self.assertTrue(tab._playlist_key_pressed(
            None,Gdk.KEY_a,0,Gdk.ModifierType.CONTROL_MASK));self.pump()
        self.assertEqual(5,len(tab.playlist_list.get_selected_rows()))
        self.assertTrue(tab._playlist_key_pressed(None,Gdk.KEY_BackSpace,0,0));self.pump()
        self.assertEqual((),service.get_playlist(playlist.id).items)
        self.assertFalse(tab.remove_item_button.get_sensitive())
        reopened=SidCatalogService(store).load();self.addCleanup(reopened.close)
        self.assertEqual((),reopened.get_playlist(playlist.id).items)

    def test_sid_multiselection_does_not_replace_core_cursor_across_shuffle(self):
        from types import SimpleNamespace
        from unittest.mock import Mock,patch
        from c64u_browser.sid_jukebox import SidCatalogService,SidSource
        from c64u_browser.sid_jukebox_client import SidJukeboxClient
        from tests.test_sid_format import sid_bytes
        service=SidCatalogService(Path(self.temp.name)/'sid-shuffle-ui.json').load()
        self.addCleanup(service.close)
        tunes=[]
        for index in range(4):
            path=Path(self.temp.name)/f'shuffle-{index}.sid'
            path.write_bytes(sid_bytes(title=f'Shuffle {index}'))
            tunes.append(service.add(SidSource.core_host(path)).wait(5).result.tune)
        playlist=service.create_playlist('Shuffle sequence')
        items=tuple(service.add_playlist_item(playlist.id,tune.id,1) for tune in tunes)
        playback=Mock()
        state=[SimpleNamespace(tune_id=tunes[0].id,selected_subtune=1,
            playlist_authorized=True,playlist_id=playlist.id,
            playlist_item_id=items[0].id,shuffle=True)]
        playback.current_playback.side_effect=lambda:state[0]
        playback.set_shuffle.side_effect=lambda enabled:SimpleNamespace(shuffle=enabled)
        playback.next.return_value=Mock()
        tab=self.app.sid_jukebox_tab;tab.client=SidJukeboxClient(service,playback)
        tab.connected=True;tab.client.playlist_id=playlist.id
        tab.refresh(False);tab.refresh_playlists();tab._sync_playback_state();self.pump()

        tab.playlist_list.unselect_all()
        tab.playlist_list.select_row(tab.playlist_rows[items[1].id])
        tab.playlist_list.select_row(tab.playlist_rows[items[2].id]);self.pump()
        editing=(items[1].id,items[2].id)
        self.assertEqual(editing,tab._selected_playlist_ids())
        self.assertTrue(tab.playlist_rows[items[0].id].playing)

        tab.shuffle.set_active(False);self.pump()
        playback.set_shuffle.assert_called_with(False)
        self.assertEqual(editing,tab._selected_playlist_ids())
        with patch.object(tab,'_run_job',side_effect=lambda submit,done,**kwargs:submit()) as run:
            tab.next()
        playback.next.assert_called_once_with();run.assert_called_once()

        state[0]=SimpleNamespace(tune_id=tunes[1].id,selected_subtune=1,
            playlist_authorized=True,playlist_id=playlist.id,
            playlist_item_id=items[1].id,shuffle=False)
        tab._sync_playback_state();self.pump()
        self.assertEqual(editing,tab._selected_playlist_ids())
        self.assertFalse(tab.playlist_rows[items[0].id].playing)
        self.assertTrue(tab.playlist_rows[items[1].id].playing)

    def test_sid_playlist_drag_reorder_and_library_drop_preserve_visible_order(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from c64u_browser.sid_jukebox import SidCatalogService,SidSource
        from c64u_browser.sid_jukebox_client import SidJukeboxClient
        from tests.test_sid_format import sid_bytes
        service=SidCatalogService(Path(self.temp.name)/'sid-drag-ui.json').load()
        self.addCleanup(service.close)
        specs=(('Zulu','Zulu',3,2),('Able','Able',2,1),('Mike','Mike',1,1),
               ('Delta','Delta',1,1))
        tunes=[]
        for index,(title,author,songs,start) in enumerate(specs):
            path=Path(self.temp.name)/f'drag-{index}.sid'
            path.write_bytes(sid_bytes(title=title,author=author,songs=songs,start=start))
            tunes.append(service.add(SidSource.core_host(path)).wait(5).result.tune)
        playlist=service.create_playlist('Drag target')
        items=tuple(service.add_playlist_item(playlist.id,tune.id,1) for tune in tunes)
        playback=Mock();playback.current_playback.return_value=SimpleNamespace(
            tune_id='',selected_subtune=None,playlist_authorized=False,
            playlist_id='',playlist_item_id='',shuffle=False)
        tab=self.app.sid_jukebox_tab;tab.client=SidJukeboxClient(service,playback)
        tab.client.playlist_id=playlist.id;tab.refresh(False);tab.refresh_playlists();self.pump()

        tab.playlist_list.select_row(tab.playlist_rows[items[1].id])
        tab.playlist_list.select_row(tab.playlist_rows[items[3].id]);self.pump()
        payload=json.dumps({'token':tab.drag_token,'kind':'playlist',
                            'ids':[items[1].id,items[3].id]})
        self.assertTrue(tab._playlist_drop(None,payload,0,100000));self.pump()
        self.assertEqual((items[0].id,items[2].id,items[1].id,items[3].id),
            tuple(item.id for item in service.get_playlist(playlist.id).items))

        tab.sort_choice.set_active_id('author');self.pump()
        visible=tuple(tab.list.get_row_at_index(index).tune_id for index in range(4))
        self.assertEqual((tunes[1].id,tunes[3].id,tunes[2].id,tunes[0].id),visible)
        tab.list.unselect_all();tab.list.select_row(tab.rows[tunes[0].id])
        tab.list.select_row(tab.rows[tunes[1].id]);self.pump()
        self.assertIsNotNone(tab._drag_content(
            'library',(tunes[0].id,tunes[1].id)))
        payload=json.dumps({'token':tab.drag_token,'kind':'library',
                            'ids':[tunes[0].id,tunes[1].id]})
        self.assertTrue(tab._playlist_drop(None,payload,0,100000));self.pump()
        appended=service.get_playlist(playlist.id).items[-2:]
        self.assertEqual(((tunes[1].id,1),(tunes[0].id,2)),
                         tuple((item.tune_id,item.subtune) for item in appended))

        tab.list.unselect_all();tab.list.select_row(tab.rows[tunes[0].id])
        tab.subtune.set_value(3);self.pump()
        payload=json.dumps({'token':tab.drag_token,'kind':'library','ids':[tunes[0].id]})
        self.assertTrue(tab._playlist_drop(None,payload,0,100000));self.pump()
        self.assertEqual((tunes[0].id,3),(
            service.get_playlist(playlist.id).items[-1].tune_id,
            service.get_playlist(playlist.id).items[-1].subtune))

    def test_game_launch_preparation_has_immediate_visible_feedback(self):
        from unittest.mock import Mock,patch
        tab=self.app.game_library_tab
        job=Mock()
        with patch.object(tab.client,'can_launch',return_value=True), \
             patch.object(tab.client,'prepare_launch',return_value=job), \
             patch.object(tab,'_run_job',side_effect=lambda submit,done,**kwargs:submit()) as run:
            tab.launch()
        run.assert_called_once()
        self.assertTrue(callable(run.call_args.args[0]))
        self.assertEqual(tab._launch_prepared,run.call_args.args[1])
        self.assertEqual('Preparing launch preview…',tab.message.get_text())
        self.assertEqual('Preparing launch preview…',self.app.status.get_text())

    def test_game_library_batch_add_reports_duplicate_core_result(self):
        from unittest.mock import Mock
        from c64u_browser.game_library import GameLibraryService
        from c64u_browser.game_library_client import GameLibraryClient
        fixture=(Path(__file__).with_name('fixtures')/
                 'vice-1541-authentic.d64')
        first=Path(self.temp.name)/'first.d64'
        duplicate=Path(self.temp.name)/'duplicate.d64'
        first.write_bytes(fixture.read_bytes());duplicate.write_bytes(first.read_bytes())
        service=GameLibraryService(Path(self.temp.name)/'batch-library.json').load()
        self.addCleanup(service.close)
        tab=self.app.game_library_tab
        launcher=Mock()
        tab.client=GameLibraryClient(service,launcher)
        self.app.local=Path(self.temp.name)
        tab.add_local();self.pump()
        picker=tab.chooser
        self.assertEqual(('core-host','c64u'),picker.model.scopes)
        row=picker.listing.get_first_child()
        while row:
            if row.item[0] in (first.name,duplicate.name):picker.listing.select_row(row)
            row=row.get_next_sibling()
        self.assertEqual(2,len(picker.listing.get_selected_rows()))
        picker.response(None,self.Gtk.ResponseType.ACCEPT)
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and 'duplicate content' not in tab.message.get_text():
            self.pump()
        self.assertEqual(1,len(service.list()))
        self.assertIn('Added 1 new game record.',tab.message.get_text())
        self.assertIn('duplicate content',tab.message.get_text())
        self.assertEqual([],launcher.mock_calls)

    def test_game_library_selection_details_and_filters_use_core_catalog(self):
        from unittest.mock import Mock
        from c64u_browser.game_library import GameLibraryService,GameSource
        from c64u_browser.game_library_client import GameLibraryClient
        fixture=(Path(__file__).with_name('fixtures')/
                 'vice-1541-authentic.d64')
        game=Path(self.temp.name)/'ui-game.d64';game.write_bytes(fixture.read_bytes())
        service=GameLibraryService(Path(self.temp.name)/'library.json').load()
        self.addCleanup(service.close)
        record=service.add(GameSource.core_host(game),title='UI Game').wait(5).result.record
        service.set_notes(record.id,'joystick test')
        tab=self.app.game_library_tab
        tab.client=GameLibraryClient(service,Mock());tab.refresh(False);self.pump()
        tab.list.select_row(tab.rows[record.id]);self.pump()
        self.assertEqual('UI Game',tab.title.get_text())
        self.assertIn('This computer',tab.source.get_text())
        tab.favorite.set_active(True);self.pump()
        tab.favorites.set_active(True);self.pump()
        self.assertIn(record.id,tab.rows)
        tab.search.set_text('no such title');self.pump_for(.36)
        self.assertIn('No games match',tab.library_state.get_text())

    def test_game_library_bulk_actions_and_recursive_options(self):
        from unittest.mock import Mock,patch
        from c64u_browser.scheduler import DeviceSession
        tab=self.app.game_library_tab
        labels={w.get_label() for w in self.walk(tab.box)
                if isinstance(w,self.Gtk.Button)}
        self.assertIn('Scan local folder…',labels)
        self.assertIn('Scan C64U folder…',labels)
        self.assertIn('Add C64U files…',labels)

        submit=Mock();dialog=tab._scan_options(
            'Test scan','/tmp/games',submit)
        dialog.recursive.set_active(True);dialog.response(self.Gtk.ResponseType.OK)
        self.pump();submit.assert_called_once_with(True)

        from dataclasses import replace
        from c64u_browser.picker_model import PickerSelection,PickerMode,GAMES
        from c64u_browser.game_library import BulkImportRequest
        session=DeviceSession('id:C64-A','session-1')
        first=PickerSelection('c64u','/USB2/Games/one.d64','one.d64',
                              '/USB2',session.device_id,session.session_id,'games','file')
        selections=(first,replace(first,path='/USB2/Games/two.crt',filename='two.crt'))
        job=Mock()
        # Mock only the picker UI boundary and Core submission; keep consumer
        # validation real and never perform a remote read, write or launch.
        with patch('c64u_browser.game_library_tab.FilePicker',autospec=True) as picker, \
             patch.object(self.app.core,'device_session',return_value=session) as current, \
             patch.object(tab.client.library,'prepare_bulk_import',return_value=job) as prepare, \
             patch.object(tab,'_start_bulk_scan') as start, \
             patch.object(tab.client,'add_selection') as add:
            tab.add_c64u()
            self.assertEqual(('c64u','core-host'),picker.call_args.kwargs['scopes'])
            self.assertEqual(PickerMode.OPEN_FILES,picker.call_args.kwargs['mode'])
            self.assertEqual(GAMES,picker.call_args.kwargs['filter'])
            picker.call_args.args[1](None)
            self.assertIsNone(tab.chooser)
            start.assert_not_called();prepare.assert_not_called();add.assert_not_called()

            tab.add_c64u();picker.call_args.args[1](selections)
            start.assert_called_once()
            submit=start.call_args.args[0]
            self.assertIs(submit(),job)
            prepare.assert_called_once_with(
                BulkImportRequest.c64u_sources(session.device_id,tuple(s.path for s in selections)),
                expected_session=session)
            prepare.reset_mock();start.reset_mock()
            for changed in (DeviceSession(session.device_id,'replacement'),
                            DeviceSession('other-device',session.session_id)):
                current.return_value=changed
                with self.assertRaises(ValueError):submit()
            prepare.assert_not_called()
            current.return_value=session
            tab.add_selections((replace(first,kind='dir'),))
            self.assertIn('Choose D64 or CRT game files.',tab.message.get_text())
            tab.add_selections((replace(first,filename='wrong.d64'),))
            start.assert_not_called();prepare.assert_not_called();add.assert_not_called()
        with patch.object(self.app.core,'device_session',return_value=DeviceSession(
                'id:C64-A','session-1')), \
             patch.object(tab.client,'scan_c64u_folder',return_value=job) as scan, \
             patch.object(tab,'_start_bulk_scan',side_effect=lambda submit:submit()) as start:
            options=tab.scan_c64u_folder('/USB2/Games')
            options.recursive.set_active(True)
            options.response(self.Gtk.ResponseType.OK);self.pump()
        scan.assert_called_once_with(
            'id:C64-A','/USB2/Games',recursive=True)
        start.assert_called_once()
        self.assertTrue(callable(start.call_args.args[0]))

    def test_game_library_bulk_review_selection_filter_and_execution(self):
        from unittest.mock import Mock,patch
        from c64u_browser.game_library import GameLibraryService,BulkImportRequest
        from c64u_browser.game_library_client import GameLibraryClient
        from c64u_browser.game_library_bulk_dialog import BulkImportDialog
        fixture=Path(__file__).with_name('fixtures')/'vice-1541-authentic.d64'
        folder=Path(self.temp.name)/'bulk';folder.mkdir()
        (folder/'one.d64').write_bytes(fixture.read_bytes())
        (folder/'two.d64').write_bytes(fixture.read_bytes())
        (folder/'bad.txt').write_text('unsupported')
        service=GameLibraryService(Path(self.temp.name)/'bulk-library.json').load()
        self.addCleanup(service.close)
        preview=service.prepare_bulk_import(
            BulkImportRequest.core_host_folder(folder)).wait(5).result
        tab=self.app.game_library_tab;tab.client=GameLibraryClient(service,Mock())
        dialog=BulkImportDialog(tab,preview);tab.bulk_dialog=dialog
        self.pump()
        self.assertIn('3 entries examined',dialog.summary.get_text())
        self.assertIn('0 invalid/inaccessible',dialog.summary.get_text())
        self.assertIn('1 unsupported',dialog.summary.get_text())
        labels=[widget.get_text() for widget in self.walk(dialog.dialog)
                if isinstance(widget,self.Gtk.Label)]
        self.assertTrue(any('New game image' in label for label in labels))
        self.assertFalse(any('New valid game' in label for label in labels))
        self.assertEqual(1,dialog.state.count)
        self.assertEqual('Import 1 game',dialog.import_button.get_label())
        unsupported=next(item for item in preview.candidates
                         if item.classification=='unsupported-file')
        self.assertFalse(dialog.row_checks[unsupported.id].get_sensitive())
        selected=dialog.state.selected_ids()
        dialog.filter.set_active_id('problems');self.pump()
        self.assertEqual(selected,dialog.state.selected_ids())
        dialog.select_none();self.assertFalse(dialog.import_button.get_sensitive())
        dialog.select_all_new();self.assertTrue(dialog.import_button.get_sensitive())
        with patch.object(tab,'refresh',wraps=tab.refresh) as refresh:
            dialog.dialog.response(self.Gtk.ResponseType.OK)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline and not dialog.finished:self.pump()
            self.assertTrue(dialog.finished)
            self.assertEqual(1,refresh.call_count)
        self.assertIn('1 added',dialog.summary.get_text())
        self.assertEqual(1,len(service.list()))
        dialog.dialog.response(self.Gtk.ResponseType.CANCEL);self.pump()

    def test_game_library_bulk_immediate_feedback_cancel_and_stale_plan(self):
        from unittest.mock import Mock,patch
        from c64u_browser.game_library import GameLibraryError
        tab=self.app.game_library_tab;job=Mock()
        with patch.object(tab,'_run_job',side_effect=lambda submit,done,**kwargs:submit()) as run:
            tab._start_bulk_scan(job)
        run.assert_called_once_with(job,tab._bulk_scanned)
        self.assertEqual('Scanning Game Library candidates…',tab.message.get_text())

        preview=Mock(plan_id='expired',default_selected_candidate_ids=('a',),
                     eligible_candidate_ids=('a',),candidates=(),issues=(),
                     classification_counts=(('new-valid',1),),entries_seen=1,
                     supported_candidates=1,directories_scanned=1)
        from c64u_browser.game_library_bulk_dialog import BulkImportDialog
        client=Mock();client.select_bulk_candidates.side_effect=GameLibraryError(
            'plan','Bulk Import review expired.')
        old=tab.client;tab.client=client
        dialog=BulkImportDialog(tab,preview);tab.bulk_dialog=dialog;self.pump()
        dialog.dialog.response(self.Gtk.ResponseType.OK);self.pump()
        self.assertIn('Scan the folder or files again',dialog.progress.get_text())
        dialog.executing=True
        with patch.object(dialog,'cancel_import',create=True,return_value=True) as cancel:
            dialog.dialog.response(self.Gtk.ResponseType.CANCEL)
        cancel.assert_called_once_with()
        dialog.finished=True;dialog.dialog.destroy();tab.client=old
    def test_preferences_auto_save_undo_close_and_checkbox_extent(self):
        from c64u_browser.app_preferences import show_preferences
        from c64u_browser.profiles import Preferences
        dialog=show_preferences(self.app);self.pump()
        self.assertEqual(dialog.pages.get_n_pages(),4)
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
        self.assertNotIn('USB/SD backup root',[
            w.get_text() for w in self.walk(general)
            if isinstance(w,self.Gtk.Label)])
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

    def test_replay_controls_are_absent_and_general_settings_still_save(self):
        from c64u_browser.app_preferences import show_preferences
        from c64u_browser.profiles import Preferences
        dialog=show_preferences(self.app);self.pump()
        general=dialog.pages.get_nth_page(0)
        for container in (general,self.app.streams_tab.box):
            labels=[w.get_label() or '' for w in self.walk(container)
                    if isinstance(w,(self.Gtk.Label,self.Gtk.Button,self.Gtk.CheckButton))]
            self.assertFalse(any('replay' in label.lower() for label in labels))
        audio=next(w for w in self.walk(general)
                   if isinstance(w,self.Gtk.CheckButton) and
                   w.get_label()=='Play preview audio by default')
        audio.set_active(False);self.pump()
        loaded=Preferences(self.app.preferences.path).load()
        self.assertFalse(loaded.app_options['preview_audio'])
        self.assertNotIn('replay_enabled',loaded.app_options)
        dialog.response(self.Gtk.ResponseType.CLOSE)

    def test_preview_feeds_audio_and_recording_without_replay(self):
        import threading
        from unittest.mock import Mock
        from c64u_browser.streaming import rgb_frame
        tab=self.app.streams_tab
        # Even an in-memory legacy value must not activate retired behavior.
        self.app.preferences.app_options.update(replay_enabled=True,replay_seconds=30)
        receiver=Mock()
        packed=bytes([0x21])*(384*240//2);samples=[bytes(768)]
        receiver.take.return_value=((240,packed),samples)
        receiver.frames=1;receiver.last_audio=time.monotonic()
        receiver.last_video=time.monotonic();receiver.started=time.monotonic()
        session=Mock(receiver=receiver,stopping=threading.Event(),with_audio=True)
        session.thread.is_alive.return_value=True
        tab.session=session
        recorder=Mock(finishing=False);tab.recorder=recorder
        output=Mock();tab.output=output
        try:
            self.assertTrue(tab.tick())
            recorder.feed.assert_called_once_with((240,rgb_frame(packed)),samples)
            output.push.assert_called_once_with(samples)
            self.assertEqual(tab.picture.get_paintable().get_height(),240)
            self.assertTrue(tab.capture_button.get_sensitive())
            self.assertFalse(hasattr(tab,'replay'))
            receiver.take.return_value=(None,samples)
            self.assertTrue(tab.tick())
            self.assertEqual(recorder.feed.call_args.args,(None,samples))
            tab.stop()
            recorder.stop.assert_called_once_with()
            session.stop.assert_called_once_with()
            output.close.assert_called_once_with()
            self.assertIsNone(tab.picture.get_paintable())
        finally:
            tab.recorder=None;tab.session=None;tab.output=None

    def test_stream_close_disposes_choosers_and_stops_owned_media(self):
        import threading
        from unittest.mock import Mock
        tab=self.app.streams_tab
        session=Mock(stopping=threading.Event())
        session.thread.is_alive.return_value=True
        recorder=Mock(finishing=False);output=Mock()
        record_chooser=Mock();capture_chooser=Mock()
        tab.session=session;tab.recorder=recorder;tab.output=output
        tab.record_chooser=record_chooser;tab.capture_chooser=capture_chooser
        tab.timer=self.GLib.timeout_add(60000,lambda:True)
        try:
            tab.close()
            record_chooser.destroy.assert_called_once_with()
            capture_chooser.destroy.assert_called_once_with()
            recorder.stop.assert_called_once_with()
            session.stop.assert_called_once_with()
            output.close.assert_called_once_with()
            self.assertIsNone(tab.timer)
            self.assertIsNone(tab.record_chooser)
            self.assertIsNone(tab.capture_chooser)
            recorder.done=True;recorder.error='';recorder.path='synthetic.webm'
            self.assertFalse(tab.record_tick())
            self.assertIsNone(tab.recorder)
            self.assertIn('Recording saved',tab.record_status.get_text())
        finally:
            tab.session=None;tab.recorder=None;tab.output=None

    def test_stream_completion_and_audio_failure_preserve_cleanup(self):
        import threading
        from unittest.mock import Mock
        tab=self.app.streams_tab
        receiver=Mock(frames=0);receiver.take.return_value=(None,[bytes(768)])
        session=Mock(receiver=receiver,stopping=threading.Event(),message='stopped')
        session.thread.is_alive.return_value=True
        tab.session=session;tab.recorder=Mock(finishing=False);tab.output=Mock()
        recorder=tab.recorder;output=tab.output
        try:
            output.push.side_effect=RuntimeError('synthetic audio failure')
            self.assertTrue(tab.tick())
            self.assertIn('synthetic audio failure',session.stop_reason)
            output.close.assert_called_once_with()
            session.stop.assert_called_once_with()
            recorder.stop.assert_called_once_with()
            session.thread.is_alive.return_value=False
            self.assertFalse(tab.tick())
            self.assertIsNone(tab.session)
            self.assertIsNone(tab.timer)
            self.assertIsNone(tab.output)
            self.assertFalse(tab.record_button.get_sensitive())
        finally:
            tab.session=None;tab.recorder=None;tab.output=None

    def test_screenshot_keeps_captured_frame_while_preview_changes(self):
        from unittest.mock import Mock
        from gi.repository import Gdk
        tab=self.app.streams_tab
        frame=Gdk.MemoryTexture.new(384,240,Gdk.MemoryFormat.R8G8B8,
                                   self.GLib.Bytes.new(bytes(384*240*3)),384*3)
        tab.picture.set_paintable(frame)
        destination=Path(self.temp.name)/'capture.png'
        chooser=Mock();chooser.get_file.return_value=self.Gio.File.new_for_path(str(destination))
        with patch.object(self.Gtk.FileChooserNative,'new',return_value=chooser):
            tab.capture()
        response=chooser.connect.call_args.args[1]
        tab.picture.set_paintable(None)
        response(chooser,self.Gtk.ResponseType.ACCEPT)
        saved=Gdk.Texture.new_from_filename(str(destination))
        self.assertEqual((saved.get_width(),saved.get_height()),(384,240))
        self.assertIsNone(tab.capture_chooser)
        self.assertEqual(self.app.preferences.screenshot_folder,self.temp.name)

    def test_recording_chooser_preserves_session_guard_and_audio(self):
        import threading
        from unittest.mock import Mock
        from gi.repository import Gdk
        tab=self.app.streams_tab
        frame=Gdk.MemoryTexture.new(384,240,Gdk.MemoryFormat.R8G8B8,
                                   self.GLib.Bytes.new(bytes(384*240*3)),384*3)
        for stale in (True,False):
            session=Mock(stopping=threading.Event(),with_audio=True)
            session.thread.is_alive.return_value=True
            tab.session=session;tab.picture.set_paintable(frame)
            chooser=Mock()
            destination=str(Path(self.temp.name)/'recording.webm')
            chooser.get_file.return_value=self.Gio.File.new_for_path(destination)
            with patch.object(self.Gtk.FileChooserNative,'new',return_value=chooser):
                tab.record()
            response=chooser.connect.call_args.args[1]
            if stale:tab.session=None
            with patch('c64u_browser.recording.Recorder') as factory, \
                    patch.object(self.GLib,'timeout_add'):
                response(chooser,self.Gtk.ResponseType.ACCEPT)
                if stale:factory.assert_not_called()
                else:
                    factory.assert_called_once_with(destination,240,True)
                    self.assertEqual(tab.record_button.get_label(),'Stop recording')
                    self.assertEqual(self.app.preferences.recording_folder,self.temp.name)
            tab.recorder=None;tab.session=None;tab.picture.set_paintable(None)

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
        self.assertIn('Save Profile',labels)
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
        self.assertEqual([dialog.pages.get_tab_label_text(dialog.pages.get_nth_page(i)) for i in range(4)],['General','Device details','About','Game Library'])
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
        self.app.tabs.set_current_page(self.app.tabs.page_num(self.app.streams_tab.box));self.pump()
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
        self.app.tabs.set_current_page(self.app.tabs.page_num(tab.box));self.pump()
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
        from c64u_browser.core import ArgonautCore
        prefs = Preferences(Path(self.temp.name) / 'stable/config.json')
        prefs.app_options['developer_mode'] = True
        prefs.save()
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT': '0'}), patch(
                'c64u_browser.gui.ArgonautCore',
                return_value=ArgonautCore(preferences=prefs)):
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
