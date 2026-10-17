"""Offline managed-row XTest coverage; frame-driven event handling, no sleeps."""
import unittest
from unittest.mock import Mock, patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib
import managed_library_gtk_check as fixtures
import c0_gtk_input
from c64u_browser.managed_library import LibraryState, parse_manifest
from c64u_browser.scheduler import DeviceSession
from tests.test_managed_library import manifest, game, PATH


class ManagedRowPointer(unittest.TestCase):
    def settle(self, *_):
        # Wait for actual frame processing, with a failure deadline, not a delay.
        window=getattr(self,'window',None)
        if window is None or not window.get_visible():
            context=GLib.MainContext.default()
            for _ in range(10000):
                if not context.pending():return
                context.iteration(False)
            self.fail('GTK queue failed to drain')
        loop=GLib.MainLoop();frames=[];expired=[]
        def tick(*_):
            frames.append(True)
            if len(frames)==2:loop.quit();return False
            return True
        def timeout():expired.append(True);loop.quit();return False
        tick_id=window.add_tick_callback(tick)
        timer=GLib.timeout_add(3000,timeout)
        try:loop.run()
        finally:
            if not expired:GLib.source_remove(timer)
            else:window.remove_tick_callback(tick_id)
        self.assertFalse(expired,'GTK frame deadline expired')

    def setUp(self):
        self.assertTrue(Gtk.init_check(),'Isolated GTK display required')
        for target, replacement in [('socket.socket.connect',Mock(side_effect=AssertionError('No networking'))),
                                    ('managed_library_gtk_check.pump',self.settle),
                                    ('c0_gtk_input.pump',self.settle)]:
            p=patch(target,replacement);p.start();self.addCleanup(p.stop)
        fixtures.ManagedViewGtk.setUp(self)
        self.addCleanup(lambda:fixtures.ManagedViewGtk.tearDown(self))
        self.window.set_default_size(1000,1000)
        self.core.managed_d64_preflight=Mock()
        self.core.execute_managed_d64=Mock()
        self.render()
        self.input=c0_gtk_input.Input(self.window);self.addCleanup(self.input.close)
        self.events=[]
        self.view.rows.connect('row-selected',lambda _,r:self.events.append(
            (r,self.view.launch_review.button.get_sensitive())))

    def render(self, **changes):
        first=game(format='D64',path='games/first.d64',size=174848,**changes)
        second=game(id='33333333-3333-4333-8333-333333333333',format='D64',
                    path='games/second.d64',size=174848,title='Second game')
        third=game(id='44444444-4444-4444-8444-444444444444',title='Unsupported CRT')
        self.library=parse_manifest(manifest(games=[first,second,third]),'device',PATH)
        self.app.preferences.game_library_location=self.library.identity.preference()
        self.view.render(LibraryState('valid','Loaded',(self.library,),self.session.session_id))
        self.settle()

    def click(self, row, x=20, y=None, eligible=True):
        self.view.rows.unselect_all();self.events.clear()
        self.input.click(row,x=x,y=y)
        self.assertIs(self.view.rows.get_selected_row(),row)
        self.assertEqual(self.view.launch_review.button.get_sensitive(),eligible)
        # Observed inside the same row-selected emission, not a later idle.
        self.assertEqual(self.events,[(row,eligible)])
        self.assertIs(row.library,self.library)
        self.assertIs(row.game,self.library.games[row.get_index()])
        self.app.run_file_job.assert_not_called()
        self.core.managed_d64_preflight.prepare.assert_not_called()
        self.core.execute_managed_d64.assert_not_called()

    def test_title_path_blank_and_row_edges(self):
        row=self.view.rows.get_first_child();label=row.get_child()
        self.assertFalse(label.get_selectable())
        self.assertEqual(label.get_tooltip_text(),PATH+'/games/first.d64')
        self.assertIn('A game · Commodore 64 · D64',label.get_text())
        for name,x,y in [('title',20,10),('path',20,row.get_height()-10),
                         ('blank',row.get_width()-40,row.get_height()/2),
                         ('left',1,row.get_height()/2),('right',row.get_width()-1,row.get_height()/2),
                         ('top',20,1),('bottom',20,row.get_height()-1)]:
            with self.subTest(region=name):self.click(row,x,y)

    def test_wrapped_label_regions(self):
        self.render(title='Long managed game title '*20)
        row=self.view.rows.get_first_child();label=row.get_child()
        self.assertGreater(label.get_layout().get_line_count(),2)
        for fraction in (.15,.5,.85):
            with self.subTest(fraction=fraction):self.click(row,20,row.get_height()*fraction)

    def test_multiple_rows_and_keyboard_navigation(self):
        first=self.view.rows.get_row_at_index(0);second=self.view.rows.get_row_at_index(1)
        self.click(second);self.click(first)
        first.grab_focus();self.input.press('Down')
        self.assertIs(self.view.rows.get_selected_row(),second)
        self.assertTrue(self.view.launch_review.button.get_sensitive())
        self.app.run_file_job.assert_not_called()

    def test_unsupported_format(self):
        self.click(self.view.rows.get_row_at_index(2),eligible=False)

    def test_busy_state(self):
        self.app.busy=True
        self.click(self.view.rows.get_first_child(),eligible=False)
        self.app.busy=False
        self.click(self.view.rows.get_first_child())

    def test_stale_session(self):
        self.session=DeviceSession('device','replacement')
        self.click(self.view.rows.get_first_child(),eligible=False)
        self.session=DeviceSession('other-device','one')
        self.click(self.view.rows.get_first_child(),eligible=False)

    def test_changed_preference(self):
        self.app.preferences.game_library_location={**self.library.identity.preference(),'library_id':'changed'}
        self.click(self.view.rows.get_first_child(),eligible=False)
