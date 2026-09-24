import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from c64u_browser import release, version


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'build_metadata_release', ROOT / 'packaging/build_metadata.py')
BUILD_METADATA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD_METADATA)


class ReleaseContractTests(unittest.TestCase):
    def test_authoritative_19_contract(self):
        self.assertEqual('1.9', release.VERSION)
        self.assertEqual('1.9', version.VERSION)
        self.assertEqual('1.9.0.0', release.WINDOWS_NUMERIC_VERSION)
        self.assertEqual('10900', release.MAC_BUNDLE_VERSION)
        self.assertEqual('v1.9', release.TAG)
        self.assertEqual('packaging/RELEASE-1.9.md', release.RELEASE_NOTES)
        self.assertEqual(8, len(release.artifact_names()))
        self.assertEqual({
            'argonaut-c64u_1.9_all.deb',
            'Argonaut-1.9-Windows-x64-Setup.exe',
            'Argonaut-1.9-Windows-x64-Portable.zip',
            'Argonaut-1.9-macOS-AppleSilicon.dmg',
            'Argonaut-1.9-macOS-AppleSilicon.zip',
            'Argonaut-1.9-macOS-Intel.dmg',
            'Argonaut-1.9-macOS-Intel.zip',
            'argonaut-1.9-source.zip',
        }, set(release.artifact_names()))

    def _repository(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / 'c64u_browser/assets').mkdir(parents=True)
        (root / 'c64u_browser/a.py').write_text('value = 1\n')
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Test'], check=True)
        subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'test@example.invalid'], check=True)
        subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(root), 'commit', '-q', '-m', 'fixture'], check=True)
        sha = subprocess.check_output(
            ['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        return root, sha

    def test_release_metadata_requires_matching_clean_commit(self):
        root, sha = self._repository()
        with patch.dict(os.environ, {'ARGONAUT_SOURCE_COMMIT': sha}, clear=False):
            result = BUILD_METADATA.metadata(root, '1.9', release=True)
        self.assertEqual(sha, result['build'])
        self.assertTrue(result['release'])
        self.assertEqual('v1.9', result['tag'])
        self.assertEqual('10900', result['bundle_version'])
        self.assertEqual('1.9.0.0', result['windows_version'])
        with patch.dict(os.environ, {'ARGONAUT_SOURCE_COMMIT': 'a' * 40}, clear=False):
            with self.assertRaisesRegex(ValueError, 'does not match'):
                BUILD_METADATA.metadata(root, '1.9', release=True)
        (root / 'c64u_browser/a.py').write_text('value = 2\n')
        with patch.dict(os.environ, {'ARGONAUT_SOURCE_COMMIT': sha}, clear=False):
            with self.assertRaisesRegex(ValueError, 'clean checkout'):
                BUILD_METADATA.metadata(root, '1.9', release=True)

    def test_release_metadata_rejects_wrong_version_and_missing_git(self):
        root, _ = self._repository()
        with self.assertRaisesRegex(ValueError, 'requires version 1.9'):
            BUILD_METADATA.metadata(root, '1.8', release=True)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'c64u_browser/assets').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'exact Git checkout'):
                BUILD_METADATA.metadata(source, '1.9', release=True)

    def test_pipeline_is_qualification_only_and_checks_final_payloads(self):
        workflow = (ROOT / '.github/workflows/stable-1.9.yml').read_text()
        self.assertIn('release_commit:', workflow)
        self.assertIn('build_metadata.py --release', workflow)
        self.assertIn('artifact_names()', workflow)
        self.assertIn('SHA256SUMS', workflow)
        self.assertIn('Signing boundary — intentionally unsigned', workflow)
        self.assertNotIn('gh release create', workflow)
        self.assertNotIn('contents: write', workflow)
        self.assertNotIn('notarytool', workflow)
        self.assertNotIn('signtool', workflow)

    def test_stable_mac_packages_use_current_readmes_without_repurposing_history(self):
        workflow = (ROOT / '.github/workflows/stable-1.9.yml').read_text()
        self.assertIn('packaging/macos/README-1.9.txt', workflow)
        self.assertIn('packaging/macos/README-1.9-Intel.txt', workflow)
        self.assertNotIn('cp packaging/macos/README.txt mac-package/README.txt', workflow)
        self.assertNotIn('cp packaging/macos/README-Intel.txt mac-package/README.txt', workflow)
        for name in ('README.txt', 'README-Intel.txt'):
            historical = (ROOT / 'packaging/macos' / name).read_text()
            self.assertTrue(historical.startswith('HISTORICAL:'))
        for name in ('README-1.9.txt', 'README-1.9-Intel.txt'):
            current = (ROOT / 'packaging/macos' / name).read_text()
            self.assertIn('Stable 1.9 platform qualification', current)
            self.assertIn('not Apple Developer ID signed or notarized', current)

    def test_windows_and_mac_specs_consume_release_resources(self):
        windows = (ROOT / 'packaging/windows/argonaut.spec').read_text()
        installer = (ROOT / 'packaging/windows/installer.iss').read_text()
        mac = (ROOT / 'packaging/macos/argonaut.spec').read_text()
        self.assertIn("version=str(version_file)", windows)
        self.assertIn('#error AppVersion must be defined', installer)
        self.assertIn('VersionInfoVersion={#AppNumericVersion}', installer)
        self.assertIn('MAC_BUNDLE_VERSION', mac)
        self.assertNotIn("get('version','1.5')", mac)


if __name__ == '__main__':
    unittest.main()
