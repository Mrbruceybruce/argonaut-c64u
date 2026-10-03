"""R3 source boundaries, inspected without importing GTK or contacting devices."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'c64u_browser'


class CompatibilityRetirementTests(unittest.TestCase):
    def test_fresh_folder_names_exist_only_as_history_label(self):
        for path in ROOT.rglob('*.py'):
            source = path.read_text()
            tree = ast.parse(source)
            hits = [node for node in ast.walk(tree)
                    if (isinstance(node, (ast.Name, ast.arg)) and
                        getattr(node, 'id', getattr(node, 'arg', '')) in
                        {'upload_new_folder', '_upload_new_folder'}) or
                       (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.alias)) and
                        node.name in {'upload_new_folder', '_upload_new_folder'}) or
                       (isinstance(node, ast.Attribute) and node.attr in
                        {'upload_new_folder', '_upload_new_folder'})]
            self.assertEqual([], hits, str(path))
            self.assertNotIn('_upload_new_folder', source, str(path))
            if path.name == 'ai_analysis.py':
                self.assertEqual(1, source.count('upload_new_folder'))
                self.assertIn('# History-only label for saved reports; no live emitter.', source)
                labels = [n for n in ast.walk(tree) if isinstance(n, ast.Constant)
                          and n.value == 'upload_new_folder']
                self.assertEqual(1, len(labels))
            else:self.assertNotIn('upload_new_folder', source, str(path))

    def test_retired_owner_surfaces_are_absent(self):
        from c64u_browser.core import ArgonautCore, CoreDeviceOperations
        from c64u_browser import file_copy, transfers
        for owner, name in ((ArgonautCore, 'credential_for'),
                            (CoreDeviceOperations, 'info'), (file_copy, 'conflicts'),
                            (transfers, 'upload_new_folder'), (transfers, '_upload_new_folder')):
            self.assertFalse(hasattr(owner, name), name)
        tree = ast.parse((ROOT/'connection_dialog.py').read_text())
        dialog = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ConnectionDialog')
        self.assertFalse(any(isinstance(n, ast.FunctionDef) and n.name == 'credential' for n in dialog.body))
        self.assertFalse(any(isinstance(n, ast.Constant) and n.value == 'credential_for'
                             for n in ast.walk(tree)))

    def test_resolver_has_only_four_core_callers_and_no_alias(self):
        calls = []
        definitions = []
        for path in ROOT.rglob('*.py'):
            tree = ast.parse(path.read_text())
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertNotIn('credential_for', node.value, str(path))
                if isinstance(node, ast.FunctionDef) and node.name == '_credential_for':
                    definitions.append((path.name, parents[node].name))
                if isinstance(node, (ast.Name, ast.Attribute, ast.FunctionDef)):
                    name = getattr(node, 'id', getattr(node, 'attr', getattr(node, 'name', '')))
                    self.assertNotEqual('credential_for', name, str(path))
                    if name != '_credential_for' or isinstance(node, ast.FunctionDef):continue
                    self.assertIsInstance(node, ast.Attribute)
                    self.assertIsInstance(node.value, ast.Name)
                    self.assertEqual('self', node.value.id)
                    self.assertIsInstance(parents[node], ast.Call)
                    self.assertIs(parents[node].func, node)
                    owner = parents[node]
                    while not isinstance(owner, ast.FunctionDef):owner = parents[owner]
                    calls.append((path.name, parents[owner].name, owner.name))
        self.assertEqual([('core.py', 'ArgonautCore')], definitions)
        self.assertCountEqual([('core.py', 'ArgonautCore', name) for name in
                               ('test_profile', 'read_model', 'connect', 'reconnect')], calls)
