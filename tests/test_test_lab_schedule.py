import unittest

from c64u_browser.test_lab_schedule import HardwareSchedule


class ScheduleTests(unittest.TestCase):
    def test_waits_until_due_and_defers_while_busy_or_disconnected(self):
        schedule = HardwareSchedule(interval=30)
        schedule.enable(100)
        self.assertFalse(schedule.due(129, connected=True, busy=False))
        self.assertFalse(schedule.due(130, connected=False, busy=False))
        self.assertFalse(schedule.due(160, connected=True, busy=True))
        self.assertTrue(schedule.due(160, connected=True, busy=False))
        schedule.mark_run(160)
        self.assertFalse(schedule.due(161, connected=True, busy=False))
        self.assertTrue(schedule.due(190, connected=True, busy=False))

    def test_reconnection_runs_once_without_catchup_flood(self):
        schedule = HardwareSchedule(interval=30)
        schedule.enable(0)
        self.assertFalse(schedule.due(300, connected=False, busy=False))
        self.assertTrue(schedule.due(301, connected=True, busy=False))
        schedule.mark_run(301)
        self.assertFalse(schedule.due(302, connected=True, busy=False))
        schedule.disable()
        self.assertFalse(schedule.due(400, connected=True, busy=False))
        self.assertIsNone(schedule.next_due)


if __name__ == '__main__':
    unittest.main()
