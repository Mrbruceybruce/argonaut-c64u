import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch
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
