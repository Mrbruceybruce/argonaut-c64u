import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
from c64u_browser.api import BrowserError

# Importing GTK types does not create windows or connect to a device.
try:
    from c64u_browser.gui import Browser
    from c64u_browser.connection_dialog import ConnectionDialog
except ImportError:
    Browser = None

@unittest.skipIf(Browser is None, 'GTK runtime unavailable')
class Lifecycle(unittest.TestCase):
    def test_second_activation_presents_existing_window(self):
        window=Mock()
        app=SimpleNamespace(window=window,get_windows=lambda:[window])
        Browser.do_activate(app)
        window.present.assert_called_once_with()

    def test_closed_executor_restores_connection_controls(self):
        pool=ThreadPoolExecutor(max_workers=1);pool.shutdown()
        enabled=Mock();enabled.get_sensitive.return_value=True
        disabled=Mock();disabled.get_sensitive.return_value=False
        app=SimpleNamespace(busy=False,busy_controls=[enabled,disabled],status=Mock(),pool=pool)
        app.run=lambda task,done:Browser.run(app,task,done)
        dialog=SimpleNamespace(app=app,controls=Mock(),status=Mock())
        task=Mock();done=Mock()
        ConnectionDialog.submit(dialog,task,done)
        self.assertFalse(app.busy)
        enabled.set_sensitive.assert_called_with(True)
        disabled.set_sensitive.assert_called_with(False)
        dialog.controls.set_sensitive.assert_called_with(True)
        self.assertIn('Close and reopen',dialog.status.set_text.call_args.args[0])
        task.assert_not_called();done.assert_not_called()

    def test_close_exits_app_even_if_child_windows_remain(self):
        app=SimpleNamespace(busy=False,recovery=Mock(),streams_tab=Mock(),pool=Mock(),quit=Mock())
        self.assertFalse(Browser.close(app))
        app.pool.shutdown.assert_called_once_with(wait=False)
        app.quit.assert_called_once_with()

    def test_busy_close_preserves_active_worker(self):
        app=SimpleNamespace(busy=True,status=Mock(),pool=Mock(),quit=Mock())
        self.assertTrue(Browser.close(app))
        app.pool.shutdown.assert_not_called();app.quit.assert_not_called()

    def test_quick_connect_uses_last_profile_and_checks_identity(self):
        profile=Mock(id='profile-id')
        preferences=SimpleNamespace(
            selected=lambda:profile,
            app_options={'remember_folders':True,
                         'remote_folders':{'profile-id':'/USB1'}})
        result=Mock()
        core=Mock();core.connect_selected.return_value=result
        app=SimpleNamespace(
            busy=False,active_profile=None,preferences_error=None,
            preferences=preferences,core=core,status=Mock(),activate_connection=Mock(),
            open_connections=Mock())
        app.run=lambda task,done:done(task())
        Browser.quick_connect(app)
        core.connect_selected.assert_called_once_with(require_bound=True)
        app.activate_connection.assert_called_once_with(result)
        app.open_connections.assert_not_called()

    def test_quick_connect_without_profile_opens_device_details(self):
        app=SimpleNamespace(
            busy=False,active_profile=None,preferences_error=None,
            core=SimpleNamespace(selected_profile=lambda:None),status=Mock(),
            open_connections=Mock())
        Browser.quick_connect(app)
        app.open_connections.assert_called_once_with()
        self.assertIn('Choose or create',app.status.set_text.call_args.args[0])


@unittest.skipIf(Browser is None, 'GTK runtime unavailable')
class QuitAction(unittest.TestCase):
    def test_quit_uses_window_close_handlers(self):
        app=SimpleNamespace(window=Mock(),quit=Mock(),pool=Mock())
        Browser.request_quit(app)
        app.window.close.assert_called_once_with()
        app.quit.assert_not_called()
        app.pool.shutdown.assert_not_called()

    def test_quit_before_activation_shuts_down_worker(self):
        app=SimpleNamespace(quit=Mock(),pool=Mock())
        Browser.request_quit(app)
        app.pool.shutdown.assert_called_once_with(wait=False)
        app.quit.assert_called_once_with()
