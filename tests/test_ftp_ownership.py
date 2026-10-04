"""Final FTP ownership boundary: AST enforcement and pre-acquisition refusal."""
import ast
import inspect
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from c64u_browser.api import UltimateClient, BrowserError

ROOT = Path(__file__).resolve().parents[1] / 'c64u_browser'
MANAGED_MODULE = 'c64u_browser.c64u_ftp'
CLIENT = MANAGED_MODULE + '.C64UFtpClient'
CLIENT_OWNER = ('C64UFtpLeaseManager', 'lease')
# Only these existing offline entry points may depend on fixture transports.
# Paths are fully qualified: a same-named module in a subpackage is not allowed.
OFFLINE_IMPORTS = {
    ('c64u_browser.test_lab', 'c64u_browser.simulated_c64u'),
    ('c64u_browser.simulated_c64u', 'c64u_browser.simulated_ftp_reads'),
    ('c64u_browser.test_lab_probe', 'c64u_browser.simulated_ftp_reads'),
}
LEGACY = {
    'c64u_browser.transfers.' + name for name in ('connect', 'upload', '_upload')
} | {'c64u_browser.files.operate'}
FORBIDDEN_MEMBERS = {'open_ftp', 'storbinary', 'retrbinary', 'retrlines'}


def production_sources(root):
    # Tests live outside this tree; exclude no application files or subpackages.
    return sorted(root.rglob('*.py'))


def module_identity(relative_path):
    parts = list(Path(relative_path).with_suffix('').parts)
    is_package = parts[-1] == '__init__'
    if is_package:
        parts.pop()
    module = '.'.join(['c64u_browser', *parts])
    package = module if is_package else module.rpartition('.')[0]
    return module, package


def ownership_violations(source, relative_path):
    """Conservative static reference guard, not a Python execution/dataflow proof.

    Resolve imports and simple assignment aliases to a fixed point. Keep all
    possible bindings (including shadowed ones) so rebinding cannot erase a
    forbidden reference. Dynamic import strings/reflection are outside this scan.
    Reject client capability references outside its owner, including assignment
    before a later call; merely importing the client for a type is permitted.
    """
    module, package = module_identity(relative_path)
    tree = ast.parse(source)
    bindings = {}
    imported = []

    def bind(name, targets):
        old = bindings.setdefault(name, set())
        before = len(old)
        old.update(targets)
        return len(old) != before

    def resolve(node):
        if isinstance(node, ast.Name):
            return bindings.get(node.id, {module + '.' + node.id})
        if isinstance(node, ast.Attribute):
            return {target + '.' + node.attr for target in resolve(node.value)}
        return set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append((node, alias.name))
                bind(alias.asname or alias.name.split('.')[0],
                     {alias.name if alias.asname else alias.name.split('.')[0]})
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split('.')
                base = base[:len(base) - node.level + 1]
                prefix = '.'.join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ''
            for alias in node.names:
                target = prefix + '.' + alias.name
                imported.append((node, target))
                bind(alias.asname or alias.name, {target})

    # Also resolve module aliases, e.g. transport = imported_module.
    canonical = {CLIENT, *LEGACY}
    canonical.update(target for _, target in imported)
    canonical = {'.'.join(target.split('.')[:i]) for target in canonical
                 for i in range(1, len(target.split('.')) + 1)}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        changed |= bind(target.id, resolve(node.value) & canonical)

    errors = set()

    def reject(node, reason):
        errors.add((node.lineno, reason))

    def check_target(node, target):
        # No current managed internals need ftplib constants/types. The existing
        # transport boundary already forbids ftplib there; keep that architecture.
        if target == 'ftplib' or target.startswith('ftplib.'):
            reject(node, 'ftplib dependency')
        if target in LEGACY:
            reject(node, 'legacy factory reference')
        parts = target.split('.')
        for index, part in enumerate(parts):
            if part.startswith('simulated_'):
                fixture_module = '.'.join(parts[:index + 1])
                if fixture_module != module and (module, fixture_module) not in OFFLINE_IMPORTS:
                    reject(node, 'offline fixture boundary')
        if parts[-1] in FORBIDDEN_MEMBERS:
            reject(node, 'legacy member reference')

    for node, target in imported:
        check_target(node, target)
        if target.endswith('.*'):
            # A wildcard makes explicit symbol resolution impossible.
            reject(node, 'wildcard import obscures ownership')

    class Guard(ast.NodeVisitor):
        def __init__(self):
            self.owner = []

        def visit_ClassDef(self, node):
            for item in [*node.decorator_list, *node.bases, *node.keywords]:
                self.visit(item)
            self.owner.append(node.name)
            for item in node.body:
                self.visit(item)
            self.owner.pop()

        def visit_FunctionDef(self, node):
            if node.name in FORBIDDEN_MEMBERS or module + '.' + node.name in LEGACY:
                reject(node, 'legacy definition')
            # Defaults/decorators run outside the method body.
            for item in [*node.decorator_list, node.args, *([node.returns] if node.returns else [])]:
                self.visit(item)
            self.owner.append(node.name)
            for item in node.body:
                self.visit(item)
            self.owner.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Lambda(self, node):
            self.visit(node.args)
            self.owner.append('<lambda>')
            self.visit(node.body)
            self.owner.pop()

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load):
                self.check_reference(node)

        def visit_Attribute(self, node):
            if node.attr in FORBIDDEN_MEMBERS:
                reject(node, 'legacy member reference')
            self.check_reference(node)
            self.generic_visit(node)

        def check_reference(self, node):
            for target in resolve(node):
                check_target(node, target)
                if target == CLIENT and not (
                    module == MANAGED_MODULE and tuple(self.owner) == CLIENT_OWNER
                ):
                    reject(node, 'client reference outside manager lease')

    Guard().visit(tree)
    return sorted(errors)


def scan_production(root):
    return {
        str(path.relative_to(root)): errors
        for path in production_sources(root)
        if (errors := ownership_violations(path.read_text(), path.relative_to(root)))
    }


class GuardSelfTests(unittest.TestCase):
    def assert_rejected(self, source, reason, path='core.py'):
        errors = ownership_violations(source, path)
        self.assertTrue(any(message == reason for _, message in errors), errors)

    def test_ftplib_imports_and_aliased_constructor_assignment(self):
        for source in (
            'import ftplib as raw_transport; factory = raw_transport.FTP; factory()',
            'import ftplib; ftplib.FTP()',
            'from ftplib import FTP; FTP()',
            'from ftplib import FTP as X; X()',
            'from ftplib import FTP_TLS as X; X()',
        ):
            with self.subTest(source=source):
                self.assert_rejected(source, 'ftplib dependency')

    def test_client_import_and_module_alias_construction(self):
        for source in (
            'from . import c64u_ftp as transport; transport.C64UFtpClient()',
            'from .c64u_ftp import C64UFtpClient; C64UFtpClient()',
            'from c64u_browser.c64u_ftp import C64UFtpClient as Client; Client()',
            'import c64u_browser.c64u_ftp as transport; transport.C64UFtpClient()',
            'import c64u_browser.c64u_ftp; c64u_browser.c64u_ftp.C64UFtpClient()',
            'from c64u_browser import c64u_ftp as t; other=t; factory=other.C64UFtpClient; factory()',
        ):
            with self.subTest(source=source):
                self.assert_rejected(source, 'client reference outside manager lease')

    def test_simulator_import_forms(self):
        for source in (
            'from c64u_browser.simulated_ftp_reads import MemoryFilesystem',
            'from .simulated_ftp_reads import MemoryFilesystem as FS',
            'from . import simulated_ftp_reads as fixture',
            'import c64u_browser.simulated_ftp_reads as fixture',
            'from c64u_browser import simulated_ftp_reads',
        ):
            with self.subTest(source=source):
                self.assert_rejected(source, 'offline fixture boundary')

    def test_legacy_factory_imports_and_references(self):
        for source in (
            'from c64u_browser.transfers import connect as raw_connect',
            'from .transfers import connect as raw_connect',
            'from . import transfers as t; factory=t.connect; factory()',
            'import c64u_browser.transfers; c64u_browser.transfers.connect()',
            'from c64u_browser import transfers as t; t.upload()',
            'from .transfers import _upload as upload',
            'from .files import operate as operation',
        ):
            with self.subTest(source=source):
                self.assert_rejected(source, 'legacy factory reference')

    def test_unrelated_lease_and_nested_owner_are_rejected(self):
        for source in (
            'def lease():\n return C64UFtpClient()',
            'class Other:\n def lease(self):\n  return C64UFtpClient()',
            'class C64UFtpLeaseManager:\n def other(self):\n  return C64UFtpClient()',
            'class C64UFtpLeaseManager:\n def lease(self):\n  def inner():\n   return C64UFtpClient()',
            'class C64UFtpLeaseManager:\n def lease(self):\n  return lambda: C64UFtpClient()',
            'class C64UFtpLeaseManager:\n def lease(self, value=C64UFtpClient()):\n  pass',
        ):
            with self.subTest(source=source):
                self.assert_rejected(source, 'client reference outside manager lease', 'c64u_ftp.py')

    def test_nested_application_sources_are_discovered_and_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / 'subpkg' / 'core.py'
            nested.parent.mkdir()
            nested.write_text('from ..transfers import connect as raw_connect\n')
            self.assertEqual([nested], production_sources(root))
            self.assertIn('subpkg/core.py', scan_production(root))

    def test_exact_manager_lease_is_accepted_only_in_managed_module(self):
        source = 'class C64UFtpLeaseManager:\n def lease(self):\n  return C64UFtpClient()'
        self.assertEqual([], ownership_violations(source, 'c64u_ftp.py'))
        self.assert_rejected('from .c64u_ftp import C64UFtpClient\n' + source,
                             'client reference outside manager lease')

    def test_explicit_offline_edges_are_accepted(self):
        # Local fixture implementation is not an import across the boundary.
        self.assertEqual([], ownership_violations(
            'class MemoryFilesystem: pass\nfilesystem = MemoryFilesystem()',
            'simulated_ftp_reads.py'))
        for importer, fixture in sorted(OFFLINE_IMPORTS):
            path = importer.removeprefix('c64u_browser.') + '.py'
            for source in (f'from {fixture} import MemoryReads',
                           f'from .{fixture.split(".")[-1]} import MemoryReads'):
                with self.subTest(path=path, source=source):
                    self.assertEqual([], ownership_violations(source, path))
            self.assert_rejected(f'from {fixture} import MemoryReads',
                                 'offline fixture boundary', 'subpkg/' + path)

    def test_legacy_definitions_members_and_wildcards_are_rejected(self):
        self.assert_rejected('def connect(): pass', 'legacy definition', 'transfers.py')
        self.assert_rejected('def operate(): pass', 'legacy definition', 'files.py')
        self.assert_rejected('def open_ftp(): pass', 'legacy definition')
        self.assert_rejected('factory = thing.storbinary', 'legacy member reference')
        self.assert_rejected('from .c64u_ftp import *', 'wildcard import obscures ownership')

    def test_package_relative_imports_and_shadowed_aliases(self):
        self.assert_rejected('from ..transfers import connect',
                             'legacy factory reference', 'subpkg/__init__.py')
        self.assert_rejected('from .. import simulated_ftp_reads',
                             'offline fixture boundary', 'subpkg/core.py')
        self.assert_rejected('from . import transfers as t\nfactory=t.connect\nt=None\nfactory()',
                             'legacy factory reference')
        self.assertEqual([], ownership_violations('from .. import c64u_ftp_types',
                                                 'subpkg/__init__.py'))


class OwnershipTests(unittest.TestCase):
    def test_production_has_no_raw_factory_or_compatibility_entry(self):
        self.assertEqual({}, scan_production(ROOT))

    def test_simulator_imports_are_only_offline_entry_points(self):
        for path in production_sources(ROOT):
            with self.subTest(module=str(path.relative_to(ROOT))):
                errors = ownership_violations(path.read_text(), path.relative_to(ROOT))
                self.assertFalse([error for error in errors if error[1] == 'offline fixture boundary'])

    def test_raw_selection_flags_and_remote_local_helpers_are_closed(self):
        from c64u_browser.folder_copy import execute_plan,Step
        from c64u_browser.deletion import delete_reviewed
        from c64u_browser.replacement import replace_file
        from c64u_browser.file_copy import copy_files
        self.assertFalse({'managed_uploads','managed_replacements','managed_folders'} & set(inspect.signature(execute_plan).parameters))
        self.assertNotIn('managed',inspect.signature(delete_reviewed).parameters)
        client=UltimateClient('fixture.invalid')
        with patch('ftplib.FTP',side_effect=AssertionError('raw FTP')),patch('socket.create_connection',side_effect=AssertionError('network')):
            with self.assertRaises(BrowserError):replace_file(client,Step('a','a','/USB2/a',False),True,False,lambda n:None)
            for source_local in (False,True):
                message,partial=copy_files(client,source_local,'/USB2',['a'],False,'/USB2/dst')
                self.assertIn('managed copy plan',message)
                self.assertIsNone(partial)

    def test_adapter_absent_remote_calls_refuse_before_network(self):
        from c64u_browser.native_files import read_remote,read_remote_game
        from c64u_browser.disk_run import mount_and_run
        from c64u_browser.usb_backup import UsbBackupService
        from c64u_browser.files import operate_managed
        from c64u_browser.transfers import upload_managed
        from c64u_browser.deletion import delete_reviewed
        client=UltimateClient('fixture.invalid')
        calls=[lambda:client.list_directory(),lambda:client.list_directory_identity(),
               lambda:read_remote(client,'/USB2/a'),lambda:read_remote_game(client,'/USB2/a',64),
               lambda:mount_and_run(client,'/USB2/a.d64'),
               lambda:UsbBackupService._remote_hash(None,client,'/USB2/a',None,'verify',0,1),
               lambda:UsbBackupService._volume_fingerprint(client,'/USB2'),
               lambda:operate_managed(client,'mkdir','/USB2/new'),
               lambda:upload_managed(client,'a','/USB2')]
        with patch('ftplib.FTP',side_effect=AssertionError('raw FTP')),patch('socket.socket',side_effect=AssertionError('network')):
            for call in calls:
                with self.subTest(call=call),self.assertRaises(BrowserError):call()
            result=delete_reviewed(client,False,['/USB2/a'],())
            self.assertIsInstance(result.error,BrowserError)
            self.assertEqual([],result.removed)

    def test_text_only_identity_fixture_is_refused(self):
        from c64u_browser.usb_backup import UsbBackupService
        client=SimpleNamespace(list_directory=lambda path:(_ for _ in ()).throw(AssertionError('text fallback')))
        with self.assertRaises(BrowserError):UsbBackupService._volume_fingerprint(client,'/USB2')

    def test_offline_checks_cannot_create_network(self):
        from c64u_browser.test_lab import run_default_checks
        with patch('socket.socket',side_effect=AssertionError('network')),patch('socket.create_connection',side_effect=AssertionError('network')),patch('ftplib.FTP',side_effect=AssertionError('raw FTP')):
            result=run_default_checks()
        self.assertEqual('pass',result['status'])
        self.assertEqual(17,len(result['checks']))
        self.assertTrue(all(c['status']=='pass' for c in result['checks']))
