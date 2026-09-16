import io
import json
import logging
import unittest
from unittest.mock import patch

from c64u_browser.api import ConnectionFailure, UltimateClient
from c64u_browser.diagnostics import LOGGER, JsonEventFormatter


class DiagnosticEventsTest(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(JsonEventFormatter())
        LOGGER.addHandler(self.handler)
        self.previous_level = LOGGER.level
        LOGGER.setLevel(logging.INFO)

    def tearDown(self):
        LOGGER.removeHandler(self.handler)
        LOGGER.setLevel(self.previous_level)

    def event(self):
        return json.loads(self.stream.getvalue().strip())

    def test_rest_success_redacts_query_and_credentials(self):
        client = UltimateClient('c64u.local', password='secret')
        with patch.object(client, '_request_json_impl', return_value={'errors': []}):
            client._request_json('PUT', '/v1/drives/a:mount?image=/private/game.d64')
        event = self.event()
        self.assertEqual((event['transport'], event['operation'], event['outcome']),
                         ('rest', 'PUT', 'ok'))
        self.assertEqual(event['target'], '/v1/drives/a:mount')
        self.assertNotIn('secret', self.stream.getvalue())
        self.assertNotIn('game.d64', self.stream.getvalue())
        self.assertGreaterEqual(event['duration_ms'], 0)

    def test_rest_failure_preserves_exception_and_category(self):
        client = UltimateClient('c64u.local')
        failure = ConnectionFailure('network', 'unreachable')
        with patch.object(client, '_request_json_impl', side_effect=failure):
            with self.assertRaises(ConnectionFailure):
                client._request_json('GET', '/v1/info')
        self.assertEqual((self.event()['outcome'], self.event()['error_kind']),
                         ('error', 'network'))

    def test_ftp_listing_does_not_record_private_path(self):
        client = UltimateClient('c64u.local')
        with patch.object(client, '_list_directory', return_value=('/', [])):
            client.list_directory('/private/files')
        self.assertEqual(self.event()['target'], 'directory')
        self.assertNotIn('/private/files', self.stream.getvalue())


if __name__ == '__main__':
    unittest.main()
