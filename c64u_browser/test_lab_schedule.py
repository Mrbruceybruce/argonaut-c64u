# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Session-only timing rule for optional read-only hardware checks."""


INTERVAL_SECONDS = 30 * 60


class HardwareSchedule:
    def __init__(self, interval=INTERVAL_SECONDS):
        self.interval = interval
        self.enabled = False
        self.next_due = None

    def enable(self, now):
        self.enabled = True
        self.next_due = now + self.interval

    def disable(self):
        self.enabled = False
        self.next_due = None

    def due(self, now, connected, busy):
        return (self.enabled and self.next_due is not None
                and now >= self.next_due and connected and not busy)

    def mark_run(self, now):
        self.next_due = now + self.interval
