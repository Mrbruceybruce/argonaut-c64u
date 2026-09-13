# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaged identity; source checkouts are explicitly marked as such."""
import json
import os
from . import development
from pathlib import Path
VERSION = '1.5'
ASSETS = Path(__file__).resolve().parent / 'assets'

def build_info():
    try:
        data = json.loads((Path(__file__).resolve().parent / '_build.json').read_text())
        if not all(isinstance(data.get(k), str) and data[k] for k in ('version', 'build')):
            raise ValueError('Invalid build identity')
        return data
    except (OSError, ValueError):
        if development.enabled():
            return {'version':VERSION+'-dev','build':os.environ.get('ARGONAUT_DEV_BUILD','development checkout')}
        return {'version': VERSION, 'build': 'source checkout (unpackaged)'}
