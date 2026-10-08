# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Browser ownership state only; callbacks and work always run outside its mutex.

GTK owns binding/release. Tokens retain ownership between short state transitions;
Core scheduling, transport and cancellation remain outside this primitive.
"""
from threading import Lock


class ForegroundSlot:
    def __init__(self):
        self._admission = Lock()
        self.token = None
        self.job = None

    def reserve(self):
        if not self._admission.acquire(blocking=False):
            return None
        try:
            if self.token is not None:return None
            self.token = object()
            return self.token
        finally:self._admission.release()

    def bind(self, token, job):
        with self._admission:
            if token is not self.token or token is None or self.job is not None:
                raise RuntimeError('Invalid foreground reservation.')
            self.job = job

    def owns(self, token, job):
        with self._admission:
            return token is not None and token is self.token and job is self.job

    def release(self, token, job=None):
        # None releases only a failed/unbound reservation; an active release
        # must also match its job. Terminal eligibility is checked by Browser.
        with self._admission:
            if token is None or token is not self.token or job is not self.job:
                return False
            self.token = self.job = None
            return True
