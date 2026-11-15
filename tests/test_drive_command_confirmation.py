"""Session-bound Drive commands: real Core, inert dialogs, blocked sockets."""
from dataclasses import replace
from functools import wraps
from unittest.mock import Mock, patch
import unittest
from tests import test_drive_reset_confirmation as reset_fixture
from tests import test_core
from c64u_browser.core import CoreError
from c64u_browser.scheduler import JobBinding


CASES = [(drive, action, mode) for drive in ('a', 'b')
         for action, mode in [('on', None), ('off', None), ('remove', None),
                              ('type', '1541'), ('type', '1571'), ('type', '1581')]]


def all_commands(test):
    """Each contract runs with fresh Core/transport state for all 12 intents."""
    @wraps(test)
    def run(self):
        for drive, action, mode in CASES:
            with self.subTest(drive=drive, action=action, mode=mode):
                self.f = reset_fixture.DriveResetConfirmation()
                try:
                    self.f.setUp()
                    self.core, self.tab = self.f.core, self.f.tab
                    self.drive, self.action, self.mode = drive, action, mode
                    self.client = self.instrument()
                    # Extend the Reset fixture's network denial to DNS as well.
                    with patch('socket.getaddrinfo', side_effect=AssertionError('OFFLINE')):
                        test(self)
                finally:
                    self.f.doCleanups()
    return run


class DriveCommandConfirmation(unittest.TestCase):
    def instrument(self):
        client = self.f.instrument()
        client.set_drive_type = Mock()
        return client

    def open(self):
        self.tab.loaded = True
        if self.action == 'type':
            selector = Mock(); selector.get_selected.return_value = ('1541', '1571', '1581').index(self.mode)
            self.tab.cards = {self.drive: {'type': selector}}
            self.tab.change_type(self.drive)
            # A subsequent UI selection must not alter the reviewed command.
            selector.get_selected.return_value = (selector.get_selected.return_value + 1) % 3
            self.tab.cards = {}
        else:
            self.tab.action(self.drive, self.action)
        return self.f.callbacks['response']

    def execute(self, session=None):
        return self.core.execute_drive_command(session or self.core.device_session(),
                                              self.drive, self.action, mode=self.mode)

    def refuse(self):
        self.f.no_dispatch()
        for client in self.f.fixture.created:
            client.set_drive_type.assert_not_called()

    def sent(self, reads=1):
        if self.action == 'type':
            self.client.set_drive_type.assert_called_once_with(self.drive, self.mode)
            self.client.drive_action.assert_not_called()
        else:
            self.client.drive_action.assert_called_once_with(self.drive, self.action)
            self.client.set_drive_type.assert_not_called()
        self.assertEqual(self.client.read_drives.call_count, reads)
        self.client.apply_configuration.assert_not_called()
        self.client._request_json.assert_not_called()

    def reconnect(self):
        self.core.reconnect(); self.instrument()

    @all_commands
    def test_valid_exact_intent_and_duplicate_response(self):
        callback = self.open(); callback(None, 1); callback(None, 1)
        self.sent(); self.tab.show.assert_called_once_with({'synthetic': True})

    @all_commands
    def test_cancel_then_duplicate_accept(self):
        callback = self.open(); callback(None, 0); callback(None, 1); self.refuse()

    @all_commands
    def test_disconnect_without_ui_rebind(self):
        callback = self.open(); self.core.disconnect(); callback(None, 1); self.refuse()

    @all_commands
    def test_loss_without_ui_rebind(self):
        callback = self.open(); self.core.mark_connection_lost(); callback(None, 1); self.refuse()

    @all_commands
    def test_same_device_reconnect(self):
        callback = self.open(); self.core.mark_connection_lost(); self.reconnect()
        callback(None, 1); callback(None, 1); self.refuse()

    @all_commands
    def test_different_device_replacement(self):
        callback = self.open(); factory = self.core._client_factory
        def different(*args, **kwargs):
            client = factory(*args, **kwargs)
            client._info = dict(test_core.INFO, info=dict(test_core.INFO['info'], unique_id='OTHER'))
            return client
        with patch.object(self.core, '_client_factory', different):
            self.core.connect(replace(self.f.fixture.profile, id='other', host='192.0.2.21', device_id='OTHER', device_mac=''))
        self.instrument(); callback(None, 1); self.refuse()

    @all_commands
    def test_delayed_worker_rechecks_session(self):
        queued = []; self.tab.app.run = lambda task, done: queued.append((task, done))
        callback = self.open(); callback(None, 1); callback(None, 1)
        self.assertEqual(len(queued), 1); self.reconnect()
        task, done = queued[0]; result = task(); done(result)
        self.assertIsInstance(result, CoreError); self.assertEqual(result.code, 'session'); self.refuse()

    @all_commands
    def test_busy_ui_consumes_response(self):
        callback = self.open(); self.tab.app.busy = True; callback(None, 1)
        self.tab.app.busy = False; callback(None, 1); self.refuse()

    @all_commands
    def test_core_only_stale_session(self):
        session = self.core.device_session(); self.reconnect()
        with self.assertRaises(CoreError): self.execute(session)
        self.refuse()

    @all_commands
    def test_core_only_disconnected_session(self):
        session = self.core.device_session(); self.core.disconnect()
        with self.assertRaises(CoreError): self.execute(session)
        with self.assertRaises(CoreError): self.execute()
        self.refuse()

    @all_commands
    def test_core_admission_contention(self):
        with self.core._session_admission():
            with self.assertRaises(CoreError) as caught: self.execute()
        self.assertEqual(caught.exception.code, 'admission_busy'); self.refuse()

    @all_commands
    def test_core_lane_contention(self):
        with self.core.scheduler.inline(JobBinding.device(self.core.device_session())):
            with self.assertRaises(Exception) as caught: self.execute()
        self.assertEqual(caught.exception.code, 'admission_busy'); self.refuse()

    @all_commands
    def test_delayed_worker_admission_contention_consumes_response(self):
        queued = []; self.tab.app.run = lambda task, done: queued.append((task, done))
        callback = self.open(); callback(None, 1)
        with self.core._session_admission():
            result = queued[0][0]()
        self.assertEqual(result.code, 'admission_busy')
        queued[0][1](result); callback(None, 1)
        self.assertEqual(len(queued), 1); self.refuse()

    @all_commands
    def test_delayed_worker_lane_contention_consumes_response(self):
        queued = []; self.tab.app.run = lambda task, done: queued.append((task, done))
        callback = self.open(); callback(None, 1)
        with self.core.scheduler.inline(JobBinding.device(self.core.device_session())):
            result = queued[0][0]()
        self.assertEqual(result.code, 'admission_busy')
        queued[0][1](result); callback(None, 1)
        self.assertEqual(len(queued), 1); self.refuse()

    @all_commands
    def test_command_failure_never_retries(self):
        command = self.client.set_drive_type if self.action == 'type' else self.client.drive_action
        command.side_effect = TimeoutError('synthetic uncertain command')
        callback = self.open(); callback(None, 1); callback(None, 1)
        self.sent(reads=0); self.assertFalse(self.tab.loaded)

    @all_commands
    def test_readback_failure_never_retries(self):
        self.client.read_drives.side_effect = TimeoutError('synthetic uncertain readback')
        callback = self.open(); callback(None, 1); callback(None, 1)
        self.sent(); self.assertFalse(self.tab.loaded)

    @all_commands
    def test_same_transport_and_session_exclusion_during_command_and_read(self):
        def guarded(*args):
            for operation in (self.core.reconnect, self.core.disconnect, self.core.mark_connection_lost):
                with self.assertRaises(CoreError) as caught: operation()
                self.assertEqual(caught.exception.code, 'admission_busy')
            return {'synthetic': True}
        self.client.drive_action.side_effect = guarded
        self.client.set_drive_type.side_effect = guarded
        self.client.read_drives.side_effect = guarded
        self.open()(None, 1); self.sent()

    @all_commands
    def test_core_revalidates_after_lane_entry(self):
        original = self.core.device_session
        calls = 0
        def changed():
            nonlocal calls
            calls += 1
            session = original()
            return session if calls < 3 else replace(session, session_id='replacement')
        with patch.object(self.core, 'device_session', side_effect=changed):
            with self.assertRaises(CoreError): self.execute()
        self.refuse()

    @all_commands
    def test_core_only_valid_command(self):
        self.assertEqual(self.execute(), {'synthetic': True}); self.sent()

    @all_commands
    def test_invalid_arguments(self):
        for drive, action, mode in [('c', self.action, self.mode), ('a', 'reset', None),
                                    ('b', 'type', '1582'), ('a', 'on', '1541')]:
            with self.assertRaises(CoreError):
                self.core.execute_drive_command(self.core.device_session(), drive, action, mode=mode)
        self.refuse()

    def test_preserved_mount_confirmations_all_access_modes(self):
        from tests import test_drives_picker
        for drive in ('a', 'b'):
            for index, mode in enumerate(('readonly', 'readwrite', 'unlinked')):
                with self.subTest(drive=drive, mode=mode):
                    fixture = test_drives_picker.DrivesPicker()
                    try:
                        fixture.setUp()
                        with patch('socket.socket.connect', side_effect=AssertionError('OFFLINE')), \
                             patch('socket.getaddrinfo', side_effect=AssertionError('OFFLINE')):
                            fixture.tab.cards[drive]['access'].get_selected.return_value = index
                            fixture.tab.mount(drive).respond(False)
                            fixture.client.mount_disk.assert_not_called()
                            fixture.client.read_drives.assert_not_called()
                            dialog = fixture.tab.mount(drive)
                            fixture.tab.cards[drive]['access'].get_selected.return_value = (index + 1) % 3
                            dialog.respond()
                            fixture.client.mount_disk.assert_called_once_with(drive, '/SD/game.d64', mode)
                            fixture.client.read_drives.assert_called_once_with()
                    finally:
                        fixture.doCleanups()
