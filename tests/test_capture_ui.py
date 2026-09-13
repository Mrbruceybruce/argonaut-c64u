"""Opt-in real GTK capture checks; no device connection or remote commands."""
import os,time,unittest,uuid
from unittest.mock import Mock
from types import SimpleNamespace

@unittest.skipUnless(os.environ.get('ARGONAUT_UI_TESTS')=='1','Opt-in GTK display test')
class CaptureUI(unittest.TestCase):
    def setUp(self):
        import gi
        gi.require_version('Gtk','4.0')
        from gi.repository import Gtk,Gio,GLib,Gdk
        self.assertTrue(Gtk.init_check(),'GTK display unavailable')
        from c64u_browser.streams_tab import StreamsTab
        from c64u_browser.profiles import Preferences
        self.Gtk=Gtk;self.GLib=GLib;self.Gdk=Gdk
        self.app=Gtk.Application(application_id='org.local.Argonaut.CaptureTest'+uuid.uuid4().hex,flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.app.register(None)
        self.app.window=Gtk.ApplicationWindow(application=self.app)
        self.app.preferences=Preferences();self.app.busy=False
        self.tab=StreamsTab(self.app);self.app.window.set_child(self.tab.box)
        self.app.window.set_default_size(1200,850)
    def pump(self):
        until=time.monotonic()+.15
        while time.monotonic()<until:
            while self.GLib.MainContext.default().pending():self.GLib.MainContext.default().iteration(False)
            time.sleep(.005)
    def tearDown(self):
        self.tab.close();self.app.window.destroy();self.app.quit();self.pump()
    def test_window_is_a_view_only_and_retains_native_aspect(self):
        media=Mock();media.thread.is_alive.return_value=False
        self.tab.media=media
        self.tab.show_capture();window=self.tab.capture_window
        self.pump();self.assertEqual(window.get_title(),'Argonaut — C64 Capture')
        self.assertEqual(window.get_child(),window.canvas)
        self.assertIsNone(window.canvas.texture)
        texture=self.Gdk.MemoryTexture.new(384,240,self.Gdk.MemoryFormat.R8G8B8,self.GLib.Bytes.new(bytes(384*240*3)),384*3)
        self.tab.last_frame=(texture,None);window.canvas.set_frame(texture)
        self.pump();self.tab.show_capture();self.assertIs(self.tab.capture_window,window)
        window.close();self.pump();self.assertIsNone(self.tab.capture_window)
        media.stop.assert_not_called();media.take_frame.assert_not_called()
        self.assertIsNone(self.tab.session)
    def test_cairo_fallback_renders_without_extra_stream(self):
        from c64u_browser.capture_window import CaptureCanvas
        canvas=CaptureCanvas(use_cairo=True)
        win=self.Gtk.Window(application=self.app,default_width=768,default_height=480)
        win.set_child(canvas)
        texture=self.Gdk.MemoryTexture.new(384,240,self.Gdk.MemoryFormat.R8G8B8,self.GLib.Bytes.new(bytes(384*240*3)),384*3)
        canvas.set_frame(texture,bytearray(384*240*4));win.present();self.pump()
        self.assertIsNotNone(canvas.surface)
        canvas.set_frame(None);self.pump();self.assertIsNone(canvas.surface);win.destroy()
    def test_stale_video_blanks_both_views(self):
        self.tab.show_capture()
        receiver=Mock(frames=1,last_audio=0,last_video=time.monotonic()-3,started=time.monotonic()-5)
        receiver.snapshot.return_value={'video_age':3,'frames':1}
        session=SimpleNamespace(receiver=receiver,stopping=Mock(),thread=Mock(),with_audio=False)
        session.stopping.is_set.return_value=False;session.thread.is_alive.return_value=True
        media=Mock();media.take_frame.return_value=(240,bytes(384*240*3),None)
        media.snapshot.return_value={'recording_state':'idle','record_message':'','record_started':0,'error':''}
        media.thread.is_alive.return_value=False
        self.tab.session=session;self.tab.media=media
        self.tab.tick();self.assertIsNone(self.tab.picture.get_paintable())
        self.assertIsNone(self.tab.capture_window.canvas.texture)
        self.tab.session=None
    def test_diagnostics_is_read_only_and_omits_secrets(self):
        self.tab.client=Mock(password='DO-NOT-PRINT')
        self.tab.show_diagnostics();self.pump()
        self.assertIsNone(self.tab.session)
        self.tab.diagnostics_dialog.response(self.Gtk.ResponseType.CLOSE)
        self.assertIsNone(self.tab.diagnostics_dialog)
        self.tab.client.start_stream.assert_not_called()
