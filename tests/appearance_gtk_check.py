"""Controlled appearance sources; never write desktop settings or call D-Bus."""
import unittest
from unittest.mock import Mock, patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib
from c64u_browser import appearance, ui_style
import test_preferences_ui


class Source:
    def __init__(self):self.handlers={};self.next_id=0
    def connect(self,signal,callback):
        self.next_id+=1;self.handlers[self.next_id]=(signal,callback);return self.next_id
    def disconnect(self,handler):del self.handlers[handler]
    def emit(self,signal,*args):
        for name,callback in list(self.handlers.values()):
            if name==signal:callback(self,*args)


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.display=Source();self.display.is_closed=Mock(return_value=False)
        self.settings=Mock();self.settings.get_property.return_value=False
        self.gnome=Source();self.gnome.get_string=Mock(return_value='default')
        self.proxy=Source();self.proxy.get_name_owner=Mock(return_value=':1.23')
        self.proxy.call=Mock();self.proxy.call_finish=Mock()
        self.schema=Mock();self.schema.has_key.return_value=True
        patches=[patch.object(appearance.sys,'platform','linux'),
                 patch.dict(appearance.os.environ,{'XDG_CURRENT_DESKTOP':'GNOME'}),
                 patch.object(Gtk.Settings,'get_for_display',return_value=self.settings),
                 patch.object(appearance.Gio.SettingsSchemaSource,'get_default',return_value=Mock(lookup=Mock(return_value=self.schema))),
                 patch.object(appearance.Gio.Settings,'new_full',return_value=self.gnome),
                 patch.object(appearance.Gio.DBusProxy,'new_for_bus'),
                 patch.object(appearance.Gio.DBusProxy,'new_for_bus_finish',return_value=self.proxy)]
        self.mocks=[]
        for p in patches:self.mocks.append(p.start());self.addCleanup(p.stop)
        self.start_proxy=self.mocks[-2];self.finish_proxy=self.mocks[-1]

    def start(self):
        self.follower=appearance.AppearanceFollower(self.display)
        self.addCleanup(self.follower.close)
        return self.follower

    def ready(self):self.follower.proxy_ready(None,Mock(),None)
    def reply(self,value,revision=None):
        self.proxy.call_finish.return_value=GLib.Variant('(v)',(GLib.Variant('u',value),))
        self.follower.read_done(self.proxy,Mock(),self.follower.revision if revision is None else revision)
    def signal(self,value):
        self.proxy.emit('g-signal',':1.23','SettingChanged',GLib.Variant('(ssv)',
            ('org.freedesktop.appearance','color-scheme',GLib.Variant('u',value))))
    def dark(self,value):self.settings.set_property.assert_called_with('gtk-application-prefer-dark-theme',value)

    def test_startup_light(self):
        self.gnome.get_string.return_value='prefer-dark'
        self.start();self.ready();self.reply(2);self.dark(False)
    def test_startup_dark(self):
        self.start();self.ready();self.reply(1);self.dark(True)
    def test_runtime_both_directions(self):
        self.start();self.ready();self.reply(2)
        self.signal(1);self.dark(True)
        self.signal(2);self.dark(False)
    def test_portal_precedes_gnome(self):
        self.start();self.ready();self.reply(2)
        self.gnome.get_string.return_value='prefer-dark';self.gnome.emit('changed::color-scheme','color-scheme')
        self.dark(False)
    def test_unavailable_bus_uses_gnome(self):
        self.gnome.get_string.return_value='prefer-dark';self.start()
        self.finish_proxy.side_effect=GLib.Error('unavailable');self.ready();self.dark(True)
    def test_failed_read_keeps_fallback(self):
        self.gnome.get_string.return_value='prefer-dark';self.start();self.ready()
        self.proxy.call_finish.side_effect=GLib.Error('unsupported')
        self.follower.read_done(self.proxy,Mock(),self.follower.revision);self.dark(True)
    def test_unknown_and_no_preference_use_fallback_or_initial(self):
        self.start();self.ready()
        for value in (0,99):
            self.gnome.get_string.return_value='prefer-dark';self.reply(value);self.dark(True)
            self.gnome.get_string.return_value='default';self.gnome.emit('changed::color-scheme','color-scheme');self.dark(False)
        for value in (None,True,'1',1.0,GLib.Variant('s','dark')):
            self.assertIsNone(appearance.AppearanceFollower.preference(value))
    def test_non_gnome_does_not_read_schema(self):
        with patch.dict(appearance.os.environ,{'XDG_CURRENT_DESKTOP':'KDE'}):self.start()
        self.mocks[3].assert_not_called();self.mocks[4].assert_not_called()
        self.ready();self.reply(1);self.dark(True)
    def test_missing_schema_is_safe(self):
        self.mocks[3].return_value=None
        self.start();self.mocks[4].assert_not_called();self.dark(False)
    def test_missing_key_is_safe(self):
        self.schema.has_key.return_value=False
        self.start();self.mocks[4].assert_not_called();self.dark(False)
    def test_non_linux_preserves_native_settings(self):
        with patch.object(appearance.sys,'platform','darwin'):self.start()
        self.start_proxy.assert_not_called();self.settings.set_property.assert_not_called()
    def test_late_read_cannot_replace_signal(self):
        self.start();self.ready();revision=self.follower.revision
        self.signal(1);self.reply(2,revision);self.dark(True)
    def test_portal_owner_loss_and_return(self):
        self.gnome.get_string.return_value='prefer-light'
        self.start();self.ready();self.reply(1);self.dark(True)
        self.proxy.get_name_owner.return_value=None
        self.proxy.emit('notify::g-name-owner',None);self.dark(False)
        self.proxy.get_name_owner.return_value=':1.99'
        self.proxy.emit('notify::g-name-owner',None);self.reply(1);self.dark(True)
    def test_cleanup_and_late_callbacks(self):
        self.start();self.ready();revision=self.follower.revision
        self.follower.close();self.follower.close()
        self.assertTrue(self.follower.cancel.is_cancelled())
        for source in (self.display,self.proxy,self.gnome):self.assertEqual(source.handlers,{})
        self.settings.set_property.reset_mock()
        self.reply(1,revision);self.ready();self.follower.apply()
        self.settings.set_property.assert_not_called()
    def test_display_close_stops_updates(self):
        self.start();self.ready();self.display.emit('closed',False)
        self.assertTrue(self.follower.closed);self.assertEqual(self.proxy.handlers,{})
    def test_closed_display_never_subscribes(self):
        self.display.is_closed.return_value=True;self.start()
        self.assertTrue(self.follower.closed);self.start_proxy.assert_not_called()
    def test_gtk48_property_only_no_css_or_timers(self):
        with patch.object(Gtk.StyleContext,'add_provider_for_display') as css, \
             patch.object(GLib,'timeout_add') as timer:
            self.start();self.ready();self.reply(1);self.signal(2)
        css.assert_not_called();timer.assert_not_called()
        self.settings.get_property.assert_called_once_with('gtk-application-prefer-dark-theme')
        self.assertEqual({c.args[0] for c in self.settings.set_property.call_args_list},
                         {'gtk-application-prefer-dark-theme'})
    def test_gnome_runtime_fallback(self):
        self.start()
        for value,dark in [('prefer-dark',True),('prefer-light',False)]:
            self.gnome.get_string.return_value=value
            self.gnome.emit('changed::color-scheme','color-scheme');self.dark(dark)
    def test_no_preference_preserves_initial_dark(self):
        self.settings.get_property.return_value=True
        self.start();self.ready();self.reply(0);self.dark(True)
    def test_synchronous_bus_error_does_not_block_startup(self):
        self.start_proxy.side_effect=GLib.Error('unavailable')
        self.start();self.dark(False)
    def test_unrelated_portal_signal_is_ignored(self):
        self.start();self.ready();self.reply(1)
        self.proxy.emit('g-signal',':1.23','SettingChanged',GLib.Variant('(ssv)',
            ('other.namespace','color-scheme',GLib.Variant('u',2))))
        self.dark(True)
    def test_closed_before_proxy_arrives(self):
        self.start();self.follower.close();self.ready()
        self.assertEqual(self.proxy.handlers,{})
        self.proxy.call.assert_not_called()
    def test_real_gtk_widgets_unchanged(self):
        self.assertTrue(Gtk.init_check())
        settings=Gtk.Settings.get_default();initial=settings.get_property('gtk-application-prefer-dark-theme')
        self.addCleanup(settings.set_property,'gtk-application-prefer-dark-theme',initial)
        window=Gtk.Window();entry=Gtk.Entry();box=Gtk.Box();box.append(entry)
        error=Gtk.Label(label='Existing error',sensitive=False);box.append(error)
        error.set_tooltip_text('Existing tooltip');ui_style.set_error(error,True)
        window.set_child(box);window.present();self.addCleanup(window.destroy)
        entry.grab_focus();focus=window.get_focus();role=error.get_accessible_role()
        self.assertIsNotNone(focus)
        with patch.object(Gtk.Settings,'get_for_display',return_value=settings), \
             patch.object(Gtk.StyleContext,'add_provider_for_display') as css:
            self.start();self.ready();self.reply(1);self.signal(2)
            self.assertIs(window.get_focus(),focus)
            self.assertEqual(error.get_accessible_role(),role)
            self.assertEqual(error.get_text(),'Existing error')
            self.assertEqual(error.get_tooltip_text(),'Existing tooltip')
            self.assertFalse(error.get_sensitive())
            self.assertTrue(error.has_css_class('error'));self.assertTrue(error.has_css_class('argonaut-error-message'))
            ui_style.set_error(error,False)
            self.assertFalse(error.has_css_class('error'));self.assertFalse(error.has_css_class('argonaut-error-message'))
            css.assert_not_called()


class ApplicationAppearance(unittest.TestCase):
    def test_activation_and_shutdown_lifecycle(self):
        fixture=test_preferences_ui.PreferencesUI();fixture.setUp()
        self.addCleanup(fixture.doCleanups);self.addCleanup(fixture.tearDown)
        app=fixture.app;provider=app.file_pane_css
        app.do_activate();app.do_activate()
        fixture.appearance_factory.assert_called_once()
        self.assertIs(app.file_pane_css,provider)
        app.busy=True;self.assertTrue(app.close())
        app.appearance.close.assert_not_called()
        app.busy=False
        with patch.object(Gtk.Application,'do_shutdown') as shutdown:
            app.do_shutdown();shutdown.assert_called_once_with(app)
        app.appearance.close.assert_called_once()
