#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify the relocated final macOS application container."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess


def output(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def verify(app, version, bundle_version, arch, build):
    app = Path(app)
    plist = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    if plist.get('CFBundleShortVersionString') != version:
        raise SystemExit('Incorrect CFBundleShortVersionString')
    if plist.get('CFBundleVersion') != bundle_version:
        raise SystemExit('Incorrect CFBundleVersion')
    executable = app / 'Contents/MacOS/Argonaut'
    architectures = output('lipo', '-archs', str(executable)).split()
    if architectures != [arch]:
        raise SystemExit(f'Expected architecture {arch}, got {architectures}')
    metadata = json.loads(next(app.rglob('_build.json')).read_text())
    if metadata.get('version') != version or metadata.get('build') != build:
        raise SystemExit('Embedded build identity is incorrect')
    bad = []
    for path in app.rglob('*'):
        if not path.is_file():
            continue
        try:
            kind = output('file', '-b', str(path))
        except subprocess.CalledProcessError:
            continue
        if 'Mach-O' not in kind:
            continue
        for line in output('otool', '-L', str(path)).splitlines()[1:]:
            dependency = line.strip().split(' (compatibility', 1)[0]
            if (dependency.startswith('/') and
                    not dependency.startswith(('/System/', '/usr/lib/'))):
                bad.append((str(path.relative_to(app)), dependency))
            if os.environ.get('GITHUB_WORKSPACE') and dependency.startswith(
                    os.environ['GITHUB_WORKSPACE']):
                bad.append((str(path.relative_to(app)), dependency))
    if bad:
        raise SystemExit(f'External build-machine dependencies: {bad}')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)],
                   check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--bundle-version', required=True)
    parser.add_argument('--arch', choices=('arm64', 'x86_64'), required=True)
    parser.add_argument('--build', required=True)
    args = parser.parse_args()
    verify(args.app, args.version, args.bundle_version, args.arch, args.build)
