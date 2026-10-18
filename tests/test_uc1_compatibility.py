"""UC-1 fake HTTP evidence and isolation; all real network calls are blocked."""
import json
import socket
import unittest
import urllib.error
from dataclasses import FrozenInstanceError, replace
from unittest.mock import Mock, patch
from types import SimpleNamespace

from c64u_browser.api import UltimateClient, ConnectionFailure, BrowserError
from c64u_browser.compatibility import CapabilityState, InspectionStatus, classify_failure, inspect
from c64u_browser.discovery import Candidate, verify
import test_core
import gi
gi.require_version("Gtk", "4.0")

INFO = {'product': 'Unknown product', 'firmware_version': '3.12', 'errors': []}
VERSION = {'version': '0.1', 'errors': []}


class Protocol(unittest.TestCase):
    def setUp(self):
        self.network = patch('socket.socket', side_effect=AssertionError('Real networking blocked'))
        self.network.start(); self.addCleanup(self.network.stop)
        self.mac = patch('c64u_browser.network_identity.peer_mac', return_value='')
        self.mac.start(); self.addCleanup(self.mac.stop)
        self.opener = patch('urllib.request.build_opener').start()
        self.addCleanup(patch.stopall)
        self.client = UltimateClient('192.0.2.20', 'typed-secret')

    def respond(self, *bodies):
        responses = []
        for body in bodies:
            if isinstance(body, Exception):
                responses.append(body)
                continue
            response = Mock()
            response.read.return_value = body if isinstance(body, bytes) else json.dumps(body).encode()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            responses.append(response)
        self.opener.return_value.open.side_effect = responses

    def recognize(self, info=INFO, version=VERSION):
        self.respond(version, info)
        return self.client.recognize_rest()

    def test_product_variants(self):
        for product in ('Ultimate-II+', 'Ultimate-II+L', 'Ultimate 64', 'Ultimate 64 Elite',
                        'Ultimate 64 Elite II', 'C64 Ultimate', 'Commodore 64 Ultimate', 'Unknown product'):
            with self.subTest(product=product):
                self.assertEqual(product, self.recognize(dict(INFO, product=product))['info']['product'])

    def test_optional_identity_absent(self):
        self.assertEqual(INFO, self.recognize()['info'])

    def test_optional_identity_malformed(self):
        for value in (None, 42, [], 'bad\nidentity'):
            with self.subTest(value=value), self.assertRaises(ConnectionFailure) as caught:
                self.recognize(dict(INFO, unique_id=value))
            self.assertEqual('malformed', caught.exception.kind)

    def test_generic_json_rejected(self):
        for info in ({}, {'errors': []}, {'product': 'HTTP server', 'errors': []}):
            with self.subTest(info=info), self.assertRaises(ConnectionFailure):
                self.recognize(info)

    def test_version_contract(self):
        for version, kind in ((None, 'malformed'), (1, 'malformed'), ('1', 'malformed'),
                              ('0.1.0', 'malformed'), ('0.2', 'unsupported_api'), ('1.0', 'unsupported_api')):
            with self.subTest(version=version), self.assertRaises(ConnectionFailure) as caught:
                self.recognize(version={'version': version, 'errors': []})
            self.assertEqual(kind, caught.exception.kind)

    def test_authentication_and_timeout(self):
        for error, kind in ((urllib.error.HTTPError('x', 401, 'Denied', {}, None), 'authentication'),
                            (urllib.error.HTTPError('x', 403, 'Denied', {}, None), 'authentication'),
                            (TimeoutError(), 'network')):
            self.opener.return_value.open.side_effect = error
            with self.assertRaises(ConnectionFailure) as caught:
                self.client.recognize_rest()
            self.assertEqual(kind, caught.exception.kind)

    def test_oversize_and_invalid_json(self):
        for body in (b'x' * 65537, b'not json', b'[]'):
            self.respond(body)
            with self.assertRaises(ConnectionFailure) as caught:
                self.client.recognize_rest()
            self.assertEqual('malformed', caught.exception.kind)

    def test_missing_protocol_endpoint(self):
        self.opener.return_value.open.side_effect = urllib.error.HTTPError('x', 404, 'Missing', {}, None)
        with self.assertRaises(ConnectionFailure) as caught:
            self.client.recognize_rest()
        self.assertEqual('unsupported_api', caught.exception.kind)

    def test_recognition_failures_agree_with_inspection_without_retry(self):
        cases = [(urllib.error.HTTPError('x', code, 'private text', {}, None), status)
                 for code, status in ((500, InspectionStatus.UNKNOWN), (502, InspectionStatus.UNKNOWN),
                     (404, InspectionStatus.UNSUPPORTED), (405, InspectionStatus.UNSUPPORTED),
                     (501, InspectionStatus.UNSUPPORTED), (401, InspectionStatus.AUTHENTICATION),
                     (403, InspectionStatus.AUTHENTICATION))]
        cases += [(b'not json', InspectionStatus.INVALID),
                  (TimeoutError('private text'), InspectionStatus.COMMUNICATION),
                  (urllib.error.URLError('private text'), InspectionStatus.COMMUNICATION),
                  (ConnectionFailure('api', 'malformed timeout unauthorized private text'), InspectionStatus.UNKNOWN)]
        for route in ('version', 'info'):
            for failure, expected in cases:
                with self.subTest(route=route, expected=expected, failure=type(failure).__name__):
                    self.opener.return_value.open.reset_mock()
                    self.respond(*([VERSION] if route == 'info' else []), failure)
                    with self.assertRaises(ConnectionFailure) as caught:
                        self.client.recognize_rest()
                    self.assertEqual(expected, classify_failure(caught.exception))
                    if expected == InspectionStatus.UNKNOWN:
                        self.assertEqual('api', caught.exception.kind)
                    calls = self.opener.return_value.open.call_args_list
                    self.assertEqual(['/v1/version'] + (['/v1/info'] if route == 'info' else []),
                                     [call.args[0].selector for call in calls])
                    self.assertTrue(all(call.args[0].method == 'GET' for call in calls))
                    self.opener.return_value.open.reset_mock();self.respond(failure)
                    result=inspect(self.client, {'version': VERSION, 'info': INFO})
                    self.assertEqual(expected, result.observations[0].status)
                    self.assertEqual(1,self.opener.return_value.open.call_count)
                    self.assertNotIn('private text',repr(result))

    def test_redirect_rejected(self):
        from c64u_browser.api import NoRedirect, BrowserError
        with self.assertRaises(BrowserError):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'http://other/')

    def test_config_authentication_rejected(self):
        identity = self.recognize()
        self.opener.return_value.open.side_effect = urllib.error.HTTPError('x', 403, 'Denied', {}, None)
        result = inspect(self.client, identity)
        self.assertEqual(InspectionStatus.AUTHENTICATION, result.observations[0].status)
        self.assertEqual(3, self.opener.return_value.open.call_count)

    def test_missing_configs_does_not_reject_protocol(self):
        identity = self.recognize()
        self.opener.return_value.open.side_effect = urllib.error.HTTPError('x', 404, 'Missing', {}, None)
        result = inspect(self.client, identity)
        self.assertEqual(CapabilityState.OBSERVED, result.protocol)
        self.assertEqual(CapabilityState.UNKNOWN, result.observations[0].state)

    def test_transport_protections(self):
        self.recognize()
        args = self.opener.call_args.args
        self.assertEqual({}, args[0].proxies)
        from c64u_browser.api import NoRedirect
        self.assertIsInstance(args[1], NoRedirect)
        for call in self.opener.return_value.open.call_args_list:
            self.assertEqual('GET', call.args[0].method)
            self.assertEqual(self.client.timeout, call.kwargs['timeout'])

    def test_discovery_recognizes_unknown(self):
        self.respond(VERSION, INFO)
        candidate = verify(Candidate('192.0.2.20'))
        self.assertIn('REST recognized', candidate.status)

    def test_operational_gate_unchanged(self):
        self.respond(VERSION, INFO)
        with self.assertRaises(ConnectionFailure): self.client.test_connection()
        for product in ('C64 Ultimate', 'Commodore 64 Ultimate', 'Ultimate 64', 'Ultimate 64 Elite', 'Ultimate 64 Elite II'):
            for firmware in ('1.1.0s2', '1.1.0'):
                self.respond(VERSION, dict(INFO, product=product, firmware_version=firmware))
                self.assertEqual(product, self.client.test_connection()['info']['product'])

    def test_category_metadata_and_secrets(self):
        identity = self.recognize()
        self.respond({'categories': ['Future settings', 'Network Settings'], 'errors': []},
                     {'Future settings': {'Unknown': 42, 'Password': {'current': 'never-return-this'}}, 'errors': []},
                     {'Network Settings': {'Name': {'current': 'x'}}, 'errors': []})
        result = inspect(self.client, identity)
        self.assertEqual(('Future settings', 'Network Settings'), result.categories)
        self.assertNotIn('never-return-this', repr(result))
        self.assertTrue(all(row.state == CapabilityState.UNQUALIFIED for row in result.operations))
        self.assertTrue(all(call.args[0].method == 'GET' for call in self.opener.return_value.open.call_args_list))
        self.assertEqual(5, self.opener.return_value.open.call_count)

    def test_category_work_bound(self):
        identity = self.recognize()
        categories = [f'Future {i}' for i in range(64)]
        self.respond({'categories': categories, 'errors': []}, *[
            {category: {}, 'errors': []} for category in categories[:4]])
        result = inspect(self.client, identity)
        self.assertEqual(64, len(result.categories))
        self.assertEqual(7, self.opener.return_value.open.call_count)
        self.assertEqual(CapabilityState.UNKNOWN, result.observations[-1].state)

    def test_unavailable_or_excessive_enumeration(self):
        identity = self.recognize()
        for categories in (None, ['x'] * 65, ['x' * 129], [3]):
            self.respond({'categories': categories, 'errors': []})
            result = inspect(self.client, identity)
            self.assertEqual((), result.categories)
            self.assertEqual(CapabilityState.UNKNOWN, result.observations[0].state)

    def test_malformed_metadata(self):
        identity = self.recognize()
        for metadata in ([], None, {str(i): {} for i in range(257)}):
            self.respond({'categories': ['Future'], 'errors': []}, {'Future': metadata, 'errors': []})
            result = inspect(self.client, identity)
            self.assertEqual(('Future',), result.categories)
            self.assertEqual(CapabilityState.UNKNOWN, result.observations[-1].state)

    @staticmethod
    def configuration_failures():
        private = 'private-password-and-exception-detail'
        return (
            *((urllib.error.HTTPError('http://private/', code, private, {}, None), InspectionStatus.UNSUPPORTED)
              for code in (404, 405, 501)),
            *((urllib.error.HTTPError('http://private/', code, private, {}, None), InspectionStatus.AUTHENTICATION)
              for code in (401, 403)),
            (TimeoutError(private), InspectionStatus.COMMUNICATION),
            (urllib.error.URLError(private), InspectionStatus.COMMUNICATION),
            (ConnectionResetError(private), InspectionStatus.COMMUNICATION),
            (b'{private-password-and-exception-detail', InspectionStatus.INVALID),
            (b'x' * 65537, InspectionStatus.INVALID),
            ({'errors': [private]}, InspectionStatus.INVALID),
            ({'errors': []}, InspectionStatus.INVALID),
            (urllib.error.HTTPError('http://private/', 500, private, {}, None), InspectionStatus.UNKNOWN),
            (BrowserError(private), InspectionStatus.UNKNOWN),
            (RuntimeError(private), InspectionStatus.UNKNOWN),
        )

    def test_enumeration_failure_classification_and_no_retries(self):
        identity = self.recognize()
        for response, status in self.configuration_failures():
            with self.subTest(status=status, response_type=type(response).__name__):
                self.opener.return_value.open.reset_mock()
                self.respond(response)
                result = inspect(self.client, identity)
                self.assertEqual(status, result.observations[0].status)
                self.assertEqual(CapabilityState.UNKNOWN, result.observations[0].state)
                self.assertEqual((), result.categories)
                self.assertEqual(1, self.opener.return_value.open.call_count)
                self.assertNotIn('private-password-and-exception-detail', repr(result))
                self.assertNotIn('private-password-and-exception-detail', result.description())
                self.assertIn('Configuration enumeration: ' + status.value, result.description())
                self.assertEqual('GET', self.opener.return_value.open.call_args.args[0].method)

    def test_metadata_failure_classification_keeps_success(self):
        identity = self.recognize()
        for response, status in self.configuration_failures():
            with self.subTest(status=status, response_type=type(response).__name__):
                self.opener.return_value.open.reset_mock()
                self.respond({'categories': ['Good', 'Failed', 'After'], 'errors': []},
                    {'Good': {'Password': {'current': 'private-value'}}, 'errors': []}, response,
                    {'After': {}, 'errors': []})
                result = inspect(self.client, identity)
                self.assertEqual(InspectionStatus.AVAILABLE, result.observations[1].status)
                self.assertEqual(status, result.observations[2].status)
                stopped = status == InspectionStatus.AUTHENTICATION or isinstance(response, RuntimeError)
                self.assertEqual(InspectionStatus.UNKNOWN if stopped else InspectionStatus.AVAILABLE,
                                 result.observations[3].status)
                self.assertEqual(3 if stopped else 4, self.opener.return_value.open.call_count)
                self.assertNotIn('private-password-and-exception-detail', repr(result))
                self.assertNotIn('private-value', repr(result))
                self.assertTrue(all(call.args[0].method == 'GET'
                    for call in self.opener.return_value.open.call_args_list))
                self.assertTrue(all(row.state == CapabilityState.UNQUALIFIED for row in result.operations))

    def test_invalid_bounds_retain_invalid_status(self):
        identity = self.recognize()
        for categories in (None, ['x'] * 65, ['x' * 129], [3], ['']):
            self.respond({'categories': categories, 'errors': []})
            self.assertEqual(InspectionStatus.INVALID, inspect(self.client, identity).observations[0].status)
        for items in ([], None, {str(i): {} for i in range(257)}):
            self.respond({'categories': ['Future'], 'errors': []}, {'Future': items, 'errors': []})
            self.assertEqual(InspectionStatus.INVALID, inspect(self.client, identity).observations[1].status)

    def test_statuses_use_structure_not_messages(self):
        for error in (RuntimeError('HTTP 404 timeout password'), BrowserError('authentication 401'),
                      ConnectionFailure('api', 'malformed unsupported 404'),
                      ConnectionFailure('future', 'network failure')):
            self.assertEqual(InspectionStatus.UNKNOWN, classify_failure(error))
        for kind, status in (('unsupported_api', InspectionStatus.UNSUPPORTED),
                             ('authentication', InspectionStatus.AUTHENTICATION),
                             ('network', InspectionStatus.COMMUNICATION),
                             ('host', InspectionStatus.COMMUNICATION),
                             ('malformed', InspectionStatus.INVALID)):
            self.assertEqual(status, classify_failure(ConnectionFailure(kind, 'irrelevant private text')))

    def test_results_and_observations_are_immutable(self):
        identity = self.recognize()
        self.respond({'categories': ['Good'], 'errors': []}, {'Good': {}, 'errors': []})
        result = inspect(self.client, identity)
        for target, name, value in ((result, 'categories', ()),
                                    (result.observations[0], 'status', InspectionStatus.UNKNOWN),
                                    (result.observations[1], 'detail', 'changed')):
            with self.assertRaises(FrozenInstanceError): setattr(target, name, value)
        for value in (result.categories, result.observations, result.identity, result.operations):
            self.assertIsInstance(value, tuple)


class Isolation(unittest.TestCase):
    setUp = test_core.CoreTests.setUp
    tearDown = test_core.CoreTests.tearDown

    def test_inspection_preserves_session_and_credentials(self):
        for connected in (False, True):
            if connected: self.core.connect(self.profile, initial_browse=False)
            before = self.core.device_session(), self.core._client, dict(self.core._session_passwords)
            client = UltimateClient(self.profile.host)
            self.core._client_factory = Mock(return_value=client)
            identity = {'version': VERSION, 'info': dict(INFO, unique_id='ABC123')}
            with patch.object(client, 'recognize_rest', return_value=identity), patch.object(
                    client, 'read_configuration', return_value={'categories': [], 'errors': []}), patch(
                    'c64u_browser.network_identity.peer_mac', return_value=''), patch(
                    'socket.socket', side_effect=AssertionError('Networking blocked')), patch(
                    'ftplib.FTP', side_effect=AssertionError('FTP blocked')), patch.object(
                    client, '_request_json', side_effect=AssertionError('Unexpected REST request')), patch.object(
                    client, '_request_binary_json', side_effect=AssertionError('Mutation blocked')):
                self.core.inspect_profile(self.profile, 'typed')
            self.assertEqual(before, (self.core.device_session(), self.core._client, self.core._session_passwords))
            self.assertEqual({}, self.credentials.values)
            self.assertEqual([], self.prefs.profiles)
            # Restore the original fake factory for the connected case.
            self.core._client_factory = lambda *a, **kw: test_core.FakeClient(*a, **kw)

    def test_http500_recognition_cannot_install_session_or_acquire_ftp(self):
        from c64u_browser.core import CoreError
        for route in ('version', 'info'):
            client=UltimateClient(self.profile.host)
            self.core._client_factory=Mock(return_value=client)
            response=Mock();response.read.return_value=json.dumps(VERSION).encode()
            response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            error=urllib.error.HTTPError('x',500,'private text',{},None)
            before=self.core.device_session(),self.core._client,dict(self.core._session_passwords)
            with patch('urllib.request.build_opener') as opener, patch('socket.socket',side_effect=AssertionError('No network')), patch('ftplib.FTP',side_effect=AssertionError('No FTP')) as ftp:
                opener.return_value.open.side_effect=([response] if route == 'info' else [])+[error]
                with self.assertRaises(CoreError) as caught:
                    self.core.inspect_profile(self.profile,'typed-secret')
                self.assertEqual(InspectionStatus.UNKNOWN,classify_failure(caught.exception,kind=caught.exception.code))
                self.assertEqual(1 if route == 'version' else 2,opener.return_value.open.call_count)
                self.assertTrue(all(c.args[0].method == 'GET' for c in opener.return_value.open.call_args_list))
                ftp.assert_not_called()
            self.assertEqual(before,(self.core.device_session(),self.core._client,self.core._session_passwords))
            self.assertEqual({},self.credentials.values);self.assertFalse(self.prefs.path.exists())

    def test_saved_identity_mismatch_rejected(self):
        client = Mock(recognize_rest=Mock(return_value={'version': VERSION, 'info': dict(INFO, unique_id='OTHER')}))
        self.core._client_factory = Mock(return_value=client)
        with patch('c64u_browser.network_identity.peer_mac', return_value=''), self.assertRaises(Exception):
            self.core.inspect_profile(self.profile)
        client.read_configuration.assert_not_called()

    def test_failed_inspection_cannot_install_session_or_acquire_ftp(self):
        identity = {'version': VERSION, 'info': dict(INFO, unique_id='ABC123')}
        for kind in ('authentication', 'network', 'malformed', 'unsupported_api', 'future'):
            client = UltimateClient(self.profile.host)
            self.core._client_factory = Mock(return_value=client)
            session = self.core.device_session()
            with patch.object(client, 'recognize_rest', return_value=identity), patch.object(
                    client, 'read_configuration', side_effect=ConnectionFailure(kind, 'secret-detail')) as read, patch(
                    'c64u_browser.network_identity.peer_mac', return_value=''), patch(
                    'socket.socket', side_effect=AssertionError('No network')) as network, patch(
                    'ftplib.FTP', side_effect=AssertionError('No FTP')) as ftp, patch.object(
                    client, '_request_json', side_effect=AssertionError('No mutation')) as request, patch.object(
                    client, '_request_binary_json', side_effect=AssertionError('No mutation')) as binary:
                result = self.core.inspect_profile(self.profile, 'typed-secret')
                read.assert_called_once_with(None)
                network.assert_not_called(); ftp.assert_not_called()
                request.assert_not_called(); binary.assert_not_called()
            self.assertIsNone(self.core._client)
            self.assertEqual(session, self.core.device_session())
            self.assertEqual({}, self.core._session_passwords)
            self.assertEqual({}, self.credentials.values)
            self.assertEqual([], self.prefs.profiles)
            self.assertNotIn('secret', repr(result))


class CallbackIsolation(unittest.TestCase):
    def dialog(self):
        from c64u_browser.connection_dialog import ConnectionDialog
        from c64u_browser.profiles import Profile
        dialog = ConnectionDialog.__new__(ConnectionDialog)
        dialog._closed = False
        dialog._inspection_generation = 0
        dialog._inspection_inflight = False
        dialog._inspection_session = 'session-1'
        dialog.compatibility_status = Mock()
        dialog.inspection_target = Mock()
        dialog.inspect_button = Mock()
        dialog.password = Mock(get_text=Mock(return_value='typed'))
        dialog.profile = Mock(return_value=Profile.new('Test', '192.0.2.20'))
        dialog.app = SimpleNamespace(core=Mock(device_session=Mock(return_value='session-1'),
                                              profiles=Mock(return_value=())))
        dialog._background = Mock()
        return dialog

    def test_stale_results_discarded(self):
        for change in ('session', 'edit', 'close'):
            dialog = self.dialog()
            dialog.inspect_compatibility()
            done = dialog._background.call_args.args[1]
            if change == 'session': dialog.app.core.device_session.return_value = 'session-2'
            elif change == 'edit': dialog.invalidate_inspection()
            else: dialog._closed = True
            with patch.object(dialog, 'compact_compatibility') as render:
                done(Mock())
                render.assert_not_called()

    def test_current_result_displayed(self):
        dialog = self.dialog(); dialog.inspect_compatibility()
        with patch.object(dialog, 'compact_compatibility', return_value='recognized; unqualified'):
            dialog._background.call_args.args[1](Mock())
        dialog.compatibility_status.set_text.assert_called_with('recognized; unqualified')
        self.assertFalse(dialog._inspection_inflight)


class GtkPresentation(unittest.TestCase):
    def test_result_in_real_gtk_label(self):
        from gi.repository import Gtk
        self.assertTrue(Gtk.init_check(), "Requires isolated X11/Xvfb display")
        client = Mock(read_configuration=Mock(side_effect=[{'categories': ['Future Settings']}, {'Future Settings': {}}]))
        result = inspect(client, {'version': VERSION, 'info': dict(INFO, product='Ultimate-II+L')})
        dialog = CallbackIsolation().dialog()
        dialog.compatibility_status = Gtk.Label(wrap=True, selectable=True)
        dialog.inspect_compatibility()
        dialog._background.call_args.args[1](result)
        text = dialog.compatibility_status.get_text()
        for value in ('Ultimate-II+L', '3.12', '0.1', 'categories discovered: 1',
                      'inspected successfully: 1', 'Requests attempted: 1',
                      'does not grant operational qualification'):
            self.assertIn(value, text)
        self.assertNotIn('Future Settings', text)

    def test_sanitized_observation_states_in_real_gtk(self):
        from gi.repository import Gtk
        self.assertTrue(Gtk.init_check(), "Requires isolated X11/Xvfb display")
        identity = {'version': VERSION, 'info': INFO}
        for status in InspectionStatus:
            client = Mock()
            if status == InspectionStatus.AVAILABLE:
                client.read_configuration.return_value = {'categories': []}
            else:
                kind = {InspectionStatus.UNSUPPORTED: 'unsupported_api',
                        InspectionStatus.AUTHENTICATION: 'authentication',
                        InspectionStatus.COMMUNICATION: 'network',
                        InspectionStatus.INVALID: 'malformed',
                        InspectionStatus.UNKNOWN: 'future'}[status]
                client.read_configuration.side_effect = ConnectionFailure(kind, 'private-error-secret')
            result = inspect(client, identity)
            dialog = CallbackIsolation().dialog()
            dialog.compatibility_status = Gtk.Label(wrap=True, selectable=True)
            dialog.inspect_compatibility()
            dialog._background.call_args.args[1](result)
            text = dialog.compatibility_status.get_text()
            self.assertIn('Inspection: ' + status.value, text)
            self.assertNotIn('private-error-secret', text)
            self.assertIn('does not grant operational qualification', text)
            if status != InspectionStatus.AVAILABLE:
                self.assertIn('categories discovered: Unknown', text)

    def test_top_level_errors_are_sanitized_in_real_gtk(self):
        from gi.repository import Gtk
        from c64u_browser.core import CoreError
        self.assertTrue(Gtk.init_check(), "Requires isolated X11/Xvfb display")
        for error, label in ((CoreError('authentication', 'secret-auth'), 'Authentication required'),
                             (CoreError('network', 'secret-network'), 'Communication failed'),
                             (RuntimeError('secret-unknown'), 'Unknown')):
            dialog = CallbackIsolation().dialog()
            dialog.compatibility_status = Gtk.Label()
            dialog.inspect_compatibility()
            dialog._background.call_args.args[1](error)
            self.assertEqual('Inspection: ' + label, dialog.compatibility_status.get_text())
        dialog.profile.side_effect = BrowserError('secret-profile')
        dialog._background.reset_mock()
        dialog.inspect_compatibility()
        dialog._background.assert_not_called()
        dialog.inspect_button.set_sensitive.assert_called_with(False)
        self.assertNotIn('secret', dialog.inspection_target.set_text.call_args.args[0])
