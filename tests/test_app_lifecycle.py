import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock,patch
from c64u_browser.api import BrowserError

# Importing GTK types does not create windows or connect to a device.
try:
    from c64u_browser.gui import Browser,job_progress_message
    from c64u_browser.connection_dialog import ConnectionDialog
    from c64u_browser.jobs import JobProgress
except ImportError:
    Browser = None

@unittest.skipIf(Browser is None, 'GTK runtime unavailable')
class Lifecycle(unittest.TestCase):
    def test_game_launch_hash_progress_is_explicit(self):
        progress=JobProgress('hash',10,20,'bytes','Validating C64U game file…')
        self.assertEqual('Validating game before launch…',
                         job_progress_message(
                             'game-library.launch-preview',progress))
        self.assertEqual('Validating C64U game file…',
                         job_progress_message('game-library.validate',progress))

    def test_file_job_completion_snapshot_recovers_a_missed_finish_event(self):
        running=SimpleNamespace(state='running')
        succeeded=SimpleNamespace(state='succeeded',result='done')
        job=Mock(operation='sid-jukebox.next',id='job')
        job.snapshot.side_effect=(running,running,succeeded)
        job.add_listener=Mock()  # Deliberately never delivers the finish event.
        control=Mock();control.get_sensitive.return_value=True
        app=SimpleNamespace(busy=False,busy_controls=[control],status=Mock(),
                            transfer_job=None,cancel_button=Mock())
        app.begin_file_job=lambda value:Browser.begin_file_job(app,value)
        app.end_file_job=lambda:Browser.end_file_job(app)
        done=Mock();timer=[]
        with patch('c64u_browser.gui.GLib.timeout_add',
                   side_effect=lambda _delay,callback:timer.append(callback)), \
             patch('c64u_browser.gui.GLib.idle_add',
                   side_effect=lambda callback,*args:callback(*args)):
            Browser.run_file_job(app,job,done)
            self.assertTrue(app.busy);self.assertTrue(timer[0]())
            self.assertFalse(timer[0]())
        self.assertFalse(app.busy);self.assertIsNone(app.transfer_job)
        done.assert_called_once_with(succeeded)

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
