# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import sys

import c64u_browser


metadata_path = Path(c64u_browser.__file__).parent / '_build.json'
package_metadata = (json.loads(metadata_path.read_text())
                    if metadata_path.is_file() else {})
if package_metadata.get('development') is True:
    os.environ['ARGONAUT_DEVELOPMENT'] = '1'
    os.environ['ARGONAUT_DEV_BUILD'] = package_metadata['build']

if '--self-test' in sys.argv:
    from c64u_browser.package_self_test import run
    run(package_metadata, sys.argv[sys.argv.index('--self-test') + 1])
else:
    from c64u_browser.platform_support import portable_root
    root = portable_root()
    os.chdir(root or Path.home())
    from c64u_browser.gui import main
    main()
