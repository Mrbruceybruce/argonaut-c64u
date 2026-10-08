"""B4 routing and real GTK checks with synthetic profiles; no device traffic."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import ast
import hashlib
import unittest
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib, GdkPixbuf
from c64u_browser.gui import Browser
from c64u_browser.core import CoreError
from c64u_browser.profiles import Profile
from c64u_browser.version import ASSETS
import test_core
import test_recovery
import test_preferences_ui


class ReconnectTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_core.CoreTests();self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.core=self.fixture.core
        self.core.preferences.profiles=[self.fixture.profile]
        self.core.preferences.selected_id=self.fixture.profile.id
        self.app=SimpleNamespace(core=self.core,busy=False,active_profile=None,
            preferences_error=None,status=Mock(),update_connection_header=Mock(),
            connection_restored=Mock(),activate_connection=Mock(),remote_root='/USB2')
        self.app.connection_lost=lambda message:self.core.mark_connection_lost(message)
        self.app.recovery=test_recovery.recovery_for(self.app)
        self.app.reconnect_available=lambda:Browser.reconnect_available(self.app)
        def run(task,done):done(task());return True
        self.app.run=run

    def test_disconnected_connects_selected_bound_profile_without_persistence(self):
        with patch.object(self.core,'_save_profile',side_effect=AssertionError('persist')), patch.object(self.fixture.credentials,'set',side_effect=AssertionError('secret write')):
            Browser.reconnect_device(self.app)
        self.assertEqual(self.core.active_profile.id,self.fixture.profile.id)
        self.app.activate_connection.assert_called_once()
        self.assertFalse(self.app.recovery.inflight)
        self.assertIn('Password storage unchanged',self.app.status.set_text.call_args.args[0])

    def test_connected_uses_active_despite_unrelated_selection(self):
        self.core.connect(self.fixture.profile)
        self.app.active_profile=self.core.active_profile
        old=self.core.device_session()
        other=Profile.new('Other','192.0.2.44',device_id='OTHER')
        self.core.preferences.profiles.append(other);self.core.preferences.selected_id=other.id
        with patch.object(self.core,'_save_profile',side_effect=AssertionError('persist')), patch.object(self.fixture.credentials,'set',side_effect=AssertionError('secret write')):
            Browser.reconnect_device(self.app)
        self.assertEqual(self.fixture.created[-1].host,self.fixture.profile.host)
        self.assertEqual(self.core.device_session().device_id,old.device_id)
        self.assertNotEqual(self.core.device_session().session_id,old.session_id)
        self.app.connection_restored.assert_called_once()
        self.app.activate_connection.assert_not_called()
        self.app.update_connection_header.assert_called()

    def test_disconnect_then_reconnect_uses_selected(self):
        self.core.connect(self.fixture.profile);self.core.disconnect()
        Browser.reconnect_device(self.app)
        self.assertEqual(self.core.active_profile.id,self.fixture.profile.id)

    def test_absent_or_unbound_profile_refuses_without_worker(self):
        self.app.run=Mock()
        for profiles in ([],[Profile.new('Unbound','192.0.2.50')]):
            self.core.preferences.profiles=profiles
            self.core.preferences.selected_id=profiles[0].id if profiles else None
            self.assertFalse(self.app.reconnect_available())
            Browser.reconnect_device(self.app)
        self.app.run.assert_not_called()

    def test_recovery_or_worker_busy_refuses(self):
        self.app.run=Mock()
        self.app.recovery.inflight=True;Browser.reconnect_device(self.app)
        self.app.recovery.inflight=False;self.app.busy=True;Browser.reconnect_device(self.app)
        self.app.run.assert_not_called()

    def test_second_reconnect_cannot_queue_while_first_is_pending(self):
        queued=[]
        self.app.run=lambda task,done:queued.append((task,done)) or True
        Browser.reconnect_device(self.app);Browser.reconnect_device(self.app)
        self.assertEqual(len(queued),1)
        self.assertTrue(self.app.recovery.inflight)
        task,done=queued.pop();done(task())
        self.assertFalse(self.app.recovery.inflight)
        self.assertEqual(len(self.fixture.created),1)

    def test_authentication_and_identity_refusals_pause_existing_recovery(self):
        self.core.connect(self.fixture.profile);self.app.active_profile=self.core.active_profile
        for code in ('authentication','identity'):
            with patch.object(self.core,'reconnect',side_effect=CoreError(code,'Safe refusal')):
                Browser.reconnect_device(self.app)
            self.assertTrue(self.app.recovery.paused)
            self.assertFalse(self.app.recovery.inflight)
            self.app.connection_restored.assert_not_called()
            self.assertEqual(self.core.device_session().session_id,'')

    def test_submission_failure_releases_inflight_gate(self):
        self.app.run=Mock(return_value=False)
        Browser.reconnect_device(self.app)
        self.assertFalse(self.app.recovery.inflight)
        self.app.run=Mock(side_effect=RuntimeError('synthetic failure'))
        Browser.reconnect_device(self.app)
        self.assertFalse(self.app.recovery.inflight)
        self.assertFalse(self.fixture.created)


if __name__=='__main__':unittest.main()
