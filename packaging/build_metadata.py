#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stamp package version and source identity without storing local paths."""
import argparse, hashlib, json, os, subprocess, sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from c64u_browser.release import (MAC_BUNDLE_VERSION, TAG, VERSION,
                                  WINDOWS_NUMERIC_VERSION, validate_version)

def _git(source, *args):
    return subprocess.check_output(
        ['git', '-C', str(source), *args], stderr=subprocess.DEVNULL,
        text=True).strip()


def metadata(source, version, release=False):
    source = Path(source).resolve()
    if release:
        version = validate_version(version)
    elif not isinstance(version, str) or not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z.+~-]*', version):
        raise ValueError('Invalid package version')
    if release and version != VERSION:
        raise ValueError(f'Stable release packaging requires version {VERSION}')
    requested = os.environ.get('ARGONAUT_SOURCE_COMMIT','')
    if requested and (len(requested)!=40 or any(c not in '0123456789abcdef' for c in requested)):
        raise ValueError('ARGONAUT_SOURCE_COMMIT must be a full Git commit ID')
    build = ''
    try:
        # Ask Git whether -C selected the worktree root. Git may print an
        # MSYS2 path (/d/...) that native Windows pathlib interprets differently.
        # An empty prefix inside a worktree proves root membership without
        # translating paths or relaxing the exact-checkout requirement.
        inside = _git(source, 'rev-parse', '--is-inside-work-tree')
        prefix = _git(source, 'rev-parse', '--show-prefix')
        if inside == 'true' and prefix == '':
            head = _git(source, 'rev-parse', 'HEAD')
            if requested and requested != head:
                raise ValueError(
                    'ARGONAUT_SOURCE_COMMIT does not match the source checkout')
            dirty = _git(source, 'status', '--porcelain',
                         '--untracked-files=all')
            if release and dirty:
                raise ValueError('Stable release packaging requires a clean checkout')
            build = head + ('-modified' if dirty else '')
        elif release:
            raise ValueError('Stable release packaging requires an exact Git checkout root')
    except (OSError, subprocess.CalledProcessError):
        if release:
            raise ValueError('Stable release packaging requires an exact Git checkout')
    if requested and not build:
        if release:
            raise ValueError('Could not verify ARGONAUT_SOURCE_COMMIT against checkout')
        build = requested
    if not build:
        if release:
            raise ValueError('Stable release packaging requires a Git commit identity')
        digest = hashlib.sha256()
        files = sorted((source/'c64u_browser').glob('*.py')) + sorted((source/'c64u_browser/assets').glob('*'))
        for path in files:
            if path.is_file():
                data=path.read_bytes()
                if path.suffix in ('.py','.svg','.json','.txt'):data=data.replace(b'\r\n',b'\n')
                digest.update(path.relative_to(source).as_posix().encode()+b'\0'+data)
        build = 'source-'+digest.hexdigest()[:16]
    result = {'version':version, 'build':build}
    if release:
        result.update({'release': True, 'tag': TAG,
                       'bundle_version': MAC_BUNDLE_VERSION,
                       'windows_version': WINDOWS_NUMERIC_VERSION})
    return result

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--version',default=VERSION)
    parser.add_argument('--release',action='store_true')
    parser.add_argument('--development',action='store_true')
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    destination=args.source/'c64u_browser/_build.json'
    data=metadata(args.source,args.version,args.release)
    if args.development:data['development']=True
    destination.write_text(json.dumps(data,indent=2)+'\n')
