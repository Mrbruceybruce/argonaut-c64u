"""Host-independent regressions for the macOS qualification verifier."""
import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'macos_bundle_verifier', Path(__file__).resolve().parents[1] /
    'packaging/macos/verify_bundle.py')
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class BundleVerificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / 'Argonaut.app'
        (self.app / 'Contents/MacOS').mkdir(parents=True)
        (self.app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleShortVersionString': '1.9', 'CFBundleVersion': '10900'}))
        (self.app / 'Contents/MacOS/Argonaut').write_bytes(b'fixture')
        (self.app / '_build.json').write_text(json.dumps({
            'version': '1.9', 'build': 'source'}), encoding='utf-8')
        self.dependencies = b'\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n'

    def tool_output(self, args, **kwargs):
        if args[0] == 'lipo':
            return b'arm64\n'
        if args[0] == 'file':
            if args[-1].endswith('/Argonaut'):
                return b'Mach-O 64-bit executable arm64\n'
            return b'data with non-UTF-8 description \xe0\n'
        if args[0] == 'otool':
            return b'Argonaut:\n' + self.dependencies
        self.fail(f'Unexpected tool: {args}')

    def verify(self):
        VERIFIER.verify(self.app, '1.9', '10900', 'arm64', 'source')

    def test_non_utf8_file_description_does_not_skip_macho_or_signature_checks(self):
        with patch.object(VERIFIER.subprocess, 'check_output', side_effect=self.tool_output) as output, patch.object(VERIFIER.subprocess, 'run') as run:
            self.verify()
        self.assertEqual(1, sum(call.args[0][0] == 'otool' for call in output.call_args_list))
        run.assert_called_once_with(['codesign', '--verify', '--deep', '--strict', str(self.app)], check=True)

    def test_non_utf8_external_dependency_is_rejected_without_losing_bytes(self):
        self.dependencies = b'\t/opt/build/\xe0.dylib (compatibility version 1.0.0)\n'
        with patch.object(VERIFIER.subprocess, 'check_output', side_effect=self.tool_output), patch.object(VERIFIER.subprocess, 'run') as run:
            with self.assertRaises(SystemExit) as error:
                self.verify()
            self.assertIn('External build-machine dependencies', str(error.exception))
            self.assertIn('\\udce0', str(error.exception))
            run.assert_not_called()

    def test_failed_file_inspection_is_not_silently_skipped(self):
        def fail_file(args, **kwargs):
            if args[0] == 'file':
                raise subprocess.CalledProcessError(1, args, output=b'failed \xe0')
            return self.tool_output(args, **kwargs)
        with patch.object(VERIFIER.subprocess, 'check_output', side_effect=fail_file):
            with self.assertRaises(SystemExit) as error:
                self.verify()
        self.assertIn('Bundle verification failed', str(error.exception))
        self.assertIn(str(self.app), str(error.exception))
