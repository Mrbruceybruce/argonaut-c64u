"""Explicit Issue #25 offline gate; no application imports before isolation proof."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import run_ci_tests as runner

SELECTORS = [('test_ultimate_menu_gate_a.RealGtkMenu', 11),
             ('test_configuration_dependencies.CoreDependencies', 24),
             ('test_dependencies.LEDTests', 2)]


def guard():
    def audit(event, args):
        if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
            raise PermissionError('Gate A denies non-Unix Python sockets')
        if event in ('socket.getaddrinfo', 'socket.gethostbyname', 'socket.gethostbyaddr'):
            raise PermissionError('Gate A denies DNS')
    sys.addaudithook(audit)
    for family in (socket.AF_INET, socket.AF_INET6):
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            try:
                socket.socket(family, kind)
            except PermissionError:
                continue
            raise RuntimeError('Socket denial self-check failed')

    print('Socket guard self-check: IPv4/IPv6 TCP/UDP denied before application imports', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inside', action='store_true')
    parser.add_argument('--selector')
    parser.add_argument('--parent')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.selector:
        runner.verify_network(args.parent)
        guard()
        os.environ['ARGONAUT_GATE_A_NETNS'] = os.readlink('/proc/self/ns/net')
        runner.preflight('gtk-regression')
        return runner.child(args.selector, out)
    if args.inside:
        runner.write_json(out / 'network.json', runner.verify_network(args.parent))
        report = {'ok': False, 'classes': []}
        with tempfile.TemporaryDirectory(prefix='argonaut-gate-a-home-') as temp:
            env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONUNBUFFERED': '1',
                   'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                   'GDK_BACKEND': 'x11', 'GSK_RENDERER': 'cairo', 'NO_AT_BRIDGE': '1'}
            for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_RUNTIME_DIR'):
                path = Path(temp) / key; path.mkdir(mode=0o700); env[key] = str(path)
            runner.write_json(out / 'environment.json', env)
            for selector, count in SELECTORS:
                target = out / (selector + '.json')
                command = ['xvfb-run', '-a', '-s', '-screen 0 1280x1024x24 -nolisten tcp',
                           'dbus-run-session', '--', '/usr/bin/python3', '-B', str(Path(__file__).resolve()),
                           '--selector', selector, '--parent', args.parent, '--output', str(target)]
                result = runner.bounded(command, 150, out / (selector + '.log'), env)
                details = json.loads(target.read_text()) if target.exists() else {}
                result.update(selector=selector, details=details,
                              ok=result['returncode'] == 0 and not result['timeout']
                              and details.get('ok', False) and details.get('tests') == count)
                report['classes'].append(result)
                runner.write_json(out / 'summary.json', report)
            report['ok'] = all(row['ok'] for row in report['classes'])
            runner.write_json(out / 'summary.json', report)
            return 0 if report['ok'] else 1
    out.mkdir(parents=True, exist_ok=False)
    command = ['unshare', '--user', '--map-current-user', '--keep-caps', '--net', '--',
               'sh', '-ec', 'ip link set lo up; exec setpriv --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all "$@"',
               'gate-a', '/usr/bin/python3', '-B', str(Path(__file__).resolve()), '--inside',
               '--parent', os.readlink('/proc/self/ns/net'), '--output', str(out)]
    result = runner.bounded(command, 495, out / 'namespace.log', supervisor=True)
    runner.write_json(out / 'launcher.json', result)
    return 1 if result['timeout'] else result['returncode']


if __name__ == '__main__':
    raise SystemExit(main())
