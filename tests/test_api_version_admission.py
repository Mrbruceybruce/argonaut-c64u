# SPDX-License-Identifier: GPL-3.0-or-later
"""Issue #24 admission regressions: real validation, synthetic REST, no network."""
import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from c64u_browser.api import ConnectionFailure, UltimateClient
from c64u_browser.core import ArgonautCore, CoreError
from c64u_browser.profiles import Preferences, Profile


MISSING = object()
REJECTED = (
    (MISSING, 'malformed'), (None, 'malformed'), (True, 'malformed'),
    (1, 'malformed'), (0.1, 'malformed'), ([], 'malformed'), ({}, 'malformed'),
    ('', 'malformed'), ('1', 'malformed'), ('0.1.0', 'malformed'),
    (' 0.1', 'malformed'), ('0.1 ', 'malformed'), ('0.1\n', 'malformed'),
    ('0.1\x00', 'malformed'), ('０.１', 'malformed'),
    ('0.2', 'unsupported_api'), ('1.0', 'unsupported_api'),
    ('00.1', 'unsupported_api'), ('0.01', 'unsupported_api'),
)


def evidence(version='0.1', **identity):
    version_data = {'errors': []}
    if version is not MISSING:
        version_data['version'] = version
    return {'version': version_data, 'info': {
        'product': 'C64 Ultimate', 'firmware_version': '1.1.0s2',
        'unique_id': 'ABC123', 'errors': [], **identity}}


class APIVersionAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.network = patch('socket.socket', side_effect=AssertionError('Network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.mac_patch = patch('c64u_browser.network_identity.peer_mac', return_value='02:11:22:33:44:55')
        self.mac = self.mac_patch.start()
        self.addCleanup(self.mac_patch.stop)
        self.client = UltimateClient('192.0.2.20', 'synthetic-secret')
        self.about_patch = patch.object(self.client, 'read_about')
        self.about = self.about_patch.start()
        self.addCleanup(self.about_patch.stop)

    def respond(self, data):
        self.about.reset_mock()
        self.about.side_effect = lambda route: copy.deepcopy(data[route])

    def test_operational_rejection_matrix_precedes_mac_lookup(self):
        for version, kind in REJECTED:
            with self.subTest(version=version, kind=kind):
                self.respond(evidence(version))
                with self.assertRaises(ConnectionFailure) as caught:
                    self.client.test_connection()
                self.assertEqual(kind, caught.exception.kind)
                self.mac.assert_not_called()
                self.assertEqual(['version', 'info'], [c.args[0] for c in self.about.call_args_list])

    def test_inspection_and_operational_rejections_agree(self):
        for version, kind in REJECTED:
            for method in (self.client.recognize_rest, self.client.test_connection):
                with self.subTest(version=version, method=method.__name__):
                    self.respond(evidence(version))
                    with self.assertRaises(ConnectionFailure) as caught:
                        method()
                    self.assertEqual(kind, caught.exception.kind)
        self.mac.assert_not_called()

    def test_exact_supported_version_retains_evidence_and_mac(self):
        data = evidence()
        self.respond(data)
        self.assertEqual(data, self.client.recognize_rest())
        self.mac.assert_not_called()
        self.assertEqual({**data, 'network_mac': self.mac.return_value}, self.client.test_connection())
        self.mac.assert_called_once_with('192.0.2.20')

    def test_supported_api_preserves_product_allowlist(self):
        products = ('C64 Ultimate', 'Commodore 64 Ultimate', 'Ultimate 64',
                    'Ultimate 64 Elite', 'Ultimate 64 Elite II', 'c64 ultimate')
        for product in products:
            with self.subTest(product=product):
                self.respond(evidence(product=product))
                self.assertEqual(product, self.client.test_connection()['info']['product'])
        for product in ('Web Server', 'Ultimate-II+', '', None, 42):
            with self.subTest(product=product):
                self.mac.reset_mock()
                self.respond(evidence(product=product))
                with self.assertRaises(ConnectionFailure) as caught:
                    self.client.test_connection()
                self.assertEqual('api', caught.exception.kind)
                self.mac.assert_not_called()

    def test_supported_api_preserves_firmware_type_gate(self):
        for firmware in (None, 42, [], {}):
            with self.subTest(firmware=firmware):
                self.respond(evidence(firmware_version=firmware))
                with self.assertRaises(ConnectionFailure) as caught:
                    self.client.test_connection()
                self.assertEqual('api', caught.exception.kind)
        self.mac.assert_not_called()


class CoreAPIVersionAdmissionTests(unittest.TestCase):
    def setUp(self):
        network = patch('socket.socket', side_effect=AssertionError('Network forbidden'))
        network.start()
        self.addCleanup(network.stop)
        mac = patch('c64u_browser.network_identity.peer_mac', return_value='02:11:22:33:44:55')
        self.mac = mac.start()
        self.addCleanup(mac.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.prefs = Preferences(Path(self.temp.name) / 'config.json')
        self.profile = Profile.new('Synthetic device', '192.0.2.20', device_id='ABC123')
        self.prefs.profiles = [self.profile]
        self.prefs.selected_id = self.profile.id
        self.prefs.save()
        self.credentials = Mock()
        self.credentials.get.return_value = 'saved-secret'
        self.data = evidence()
        self.clients = []

        def factory(*args, **kwargs):
            client = UltimateClient(*args, **kwargs)
            # Exercise the real info/test_connection/recognize_rest policy paths.
            client.read_about = Mock(side_effect=lambda route: copy.deepcopy(self.data[route]))
            self.clients.append(client)
            return client

        self.core = ArgonautCore(preferences=self.prefs, credentials=self.credentials,
                                 client_factory=factory)
        self.addCleanup(self.core.close)
        lease = patch.object(self.core._ftp_manager, 'lease', side_effect=AssertionError('FTP forbidden'))
        self.lease = lease.start()
        self.addCleanup(lease.stop)
        listing = patch('c64u_browser.core.initial_directory', return_value=('/USB2', []))
        self.listing = listing.start()
        self.addCleanup(listing.stop)

    def snapshot(self):
        return (self.core.session(), self.core.device_session(), self.core._client,
                copy.deepcopy(self.prefs.profiles), self.prefs.selected_id,
                self.prefs.path.read_bytes(), dict(self.core._session_passwords))

    def assert_refusal(self, operation, kind):
        before = self.snapshot()
        self.mac.reset_mock()
        self.listing.reset_mock()
        with self.assertRaises(CoreError) as caught:
            operation()
        self.assertEqual(kind, caught.exception.code)
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(before, self.snapshot())
        self.assertIsNot(self.clients[-1], self.core._client)
        self.assertIsNone(self.clients[-1]._ftp_reads)
        self.mac.assert_not_called()
        self.lease.assert_not_called()
        self.listing.assert_not_called()
        self.credentials.set.assert_not_called()
        self.credentials.delete.assert_not_called()

    def test_connect_rejects_before_binding_persistence_or_browse(self):
        candidate = replace(self.profile, name='Candidate', device_id='', device_mac='')
        for version, kind in REJECTED:
            with self.subTest(version=version):
                self.data = evidence(version)
                self.assert_refusal(lambda: self.core.connect(candidate, entered_password='candidate-secret',
                    persist=True, remember=True, bind_identity=True), kind)

    def test_binding_revalidation_rejects_changed_api_without_persistence(self):
        candidate = replace(self.profile, device_id='', device_mac='')
        for version, kind in REJECTED:
            with self.subTest(version=version):
                calls = []
                initial = evidence()
                changed = evidence(version)

                def read_about(route):
                    if route == 'version':
                        calls.append(route)
                    return copy.deepcopy((initial if len(calls) == 1 else changed)[route])

                before = self.snapshot()
                self.mac.reset_mock()
                with patch.object(UltimateClient, 'info', side_effect=lambda: {
                        route: read_about(route) for route in ('version', 'info')}):
                    with self.assertRaises(CoreError) as caught:
                        self.core.connect(candidate, entered_password='candidate-secret',
                                          bind_identity=True, persist=True, remember=True)
                self.assertEqual(kind, caught.exception.code)
                self.assertFalse(caught.exception.retryable)
                self.assertEqual(2, len(calls))
                self.assertEqual(before, self.snapshot())
                self.assertIsNone(self.clients[-1]._ftp_reads)
                self.mac.assert_called_once_with(candidate.host)
                self.listing.assert_not_called()
                self.lease.assert_not_called()
                self.credentials.set.assert_not_called()
                self.credentials.delete.assert_not_called()

    def test_rejected_connect_preserves_existing_live_session(self):
        self.core.connect(self.profile, initial_browse=False)
        self.data = evidence('0.2')
        self.assert_refusal(lambda: self.core.connect(self.profile, entered_password='candidate-secret',
                            persist=True), 'unsupported_api')

    def test_reconnect_rejects_without_adoption_or_ftp(self):
        self.core.connect(self.profile, initial_browse=False)
        self.core.mark_connection_lost()
        for version, kind in REJECTED:
            with self.subTest(version=version):
                self.data = evidence(version)
                self.assert_refusal(self.core.reconnect, kind)

    def test_profile_inspection_and_test_refuse_without_state_changes(self):
        for method in (self.core.inspect_profile, self.core.test_profile):
            for version, kind in REJECTED:
                with self.subTest(method=method.__name__, version=version):
                    self.data = evidence(version)
                    self.assert_refusal(lambda: method(self.profile, entered_password='candidate-secret'), kind)

    def test_supported_connect_and_reconnect_keep_identity_and_renew_session(self):
        result = self.core.connect(self.profile, require_bound=True)
        first = self.core.device_session()
        self.assertEqual('0.1', result.device_info['version']['version'])
        self.assertIs(self.clients[-1], self.core._client)
        self.core.mark_connection_lost()
        result = self.core.reconnect()
        second = self.core.device_session()
        self.assertEqual(first.device_id, second.device_id)
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertIs(self.clients[-1], self.core._client)
        self.assertEqual('/USB2', result.remote_path)
        self.lease.assert_not_called()
        self.credentials.set.assert_not_called()
        self.credentials.delete.assert_not_called()

    def test_supported_api_does_not_bypass_bound_identity(self):
        for operation in ('connect', 'reconnect'):
            with self.subTest(operation=operation):
                self.data = evidence()
                self.core.connect(self.profile, initial_browse=False)
                if operation == 'reconnect':
                    self.core.mark_connection_lost()
                before = self.snapshot()
                self.data = evidence(unique_id='OTHER')
                self.listing.reset_mock()
                with self.assertRaises(CoreError) as caught:
                    if operation == 'connect':
                        self.core.connect(self.profile, require_bound=True)
                    else:
                        self.core.reconnect()
                self.assertEqual('identity', caught.exception.code)
                self.assertEqual(before, self.snapshot())
                self.listing.assert_not_called()
                self.lease.assert_not_called()
