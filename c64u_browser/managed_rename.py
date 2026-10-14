# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit same-lease continuation; no publication, retry or cleanup authority."""
import threading
import time
from .api import BrowserError
from .required_evidence import RequiredEvidence


class RenameStopped(BrowserError):
    retryable = False
    code = 'evidenced-rename-stopped'
    def __init__(self, owner):
        self.rename_owner = owner
        super().__init__('Evidenced rename stopped; retain evidence and inspect. No retry authorized.')


class ManagedRename:
    """Entry-issued live owner. Copying/serializing it cannot continue a rename.

    Use adapter.begin_evidenced_rename inside an explicit adapter.operation.
    Begin persists intent and outcome and returns RNFR evidence only. The owner
    must explicitly invoke continue_rename() while still in that operation.
    Any failure poisons this operation. Leaving the operation abandons a pending
    server RNFR by closing the connection, never by sending another FTP command.
    """
    def __init__(self, adapter, state, client, source, destination, sink):
        self._adapter, self._state, self._client = adapter, state, client
        self._source, self._destination = source, destination
        self._thread = threading.get_ident()
        self._expires = time.monotonic() + 300
        self._lease = client.identity
        self._channel = sink if type(sink) is RequiredEvidence else RequiredEvidence(sink)
        self._wire = None
        self._rnfr = self._rnto = None
        self._continued = self._finished = self._blocked = False
        self._active = True
        self._ready = False

    @property
    def rnfr(self): return self._rnfr
    @property
    def rnto(self): return self._rnto
    @property
    def verified(self): return self._finished and not self._blocked and not self._channel.blocked
    @property
    def blocked(self): return self._blocked or self._channel.blocked

    def _check(self, *, cancellation=True):
        a = self._adapter
        if (a._rename_owners.get(id(self)) is not self or not self._active or self.blocked or
                self._finished or threading.get_ident() != self._thread or
                time.monotonic() >= self._expires or a._context.get() is not self._state or
                self._state.rename_owner is not self or self._state.client is not self._client or
                self._client.identity != self._lease):
            raise RenameStopped(self)
        a._manager._check(a.binding)
        with a._manager._lock:
            if a._manager._leases.get(self._lease.device_id) is not self._client:
                raise RenameStopped(self)
        if cancellation:
            self._state.check_required()
            self._client._check()
        else:
            if not self._client._rename_ready():raise RenameStopped(self)

    def _dispatch(self):
        return self._channel.dispatch(self._check)

    def _intent(self, verb):
        return dict(verb=verb, source_hex=self._source.hex(), destination_hex=self._destination.hex(),
                    request_hex=(verb.encode() + b' ' +
                        (self._source if verb == 'RNFR' else self._destination) + b'\r\n').hex(),
                    device_id=self._lease.device_id, core_session_id=self._lease.core_session_id,
                    ftp_session_id=self._lease.ftp_session_id, adapter_owner=self._adapter._owner_id)

    def _stop(self, exc):
        self._blocked = True
        self._adapter._evidence_blocked = True
        self._state.failure = exc
        # Keep this owner in the adapter registry. No successor can get a client.
        # Context exit will abandon the socket without remote cleanup commands.
        if getattr(exc, 'cancelled', False):
            self._channel.save('rename-cancellation', dict(
                device_id=self._lease.device_id, core_session_id=self._lease.core_session_id,
                ftp_session_id=self._lease.ftp_session_id,
                rnfr_submitted=self._rnfr is not None and self._rnfr.submitted,
                rnto_submitted=self._rnto is not None and self._rnto.submitted,
                completed=False))

    def _begin(self):
        try:
            self._check()
            self._channel.save('rnfr-intent', self._intent('RNFR'))
            self._check()
            self._wire = self._client._begin_owned_rename(self._source, self._destination, self._dispatch)
            self._rnfr = self._wire.rnfr()
            self._channel.save('rnfr-outcome', self._rnfr.private_record())
            if not self._rnfr.accepted:
                self._state.check_required()
                raise RenameStopped(self)
            self._check()
            self._ready = True
            return self
        except BaseException as exc:
            self._stop(exc)
            raise

    def continue_rename(self):
        """No target arguments: continuation cannot select a different destination."""
        try:
            self._check()
            if not self._ready or self._continued or self._rnfr is None or not self._rnfr.accepted:
                raise RenameStopped(self)
            self._ready = False
            self._continued = True  # consumed even if intent persistence fails
            self._channel.save('rnto-intent', self._intent('RNTO'))
            self._check()
            self._rnto = self._wire.rnto()
            # Persist acceptance before honoring subsequent cancellation.
            self._channel.save('rnto-outcome', self._rnto.private_record())
            if not self._rnto.accepted:
                self._state.check_required()
                raise RenameStopped(self)
            self._check(cancellation=False)
            self._finished = True
            self._wire.finish()
            self._state.rename_owner = None
            self._active = False
            del self._adapter._rename_owners[id(self)]
            return self._rnfr, self._rnto
        except BaseException as exc:
            self._stop(exc)
            raise

    def _scope_ended(self):
        self._active = False
        if self._wire is not None: self._wire.abandon()
        if not self._finished:
            self._blocked = True
            self._adapter._evidence_blocked = True
