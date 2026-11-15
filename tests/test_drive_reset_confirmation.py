"""Reset confirmation contracts: inert GTK and synthetic Core transports only."""
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import socket
import unittest
import gi
gi.require_version('Gtk', '4.0')
from c64u_browser.core import CoreError
from c64u_browser.drives_tab import DrivesTab
from c64u_browser.scheduler import JobBinding
from tests import test_core


class DriveResetConfirmation(unittest.TestCase):
    def setUp(self):
        for method in ('connect', 'connect_ex', 'sendto'):
            p = patch.object(socket.socket, method, side_effect=AssertionError('OFFLINE'))
            p.start(); self.addCleanup(p.stop)
        p = patch('socket.create_connection', side_effect=AssertionError('OFFLINE'))
        p.start(); self.addCleanup(p.stop)
        self.fixture = test_core.CoreTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.core = self.fixture.core
        self.core.connect(self.fixture.profile)
        self.instrument()
        self.tab = DrivesTab.__new__(DrivesTab)
        self.tab.client = self.core.device_operations; self.tab.loaded = True
        self.tab.cards = {}; self.tab.message = Mock(); self.tab.show = Mock()
        self.tab.app = NS(core=self.core, busy=False, window=None,
                          run=lambda task, done: done(task()))
        self.dialog = Mock(); self.callbacks = {}
        self.dialog.connect.side_effect = lambda event, fn: self.callbacks.update({event: fn})
        fake = NS(Dialog=Mock(return_value=self.dialog), Label=Mock(),
                  ResponseType=NS(OK=1, CANCEL=0))
        p = patch('c64u_browser.drives_tab.Gtk', fake); p.start(); self.addCleanup(p.stop)

    def instrument(self):
        client = self.fixture.created[-1]
        client.drive_action = Mock(); client.read_drives = Mock(return_value={'synthetic': True})
        client.apply_configuration = Mock(); client._request_json = Mock()
        return client

    def open(self):
        self.tab.action('a', 'reset')
        return self.callbacks['response']

    def no_dispatch(self):
        for client in self.fixture.created:
            client.drive_action.assert_not_called(); client.read_drives.assert_not_called()
            client.apply_configuration.assert_not_called(); client._request_json.assert_not_called()

    def reconnect(self):
        self.core.mark_connection_lost(); self.tab.bind(None)
        self.core.reconnect(); self.instrument(); self.tab.bind(self.core.device_operations)

    def test_valid_confirmation_resets_once_and_reads_same_transport(self):
        callback = self.open(); callback(self.dialog, 1); callback(self.dialog, 1)
        client = self.fixture.created[0]
        client.drive_action.assert_called_once_with('a', 'reset')
        client.read_drives.assert_called_once_with()
        client.apply_configuration.assert_not_called(); client._request_json.assert_not_called()
        self.tab.show.assert_called_once_with({'synthetic': True})

    def test_cancel_consumes_confirmation(self):
        callback = self.open(); callback(self.dialog, 0); callback(self.dialog, 1)
        self.no_dispatch()

    def test_disconnect_invalidates_confirmation(self):
        callback = self.open(); self.core.disconnect(); self.tab.bind(None)
        callback(self.dialog, 1); self.no_dispatch()

    def test_connection_loss_invalidates_confirmation_without_ui_rebind(self):
        callback = self.open(); self.core.mark_connection_lost()
        callback(self.dialog, 1); self.no_dispatch()

    def test_same_device_reconnect_invalidates_confirmation(self):
        callback = self.open(); self.reconnect(); callback(self.dialog, 1)
        self.no_dispatch()
        self.assertIn('Reset was not sent', self.tab.message.set_text.call_args.args[0])

    def test_session_replacement_without_ui_rebind_invalidates_confirmation(self):
        callback = self.open(); self.core.reconnect(); self.instrument()
        callback(self.dialog, 1); self.no_dispatch()

    def test_different_device_invalidates_confirmation(self):
        callback = self.open()
        factory = self.core._client_factory
        def different(*args, **kwargs):
            client = factory(*args, **kwargs)
            client._info = dict(test_core.INFO, info=dict(test_core.INFO['info'], unique_id='OTHER'))
            return client
        with patch.object(self.core, '_client_factory', different):
            self.core.connect(replace(self.fixture.profile, id='other', host='192.0.2.21', device_id='OTHER', device_mac=''))
        self.instrument(); self.tab.bind(self.core.device_operations)
        callback(self.dialog, 1); self.no_dispatch()

    def test_reconnect_between_response_and_worker_is_rejected_by_core(self):
        queued = []
        self.tab.app.run = lambda task, done: queued.append((task, done))
        self.open()(self.dialog, 1)
        self.assertEqual(len(queued), 1)
        self.reconnect()
        task, done = queued[0]; result = task(); done(result)
        self.assertIsInstance(result, CoreError); self.assertEqual(result.code, 'session')
        self.no_dispatch()

    def test_busy_response_consumes_confirmation_without_dispatch(self):
        callback = self.open(); self.tab.app.busy = True; callback(self.dialog, 1)
        self.tab.app.busy = False; callback(self.dialog, 1); self.no_dispatch()

    def test_core_refuses_stale_session_even_without_ui(self):
        session = self.core.device_session(); self.reconnect()
        with self.assertRaises(CoreError): self.core.execute_drive_reset(session, 'a')
        self.no_dispatch()

    def test_session_admission_contention_refuses_without_dispatch(self):
        with self.core._session_admission():
            with self.assertRaises(CoreError) as caught:
                self.core.execute_drive_reset(self.core.device_session(), 'a')
        self.assertEqual(caught.exception.code, 'admission_busy'); self.no_dispatch()

    def test_busy_device_lane_refuses_without_dispatch(self):
        session = self.core.device_session()
        with self.core.scheduler.inline(JobBinding.device(session)):
            with self.assertRaises(Exception) as caught: self.core.execute_drive_reset(session, 'a')
        self.assertEqual(caught.exception.code, 'admission_busy'); self.no_dispatch()

    def test_session_cannot_change_during_dispatch_or_readback(self):
        client = self.fixture.created[0]
        def guarded(*args):
            with self.assertRaises(CoreError) as caught: self.core.reconnect()
            self.assertEqual(caught.exception.code, 'admission_busy')
            return {}
        client.drive_action.side_effect = guarded; client.read_drives.side_effect = guarded
        self.open()(self.dialog, 1)
        client.drive_action.assert_called_once_with('a', 'reset'); client.read_drives.assert_called_once()

    def test_uncertain_command_and_readback_failures_never_retry(self):
        for failure in ('drive_action', 'read_drives'):
            with self.subTest(failure=failure):
                client = self.instrument(); self.tab.loaded = True
                getattr(client, failure).side_effect = TimeoutError('synthetic timeout')
                callback = self.open(); callback(self.dialog, 1); callback(self.dialog, 1)
                client.drive_action.assert_called_once_with('a', 'reset')
                self.assertEqual(client.read_drives.call_count, int(failure == 'read_drives'))
                self.assertFalse(self.tab.loaded)

    def test_invalid_drive_rejected_before_transport(self):
        with self.assertRaises(CoreError): self.core.execute_drive_reset(self.core.device_session(), 'c')
        self.no_dispatch()
