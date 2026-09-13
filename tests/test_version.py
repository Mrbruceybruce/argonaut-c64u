import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from c64u_browser import version

class VersionTests(unittest.TestCase):
    def test_packaged_identity_and_source_fallback(self):
        with tempfile.TemporaryDirectory() as d, patch.object(version,'__file__',str(Path(d)/'version.py')):
            self.assertIn('unpackaged',version.build_info()['build'])
            p=Path(d)/'_build.json'
            p.write_text(json.dumps({'version':'2.3.4','build':'abcdef123'}))
            self.assertEqual(version.build_info(),{'version':'2.3.4','build':'abcdef123'})
            p.write_text('{broken')
            self.assertIn('unpackaged',version.build_info()['build'])
