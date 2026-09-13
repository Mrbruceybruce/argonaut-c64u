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
        self.Gtk=Gtk;self.GLib=GLib
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
        self.assertTrue(tab.text_return.get_active());self.assertFalse(tab.zoom.get_editable())
        buttons=[w for w in self.walk(tab.box) if isinstance(w,self.Gtk.Button)]
        plus=next(w for w in buttons if w.get_label()=='+');minus=next(w for w in buttons if w.get_label()=='−')
        self.app.tabs.set_current_page(5);self.pump()
        before=(self.app.window.get_width(),self.app.window.get_height())
        for _ in range(6):plus.emit('clicked')
        self.assertEqual(tab.zoom.get_text(),'300');self.assertFalse(plus.get_sensitive())
        self.assertEqual(self.app.preferences.app_options['preview_scale'],150)
        self.app.preferences.save()
        from c64u_browser.profiles import Preferences
        self.assertEqual(Preferences(self.app.preferences.path).load().app_options['preview_scale'],150)
        self.pump()
        self.assertEqual(before,(self.app.window.get_width(),self.app.window.get_height()))
        v=tab.preview_scroll.get_vadjustment();self.assertGreater(v.get_upper(),v.get_page_size())
        for _ in range(8):minus.emit('clicked')
        self.assertEqual(tab.zoom.get_text(),'100');self.assertFalse(minus.get_sensitive())
    def test_preferences_save_cancel_reopen_and_checkbox_extent(self):
        from c64u_browser.app_preferences import show_preferences
        dialog=show_preferences(self.app);self.pump()
        self.assertEqual(dialog.pages.get_n_pages(),3)
        general=dialog.pages.get_nth_page(0)
        checks=[w for w in self.walk(general) if isinstance(w,self.Gtk.CheckButton)]
        for w in checks:
            self.assertEqual(w.get_halign(),self.Gtk.Align.START)
            self.assertLess(w.get_width(),general.get_width()-80)
        plus=next(w for w in self.walk(general) if isinstance(w,self.Gtk.Button) and w.get_label()=='+')
        plus.emit('clicked');dialog.response(self.Gtk.ResponseType.CANCEL)
        self.assertIsNone(self.app.preferences_dialog);self.assertEqual(self.app.preferences.app_options['preview_scale'],150)
        dialog=show_preferences(self.app)
        plus=next(w for w in self.walk(dialog.pages.get_nth_page(0)) if isinstance(w,self.Gtk.Button) and w.get_label()=='+')
        plus.emit('clicked');dialog.response(self.Gtk.ResponseType.OK)
        self.assertEqual(self.app.preferences.app_options['preview_scale'],175)
        dialog=show_preferences(self.app);dialog.close();self.pump();self.assertIsNone(self.app.preferences_dialog)
    def test_device_details_follow_profile_and_save_box_model(self):
        from c64u_browser.app_preferences import show_preferences
        from c64u_browser.profiles import Profile,Preferences
        one=Profile.new('First','first.local',case_edition='Existing case')
        two=Profile.new('Second','second.local',case_edition='Second case')
        self.app.preferences.profiles=[one,two];self.app.preferences.selected_id=one.id
        dialog=show_preferences(self.app,2);c=dialog.connections
        self.assertEqual(c.fields['case_edition'].get_text(),'Existing case')
        self.assertTrue(c.fields['case_edition'].get_editable());self.assertFalse(c.model.get_editable())
        c.saved.set_active_id(two.id);c.fields['case_edition'].set_text('New box');c.fields['serial_number'].set_text('SN2')
        self.app.run=lambda task,done:done(task())
        c.save()
        loaded=Preferences(self.app.preferences.path).load()
        self.assertEqual(loaded.profiles[0].case_edition,'Existing case')
        self.assertEqual(loaded.profiles[1].case_edition,'New box');self.assertEqual(loaded.profiles[1].serial_number,'SN2')
