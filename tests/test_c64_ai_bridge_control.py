import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from c64u_browser.api import BrowserError
from c64u_browser.c64_ai_bridge_config import (
    C64BridgeConfig, load_bridge_config, save_bridge_config,
)
from c64u_browser.c64_ai_bridge_control import (
    SERVICE, activate_bridge, bridge_status, local_bridge_host,
    pair_bridge_address, setup_bridge,
)


TOKEN = 'T' * 48


def result(args, code=0, output=''):
    return subprocess.CompletedProcess(args, code, stdout=output, stderr='')


class C64AIBridgeControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'bridge.json'
        self.config = C64BridgeConfig(
            'gemma3:4b', '192.0.2.1', 6464, ('192.0.2.10',), TOKEN)

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_setting_reports_setup_without_checking_service(self):
        called = []
        status = bridge_status(self.path, lambda *args, **kwargs: called.append(args))
        self.assertEqual(status.state, 'setup')
        self.assertIn('Setup needed', status.message)
        self.assertEqual(called, [])

    def test_ready_status_contains_no_private_token(self):
        save_bridge_config(self.path, self.config)

        def runner(args, **_kwargs):
            self.assertEqual(args[:2], ['systemctl', '--user'])
            self.assertEqual(args[-1], SERVICE)
            return result(args, output='active\n' if args[2] == 'is-active'
                          else 'enabled\n')

        status = bridge_status(self.path, runner)
        self.assertEqual(status.state, 'ready')
        self.assertTrue(status.enabled)
        self.assertEqual(status.allowed_clients, ('192.0.2.10',))
        self.assertNotIn(TOKEN, status.message)
        self.assertIn('1 paired address', status.message)

    def test_pair_preserves_token_adds_address_and_restarts(self):
        save_bridge_config(self.path, self.config)
        commands = []

        def runner(args, **_kwargs):
            commands.append(args[2])
            if args[2] == 'is-active':
                return result(args, output='active\n')
            return result(args, output='enabled\n')

        status = pair_bridge_address(self.path, '192.0.2.11', runner)
        stored = load_bridge_config(self.path)
        self.assertEqual(stored.token, TOKEN)
        self.assertEqual(stored.allowed_clients,
                         ('192.0.2.10', '192.0.2.11'))
        self.assertEqual(status.state, 'ready')
        self.assertEqual(commands, ['restart', 'is-active', 'is-enabled'])

    def test_activate_restarts_and_requires_ready_service(self):
        save_bridge_config(self.path, self.config)
        commands = []

        def runner(args, **_kwargs):
            commands.append(args[2])
            if args[2] == 'is-active':
                return result(args, output='active\n')
            return result(args, output='enabled\n')

        self.assertEqual(activate_bridge(self.path, runner).state, 'ready')
        self.assertEqual(commands, ['restart', 'is-active', 'is-enabled'])

    def test_activate_reloads_newly_installed_user_service(self):
        save_bridge_config(self.path, self.config)
        commands = []

        def runner(args, **_kwargs):
            command = args[2]
            commands.append(command)
            if command == 'restart' and commands.count('restart') == 1:
                return result(args, code=5)
            return result(args, output=('active\n' if command == 'is-active'
                                        else 'enabled\n'))

        self.assertEqual(activate_bridge(self.path, runner).state, 'ready')
        self.assertEqual(commands,
                         ['restart', 'daemon-reload', 'restart',
                          'is-active', 'is-enabled'])

    def test_failed_restart_restores_previous_pairing(self):
        save_bridge_config(self.path, self.config)
        restarts = 0

        def runner(args, **_kwargs):
            nonlocal restarts
            if args[2] == 'restart':
                restarts += 1
                return result(args, code=1 if restarts == 1 else 0)
            return result(args, output='active\n')

        with self.assertRaises(BrowserError):
            pair_bridge_address(self.path, '192.0.2.11', runner)
        self.assertEqual(load_bridge_config(self.path), self.config)
        self.assertEqual(restarts, 2)

    def test_existing_pairing_does_not_restart(self):
        save_bridge_config(self.path, self.config)
        commands = []

        def runner(args, **_kwargs):
            commands.append(args[2])
            return result(args, output=('active\n' if args[2] == 'is-active'
                                        else 'enabled\n'))

        status = pair_bridge_address(self.path, '192.0.2.10', runner)
        self.assertEqual(status.state, 'ready')
        self.assertEqual(commands, ['is-active', 'is-enabled'])

    def test_setup_uses_route_address_private_token_and_starts(self):
        class RouteSocket:
            def connect(self, destination):
                self.destination = destination
            def getsockname(self):
                return ('192.0.2.1', 40000)
            def close(self):
                pass

        def socket_factory(*_args):
            return RouteSocket()

        commands = []
        def runner(args, **_kwargs):
            command = args[2]
            commands.append(command)
            if command == 'is-enabled' and commands.count('is-enabled') == 1:
                return result(args, code=1, output='disabled\n')
            return result(args, output=('active\n' if command == 'is-active'
                                        else 'enabled\n'))

        status = setup_bridge(
            self.path, 'gemma3:4b', '192.0.2.10', runner,
            socket_factory, lambda size: 'ab' * size)
        stored = load_bridge_config(self.path)
        self.assertEqual(status.state, 'ready')
        self.assertEqual(stored.host, '192.0.2.1')
        self.assertEqual(stored.allowed_clients, ('192.0.2.10',))
        self.assertEqual(stored.token, ('AB' * 32))
        self.assertEqual(commands[:4],
                         ['daemon-reload', 'is-enabled', 'enable', 'restart'])

    def test_failed_setup_removes_new_private_setting(self):
        route = Mock()
        route.getsockname.return_value = ('192.0.2.1', 40000)
        socket_factory = Mock(return_value=route)
        runner = Mock(return_value=result([], code=1))
        with self.assertRaises(BrowserError):
            setup_bridge(
                self.path, 'gemma3:4b', '192.0.2.10', runner,
                socket_factory, lambda _size: 'A' * 64)
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()
