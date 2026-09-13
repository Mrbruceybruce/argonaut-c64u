"""Package identity survives Windows text conversion and explicit source imports."""
import importlib.util, tempfile, unittest, os
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('build_metadata',Path(__file__).resolve().parents[1]/'packaging/build_metadata.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class PackageIdentity(unittest.TestCase):
    def test_same_fingerprint_for_windows_and_unix_sources(self):
        with tempfile.TemporaryDirectory() as d, patch.object(module.subprocess,'check_output',side_effect=OSError):
            source=Path(d);(source/'c64u_browser/assets').mkdir(parents=True)
            code=source/'c64u_browser/a.py';code.write_bytes(b'hello\nworld\n')
            first=module.metadata(source,'0.1.4-dev.3')
            code.write_bytes(b'hello\r\nworld\r\n')
            self.assertEqual(first,module.metadata(source,'0.1.4-dev.3'))
    def test_explicit_commit_survives_missing_git(self):
        with patch.dict(os.environ,{'ARGONAUT_SOURCE_COMMIT':'a'*40}),patch.object(module.subprocess,'check_output',side_effect=OSError):
            self.assertEqual(module.metadata(Path('.'),'test')['build'],'a'*40)
