"""Exercise complete installed-package UI checks without a packaged runtime."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from c64u_browser import package_self_test


class PackageUiPredicates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Compile the actual _require calls: copying predicates here would hide
        # stale expectations, and extracting helpers would expand production scope.
        source = Path(package_self_test.__file__)
        tree = ast.parse(source.read_text(encoding='utf-8'))
        run = next(node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == 'run')
        cls.checks = {}
        for check_id in ('ui.connection_header', 'ui.active_file_pane'):
            calls = [node for node in ast.walk(run)
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name)
                     and node.func.id == '_require'
                     and len(node.args) == 4
                     and isinstance(node.args[1], ast.Constant)
                     and node.args[1].value == check_id]
            if len(calls) != 1:
                raise AssertionError(f'Expected one complete check: {check_id}')
            cls.checks[check_id] = compile(
                ast.Expression(calls[0]), str(source), 'eval')

    def setUp(self):
        self.app = SimpleNamespace(
            connection_button=Mock(), new_d64_button=Mock(),
            remote_new_d64_button=Mock(), tabs=Mock(),
            settings_tab=SimpleNamespace(box=object()),
            file_pane_labels={True: Mock(), False: Mock()},
            file_pane_boxes={True: Mock(), False: Mock()})
        self.app.connection_button.get_label.return_value = 'Connect…'
        self.app.connection_button.get_sensitive.return_value = True
        self.app.new_d64_button.get_tooltip_text.return_value = 'New D64 disk…'
        self.app.remote_new_d64_button.get_tooltip_text.return_value = 'New D64 disk on C64 Ultimate…'
        self.app.remote_new_d64_button.get_sensitive.return_value = False
        self.app.tabs.get_tab_label_text.side_effect = (
            lambda box: 'Ultimate Menu' if box is self.app.settings_tab.box else None)
        self.app.file_pane_labels[True].get_text.return_value = 'This Computer · Active'
        self.app.file_pane_labels[False].get_text.return_value = 'C64 Ultimate'
        self.app.file_pane_boxes[True].has_css_class.side_effect = (
            lambda name: name == 'argonaut-file-pane-active')
        self.app.file_pane_boxes[False].has_css_class.side_effect = (
            lambda name: name == 'argonaut-file-pane-inactive')

    def exercise(self, check_id, passed):
        checks = []
        namespace = dict(vars(package_self_test), app=self.app, checks=checks)
        if passed:
            eval(self.checks[check_id], namespace)
            self.assertEqual(checks, [{'id': check_id, 'status': 'pass'}])
        else:
            with self.assertRaises(package_self_test.PackageSelfTestFailure) as caught:
                eval(self.checks[check_id], namespace)
            self.assertEqual(caught.exception.check_id, check_id)
            self.assertEqual(caught.exception.error_kind, 'verification')
            self.assertEqual(checks, [])

    def test_complete_connection_header_accepts_current_ui(self):
        self.exercise('ui.connection_header', True)

    def test_connection_header_rejects_each_incorrect_control(self):
        for control, method, value in (
            ('connection_button', 'get_label', 'Disconnect'),
            ('connection_button', 'get_sensitive', False),
            ('new_d64_button', 'get_tooltip_text', 'Wrong local tooltip'),
            ('remote_new_d64_button', 'get_tooltip_text', 'New D64 disk on C64U…'),
            ('remote_new_d64_button', 'get_sensitive', True),
            ('tabs', 'get_tab_label_text', 'Settings'),
        ):
            with self.subTest(control=control, method=method):
                self.setUp()
                mocked = getattr(getattr(self.app, control), method)
                mocked.side_effect = None
                mocked.return_value = value
                self.exercise('ui.connection_header', False)

    def test_connection_header_rejects_each_retired_control(self):
        for name in ('connection_menu', 'reconnect_button'):
            with self.subTest(control=name):
                self.setUp()
                setattr(self.app, name, None)
                self.exercise('ui.connection_header', False)

    def test_complete_active_file_pane_accepts_current_ui(self):
        self.exercise('ui.active_file_pane', True)

    def test_active_file_pane_rejects_each_stale_label(self):
        for local, text in ((True, 'Local files · Active'), (False, 'C64 Ultimate files')):
            with self.subTest(local=local):
                self.setUp()
                self.app.file_pane_labels[local].get_text.return_value = text
                self.exercise('ui.active_file_pane', False)

    def test_active_file_pane_rejects_each_missing_css_class(self):
        for local in (True, False):
            with self.subTest(local=local):
                self.setUp()
                self.app.file_pane_boxes[local].has_css_class.side_effect = None
                self.app.file_pane_boxes[local].has_css_class.return_value = False
                self.exercise('ui.active_file_pane', False)


if __name__ == '__main__':
    unittest.main()
