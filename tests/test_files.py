import unittest
from unittest.mock import Mock, patch
from c64u_browser.api import Entry, BrowserError
from c64u_browser.files import operate, child

class Files(unittest.TestCase):
    def test_invalid_names(self):
        for name in ['..', 'a/b', 'a\\b', 'x*', 'name.', '']:
            with self.assertRaises(BrowserError): child('/USB2', name)
    def test_existing_case_insensitive_rename(self):
        client = Mock()
        client.list_directory.return_value = ('/USB2', [Entry('a', 'file', 1), Entry('B', 'file', 1)])
        with patch('c64u_browser.files.connect') as connect:
            with self.assertRaises(BrowserError): operate(client, 'rename', '/USB2/a', 'b')
            connect.assert_not_called()
    def test_confirmation(self):
        client = Mock()
        client.list_directory.return_value = ('/USB2', [Entry('a', 'file', 1)])
        with patch('c64u_browser.files.connect') as connect:
            with self.assertRaises(BrowserError): operate(client, 'delete', '/USB2/a', confirmation='yes')
            connect.assert_not_called()
    def test_nonempty_folder(self):
        client = Mock()
        client.list_directory.side_effect = [('/USB2', [Entry('a', 'dir', 0)]), ('/USB2/a', [Entry('b', 'file', 1)])]
        with patch('c64u_browser.files.connect') as connect:
            with self.assertRaises(BrowserError): operate(client, 'delete', '/USB2/a', confirmation='/USB2/a')
            connect.assert_not_called()
    def test_delete_file(self):
        client = Mock()
        client.list_directory.return_value = ('/USB2', [Entry('a', 'file', 1)])
        with patch('c64u_browser.files.connect') as connect:
            operate(client, 'delete', '/USB2/a', confirmation='/USB2/a')
            connect.return_value.delete.assert_called_once_with('/USB2/a')
            connect.return_value.rmd.assert_not_called()
    def test_mkdir(self):
        client = Mock()
        client.list_directory.return_value = ('/USB2', [])
        with patch('c64u_browser.files.connect') as connect:
            operate(client, 'mkdir', '/USB2/new')
            connect.return_value.mkd.assert_called_once_with('/USB2/new')
    def test_case_only_rename(self):
        client = Mock()
        original = ('/USB2', [Entry('Test', 'dir', 0)])
        client.list_directory.side_effect = [original, original, original, ('/USB2', [Entry('test', 'dir', 0)])]
        with patch('c64u_browser.files.connect') as connect:
            result = operate(client, 'rename', '/USB2/Test', 'test')
            calls = connect.return_value.rename.call_args_list
            self.assertEqual(result, '/USB2/test')
            self.assertEqual(len(calls), 2)
            temporary = calls[0].args[1]
            self.assertTrue(temporary.startswith('/USB2/c64u-rename-'))
            self.assertEqual(calls[0].args[0], '/USB2/Test')
            self.assertEqual(calls[1].args, (temporary, '/USB2/test'))
    def test_case_only_second_step_failure(self):
        client = Mock()
        client.list_directory.return_value = ('/USB2', [Entry('Test', 'file', 1)])
        with patch('c64u_browser.files.connect') as connect:
            connect.return_value.rename.side_effect = [None, OSError('connection lost')]
            with self.assertRaisesRegex(BrowserError, 'c64u-rename-'):
                operate(client, 'rename', '/USB2/Test', 'test')
            self.assertEqual(connect.return_value.rename.call_count, 2)
            connect.return_value.delete.assert_not_called()
    def test_same_name_noop(self):
        client = Mock()
        client.list_directory.return_value = ('/USB2', [Entry('Test', 'dir', 0)])
        with patch('c64u_browser.files.connect') as connect:
            self.assertEqual(operate(client, 'rename', '/USB2/Test', 'Test'), '/USB2/Test')
            connect.assert_not_called()
