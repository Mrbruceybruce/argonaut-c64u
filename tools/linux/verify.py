#!/usr/bin/env python3
"""Fail-closed P4-4 archive/report checks; never install or extract a package."""
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

CONTRACT = json.loads(Path(__file__).with_name('contract.json').read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(sha, epoch):
    require(isinstance(sha, str) and re.fullmatch('[0-9a-f]{40}', sha), 'source SHA')
    require(type(epoch) is int and 0 < epoch < 2**32, 'source epoch')


def ar_members(data, epoch=None):
    require(data[:8] == b'!<arch>\n', 'ar magic')
    result = []
    offset = 8
    while offset < len(data):
        header = data[offset:offset + 60]
        require(len(header) == 60 and header[58:] == b'`\n', 'ar header')
        require(int(header[28:34]) == int(header[34:40]) == 0, 'ar ownership')
        require(int(header[40:48], 8) == 0o100644, 'ar mode')
        if epoch is not None:
            require(int(header[16:28]) == epoch, 'ar epoch')
        name = header[:16].decode('ascii').strip().removesuffix('/')
        size = int(header[48:58])
        require(size >= 0 and offset + 60 + size <= len(data), 'ar size')
        result.append((name, data[offset + 60:offset + 60 + size]))
        offset += 60 + size
        if size % 2:
            require(data[offset:offset + 1] == b'\n', 'ar padding')
            offset += 1
    require(len(result) == 3 and result[0] == ('debian-binary', b'2.0\n') and
            re.fullmatch(r'control\.tar\.(xz|gz|zst)', result[1][0]) and
            re.fullmatch(r'data\.tar\.(xz|gz|zst)', result[2][0]), 'exact deb members')
    return result


def tar_members(data, epoch):
    files, directories, seen = {}, set(), set()
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
        for member in archive:
            name = member.name
            if name.startswith('./'):
                name = name[2:]
            if name in ('', '.') and member.isdir():
                name = '.'
            require(name == '.' or (not name.startswith('/') and
                    all(p not in ('', '.', '..') for p in name.split('/'))), 'unsafe path')
            require(name not in seen, 'duplicate archive path')
            seen.add(name)
            require(member.uid == member.gid == 0, 'archive ownership')
            require(member.mtime == epoch, 'archive epoch')
            require(member.isfile() or member.isdir(), 'links/devices forbidden')
            mode = member.mode
            # TemporaryDirectory is 0700; dpkg may retain that on the archive root.
            allowed = (0o700, 0o755) if name == '.' and member.isdir() else (0o755,) if member.isdir() else (0o644, 0o755)
            require(mode in allowed, 'unsafe mode')
            if member.isdir():
                directories.add(name)
            else:
                require(member.size <= 32 * 1024 * 1024, 'oversized member')
                files[name] = {'sha256': digest(archive.extractfile(member).read()),
                               'mode': mode, 'size': member.size}
    expected_dirs = {'.'}
    for name in files:
        expected_dirs.update(str(p) for p in PurePosixPath(name).parents)
    require(directories == expected_dirs, 'unexpected/missing directories')
    return files


def check_control(text):
    fields = {}
    for line in text.splitlines():
        if line.startswith(' '):
            require('Description' in fields, 'unexpected continuation')
            continue
        key, value = line.split(': ', 1)
        require(key not in fields, 'duplicate control field')
        fields[key] = value
    require(set(fields) == set(CONTRACT['control']) | {'Installed-Size'}, 'control fields')
    for key, value in CONTRACT['control'].items():
        require(fields[key] == value, 'control ' + key)
    require(re.fullmatch('[1-9][0-9]*', fields['Installed-Size']), 'installed size')


def read_archive(package, epoch):
    require(8 < package.stat().st_size <= 64 * 1024 * 1024, 'package size limit')
    ar_members(package.read_bytes(), epoch)
    # dpkg only decodes here. No extraction, maintainer scripts or installation.
    streams = [subprocess.check_output(['dpkg-deb', flag, str(package)], timeout=45)
               for flag in ('--ctrl-tarfile', '--fsys-tarfile')]
    control, payload = [tar_members(stream, epoch) for stream in streams]
    require(set(control) == {'control'}, 'unexpected maintainer/control files')
    with tarfile.open(fileobj=io.BytesIO(streams[0])) as archive:
        entry = next(m for m in archive if m.isfile())
        check_control(archive.extractfile(entry).read().decode())
    require(set(payload) == set(CONTRACT['payload']), 'exact payload inventory')
    for name, expected in CONTRACT['generated_sha256'].items():
        require(payload[name]['sha256'] == expected, 'launcher/desktop/unit contract: ' + name)
    return control, payload


def verify_package(package, manifest):
    identity(manifest['source_sha'], manifest['source_epoch'])
    require(manifest['schema'] == 1 and manifest['result'] == 'passed', 'manifest status')
    require(package.name == CONTRACT['filename'], 'package filename')
    require(digest(package.read_bytes()) == manifest['sha256'], 'package checksum')
    control, payload = read_archive(package, manifest['source_epoch'])
    require(control == manifest['control'] and payload == manifest['payload'], 'payload hashes/modes')


def check_report(report, sha):
    require(report.get('schema') == 1 and report.get('suite') == 'package' and
            report.get('result') == 'passed' and report.get('platform') == 'linux' and
            report.get('version') == CONTRACT['display_version'] and
            report.get('build') == sha and 'failure' not in report, 'report identity/status')
    checks = report.get('checks')
    require(isinstance(checks, list) and all(isinstance(c, dict) and
            set(c) == {'id', 'status'} and c['status'] == 'pass' for c in checks), 'check status')
    ids = [c['id'] for c in checks]
    require(len(ids) == len(set(ids)) and set(ids) == set(CONTRACT['self_test_ids']),
            'complete unique check IDs')


def verify_build(source, output, sha, epoch):
    """Reuse the existing staging contract, then compare every final archive byte hash."""
    import importlib.util
    import os
    import sys
    import tempfile
    identity(sha, epoch)
    require(sorted(p.name for p in output.glob('*.deb')) == [CONTRACT['filename']], 'package outputs')
    require(os.environ.get('ARGONAUT_SOURCE_COMMIT') == sha and
            os.environ.get('SOURCE_DATE_EPOCH') == str(epoch), 'build environment')
    sys.path.insert(0, str(source / 'packaging'))
    spec = importlib.util.spec_from_file_location('build_deb', source / 'packaging/build_deb.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    package = output / CONTRACT['filename']
    control, payload = read_archive(package, epoch)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        name, staged_epoch = builder.stage_package(source, root, CONTRACT['version'], development=True)
        require(name == CONTRACT['control']['Package'] and staged_epoch == epoch, 'staging identity')
        expected = {}
        for path in root.rglob('*'):
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                expected[relative] = {'sha256': digest(path.read_bytes()),
                                      'mode': path.stat().st_mode & 0o7777,
                                      'size': path.stat().st_size}
        require(control == {'control': expected.pop('DEBIAN/control')} and payload == expected,
                'staged/archive content mismatch')
        metadata = json.loads((root / 'usr/lib/argonaut-development/c64u_browser/_build.json').read_text())
        notes = source / 'packaging/RELEASE-DEVELOPMENT.md'
        require(metadata == {'version': CONTRACT['display_version'], 'build': sha,
                'development': True, 'package_format': 'deb', 'package_version': CONTRACT['version'],
                'release_notes_sha256': digest(notes.read_bytes())}, 'embedded provenance')
        for path in (root / 'usr/lib/systemd/user').iterdir():
            require('@' not in path.read_text(), 'unresolved unit placeholder')
    manifest = {'schema': 1, 'result': 'passed', 'source_sha': sha, 'source_epoch': epoch,
                'sha256': digest(package.read_bytes()), 'control': control, 'payload': payload}
    (output / 'verified.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'SHA256SUMS').write_text(manifest['sha256'] + '  ' + package.name + '\n')
    return manifest
