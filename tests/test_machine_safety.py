"""Offline confirmation/dispatch races using real UltimatePower and Core admission."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import gi
gi.require_version('Gtk', '4.0')
from c64u_browser.api import BrowserError, ConnectionFailure
from c64u_browser.core import CoreError
from c64u_browser.jobs import CoreJob
from c64u_browser.power_dialog import UltimatePower
from c64u_browser.scheduler import JobBinding
import test_core


class Dialog:
    def __init__(self, **kwargs):self.callback=None
    def add_button(self, *args):pass
    def get_content_area(self):return self
    def append(self, child):pass
    def connect(self, signal, callback):self.callback=callback
    def destroy(self):pass
    def present(self):pass
    def respond(self, ok=True):self.callback(self, int(ok))


class MachineSafetyTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_core.CoreTests();self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.core=self.fixture.core
        self.core.connect(self.fixture.profile)
        self.client=self.fixture.created[-1]
        self.client.machine_action=Mock(return_value={})
        self.recovery=SimpleNamespace(inflight=False, lost=Mock())
        self.app=SimpleNamespace(core=self.core, busy=False, window=None,
            recovery=self.recovery, status=SimpleNamespace(set_text=Mock()),
            run=lambda task, done:done(task()))
        self.tab=UltimatePower.__new__(UltimatePower)
        self.tab.app=self.app;self.tab.client=self.core.device_operations
        fake=SimpleNamespace(Dialog=Dialog, Label=lambda **kwargs:None,
            ResponseType=SimpleNamespace(OK=1,CANCEL=0))
        self.gtk=patch('c64u_browser.power_dialog.Gtk',fake);self.gtk.start()
        self.addCleanup(self.gtk.stop)

    def fresh(self):
        self.core.reconnect()
        client=self.fixture.created[-1]
        client.machine_action=Mock(return_value={})
        return client

    def test_unchanged_confirmations_send_exactly_once(self):
        for action in ('reset','reboot'):
            with self.subTest(action=action):
                self.client.machine_action.reset_mock();self.recovery.lost.reset_mock()
                dialog=self.tab.command(action);dialog.respond()
                self.client.machine_action.assert_called_once_with(action)
                self.recovery.lost.assert_called_once()
                self.assertIn('acknowledged',self.recovery.lost.call_args.args[0])
                dialog.respond() # Duplicate signals cannot replay a consumed target.
                self.client.machine_action.assert_called_once_with(action)

    def test_cancel_both_commands_has_no_recovery_consequence(self):
        for action in ('reset','reboot'):
            self.tab.command(action).respond(False)
        self.client.machine_action.assert_not_called()
        self.recovery.lost.assert_not_called()
        self.assertFalse(self.core._machine_targets)

    def test_recovered_session_before_confirmation_refuses_both(self):
        for action in ('reset','reboot'):
            with self.subTest(action=action):
                old=self.fixture.created[-1]
                dialog=self.tab.command(action)
                new=self.fresh()
                dialog.respond()
                old.machine_action.assert_not_called();new.machine_action.assert_not_called()
                self.app.status.set_text.assert_called_with(
                    'Connection changed. '+action.title()+' was not sent.')
        self.recovery.lost.assert_not_called()

    def test_disconnected_before_confirmation_refuses(self):
        dialog=self.tab.command('reset');self.core.disconnect();self.tab.client=None
        dialog.respond()
        self.client.machine_action.assert_not_called()
        self.app.status.set_text.assert_called_with('Connection changed. Reset was not sent.')

    def test_replacement_between_callback_and_worker_refuses_both(self):
        for action in ('reset','reboot'):
            queued=[];self.app.run=lambda task,done:queued.append((task,done))
            old=self.fixture.created[-1];self.tab.command(action).respond()
            self.assertEqual(len(queued),1) # callback only schedules; never waits.
            old.machine_action.assert_not_called()
            new=self.fresh();task,done=queued.pop();done(task())
            old.machine_action.assert_not_called();new.machine_action.assert_not_called()
        self.recovery.lost.assert_not_called()

    def test_session_reuse_does_not_bypass_private_transport_binding(self):
        for action in ('reset','reboot'):
            dialog=self.tab.command(action)
            replacement=test_core.FakeClient('synthetic');replacement.machine_action=Mock()
            self.core._client=replacement # Deliberately retain session/profile IDs.
            dialog.respond()
            replacement.machine_action.assert_not_called()
            self.app.status.set_text.assert_called_with(
                'Connection changed. '+action.title()+' was not sent.')
        self.client.machine_action.assert_not_called()

    def test_reused_session_with_different_device_or_profile_refuses(self):
        for field,value in (('_device_identity','id:OTHER'),('_active_profile',
                replace(self.fixture.profile,id='another-profile'))):
            target=self.core.prepare_machine_command('reset')
            original=getattr(self.core,field);setattr(self.core,field,value)
            try:
                with self.assertRaisesRegex(CoreError,'Connection changed'):
                    self.core.execute_machine_command(target)
            finally:setattr(self.core,field,original)
        self.client.machine_action.assert_not_called()

    def test_recovery_inflight_refuses_open_and_confirm(self):
        for action in ('reset','reboot'):
            dialog=self.tab.command(action)
            self.recovery.inflight=True
            self.assertIsNone(self.tab.command(action))
            dialog.respond();self.recovery.inflight=False
        self.client.machine_action.assert_not_called()
        self.recovery.lost.assert_not_called()
        self.assertFalse(self.core._machine_targets)

    def test_busy_confirmation_refuses_without_queue(self):
        self.app.run=Mock()
        for action in ('reset','reboot'):
            dialog=self.tab.command(action);self.app.busy=True
            dialog.respond();self.app.busy=False
        self.app.run.assert_not_called();self.client.machine_action.assert_not_called()

    def test_recovery_holds_admission_and_rejected_commands_never_queue(self):
        for action in ('reset','reboot'):
            target=self.core.prepare_machine_command(action)
            entered=Event();release=Event()
            def identity(client):
                entered.set()
                if not release.wait(3):raise AssertionError('recovery not released')
                return client._info
            with ThreadPoolExecutor(1) as pool, patch.object(test_core.FakeClient,'test_connection',identity):
                future=pool.submit(self.core.reconnect)
                try:
                    self.assertTrue(entered.wait(2))
                    with self.assertRaisesRegex(CoreError,'already running'):
                        self.core.execute_machine_command(target)
                finally:release.set()
                future.result(3)
            new=self.fixture.created[-1];new.machine_action=Mock()
            with self.assertRaisesRegex(CoreError,'Connection changed'):
                self.core.execute_machine_command(target)
            new.machine_action.assert_not_called()
        self.client.machine_action.assert_not_called()

    def test_replacement_at_validation_dispatch_boundary_cannot_redirect(self):
        inline=self.core.scheduler.inline
        for action in ('reset','reboot'):
            with self.subTest(action=action):
                self.client.machine_action.reset_mock()
                target=self.core.prepare_machine_command(action)
                @contextmanager
                def boundary(*args,**kwargs):
                    with inline(*args,**kwargs) as check:
                        # Gate is held between final session checks and send.
                        with ThreadPoolExecutor(1) as pool:
                            future=pool.submit(self.core.reconnect)
                            with self.assertRaisesRegex(CoreError,'already running'):
                                future.result(2)
                        yield check
                with patch.object(self.core.scheduler,'inline',boundary):
                    self.core.execute_machine_command(target)
                self.client.machine_action.assert_called_once_with(action)
                self.assertEqual(len(self.fixture.created),1)

    def test_dispatch_holds_session_gate_without_blocking_transition_callers(self):
        for action in ('reset','reboot'):
            entered=Event();release=Event();sent=[]
            def send(value):
                sent.append(value);entered.set()
                if not release.wait(3):raise AssertionError('command not released')
                return {}
            self.client.machine_action=send
            target=self.core.prepare_machine_command(action)
            with ThreadPoolExecutor(1) as pool:
                future=pool.submit(self.core.execute_machine_command,target)
                try:
                    self.assertTrue(entered.wait(2))
                    for transition in (self.core.reconnect,self.core.disconnect,
                            self.core.mark_connection_lost,
                            lambda:self.core.connect(self.fixture.profile)):
                        with self.assertRaisesRegex(CoreError,'already running'):transition()
                finally:release.set()
                future.result(3)
            self.assertEqual(sent,[action])
        self.assertEqual(len(self.fixture.created),1)

    def test_busy_device_lane_refuses_without_later_execution(self):
        entered=Event();release=Event()
        job=self.core.scheduler.submit(CoreJob('fixture',
            lambda _:(entered.set(),release.wait(3))),JobBinding.device(self.core.device_session()))
        try:
            self.assertTrue(entered.wait(2))
            for action in ('reset','reboot'):
                target=self.core.prepare_machine_command(action)
                with self.assertRaisesRegex(BrowserError,'already running'):
                    self.core.execute_machine_command(target)
        finally:release.set();job.wait(3)
        self.client.machine_action.assert_not_called()
        self.assertFalse(self.core._machine_targets)

    def test_uncertain_response_never_replayed_after_reconnect(self):
        for action in ('reset','reboot'):
            old=self.fixture.created[-1]
            old.machine_action=Mock(side_effect=ConnectionFailure('network','Response lost.'))
            dialog=self.tab.command(action);dialog.respond()
            old.machine_action.assert_called_once_with(action)
            self.assertIn('will not be repeated',self.recovery.lost.call_args.args[0])
            new=self.fresh();dialog.respond()
            new.machine_action.assert_not_called()
            old.machine_action.assert_called_once_with(action)

    def test_worker_submission_failure_consumes_target_and_old_response(self):
        from c64u_browser.gui import Browser
        for action in ('reset','reboot'):
            self.app.busy_controls=[]
            self.app.pool=Mock()
            self.app.pool.submit.side_effect=RuntimeError('synthetic submission failure')
            self.app.run=lambda task,done:Browser.run(self.app,task,done)
            dialog=self.tab.command(action);dialog.respond()
            self.assertFalse(self.core._machine_targets)
            self.client.machine_action.assert_not_called()
            self.recovery.lost.assert_not_called()
            self.app.pool.submit.assert_called_once()
            self.app.pool.submit.reset_mock(side_effect=True)
            dialog.respond()
            self.app.pool.submit.assert_not_called()
            self.client.machine_action.assert_not_called()
            self.recovery.lost.assert_not_called()
            self.assertIn('was not sent',self.app.status.set_text.call_args.args[0])

    def test_synchronous_handoff_exception_consumes_target_and_old_response(self):
        for action in ('reset','reboot'):
            self.app.run=Mock(side_effect=RuntimeError('private synthetic failure'))
            dialog=self.tab.command(action);dialog.respond()
            self.assertFalse(self.core._machine_targets)
            self.assertNotIn('private synthetic',self.app.status.set_text.call_args.args[0])
            self.app.run.reset_mock(side_effect=True)
            dialog.respond()
            self.app.run.assert_not_called()
        self.client.machine_action.assert_not_called();self.recovery.lost.assert_not_called()

    def test_run_refusal_consumes_target_without_queue(self):
        from c64u_browser.gui import Browser
        for action in ('reset','reboot'):
            self.app.pool=Mock()
            def refuse(task,done):
                self.app.busy=True
                return Browser.run(self.app,task,done)
            self.app.run=refuse
            dialog=self.tab.command(action);dialog.respond();self.app.busy=False
            self.assertFalse(self.core._machine_targets)
            self.app.pool.submit.assert_not_called()
            self.app.run=Mock();dialog.respond();self.app.run.assert_not_called()
        self.client.machine_action.assert_not_called();self.recovery.lost.assert_not_called()

    def test_destroy_exception_cannot_reuse_confirmation(self):
        for action in ('reset','reboot'):
            self.app.run=Mock()
            dialog=self.tab.command(action)
            dialog.destroy=Mock(side_effect=RuntimeError('synthetic destroy failure'))
            dialog.respond()
            self.assertFalse(self.core._machine_targets)
            dialog.destroy.reset_mock(side_effect=True)
            dialog.respond()
            dialog.destroy.assert_not_called();self.app.run.assert_not_called()
        self.client.machine_action.assert_not_called();self.recovery.lost.assert_not_called()

    def test_reentrant_destroy_and_double_response_schedule_only_once(self):
        from c64u_browser.gui import Browser
        from concurrent.futures import Future
        for action in ('reset','reboot'):
            self.client.machine_action.reset_mock();self.recovery.lost.reset_mock()
            self.app.busy_controls=[];self.app.pool=Mock()
            future=Future();self.app.pool.submit.return_value=future
            self.app.run=lambda task,done:Browser.run(self.app,task,done)
            dialog=self.tab.command(action)
            dialog.destroy=Mock(side_effect=lambda:dialog.respond())
            dialog.respond();dialog.respond()
            self.app.pool.submit.assert_called_once()
            self.client.machine_action.assert_not_called()
            self.assertEqual(len(self.core._machine_targets),1)
            task=self.app.pool.submit.call_args.args[0]
            with patch('c64u_browser.gui.GLib.idle_add',side_effect=lambda callback:callback()):
                future.set_result(task())
            self.client.machine_action.assert_called_once_with(action)
            self.recovery.lost.assert_called_once()
            self.assertFalse(self.core._machine_targets)
            dialog.respond();self.app.pool.submit.assert_called_once()
            self.recovery.lost.assert_called_once()

    def test_disconnect_refusal_keeps_recovery_watch_intact(self):
        from c64u_browser.gui import Browser
        app=SimpleNamespace(busy=False,core=Mock(),recovery=Mock(),status=Mock())
        app.core.disconnect.side_effect=CoreError('admission_busy','Operation running.')
        Browser.disconnect_device(app)
        app.status.set_text.assert_called_once_with('Operation running.')
        app.recovery.cancel.assert_not_called()

    def test_confirmation_target_has_no_transport_or_secret(self):
        target=self.core.prepare_machine_command('reset')
        self.assertEqual(set(vars(target)),{'action','session','profile_id','host','token'})
        self.assertEqual(target.session,self.core.device_session())
        self.assertFalse(hasattr(self.core.device_operations,'machine_action'))
        with self.assertRaisesRegex(CoreError,'Unsupported'):
            self.core.prepare_machine_command('poweroff')

    def test_machine_commands_do_not_change_credentials(self):
        before=dict(self.fixture.credentials.values)
        session=dict(self.core._session_passwords)
        for action in ('reset','reboot'):self.tab.command(action).respond()
        self.assertEqual(self.fixture.credentials.values,before)
        self.assertEqual(self.core._session_passwords,session)


if __name__=='__main__':unittest.main()
