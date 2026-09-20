import json
import unittest
from unittest.mock import Mock, patch

from c64u_browser.api import Entry, UltimateClient
from c64u_browser.hardware_checks import run_hardware_checks
from c64u_browser.profiles import Profile


class HardwareChecksTests(unittest.TestCase):
    def test_without_connection_every_check_skips_and_no_network_opens(self):
        with patch('urllib.request.build_opener') as opener, patch('ftplib.FTP') as ftp:
            report = run_hardware_checks(None, None)
        self.assertEqual(report['suite'], 'hardware')
        self.assertEqual(report['status'], 'skip')
        self.assertEqual([check['status'] for check in report['checks']], ['skip'] * 4)
        self.assertEqual(report['checks'][0]['error_kind'], 'not_connected')
        opener.assert_not_called()
        ftp.assert_not_called()

    def test_unbound_profile_skips_before_network(self):
        client = UltimateClient('fixture.invalid')
        profile = Profile.new('Fixture', 'fixture.invalid')
        with patch.object(client, 'test_connection') as connect:
            report = run_hardware_checks(client, profile)
        self.assertEqual(report['status'], 'skip')
        self.assertEqual(report['checks'][0]['error_kind'], 'identity_unbound')
        connect.assert_not_called()

    def test_bound_suite_uses_only_rest_get_and_ftp_listing(self):
        client = UltimateClient('fixture.invalid', password='private')
        profile = Profile.new('Fixture', 'fixture.invalid', device_id='device-1')
        requests = []
        responses = {
            '/v1/version': {'errors': [], 'version': 'v1'},
            '/v1/info': {'errors': [], 'product': 'C64 Ultimate',
                         'firmware_version': '1.1', 'unique_id': 'device-1'},
            '/v1/drives': {'errors': [], 'drives': [{'a': {'enabled': True}}]},
        }

        def rest(method, path, payload=None):
            requests.append((method, path, payload))
            return responses[path]

        ftp = Mock()
        ftp.pwd.return_value = '/'
        ftp.mlsd.return_value = [('USB2', {'type': 'dir'})]
        with patch.object(client, '_request_json_impl', side_effect=rest), patch(
                'c64u_browser.network_identity.peer_mac', return_value=''), patch(
                'ftplib.FTP', return_value=ftp):
            report = run_hardware_checks(client, profile)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual([check['status'] for check in report['checks']], ['pass'] * 4)
        self.assertEqual(len(requests), 4)
        self.assertTrue(all(method == 'GET' and payload is None
                            for method, _, payload in requests))
        ftp.cwd.assert_called_once_with('/')
        ftp.close.assert_called_once()
        self.assertEqual(sum(len(check['operations']) for check in report['checks']), 5)
        self.assertNotIn('private', json.dumps(report))
        self.assertNotIn('fixture.invalid', json.dumps(report))
        self.assertNotIn('device-1', json.dumps(report))

    def test_identity_mismatch_fails_then_dependent_checks_skip(self):
        client = Mock(spec=UltimateClient)
        profile = Profile.new('Fixture', 'fixture.invalid', device_id='expected')
        client.test_connection.return_value = {
            'info': {'firmware_version': '1.1', 'unique_id': 'different'},
            'version': {'version': 'v1'}, 'network_mac': ''}
        report = run_hardware_checks(client, profile)
        self.assertEqual([check['status'] for check in report['checks']],
                         ['fail', 'skip', 'skip', 'skip'])
        self.assertEqual(report['checks'][0]['error_kind'], 'identity')
        client.read_drives.assert_not_called()
        client.list_directory.assert_not_called()
        client.read_about.assert_not_called()


if __name__ == '__main__':
    unittest.main()
