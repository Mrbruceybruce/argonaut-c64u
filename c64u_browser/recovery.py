# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Read-only health checks and bounded reconnect backoff for one active profile."""
import time
from gi.repository import GLib
from .core import CoreError


class Recovery:
    def __init__(self, app):
        self.app=app;self.generation=0;self.profile=None
        self.offline=False;self.paused=False;self.inflight=False
        self.next_check=0;self.delay=5
        self.timer=GLib.timeout_add_seconds(5,self.tick)

    def watch(self):
        self.cancel()
        self.profile=self.app.core.active_profile
        self.next_check=time.monotonic()+5

    def cancel(self):
        self.generation+=1;self.profile=None
        self.offline=False;self.paused=False;self.delay=5

    def close(self):
        self.cancel()
        if self.timer:GLib.source_remove(self.timer);self.timer=None

    def lost(self, message='C64U is offline. Reconnecting…'):
        if not self.profile:return
        self.offline=True;self.next_check=time.monotonic()+5
        self.app.connection_lost(message)

    def tick(self):
        if not self.profile or self.paused or self.inflight or self.app.busy or time.monotonic()<self.next_check:return True
        generation=self.generation;was_offline=self.offline
        preferred=getattr(self.app,"remote_root","/USB2")
        self.inflight=True
        def task():
            try:
                if was_offline:return self.app.core.reconnect(preferred)
                # A connected health check uses the same identity rules but
                # does not replace the active session unless recovery is needed.
                self.app.core.check_health()
                return None
            except Exception as exc:return exc
        future=self.app.pool.submit(task)
        def finish():
            if generation!=self.generation:
                self.inflight=False;return False
            if self.app.busy:
                GLib.timeout_add(100,finish);return False
            self.inflight=False
            self.accept(future.result(),was_offline)
            return False
        future.add_done_callback(lambda _:GLib.idle_add(finish))
        return True

    def accept(self, result, was_offline):
        if isinstance(result,Exception):
            self.lost(str(result))
            if isinstance(result,CoreError) and result.code in ('authentication','identity'):
                self.paused=True
                self.app.connection_lost(str(result)+' Automatic retries stopped; use Connections.')
            else:
                self.next_check=time.monotonic()+self.delay
                self.delay=min(self.delay*2,30)
            return
        self.delay=5;self.next_check=time.monotonic()+5
        if was_offline:
            self.offline=False
            self.app.connection_restored(result)
