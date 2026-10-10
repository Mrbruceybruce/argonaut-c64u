"""Exercise Debian staging without invoking dpkg, installing, or contacting devices."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
with patch.object(sys,'path',[str(ROOT/'packaging'),*sys.path]):
    spec=importlib.util.spec_from_file_location('build_deb',ROOT/'packaging/build_deb.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
from c64u_browser.package_self_test import _check_debian_package, PackageSelfTestFailure

real_run=builder.subprocess.run
def no_package_build(command, *args, **kwargs):
    if command[0] != 'git':raise AssertionError('Only read-only Git subprocesses allowed')
    return real_run(command,*args,**kwargs)

class DebianPackaging(unittest.TestCase):
    def test_development_notes_override_versioned_and_historical_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            assets=Path(directory)
            for name in ('RELEASE-DEVELOPMENT.md','RELEASE-1.10~dev2.md','RELEASE-NOTES.md'):
                (assets/name).write_text(name)
            self.assertEqual('RELEASE-DEVELOPMENT.md',builder.release_notes_path(assets,'1.10~dev2',True).name)
            (assets/'RELEASE-DEVELOPMENT.md').unlink()
            with self.assertRaisesRegex(ValueError,'required Development'):
                builder.release_notes_path(assets,'1.10~dev2',True)
    def test_stable_notes_rules_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            assets=Path(directory);(assets/'RELEASE-1.9.md').write_text('stable')
            (assets/'RELEASE-DEVELOPMENT.md').write_text('development')
            (assets/'RELEASE-NOTES.md').write_text('historical')
            self.assertEqual('RELEASE-1.9.md',builder.release_notes_path(assets,'1.9',release=True).name)
            self.assertEqual('RELEASE-NOTES.md',builder.release_notes_path(assets,'local').name)
            with self.assertRaisesRegex(ValueError,'Missing release notes'):
                builder.release_notes_path(assets,'1.10',release=True)
    def test_missing_development_notes_fails_before_staging_or_metadata(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(builder,'metadata') as metadata:
            source=Path(directory)/'source';root=Path(directory)/'staged';root.mkdir()
            with self.assertRaisesRegex(ValueError,'required Development'):
                builder.stage_package(source,root,'1.10~dev2',True)
            metadata.assert_not_called();self.assertEqual([],list(root.iterdir()))
    def test_development_and_release_flags_cannot_mix(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'separate'):
                builder.stage_package(ROOT,directory,'1.9',True,True)
    def test_development_staging_identity_resources_and_self_test(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{},clear=True),patch.object(builder.subprocess,'run',side_effect=no_package_build):
            root=Path(directory)
            package,epoch=builder.stage_package(ROOT,root,'1.10~dev2',True)
            self.assertEqual('argonaut-c64u-development',package);self.assertGreater(epoch,0)
            modules=root/'usr/lib/argonaut-development/c64u_browser'
            data=json.loads((modules/'_build.json').read_text())
            self.assertEqual('1.10-dev2',data['version']);self.assertTrue(data['development'])
            self.assertEqual('1.10~dev2',data['package_version'])
            self.assertRegex(data['build'],r'^[0-9a-f]{40}(-modified)?$')
            expected={p.name for p in (ROOT/'c64u_browser').glob('*.py')}
            self.assertEqual(expected,{p.name for p in modules.glob('*.py')})
            for source in (ROOT/'c64u_browser/assets').rglob('*'):
                if source.is_file():self.assertEqual(source.read_bytes(),(modules/'assets'/source.relative_to(ROOT/'c64u_browser/assets')).read_bytes())
            doc=root/'usr/share/doc'/package
            self.assertEqual((ROOT/'packaging/RELEASE-DEVELOPMENT.md').read_bytes(),(doc/'RELEASE-NOTES.md').read_bytes())
            self.assertNotIn('Argonaut 0.1.0',(doc/'RELEASE-NOTES.md').read_text())
            control=(root/'DEBIAN/control').read_text()
            self.assertIn('Package: argonaut-c64u-development',control);self.assertIn('Version: 1.10~dev2',control)
            desktop=(root/'usr/share/applications/argonaut-development.desktop').read_text()
            for text in ('Name=Argonaut Development 1.10-dev2','Exec=argonaut-development','Icon=argonaut-development'):
                self.assertIn(text,desktop)
            self.assertIn('ARGONAUT_DEVELOPMENT', (root/'usr/lib/argonaut-development/launch.py').read_text())
            self.assertFalse((root/'usr/lib/argonaut').exists())
            self.assertEqual(0o755,(root/'usr/bin/argonaut-development').stat().st_mode&0o777)
            checks=[];_check_debian_package(data,checks,modules,doc);self.assertEqual(4,len(checks))
            (doc/'RELEASE-NOTES.md').write_text('# Argonaut 0.1.0')
            with self.assertRaises(PackageSelfTestFailure):_check_debian_package(data,[],modules,doc)
    def test_stable_staging_keeps_stable_identity_and_notes(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{},clear=True),patch.object(builder.subprocess,'run',side_effect=no_package_build):
            root=Path(directory);package,_=builder.stage_package(ROOT,root,'1.9')
            self.assertEqual('argonaut-c64u',package)
            data=json.loads((root/'usr/lib/argonaut/c64u_browser/_build.json').read_text())
            self.assertEqual('1.9',data['version']);self.assertNotIn('development',data)
            self.assertEqual((ROOT/'packaging/RELEASE-1.9.md').read_bytes(),(root/'usr/share/doc/argonaut-c64u/RELEASE-NOTES.md').read_bytes())

    def test_release_staging_preserves_strict_metadata_validation(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(builder,'metadata',side_effect=ValueError('strict release rejection')) as metadata:
            with self.assertRaisesRegex(ValueError,'strict release rejection'):
                builder.stage_package(ROOT,directory,'1.9',release=True)
            metadata.assert_called_once_with(ROOT,'1.9',True)
            self.assertEqual([],list(Path(directory).iterdir()))
