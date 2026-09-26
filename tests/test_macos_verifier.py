"""Release verifier classification must not decode arbitrary file descriptions."""
import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'macos_verifier', Path(__file__).resolve().parents[1] /
    'packaging/macos/verify_bundle.py')
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


# Exact 231-byte macOS file-5.41 description of the valid Tamil gtk40.mo.
# The description ends mid-codepoint; the catalog itself is valid UTF-8.
TAMIL_DESCRIPTION = bytes.fromhex(
    '474e55206d65737361676520636174616c6f6720286c6974746c6520656e6469'
    '616e292c207265766973696f6e20302e302c2031313437206d65737361676573'
    '2c2050726f6a6563742d49642d56657273696f6e3a2067746b2b2e6d61737465'
    '722e7461202722257322e0aeaee0aea4e0aebfe0aeaae0af8de0aeaae0af81e0'
    'aeb0e0af81e0ae95e0af8de0ae95e0aeb3e0af81e0ae95e0af8de0ae95e0af81'
    '202225732220e0aeb5e0ae95e0af8820e0aeaee0aea4e0aebfe0aeaae0af8de0'
    'aeaae0aebee0ae9520e0aeaee0aebee0aeb1e0af8de0aeb1e0aeaae0af8de0ae'
    'aae0ae9fe0270a'
)


class MacOSVerifierTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / 'Argonaut.app'
        contents = self.app / 'Contents'
        (contents / 'MacOS').mkdir(parents=True)
        self.executable = contents / 'MacOS/Argonaut'
        self.executable.write_bytes(b'fixture')
        (contents / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleShortVersionString': '1.9', 'CFBundleVersion': '10900'}))
        (contents / '_build.json').write_text(json.dumps({
            'version': '1.9', 'build': 'reviewed-sha'}))
        self.catalog = contents / 'gtk40.mo'
        self.catalog.write_bytes(b'translation fixture')
        self.inspected = []
        self.dependencies = '    /usr/lib/libSystem.B.dylib (compatibility version 1.0.0)'
        self.architecture = b'arm64\n'

    def command(self, args, **kwargs):
        if args[0] == 'lipo':
            return self.architecture
        if args[0] == 'file':
            self.assertFalse(kwargs.get('text', False))
            self.inspected.append(Path(args[-1]))
            if Path(args[-1]) == self.executable:
                return b'Mach-O 64-bit executable arm64\n'
            return TAMIL_DESCRIPTION
        if args[0] == 'otool':
            self.assertEqual(str(self.executable), args[-1])
            return f'{self.executable}:\n{self.dependencies}\n'.encode('utf-8')
        self.fail(f'Unexpected command: {args}')

    def verify(self):
        VERIFIER.verify(self.app, '1.9', '10900', 'arm64', 'reviewed-sha')

    def test_non_utf8_description_is_inspected_without_decoding_or_macho_misclassification(self):
        with patch.object(VERIFIER.subprocess, 'check_output', side_effect=self.command), \
                patch.object(VERIFIER.subprocess, 'run') as signing:
            self.verify()
        self.assertIn(self.catalog, self.inspected)
        self.assertEqual(set(self.app.rglob('*')) -
                         {p for p in self.app.rglob('*') if p.is_dir()}, set(self.inspected))
        signing.assert_called_once_with(
            ['codesign', '--verify', '--deep', '--strict', str(self.app)], check=True)

    def test_macho_dependencies_still_reject_external_build_paths(self):
        self.dependencies = '    /opt/homebrew/lib/unsafe.dylib (compatibility version 1.0.0)'
        with patch.object(VERIFIER.subprocess, 'check_output', side_effect=self.command), \
                patch.object(VERIFIER.subprocess, 'run') as signing:
            with self.assertRaisesRegex(SystemExit, 'External build-machine dependencies'):
                self.verify()
        signing.assert_not_called()

    def test_wrong_architecture_still_rejected(self):
        self.architecture = b'x86_64\n'
        with patch.object(VERIFIER.subprocess, 'check_output', side_effect=self.command):
            with self.assertRaisesRegex(SystemExit, 'Expected architecture arm64'):
                self.verify()

    def test_signature_failure_still_propagates(self):
        with patch.object(VERIFIER.subprocess, 'check_output', side_effect=self.command), \
                patch.object(VERIFIER.subprocess, 'run', side_effect=
                             subprocess.CalledProcessError(1, 'codesign')):
            with self.assertRaises(subprocess.CalledProcessError):
                self.verify()
