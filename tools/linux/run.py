#!/usr/bin/env python3
"""Bounded Linux verification orchestration; build/smoke require separate approval locally."""
import argparse
from contextlib import contextmanager
import grp
import importlib
import pwd
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from pathlib import Path

from verify import CONTRACT, check_report, digest, identity, require, verify_build, verify_package

TOOLS = Path(__file__).resolve().parent


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def error_evidence(error, step):
    return {'step': step, 'type': type(error).__name__, 'message': str(error),
            'traceback': ''.join(traceback.format_exception(error))}


def command(args, log, timeout=60, **kwargs):
    """Persist output even when a command fails, hangs, or is interrupted."""
    with log.open('ab') as stream:
        stream.write(('\nCOMMAND ' + repr(args) + '\n').encode())
        stream.flush()
        process = subprocess.Popen(args, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True, **kwargs)
        try:
            code = process.wait(timeout=timeout)
            require(code == 0, f'command exited {code}: {args[0]} (see {log.name})')
        finally:
            # Also kills surviving descendants after a successful parent exit.
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=3)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def capture(args, timeout=30):
    return subprocess.check_output(args, text=True, timeout=timeout).strip()


def isolation():
    require(os.getuid() != 0, 'runtime must be nonroot')
    status = Path('/proc/self/status').read_text()
    for field in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'):
        require(int(re.search(r'^' + field + r':\s*(\w+)', status, re.M)[1], 16) == 0,
                'capabilities: ' + field)
    require(re.search(r'^NoNewPrivs:\s*1$', status, re.M), 'no-new-privileges')
    require({p.name for p in Path('/sys/class/net').iterdir()} == {'lo'}, 'network isolation')
    return {'uid': os.getuid(), 'status': status,
            'interfaces': ['lo'], 'network_namespace': os.readlink('/proc/self/ns/net')}


def preflight(output):
    evidence = {'identity': {}, 'dbus': {}, 'typelibs': {}, 'factories': {}, 'errors': []}

    def record(name, operation):
        try:
            result = operation()
            evidence[name] = result
            return result
        except Exception as error:
            evidence['errors'].append({'step': name, 'error': type(error).__name__ + ': ' + str(error)})
            raise
        finally:
            write_json(output / 'preflight.json', evidence)

    def account():
        uid, gid = os.getuid(), os.getgid()
        evidence['identity'].update(uid=uid, gid=gid, euid=os.geteuid(), egid=os.getegid())
        require(uid > 0 and gid > 0 and uid == os.geteuid() and gid == os.getegid(), 'runtime IDs')
        user, group = pwd.getpwuid(uid), grp.getgrgid(gid)
        evidence['identity'].update(user=user.pw_name, group=group.gr_name)
        require(user.pw_name == 'runtime' and user.pw_gid == gid and
                pwd.getpwnam(user.pw_name).pw_uid == uid and
                grp.getgrnam(group.gr_name).gr_gid == gid, 'passwd/group resolution')
        return evidence['identity']

    record('identity', account)
    record('pygobject_import', lambda: importlib.import_module('gi').__version__)
    gi = importlib.import_module('gi')
    modules = {}
    for name, version in [('Gio', '2.0'), ('GLib', '2.0'), ('Gtk', '4.0'),
                          ('Gst', '1.0'), ('GstPbutils', '1.0'), ('Secret', '1')]:
        def load():
            gi.require_version(name, version)
            modules[name] = importlib.import_module('gi.repository.' + name)
            evidence['typelibs'][name] = {'version': version, 'loaded': True}
            return evidence['typelibs']
        try:
            record('typelibs', load)
        except Exception:
            evidence['typelibs'][name] = {'version': version, 'loaded': False}
            write_json(output / 'preflight.json', evidence)
            raise

    def session_bus():
        Gio, GLib = modules['Gio'], modules['GLib']
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        unique = bus.get_unique_name()
        evidence['dbus']['unique_name'] = unique
        uid = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                            'org.freedesktop.DBus', 'GetConnectionUnixUser',
                            GLib.Variant('(s)', (unique,)), GLib.VariantType.new('(u)'),
                            Gio.DBusCallFlags.NONE, 10000, None).unpack()[0]
        evidence['dbus']['authenticated_uid'] = uid
        require(uid == os.getuid(), 'private D-Bus authenticated UID')
        return evidence['dbus']

    record('dbus', session_bus)
    Gtk, Gst, GLib = modules['Gtk'], modules['Gst'], modules['GLib']
    def gtk_check():
        evidence['gtk'] = {'version': [Gtk.get_major_version(), Gtk.get_minor_version(),
                                      Gtk.get_micro_version()], 'initialized': bool(Gtk.init_check())}
        require(evidence['gtk']['initialized'], 'GTK initialization')
        return evidence['gtk']
    record('gtk', gtk_check)
    record('glib', lambda: [GLib.MAJOR_VERSION, GLib.MINOR_VERSION, GLib.MICRO_VERSION])
    def media_check():
        Gst.init(None)
        evidence['gstreamer'] = Gst.version_string()
        for name in CONTRACT['media_factories']:
            evidence['factories'][name] = bool(Gst.ElementFactory.find(name))
            write_json(output / 'preflight.json', evidence)
        require(all(evidence['factories'].values()), 'media factories')
        return evidence['factories']
    record('factories', media_check)


def installed_check(manifest):
    for name, expected in manifest['payload'].items():
        path = Path('/') / name
        require(path.is_file() and not path.is_symlink() and
                digest(path.read_bytes()) == expected['sha256'] and
                path.stat().st_mode & 0o7777 == expected['mode'], 'installed bytes: ' + name)
    require(capture(['dpkg-query', '-W', '-f=${Status} ${Version} ${Architecture}',
                     CONTRACT['control']['Package']]) ==
            'install ok installed ' + CONTRACT['version'] + ' all', 'installed identity')


def internal(args):
    os.umask(0o022)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    if args.phase == 'preflight':
        preflight(out)
        return
    if args.phase == 'build-child':
        write_json(out / 'isolation.json', isolation())
        shutil.copyfile('/opt/evidence/dependencies.txt', out / 'dependencies.txt')
        build_evidence = json.loads((out / 'build-evidence.txt').read_text())
        build_evidence.update(dependencies_sha256=digest((out / 'dependencies.txt').read_bytes()),
                              python=sys.version, dpkg=capture(['dpkg-deb', '--version']))
        write_json(out / 'build-evidence.txt', build_evidence)
        evidence = json.loads((out / 'source.json').read_text())
        identity(evidence['source_sha'], evidence['source_epoch'])
        os.environ.update(ARGONAUT_SOURCE_COMMIT=evidence['source_sha'],
                          SOURCE_DATE_EPOCH=str(evidence['source_epoch']),
                          ARGONAUT_BUILD_EVIDENCE=str(out / 'build-evidence.txt'),
                          PYTHONDONTWRITEBYTECODE='1')
        command(['/usr/bin/python3', '/source/packaging/build_deb.py', '--source', '/source',
                 '--output', str(out), '--development', '--version', CONTRACT['version']],
                out / 'build.log', 180)
        verify_build(Path('/source'), out, evidence['source_sha'], evidence['source_epoch'])
        return
    manifest = json.loads(Path('/input/verified.json').read_text())
    if args.phase in ('install-child', 'remove-child'):
        require(os.getuid() == 0, 'installation requires disposable root')
        package = Path('/input') / CONTRACT['filename']
        verify_package(package, manifest)
        sentinel = Path('/home/runtime/.config/argonaut-development/preservation-check')
        if args.phase == 'install-child':
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text('preserve development configuration\n')
            for _ in range(2):
                command(['dpkg', '--install', str(package)], out / 'install.log', 60)
                installed_check(manifest)
                require(sentinel.read_text() == 'preserve development configuration\n', 'reinstall config')
            command(['dpkg', '--audit'], out / 'install.log')
        else:
            command(['dpkg', '--remove', CONTRACT['control']['Package']], out / 'remove.log', 60)
            require(sentinel.read_text() == 'preserve development configuration\n', 'remove config')
            require(not any((Path('/') / p).exists() for p in manifest['payload']), 'removed payload')
            write_json(out / 'removal.json', {'removed': True, 'configuration_preserved': True})
        return
    write_json(out / 'isolation.json', isolation())
    installed_check(manifest)
    shutil.copyfile('/opt/evidence/dependencies.txt', out / 'dependencies.txt')
    home = Path('/tmp/home')
    home.mkdir(mode=0o700)
    for name in ('config', 'cache', 'data', 'runtime'):
        (home / name).mkdir(mode=0o700)
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'LANG': 'C.UTF-8',
           'XDG_CONFIG_HOME': str(home / 'config'), 'XDG_CACHE_HOME': str(home / 'cache'),
           'XDG_DATA_HOME': str(home / 'data'), 'XDG_RUNTIME_DIR': str(home / 'runtime'),
           'GDK_BACKEND': 'x11', 'GSK_RENDERER': 'cairo', 'GTK_A11Y': 'none',
           'PYTHONDONTWRITEBYTECODE': '1'}
    # Both commands run under the same private display/session, with no host sockets.
    script = ('set -eu; /usr/bin/python3 /tool/run.py preflight --output /results; '
              'exec /usr/bin/argonaut-development --self-test /results/self-test.json')
    command(['xvfb-run', '-a', '-s', '-screen 0 1280x1024x24 -nolisten tcp',
             'dbus-run-session', '--', 'sh', '-c', script], out / 'self-test.log', 180, env=env)
    check_report(json.loads((out / 'self-test.json').read_text()), manifest['source_sha'])
    write_json(out / 'smoke.json', {'result': 'passed', 'sha256': manifest['sha256']})


def snapshot(repo, destination, output, sha):
    require(capture(['git', '-C', str(repo), 'rev-parse', 'HEAD']) == sha, 'checkout SHA mismatch')
    require(not capture(['git', '-C', str(repo), 'diff', 'HEAD', '--name-only']), 'tracked changes')
    epoch = int(capture(['git', '-C', str(repo), 'show', '-s', '--format=%ct', sha]))
    identity(sha, epoch)
    archive_path = output / 'source.tar'
    with archive_path.open('wb') as stream:
        subprocess.run(['git', '-C', str(repo), '-c', 'tar.umask=0022', 'archive', '--format=tar', sha],
                       stdout=stream, check=True, timeout=60)
    # Git archive includes committed files only; reject links and submodules.
    require('160000 commit' not in capture(['git', '-C', str(repo), 'ls-tree', '-r', sha]),
            'submodules unsupported')
    with tarfile.open(archive_path) as archive:
        for item in archive:
            require(item.isfile() or item.isdir(), 'snapshot links unsupported')
            require(not item.name.startswith('/') and '..' not in Path(item.name).parts,
                    'snapshot path')
        archive.extractall(destination, filter='data')
    evidence = {'source_sha': sha, 'source_epoch': epoch,
                'source_archive_sha256': digest(archive_path.read_bytes())}
    write_json(output / 'source.json', evidence)
    archive_path.unlink()
    return evidence


class Docker:
    def __init__(self, output, job):
        require(re.fullmatch('[a-z0-9][a-z0-9-]{0,90}', job), 'job name')
        self.output, self.job = output, job
        self.log = output / 'docker.log'
        self.termination_verified = False
        self.secondary_errors = []

    @contextmanager
    def preserve_primary(self, step):
        """Record a secondary failure without replacing an exception in flight."""
        primary = sys.exception()
        try:
            yield
        except BaseException as error:
            if primary is None:
                raise
            self.secondary_errors.append(error_evidence(error, step))

    def image(self, target):
        command(['docker', 'pull', 'ubuntu:24.04'], self.log, 180)
        base = json.loads(capture(['docker', 'image', 'inspect', 'ubuntu:24.04']))
        write_json(self.output / 'base-image.json', base)
        resolved = base[0]['RepoDigests'][0]
        require(re.fullmatch(r'ubuntu@sha256:[0-9a-f]{64}', resolved), 'resolved base digest')
        dockerfile = TOOLS.joinpath('Dockerfile').read_text().replace('FROM ubuntu:24.04', 'FROM ' + resolved)
        with tempfile.TemporaryFile() as stream:
            stream.write(dockerfile.encode()); stream.seek(0)
            command(['docker', 'build', '--target', target, '--tag', self.job,
                     '--build-arg', f'RUNTIME_UID={os.getuid()}',
                     '--build-arg', f'RUNTIME_GID={os.getgid()}', '-'],
                    self.log, 600, stdin=stream)
        info = json.loads(capture(['docker', 'image', 'inspect', self.job]))
        write_json(self.output / 'image.json', info)
        return info[0]['Id']

    def container(self, suffix, image, phase, mounts, root=False):
        self.termination_verified = False
        name = self.job + '-' + suffix
        pending = self.output / (name + '.pending')
        pending.write_text(name)
        flags = ['docker', 'create', '--name', name, '--label', 'argonaut.linux-job=' + self.job,
                 '--network', 'none', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                 '--cpus', '2', '--memory', '2g', '--memory-swap', '2g', '--pids-limit', '256',
                 '--ulimit', 'nofile=1024:1024', '--init',
                 '--tmpfs', '/tmp:rw,nosuid,nodev,size=512m,mode=1777',
                 '--env', 'PYTHONDONTWRITEBYTECODE=1']
        if root:
            flags += ['--user', '0:0', '--cap-add', 'CHOWN', '--cap-add', 'FOWNER',
                      '--cap-add', 'DAC_OVERRIDE']
        else:
            flags += ['--read-only', '--user', f'{os.getuid()}:{os.getgid()}']
        for source, target, readonly in mounts:
            require(',' not in str(source), 'comma in mount path')
            flags += ['--mount', f'type=bind,src={source},dst={target}' + (',readonly' if readonly else '')]
        flags += [image, '/usr/bin/python3', '/tool/run.py', phase, '--output', '/results']
        command(flags, self.log, 30)
        pending.unlink()
        try:
            command(['docker', 'start', '--attach', name], self.output / (suffix + '.log'), 300)
            state = json.loads(capture(['docker', 'inspect', name]))
            write_json(self.output / (suffix + '-container.json'), state)
            require(state[0]['State']['ExitCode'] == 0 and not state[0]['State']['OOMKilled'],
                    'container exit/OOM')
        finally:
            with self.preserve_primary(suffix + '-termination'):
                self.termination_verified = self.stop_and_verify(name, suffix)
                require(self.termination_verified, 'container termination unverified; removal test blocked')
        return name

    def smoke_and_remove(self, image, mounts):
        try:
            self.container('runtime', image, 'smoke-child', mounts)
        finally:
            if self.termination_verified:
                with self.preserve_primary('removal'):
                    self.container('remove', image, 'remove-child', mounts, root=True)
            else:
                write_json(self.output / 'removal.json', {'result': 'skipped',
                    'reason': 'smoke container termination unverified'})

    def stop_and_verify(self, name, suffix):
        # Preserve the filesystem and logs until global cleanup, including on timeout.
        evidence = {'name': name, 'stopped': False, 'errors': []}
        def inspect():
            state = json.loads(capture(['docker', 'inspect', name], timeout=15))
            evidence['state'] = state
            write_json(self.output / (suffix + '-final.json'), state)
            status = state[0]['State']
            return (status.get('Running') is False and status.get('Restarting') is False
                    and status.get('Status') in ('exited', 'created', 'dead'))
        try:
            evidence['stopped'] = inspect()
        except Exception as error:
            evidence['errors'].append('inspect: ' + str(error))
        for operation in (['stop', '--time', '10', name], ['kill', name]):
            if evidence['stopped']:
                break
            try:
                command(['docker', *operation], self.log, 20)
            except Exception as error:
                evidence['errors'].append(operation[0] + ': ' + str(error))
            try:
                evidence['stopped'] = inspect()
            except Exception as error:
                evidence['errors'].append('inspect: ' + str(error))
        write_json(self.output / (suffix + '-termination.json'), evidence)
        return evidence['stopped']

    def cleanup(self):
        failed = []
        pending = list(self.output.glob('*.pending'))
        for _ in range(10 if pending else 1):
            try:
                ids = capture(['docker', 'ps', '-aq', '--filter', 'label=argonaut.linux-job=' + self.job]).split()
                for item in ids:
                    for operation in (['inspect', item], ['logs', item], ['stop', '--time', '10', item],
                                      ['rm', '--force', item]):
                        try:
                            command(['docker', *operation], self.output / 'cleanup.log', 25)
                        except Exception as error:
                            failed.append(str(error))
            except Exception as error:
                failed.append(str(error))
            if pending:
                time.sleep(1)
        try:
            remaining = capture(['docker', 'ps', '-aq', '--filter', 'label=argonaut.linux-job=' + self.job])
        except Exception as error:
            remaining = 'unverified'
            failed.append(str(error))
        # Remove only this job's image tags; keep the shared pulled base cache.
        for tag in (self.job + '-installed', self.job):
            try:
                if capture(['docker', 'image', 'ls', '-q', tag]):
                    command(['docker', 'image', 'rm', tag], self.output / 'cleanup.log', 30)
                require(not capture(['docker', 'image', 'ls', '-q', tag]), 'remaining image: ' + tag)
            except Exception as error:
                failed.append(str(error))
        evidence = {'remaining': remaining, 'errors': failed,
                    'unresolved_creation': [p.name for p in pending]}
        write_json(self.output / 'cleanup.json', evidence)
        with (self.output / 'cleanup-history.jsonl').open('a') as stream:
            stream.write(json.dumps(evidence) + '\n')
        require(not remaining and not failed and not pending, 'cleanup failure/uncertain creation')


def host(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    docker = Docker(out, args.job)
    if args.phase == 'cleanup':
        docker.cleanup()
        return
    require(os.getuid() != 0, 'host must be nonroot')
    require(not (out / 'status.json').exists(), 'use a fresh output directory')
    status = {'phase': args.phase, 'result': 'running'}
    write_json(out / 'status.json', status)
    try:
        command(['docker', 'version'], out / 'environment.log')
        command(['uname', '-a'], out / 'environment.log')
        with tempfile.TemporaryDirectory(prefix='argonaut-linux-') as directory:
            temp = Path(directory)
            tool = temp / 'tool'; tool.mkdir()
            for name in ('run.py', 'verify.py', 'contract.json'):
                shutil.copyfile(TOOLS / name, tool / name)
            mounts = [(tool, '/tool', True), (out, '/results', False)]
            if args.phase == 'build':
                source = temp / 'source'; source.mkdir()
                evidence = snapshot(args.source.resolve(), source, out, args.sha)
                image = docker.image('build')
                (out / 'build-evidence.txt').write_text(json.dumps({**evidence, 'image': image,
                    'base': json.loads((out / 'base-image.json').read_text())[0]['RepoDigests'],
                    'runner_os': os.environ.get('ImageOS'), 'runner_version': os.environ.get('ImageVersion')},
                    sort_keys=True) + '\n')
                docker.container('build', image, 'build-child', mounts + [(source, '/source', True)])
            else:
                incoming = args.input.resolve()
                require(sorted(p.name for p in incoming.iterdir()) ==
                        sorted([CONTRACT['filename'], 'verified.json', 'SHA256SUMS']), 'handoff files')
                require(re.fullmatch('[0-9a-f]{64}', args.manifest_sha or ''), 'trusted manifest checksum')
                require(digest((incoming / 'verified.json').read_bytes()) == args.manifest_sha,
                        'handoff manifest checksum')
                manifest = json.loads((incoming / 'verified.json').read_text())
                require(manifest['source_sha'] == args.sha, 'handoff source SHA')
                require((incoming / 'SHA256SUMS').read_text() ==
                        manifest['sha256'] + '  ' + CONTRACT['filename'] + '\n', 'checksum manifest')
                verify_package(incoming / CONTRACT['filename'], manifest)
                image = docker.image('runtime')
                mounts += [(incoming, '/input', True)]
                installer = docker.container('install', image, 'install-child', mounts, root=True)
                tag = args.job + '-installed'
                command(['docker', 'commit', installer, tag], docker.log, 60)
                installed = json.loads(capture(['docker', 'image', 'inspect', tag]))
                write_json(out / 'installed-image.json', installed)
                docker.smoke_and_remove(installed[0]['Id'], mounts)
            status['result'] = 'passed'
    except BaseException as error:
        status.update(result='failed', error=type(error).__name__ + ': ' + str(error),
                      primary_error=error_evidence(error, args.phase))
        write_json(out / 'status.json', {**status, 'secondary_errors': docker.secondary_errors})
        raise
    finally:
        try:
            with docker.preserve_primary('cleanup'):
                docker.cleanup()
        except BaseException as error:
            status.update(result='failed', error=type(error).__name__ + ': ' + str(error),
                          primary_error=error_evidence(error, 'cleanup'))
            raise
        finally:
            write_json(out / 'status.json', {**status, 'secondary_errors': docker.secondary_errors})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['build', 'smoke', 'cleanup', 'build-child',
                        'install-child', 'remove-child', 'smoke-child', 'preflight'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=Path.cwd())
    parser.add_argument('--input', type=Path)
    parser.add_argument('--sha')
    parser.add_argument('--manifest-sha')
    parser.add_argument('--job', default=os.environ.get('ARGONAUT_LINUX_JOB', 'argonaut-linux-local'))
    args = parser.parse_args()
    def interrupted(signum, frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise InterruptedError(f'signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    if args.phase.endswith('-child') or args.phase == 'preflight':
        internal(args)
    else:
        host(args)


if __name__ == '__main__':
    main()
