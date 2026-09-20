import unittest

from c64u_browser.ai_gateway import GatewayError
from c64u_browser.ai_presentation import readable_diagnosis, unavailable_message


class AIPresentationTests(unittest.TestCase):
    def test_readable_diagnosis_preserves_meaning_without_markdown_markers(self):
        text = ('**Diagnosis:** The `simulation: true` flag marks a fixture.\n\n'
                '### Next checks\nKeep the probe; no C64U fault was detected.')
        self.assertEqual(readable_diagnosis(text),
            'Diagnosis: The simulation: true flag marks a fixture.\n\n'
            'Next checks\nKeep the probe; no C64U fault was detected.')

    def test_local_network_failure_says_ollama_must_run_on_this_computer(self):
        message = unavailable_message(
            'ollama', GatewayError('network', 'AI service could not be reached.'))
        self.assertIn('Local AI unavailable', message)
        self.assertIn('Ollama must be installed and running on this computer', message)

    def test_missing_local_model_gives_configuration_action(self):
        message = unavailable_message(
            'ollama', GatewayError('configuration', 'Enter a valid model name.'))
        self.assertIn('Enter the name of a downloaded Ollama model', message)

    def test_cloud_failure_is_identified_separately(self):
        message = unavailable_message(
            'openai', GatewayError('authentication', 'OpenAI API key is unavailable.'))
        self.assertEqual(message,
            'Cloud AI unavailable: OpenAI API key is unavailable. '
            'Check the provider settings and try again.')
