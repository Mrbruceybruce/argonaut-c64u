import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from c64u_browser.ai_gateway import GatewayError
from c64u_browser.test_lab_replay import main


def report(status, *, identifier='hardware.identity', title='Identity'):
    return {'schema': 1, 'suite': 'hardware', 'status': status,
            'checks': [{'id': identifier, 'title': title, 'status': status,
                        'error_kind': 'network' if status == 'fail' else None,
                        'duration_ms': 1.0, 'operations': []}]}


class SavedReportReplayTests(unittest.TestCase):
    def test_saved_failure_analyzes_without_rerunning_or_changing_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            original = report('fail', identifier='private_password',
                              title='password=secret')
            path.write_text(json.dumps(original), encoding='utf-8')
            adapter = Mock(return_value='Check the network.')
            output = io.StringIO()
            with patch('c64u_browser.test_lab_replay.AIGateway',
                       return_value=adapter), patch(
                       'c64u_browser.hardware_checks.run_hardware_checks') as checks:
                code = main(['--report', str(path), '--ai-provider', 'ollama',
                             '--ai-model', 'local-test'], stdout=output)
            result = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(result['report_status'], 'fail')
            self.assertEqual(result['analysis']['status'], 'analyzed')
            self.assertEqual(result['analysis']['diagnosis'], 'Check the network.')
            self.assertNotIn('secret', json.dumps(adapter.call_args.args[0]))
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), original)
            checks.assert_not_called()

    def test_saved_pass_never_contacts_ai(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            path.write_text(json.dumps(report('pass')), encoding='utf-8')
            output = io.StringIO()
            with patch('c64u_browser.test_lab_replay.AIGateway') as gateway:
                code = main(['--report', str(path)], stdout=output)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())['analysis']['status'],
                             'no_failures')
            gateway.assert_not_called()

    def test_model_outage_is_separate_from_saved_failure_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            path.write_text(json.dumps(report('fail')), encoding='utf-8')
            output = io.StringIO()
            adapter = Mock(side_effect=GatewayError('network', 'Unavailable'))
            with patch('c64u_browser.test_lab_replay.AIGateway',
                       return_value=adapter):
                code = main(['--report', str(path), '--ai-provider', 'ollama',
                             '--ai-model', 'local-test'], stdout=output)
            result = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(result['report_status'], 'fail')
            self.assertEqual(result['analysis']['error_kind'], 'network')

    def test_damaged_report_stops_before_model_call(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            path.write_text(json.dumps({**report('pass'), 'status': 'fail'}),
                            encoding='utf-8')
            output, error = io.StringIO(), io.StringIO()
            with patch('c64u_browser.test_lab_replay.AIGateway') as gateway:
                code = main(['--report', str(path), '--ai-provider', 'ollama',
                             '--ai-model', 'local-test'], stdout=output,
                            stderr=error)
            self.assertEqual(code, 3)
            self.assertEqual(output.getvalue(), '')
            self.assertNotIn(str(path), error.getvalue())
            gateway.assert_not_called()


if __name__ == '__main__':
    unittest.main()
