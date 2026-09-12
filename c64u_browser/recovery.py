# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Read-only health checks and bounded reconnect backoff for one active profile."""
from .storage import initial_directory
import time
from gi.repository import GLib
from .api import UltimateClient, ConnectionFailure


class Recovery:
    def __init__(self, app):
        self.app=app;self.generation=0;self.profile=None;self.client=None
        self.info=None;self.offline=False;self.paused=False;self.inflight=False
        self.next_check=0;self.delay=5
        self.timer=GLib.timeout_add_seconds(5,self.tick)

    def watch(self, profile, client, info):
        self.cancel()
        self.profile=profile;self.client=client;self.info=info
        self.next_check=time.monotonic()+5

    def cancel(self):
        self.generation+=1;self.profile=None;self.client=None;self.info=None
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
        recovering_client=self.client;preferred=getattr(self.app,"remote_root","/USB2")
        client=UltimateClient(self.client.host,self.client.password,port=self.client.port,http_port=self.client.http_port,timeout=3)
        self.inflight=True
        def task():
            try:
                info=client.test_connection()
                if self.profile.device_id or self.profile.device_mac:
                    self.profile.verify_identity(info)
                expected=self.info['info'].get('unique_id')
                if not (self.profile.device_id or self.profile.device_mac) and expected and info['info'].get('unique_id')!=expected:
                    raise ConnectionFailure('identity','A different device answered at this address. Connect manually.')
                if was_offline and not expected and not self.profile.device_mac:
                    raise ConnectionFailure('identity','No device ID was available to verify reconnection. Connect manually.')
                listing=initial_directory(client,preferred) if was_offline else None
                if was_offline:recovering_client.storage_roots=client.storage_roots
                return info,listing
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
            if isinstance(result,ConnectionFailure) and result.kind in ('authentication','identity'):
                self.paused=True
                self.app.connection_lost(str(result)+' Automatic retries stopped; use Connections.')
            else:
                self.next_check=time.monotonic()+self.delay
                self.delay=min(self.delay*2,30)
            return
        info,listing=result
        self.delay=5;self.next_check=time.monotonic()+5
        if was_offline:
            self.offline=False
            self.app.connection_restored(self.client,info,listing)
