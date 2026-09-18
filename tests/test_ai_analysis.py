import json
import unittest
from unittest.mock import Mock

from c64u_browser.ai_analysis import analyze_failures, failure_evidence


class AnalysisBoundaryTests(unittest.TestCase):
    def test_only_failed_checks_and_whitelisted_operation_fields(self):
        report = {'schema': 1, 'status': 'fail', 'checks': [
            {'id': 'ok', 'title': 'Good', 'status': 'pass', 'error_kind': None,
             'operations': [{'secret': 'never include'}]},
            {'id': 'bad', 'title': 'Bad', 'status': 'fail',
             'error_kind': 'network', 'exception_message': 'password=private',
             'operations': [{'transport': 'rest', 'operation': 'GET',
                             'target': '/v1/info?token=secret', 'outcome': 'error',
                             'error_kind': 'network', 'password': 'private'}]},
        ]}
        evidence = failure_evidence(report)
        self.assertFalse(evidence['simulation'])
        self.assertEqual([item['id'] for item in evidence['failures']], ['check-1'])
        self.assertEqual(evidence['failures'][0]['operations'][0]['target'], '/v1/info')
        self.assertNotIn('private', json.dumps(evidence))
        self.assertNotIn('secret', json.dumps(evidence))

    def test_adapter_diagnosis_is_separate_from_verdict(self):
        report = {'schema': 1, 'status': 'fail', 'checks': [
            {'id': 'bad', 'title': 'Bad', 'status': 'fail',
             'error_kind': 'AssertionError', 'operations': []}]}
        adapter = Mock(return_value='Check the response shape.')
        analysis = analyze_failures(report, adapter)
        self.assertEqual(analysis['status'], 'analyzed')
        self.assertEqual(analysis['check_ids'], ['bad'])
        self.assertEqual(analysis['diagnosis'], 'Check the response shape.')
        self.assertEqual(report['checks'][0]['status'], 'fail')
        adapter.assert_called_once()

    def test_unexpected_operation_labels_cannot_reach_ai_evidence(self):
        report = {'schema': 1, 'status': 'fail', 'checks': [
            {'id': 'bad', 'title': 'Bad', 'status': 'fail', 'error_kind': 'network',
             'operations': [
                 {'transport': 'rest', 'operation': 'GET',
                  'target': '/v1/configs/private-category/*?password=secret',
                  'outcome': 'error', 'error_kind': 'network'},
                 {'transport': 'ftp', 'operation': 'RETR /USB2/private-file',
                  'target': '/USB2/private-file', 'outcome': 'error',
                  'error_kind': 'ftp'},
             ]}]}
        evidence = failure_evidence(report)
        operations = evidence['failures'][0]['operations']
        self.assertEqual(operations[0]['target'], '/v1/configs/category')
        self.assertEqual((operations[1]['operation'], operations[1]['target']),
                         ('other', 'other'))
        self.assertNotIn('private', json.dumps(evidence))
        self.assertNotIn('secret', json.dumps(evidence))

    def test_bridge_failure_uses_only_stable_probe_evidence(self):
        report = {'schema': 1, 'suite': 'bridge', 'status': 'fail', 'checks': [
            {'id': 'bridge.end_to_end', 'title': 'private model answer',
             'status': 'fail', 'error_kind': 'response', 'operations': [
                 {'transport': 'bridge', 'operation': 'readiness_probe',
                  'target': 'local_model', 'outcome': 'error',
                  'error_kind': 'response', 'reply': 'private answer'}]}]}
        evidence = failure_evidence(report)
        self.assertEqual(evidence['failures'], [{
            'id': 'bridge.end_to_end', 'error_kind': 'response',
            'operations': [{
                'transport': 'bridge', 'operation': 'readiness_probe',
                'target': 'local_model', 'outcome': 'error',
                'error_kind': 'response'}]}])
        self.assertNotIn('private', json.dumps(evidence))

    def test_disk_failure_uses_only_generic_format_and_operation_labels(self):
        report = {'schema': 1, 'suite': 'offline', 'status': 'fail', 'checks': [
            {'id': 'disk.d64_parser', 'title': 'private disk label',
             'status': 'fail', 'error_kind': 'DiskImageError', 'operations': [
                 {'transport': 'disk_image', 'operation': 'validate',
                  'target': 'd64', 'outcome': 'error',
                  'error_kind': 'DiskImageError', 'filename': 'private.d64'}]}]}
        evidence = failure_evidence(report)
        self.assertEqual(evidence['failures'], [{
            'id': 'disk.d64_parser', 'error_kind': 'DiskImageError',
            'operations': [{
                'transport': 'disk_image', 'operation': 'validate',
                'target': 'd64', 'outcome': 'error',
                'error_kind': 'DiskImageError'}]}])
        self.assertNotIn('private', json.dumps(evidence))

    def test_passing_report_does_not_call_adapter(self):
        adapter = Mock()
        result = analyze_failures({'schema': 1, 'status': 'pass', 'checks': [
            {'id': 'hardware.identity', 'status': 'pass'}]}, adapter)
        self.assertEqual(result['status'], 'no_failures')
        adapter.assert_not_called()

    def test_untrusted_check_title_and_identifier_stay_out_of_model_evidence(self):
        report = {'schema': 1, 'status': 'fail', 'checks': [
            {'id': 'private_password', 'title': 'password=secret',
             'status': 'fail', 'error_kind': 'BrowserError',
             'operations': []}]}
        adapter = Mock(return_value='Inspect the failed check.')
        analysis = analyze_failures(report, adapter)
        evidence = adapter.call_args.args[0]
        self.assertEqual(evidence['failures'][0]['id'], 'check-1')
        self.assertNotIn('private_password', json.dumps(evidence))
        self.assertNotIn('secret', json.dumps(evidence))
        self.assertEqual(analysis['check_ids'], ['private_password'])
        self.assertEqual(report['status'], 'fail')

    def test_excessive_failures_are_rejected_before_model_call(self):
        report = {'schema': 1, 'status': 'fail', 'checks': [
            {'id': f'custom.{index}', 'status': 'fail', 'operations': []}
            for index in range(33)]}
        adapter = Mock()
        with self.assertRaises(ValueError):
            analyze_failures(report, adapter)
        adapter.assert_not_called()


if __name__ == '__main__':
    unittest.main()
