"""Exercise complete installed-package UI checks without a packaged runtime."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

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
        for check_id in ('ui.connection_header', 'ui.active_file_pane',
                         'development.preferences_ui'):
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

    def exercise(self, check_id, passed, **extra):
        checks = []
        namespace = dict(vars(package_self_test), app=self.app, checks=checks, **extra)
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

    def test_complete_settings_predicate(self):
        for pages, model_editable, case_editable, passed in (
            (4, False, True, True), (3, False, True, False),
            (5, False, True, False), (4, True, True, False),
            (4, False, False, False),
        ):
            with self.subTest(pages=pages, model=model_editable, case=case_editable):
                dialog = SimpleNamespace(
                    pages=Mock(get_n_pages=Mock(return_value=pages)),
                    connections=SimpleNamespace(
                        model=Mock(get_editable=Mock(return_value=model_editable)),
                        fields={'case_edition': Mock(
                            get_editable=Mock(return_value=case_editable))}))
                self.exercise('development.preferences_ui', passed,
                              preferences_dialog=dialog)


class PackageDriveSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Execute the real setup, call, verdict and finally from run(), without
        # starting the packaged application or creating a device transport.
        source = Path(package_self_test.__file__)
        tree = ast.parse(source.read_text(encoding='utf-8'))
        blocks = [node for node in ast.walk(tree) if isinstance(node, ast.Try)
                  and any(isinstance(child, ast.Name)
                          and child.id == 'saved_device_session'
                          for final in node.finalbody for child in ast.walk(final))]
        if len(blocks) != 1:
            raise AssertionError('Expected one scoped drive selection block')
        block = blocks[0]
        parent = next(node for node in ast.walk(tree)
                      if isinstance(getattr(node, 'body', None), list)
                      and block in node.body)
        index = parent.body.index(block)
        cls.setup_and_call = compile(ast.Module(
            body=parent.body[index - 4:index + 1], type_ignores=[]), str(source), 'exec')

    def setUp(self):
        import gi
        gi.require_version('Gtk', '4.0')
        from c64u_browser.drives_tab import DrivesTab
        from c64u_browser.scheduler import DeviceSession
        self.original = Mock(return_value=DeviceSession('', ''))
        # Strict core has no connection, execution, or transport methods.
        self.core = SimpleNamespace(device_session=self.original)
        self.tab = DrivesTab.__new__(DrivesTab)
        self.app = SimpleNamespace(core=self.core, drives_tab=self.tab)
        self.tab.app = self.app
        self.path = Mock()
        self.path.set_text.side_effect = lambda text: setattr(self.path.get_text, 'return_value', text)
        self.tab.cards = {'a': {'path': self.path, 'selection': None}}
        self.tab.message = Mock()
        self.tab.message.set_text.side_effect = lambda text: setattr(
            self.tab.message.get_text, 'return_value', text)
        self.tab.setting_path = False
        self.checks = []

    def exercise(self):
        try:
            exec(self.setup_and_call, dict(vars(package_self_test),
                                          app=self.app, checks=self.checks))
        finally:
            self.assertIs(self.core.device_session, self.original)
            self.original.assert_not_called()

    def test_actual_setup_selects_typed_image_and_restores_provider(self):
        from c64u_browser.picker_model import PickerSelection, PickerError
        self.exercise()
        selection = self.tab.cards['a']['selection']
        self.assertIsInstance(selection, PickerSelection)
        self.assertTrue(selection.device_id)
        self.assertTrue(selection.session_id)
        self.assertEqual(selection.path, '/USB2/PACKAGE.D64')
        self.assertEqual(self.checks, [{'id': 'ui.disk_mount_selection', 'status': 'pass'}])
        # The captured reference is unusable after leaving the simulated scope.
        with self.assertRaises(PickerError):
            self.tab.select_image(selection)

    def test_invalid_and_stale_selections_restore_provider(self):
        from dataclasses import replace
        from c64u_browser.drives_selection import remote_selection
        from c64u_browser.api import BrowserError
        from c64u_browser.picker_model import PickerError
        for change in (lambda s: s.path, lambda s: replace(s, scope='core-host'),
                       lambda s: replace(s, storage_root='/USB0'),
                       lambda s: replace(s, session_id='stale'),
                       lambda s: replace(s, device_id='other')):
            with self.subTest(change=change):
                self.setUp()
                with patch('c64u_browser.drives_selection.remote_selection',
                           side_effect=lambda path, session: change(remote_selection(path, session))):
                    with self.assertRaises((BrowserError, PickerError)):
                        self.exercise()
                self.path.set_text.assert_not_called()
                self.assertEqual(self.checks, [])

    def test_restores_provider_when_construction_or_ui_raises(self):
        for target in ('construction', 'ui'):
            with self.subTest(target=target):
                self.setUp()
                failing = (patch('c64u_browser.drives_selection.remote_selection',
                                 side_effect=RuntimeError('fixture')) if target == 'construction'
                           else patch.object(self.path, 'set_text', side_effect=RuntimeError('fixture')))
                with failing, self.assertRaisesRegex(RuntimeError, 'fixture'):
                    self.exercise()
                self.assertFalse(self.tab.setting_path)
                self.assertEqual(self.checks, [])

    def test_restores_provider_when_complete_verdict_fails(self):
        for control in (self.path, self.tab.message):
            with self.subTest(control=control):
                with patch.object(control.get_text, 'return_value', 'incorrect'):
                    with patch.object(control.set_text, 'side_effect', None):
                        with self.assertRaises(package_self_test.PackageSelfTestFailure):
                            self.exercise()
                self.assertEqual(self.checks, [])


if __name__ == '__main__':
    unittest.main()
