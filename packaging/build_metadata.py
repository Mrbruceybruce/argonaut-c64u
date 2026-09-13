#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stamp package version and source identity without storing local paths."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path

def metadata(source, version):
    source = Path(source).resolve()
    build = ''
    try:
        root = subprocess.check_output(['git','-C',str(source),'rev-parse','--show-toplevel'],stderr=subprocess.DEVNULL,text=True).strip()
        if Path(root).resolve() == source:
            build = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
            dirty = subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no'],text=True).strip()
            if dirty: build += '-modified'
    except (OSError, subprocess.CalledProcessError):
        pass
    if not build:
        digest = hashlib.sha256()
        files = sorted((source/'c64u_browser').glob('*.py')) + sorted((source/'c64u_browser/assets').glob('*'))
        for path in files:
            if path.is_file():
                digest.update(path.relative_to(source).as_posix().encode()+b'\0'+path.read_bytes())
        build = 'source-'+digest.hexdigest()[:16]
    return {'version':version, 'build':build}

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--version',required=True)
    parser.add_argument('--development',action='store_true')
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    destination=args.source/'c64u_browser/_build.json'
    data=metadata(args.source,args.version)
    if args.development:data['development']=True
    destination.write_text(json.dumps(data,indent=2)+'\n')
