import json
import unittest
from unittest.mock import Mock, patch

from c64u_browser.ai_analysis import analyze_failures, failure_evidence
from c64u_browser.test_lab_probe import run_diagnosis_probe


class DiagnosisProbeTests(unittest.TestCase):
    def test_simulated_transport_failure_is_code_determined_and_sanitized(self):
        with patch('socket.create_connection') as connect, patch(
                'urllib.request.build_opener') as opener:
            report = run_diagnosis_probe()
        connect.assert_not_called()
        opener.assert_not_called()
        self.assertEqual(report['suite'], 'diagnosis_probe')
        self.assertEqual(report['status'], 'fail')
        check = report['checks'][0]
        self.assertEqual((check['id'], check['status'], check['error_kind']),
                         ('probe.ftp_authentication', 'fail', 'authentication'))
        self.assertEqual(len(check['operations']), 1)
        self.assertEqual(check['operations'][0]['origin'], 'simulation')
        evidence = failure_evidence(report)
        self.assertTrue(evidence['simulation'])
        self.assertEqual(evidence['failures'][0], {
            'id': 'probe.ftp_authentication', 'error_kind': 'authentication',
            'operations': [{'transport': 'ftp', 'operation': 'list_directory',
                            'target': 'directory', 'outcome': 'error',
                            'error_kind': 'authentication'}]})
        self.assertNotIn('fixture.invalid', json.dumps(evidence))
        adapter = Mock(return_value='Check the FTP login setting.')
        result = analyze_failures(report, adapter)
        self.assertEqual(result['status'], 'analyzed')
        self.assertEqual(report['status'], 'fail')
        adapter.assert_called_once_with(evidence)
