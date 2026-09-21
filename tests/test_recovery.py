# SPDX-License-Identifier: GPL-3.0-or-later
from types import SimpleNamespace
import unittest

from c64u_browser.core import CoreError
from c64u_browser.recovery import Recovery
from c64u_browser.scheduler import DeviceSession


class FakeCore:
    def __init__(self):
        self.session = DeviceSession('id:25EA78', 'session-before-preview')

    def device_session(self):
        return self.session


class FakeApp:
    def __init__(self):
        self.core = FakeCore()
        self.status = SimpleNamespace(set_text=lambda value:setattr(
            self, 'status_text', value))
        self.status_text = ''
        self.lost = []

    def connection_lost(self, message):
        self.lost.append(message)
        self.core.session = DeviceSession(self.core.session.device_id, '')


def recovery_for(app):
    recovery = Recovery.__new__(Recovery)
    recovery.app = app
    recovery.generation = 0
    recovery.profile = object()
    recovery.offline = False
    recovery.paused = False
    recovery.inflight = False
    recovery.next_check = 0
    recovery.delay = 5
    recovery.health_failures = 0
    recovery.timer = None
    return recovery


class RecoverySessionTests(unittest.TestCase):
    def test_transient_health_timeout_keeps_reviewed_session(self):
        app = FakeApp()
        recovery = recovery_for(app)
        preview_session = app.core.device_session()

        recovery.accept(CoreError(
            'network', 'Timed out reading C64U identity.', retryable=True),
            was_offline=False)

        self.assertEqual(preview_session, app.core.device_session())
        self.assertFalse(app.lost)
        self.assertEqual(1, recovery.health_failures)
        self.assertIn('confirming', app.status_text)

        recovery.accept(None, was_offline=False)
        self.assertEqual(preview_session, app.core.device_session())
        self.assertEqual(0, recovery.health_failures)

    def test_confirmed_health_failure_ends_session(self):
        app = FakeApp()
        recovery = recovery_for(app)
        error = CoreError('network', 'C64U is unavailable.', retryable=True)

        recovery.accept(error, was_offline=False)
        recovery.accept(error, was_offline=False)

        self.assertEqual(['C64U is unavailable.'], app.lost)
        self.assertEqual('', app.core.device_session().session_id)
        self.assertTrue(recovery.offline)

    def test_identity_failure_is_not_retried(self):
        app = FakeApp()
        recovery = recovery_for(app)

        recovery.accept(CoreError(
            'identity', 'A different C64U answered.'), was_offline=False)

        self.assertTrue(app.lost)
        self.assertTrue(recovery.paused)
        self.assertEqual('', app.core.device_session().session_id)


if __name__ == '__main__':unittest.main()
