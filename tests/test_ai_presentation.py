import unittest

from c64u_browser.ai_presentation import readable_diagnosis


class AIPresentationTests(unittest.TestCase):
    def test_readable_diagnosis_preserves_meaning_without_markdown_markers(self):
        text = ('**Diagnosis:** The `simulation: true` flag marks a fixture.\n\n'
                '### Next checks\nKeep the probe; no C64U fault was detected.')
        self.assertEqual(readable_diagnosis(text),
            'Diagnosis: The simulation: true flag marks a fixture.\n\n'
            'Next checks\nKeep the probe; no C64U fault was detected.')
