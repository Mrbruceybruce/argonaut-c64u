import json
import unittest
from unittest.mock import Mock, patch
import urllib.error

from c64u_browser.ai_gateway import AIGateway, GatewayConfig, GatewayError
from c64u_browser.ai_analysis import analyze_failures


EVIDENCE = {'schema': 1, 'failures': [{'id': 'case', 'title': 'Case',
                                      'error_kind': 'api', 'operations': []}]}


def response(body):
    item = Mock()
    item.read.return_value = json.dumps(body).encode('utf-8')
    item.__enter__ = Mock(return_value=item)
    item.__exit__ = Mock(return_value=False)
    return item


class GatewayTests(unittest.TestCase):
    def test_local_ollama_nonstreaming_request(self):
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.return_value = response({
                'done': True, 'message': {'role': 'assistant', 'content': 'Check FTP login.'}})
            text = AIGateway(GatewayConfig('ollama', 'local-model'))(EVIDENCE)
        self.assertEqual(text, 'Check FTP login.')
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://127.0.0.1:11434/api/chat')
        payload = json.loads(request.data)
        self.assertFalse(payload['stream'])
        self.assertEqual(payload['model'], 'local-model')
        self.assertEqual(json.loads(payload['messages'][1]['content']), EVIDENCE)
        self.assertNotIn('Authorization', request.headers)

    def test_openai_stateless_request_and_output(self):
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.return_value = response({
                'status': 'completed', 'output': [{'type': 'message', 'content': [
                    {'type': 'output_text', 'text': 'Check REST response shape.'}]}]})
            text = AIGateway(GatewayConfig('openai', 'cloud-model'),
                             api_key='test-private-key')(EVIDENCE)
        self.assertEqual(text, 'Check REST response shape.')
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.openai.com/v1/responses')
        payload = json.loads(request.data)
        self.assertIs(payload['store'], False)
        self.assertEqual(json.loads(payload['input']), EVIDENCE)
        self.assertNotIn('test-private-key', json.dumps(payload))
        self.assertIn('Bearer test-private-key', request.get_header('Authorization'))

    def test_cloud_without_key_does_not_open_network(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}), patch(
                'urllib.request.build_opener') as build:
            with self.assertRaises(GatewayError) as caught:
                AIGateway(GatewayConfig('openai', 'cloud-model'))(EVIDENCE)
        self.assertEqual(caught.exception.kind, 'configuration')
        build.assert_not_called()

    def test_local_mode_rejects_ollama_cloud_model(self):
        with self.assertRaises(GatewayError) as caught:
            GatewayConfig('ollama', 'gemma4:cloud')
        self.assertEqual(caught.exception.kind, 'configuration')

    def test_oversized_evidence_does_not_open_network(self):
        huge = {'schema': 1, 'failures': [{'id': 'case', 'title': 'x' * 70000}]}
        with patch('urllib.request.build_opener') as build:
            with self.assertRaises(GatewayError) as caught:
                AIGateway(GatewayConfig('ollama', 'model'))(huge)
        self.assertEqual(caught.exception.kind, 'configuration')
        build.assert_not_called()

    def test_http_authentication_and_incomplete_response_are_categorized(self):
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.side_effect = urllib.error.HTTPError(
                'http://127.0.0.1', 403, 'Forbidden', {}, None)
            with self.assertRaises(GatewayError) as caught:
                AIGateway(GatewayConfig('ollama', 'local-model'))(EVIDENCE)
        self.assertEqual(caught.exception.kind, 'authentication')
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.return_value = response({'done': False})
            with self.assertRaises(GatewayError) as caught:
                AIGateway(GatewayConfig('ollama', 'local-model'))(EVIDENCE)
        self.assertEqual(caught.exception.kind, 'response')

    def test_failed_model_call_cannot_change_code_verdict(self):
        report = {'schema': 1, 'status': 'fail', 'checks': [{
            'id': 'case', 'title': 'Case', 'status': 'fail',
            'error_kind': 'api', 'operations': []}]}
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.side_effect = urllib.error.URLError('offline')
            with self.assertRaises(GatewayError):
                analyze_failures(report, AIGateway(GatewayConfig('ollama', 'model')))
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['checks'][0]['status'], 'fail')


if __name__ == '__main__':
    unittest.main()
