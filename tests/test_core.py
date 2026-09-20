# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless contract tests for the initial Argonaut Core boundary."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from c64u_browser.api import ConnectionFailure, Entry, UltimateClient
from c64u_browser.core import ArgonautCore, CoreError
from c64u_browser.discovery import Candidate
from c64u_browser.profiles import Preferences, Profile


INFO = {'version': {'version': '0.1'},
        'info': {'product': 'C64 Ultimate', 'firmware_version': '1.1.0',
                 'hostname': 'C64U', 'unique_id': 'ABC123'},
        'network_mac': '00:11:22:33:44:55'}


class FakeCredentials:
    session_only = False
    def __init__(self): self.values = {}
    def get(self, key): return self.values.get(key, '')
    def set(self, key, value): self.values[key] = value
    def delete(self, key): self.values.pop(key, None)


class FakeClient:
    def __init__(self, host, password='', port=21, http_port=80, info=None):
        self.host, self.password = host, password
        self.port, self.http_port = port, http_port
        self.timeout, self.encoding, self.storage_roots = 10, 'utf-8', []
        self._info = info or INFO

    def test_connection(self): return self._info
    def list_directory(self, path='/'):
        if path == '/': return '/', [Entry('USB2', 'dir', None)]
        return path, [Entry('HELLO.PRG', 'file', 12)]


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.prefs = Preferences(Path(self.temp.name) / 'config.json')
        self.credentials = FakeCredentials()
        self.created = []
        def factory(*args, **kwargs):
            client = FakeClient(*args, **kwargs)
            self.created.append(client)
            return client
        self.core = ArgonautCore(preferences=self.prefs,
                                 credentials=self.credentials,
                                 client_factory=factory)
        self.profile = Profile.new('Living room', '192.0.2.20',
                                   device_id='ABC123')

    def tearDown(self): self.temp.cleanup()

    def test_profile_credentials_and_selected_state_are_owned_by_core(self):
        saved = self.core.save_profile(self.profile, 'secret', remember=True)
        self.assertEqual(saved.id, self.prefs.selected_id)
        self.assertEqual('secret', self.credentials.values[saved.id])
        loaded = Preferences(self.prefs.path).load()
        self.assertEqual(saved, loaded.selected())
        self.assertNotIn('secret', self.prefs.path.read_text())

    def test_connection_returns_data_and_keeps_transport_private(self):
        self.core.save_profile(self.profile, 'secret')
        result = self.core.connect_selected()
        self.assertEqual('Living room', result.profile.name)
        self.assertEqual('/USB2', result.remote_path)
        self.assertEqual('HELLO.PRG', result.entries[0].name)
        self.assertNotIsInstance(self.core.device_operations, UltimateClient)
        self.assertFalse(hasattr(self.core.device_operations, 'password'))
        self.assertNotIn('secret', repr(result))
        self.assertEqual('connected', self.core.session().state)

    def test_identity_failure_is_structured_and_does_not_activate(self):
        def wrong_factory(*args, **kwargs):
            wrong = {**INFO, 'info': {**INFO['info'], 'unique_id': 'OTHER'}}
            return FakeClient(*args, **kwargs, info=wrong)
        core = ArgonautCore(preferences=self.prefs,
                            credentials=self.credentials,
                            client_factory=wrong_factory)
        with self.assertRaises(CoreError) as caught:
            core.connect(self.profile, require_bound=True)
        self.assertEqual('identity', caught.exception.code)
        self.assertFalse(caught.exception.retryable)
        self.assertEqual('disconnected', core.session().state)

    def test_reconnect_replaces_private_transport_and_emits_event(self):
        events = []
        self.core.add_listener(events.append)
        self.core.connect(self.profile)
        first = self.created[-1]
        self.core.mark_connection_lost('cable unplugged')
        result = self.core.reconnect('/USB2')
        self.assertIsNot(first, self.created[-1])
        self.assertEqual('/USB2', result.remote_path)
        self.assertEqual(['connected', 'offline', 'reconnected'],
                         [event.kind for event in events])

    def test_discovery_returns_plain_candidates_without_gtk(self):
        candidate = Candidate('192.0.2.30', source='test')
        core = ArgonautCore(preferences=self.prefs,
            credentials=self.credentials,
            standard_discovery=lambda **_: ([candidate], ['done']),
            subnet_discovery=lambda subnet: [candidate],
            networks=lambda: ['192.0.2.0/24'])
        candidates, notes, networks = core.discover()
        self.assertEqual((candidate,), candidates)
        self.assertEqual(('done',), notes)
        self.assertEqual(('192.0.2.0/24',), networks)
        self.assertEqual((candidate,), core.discover(subnet='192.0.2.0/24')[0])

    def test_core_module_imports_with_no_display_and_without_gtk(self):
        root = str(Path(__file__).resolve().parents[1])
        code = ("import sys; import c64u_browser.core; "
                "assert 'gi.repository.Gtk' not in sys.modules; "
                "assert 'Gtk' not in sys.modules")
        env = dict(os.environ)
        env.pop('DISPLAY', None); env.pop('WAYLAND_DISPLAY', None)
        completed = subprocess.run([sys.executable, '-c', code], cwd=root,
                                   env=env, capture_output=True, text=True)
        self.assertEqual(0, completed.returncode, completed.stderr)


if __name__ == '__main__': unittest.main()
