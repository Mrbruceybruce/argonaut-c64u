import unittest
from unittest.mock import Mock

from c64u_browser.text_input import c64_upper, uppercase_entry


class C64TextInputTests(unittest.TestCase):
    def test_uppercases_only_ascii_letters(self):
        self.assertEqual(c64_upper('print "Hello 64!"'), 'PRINT "HELLO 64!"')
        self.assertEqual(c64_upper('π £ _'), 'π £ _')

    def test_entry_uppercase_preserves_caret(self):
        entry = Mock()
        entry.get_text.return_value = 'hello'
        entry.get_position.return_value = 3
        uppercase_entry(entry)
        entry.set_text.assert_called_once_with('HELLO')
        entry.set_position.assert_called_once_with(3)

    def test_already_uppercase_entry_is_unchanged(self):
        entry = Mock()
        entry.get_text.return_value = 'RUN'
        uppercase_entry(entry)
        entry.set_text.assert_not_called()


if __name__ == '__main__':
    unittest.main()
