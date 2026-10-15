# SPDX-License-Identifier: GPL-3.0-or-later
"""Core-owned C64U FTP transport.

One operation-scoped lease, no pool, no retries, no generic command/socket API.
All wire parsing uses bytes. Only this module owns the sockets. Core services
retain authorization, staging, integrity policy and filesystem scope decisions.
"""
from contextlib import contextmanager, nullcontext
from dataclasses import replace
import errno
import hashlib
import re
import socket
import threading
import time
import uuid

from .c64u_ftp_types import (
    CapabilityState as CS, ContainerPresentation, C64UFtpCapabilities,
    ConnectionBinding, ErrorCode as EC, FtpOperationError, FtpPolicy,
    FtpSessionIdentity, ListingLimits, ListingParser, ListingResult,
    Outcome, SessionState, TransferResult, MutationEvidence, WriteEvidence, checked_path,
)


class C64UFtpLeaseManager:
    """One live lease per physical device (below the four-session ceiling).

    binding_provider(device_id) returns the current ConnectionBinding, or None.
    password_provider(binding) supplies the private Network Password transiently.
    Nested helpers must receive the existing client, not acquire another lease.
    Busy acquisition fails promptly; scheduling/waiting belongs to Core jobs.
    """
    def __init__(self, binding_provider, password_provider, *, policy=None,
                 diagnostic=None):
        self._binding_provider = binding_provider
        self._password_provider = password_provider
        self._policy = policy or FtpPolicy()
        self._diagnostic = diagnostic
        self._lock = threading.Lock()
        self._leases = {}
        self._recovering = set()

    @property
    def active_count(self):
        with self._lock:
            return len(self._leases)

    def _check(self, binding):
        with self._lock:
            recovering = binding.device.physical_id in self._recovering
        if recovering:
            raise FtpOperationError(EC.RECOVERING, 'binding')
        if self._binding_provider(binding.device.physical_id) != binding:
            raise FtpOperationError(EC.STALE, 'binding')

    def invalidate(self, device_id, *, recovering=False):
        """Called by the future Core recovery owner; never reconnects/replays."""
        with self._lock:
            if recovering:
                self._recovering.add(device_id)
            client = self._leases.get(device_id)
        if client is not None:
            client._invalid_reason = EC.RECOVERING if recovering else EC.STALE
            client._invalidate(SessionState.RECOVERING if recovering else SessionState.FAILED)

    def recovery_complete(self, device_id):
        with self._lock:
            self._recovering.discard(device_id)

    @contextmanager
    def lease(self, binding, *, presentation=ContainerPresentation.FILES,
              cancelled=None):
        if (not isinstance(binding, ConnectionBinding) or
                not binding.device.physical_id or not binding.core_session_id or
                not isinstance(binding.host, str) or not binding.host or
                any(c.isspace() for c in binding.host) or
                any(c in binding.host for c in '/:@?#') or
                type(binding.port) is not int or not 1 <= binding.port <= 65535 or
                not isinstance(presentation, ContainerPresentation)):
            raise FtpOperationError(EC.INVALID_ARGUMENT, 'binding')
        self._check(binding)
        client = C64UFtpClient(self, binding, presentation, cancelled)
        key = binding.device.physical_id
        with self._lock:
            if key in self._leases:
                raise FtpOperationError(EC.BUSY, 'lease')
            self._leases[key] = client
        try:
            client._open()
            yield client
        finally:
            client.close()
            with self._lock:
                self._leases.pop(key, None)


class C64UFtpClient:
    """Obtain through manager.lease(); not a GUI-facing service contract.

    read_into/write_from use caller-prepared binary streams. Read bounds are
    mandatory. write_from's expected_bytes is exact and must be known before
    PASV. Successful STOR is transport completion, NOT readback verification.
    cancellation is a zero-argument boolean predicate, never a retry request.
    """
    def __init__(self, manager, binding, presentation, cancelled):
        self._manager = manager
        self._binding = binding
        self._policy = manager._policy
        self._cancelled = cancelled or (lambda: False)
        self._control = None
        self._data = None
        self._buffer = bytearray()
        self._operation_lock = threading.Lock()
        self._state = SessionState.DISCONNECTED
        self._identity = FtpSessionIdentity(binding.device.physical_id,
                                            binding.core_session_id, uuid.uuid4().hex)
        self._capabilities = C64UFtpCapabilities(presentation, binding.device)
        self._operation = 'open'
        self._phase = 'control-connect'
        self._count = 0
        self._submitted = False
        self._invalid_reason = None
        self._cancel_deferred = 0
        self._mutation = None
        self._write = None

    @property
    def identity(self):
        return self._identity

    @property
    def state(self):
        return self._state

    @property
    def capabilities(self):
        return self._capabilities

    def _event(self, kind, **fields):
        callback = self._manager._diagnostic
        if callback is None:
            return
        event = dict(schema=1, timestamp=time.time(), kind=kind,
                     device_id=self._identity.device_id,
                     core_session_id=self._identity.core_session_id,
                     ftp_session_id=self._identity.ftp_session_id,
                     operation=self._operation, phase=self._phase)
        event.update(fields)
        try:
            callback(event)
        except Exception:
            # An optional diagnostic sink cannot interrupt a consequential command.
            pass

    def _state_to(self, state):
        previous = self._state
        self._state = state
        self._event('lifecycle', previous=previous.value, state=state.value)

    def _check(self):
        if self._invalid_reason is not None:
            raise FtpOperationError(self._invalid_reason, 'binding')
        self._manager._check(self._binding)
        if not self._cancel_deferred and self._cancelled():
            raise FtpOperationError(EC.CANCELLED, self._phase)
        if self._state in (SessionState.FAILED, SessionState.RECOVERING):
            raise FtpOperationError(EC.STALE, self._phase)

    def _invalidate(self, state=SessionState.FAILED):
        for stream in (self._data, self._control):
            if stream is not None:
                try:
                    stream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                stream.close()
        self._data = self._control = None
        self._buffer.clear()
        self._state_to(state)

    def close(self):
        # Socket closure is deterministic even after a partial reply. No ABOR,
        # QUIT, or extra command is sent on a possibly desynchronized stream.
        if self._state != SessionState.DISCONNECTED:
            self._invalidate(SessionState.DISCONNECTED)

    def _failure(self, exc):
        if self._invalid_reason is not None:
            exc = FtpOperationError(self._invalid_reason, 'binding')
        if isinstance(exc, FtpOperationError):
            error = exc
        elif isinstance(exc, socket.gaierror):
            error = FtpOperationError(EC.DNS, self._phase, retryable=True)
        elif isinstance(exc, TimeoutError):
            code = {'data-connect': EC.DATA_CONNECT_TIMEOUT,
                    'data-io': EC.DATA_IDLE_TIMEOUT,
                    'completion': EC.COMPLETION_UNKNOWN,
                    'mutation-reply': EC.COMPLETION_UNKNOWN}.get(self._phase, EC.CONTROL_TIMEOUT)
            error = FtpOperationError(code, self._phase, retryable=True)
        elif isinstance(exc, ConnectionRefusedError) and self._phase == 'control-connect':
            error = FtpOperationError(EC.CONTROL_REFUSED, self._phase, retryable=True)
        elif isinstance(exc, OSError) and exc.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
            error = FtpOperationError(EC.NETWORK, self._phase, retryable=True)
        else:
            code = (EC.COMPLETION_UNKNOWN if self._phase in ('completion', 'mutation-reply') else
                    EC.LOCAL_IO if self._phase == 'local-io' else
                    EC.STOR if self._operation == 'STOR' else
                    EC.RETR if self._operation == 'RETR' else
                    EC.INCOMPLETE_LISTING if self._operation in ('MLSD', 'LIST') else EC.PROTOCOL)
            error = FtpOperationError(code, self._phase)
        outcome = error.outcome
        if self._submitted and outcome == Outcome.NOT_STARTED:
            outcome = Outcome.UNKNOWN
        mutation = self._mutation
        if mutation is not None:
            # RNFR loss leaves rename unsubmitted; RNTO loss is uncertain mutation.
            outcome = (Outcome.REJECTED if error.outcome == Outcome.REJECTED else
                       Outcome.UNKNOWN if mutation.consequential_submitted else
                       Outcome.NOT_STARTED)
            mutation = replace(mutation, outcome=outcome,
                               error_category=error.code.value)
        write = self._write
        if write is not None:
            write = replace(write, submitted=self._submitted, transferred=self._count,
                            outcome=outcome if self._submitted else Outcome.NOT_STARTED,
                            error_category=error.code.value)
        error = FtpOperationError(error.code, error.phase, reply_code=error.reply_code,
                                  retryable=error.retryable, outcome=outcome,
                                  transferred=self._count, mutation=mutation, transfer=write)
        self._event('error', **error.as_dict())
        self._invalidate(SessionState.RECOVERING if error.code == EC.RECOVERING else SessionState.FAILED)
        return error

    @contextmanager
    def _operation_scope(self, verb):
        if not self._operation_lock.acquire(blocking=False):
            raise FtpOperationError(EC.BUSY, 'operation')
        start = time.monotonic()
        try:
            self._write = None
            self._mutation = (MutationEvidence(verb, 'RNFR' if verb == 'rename' else verb)
                              if verb in ('rename', 'MKD', 'DELE', 'RMD') else None)
            self._submitted = False
            if self._invalid_reason is not None:
                raise FtpOperationError(self._invalid_reason, 'binding')
            if self._state != SessionState.READY:
                raise FtpOperationError(EC.STALE, 'operation')
            self._operation = verb
            self._phase = 'control-reply'
            self._count = 0
            self._submitted = False
            self._check()
            yield
        except Exception as exc:
            raise self._failure(exc) from None
        finally:
            self._event('operation-end', duration_ms=round((time.monotonic()-start)*1000, 3),
                        transferred=self._count)
            self._operation_lock.release()

    def _line(self, deadline, *, capture=None):
        while b'\n' not in self._buffer:
            if len(self._buffer) > self._policy.reply_line_bytes + 1:
                raise FtpOperationError(EC.PROTOCOL, self._phase)
            self._check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            self._control.settimeout(remaining)
            block = self._control.recv(min(4096, self._policy.reply_line_bytes + 2))
            if not block:
                raise EOFError()
            self._buffer.extend(block)
        line, _, remainder = self._buffer.partition(b'\n')
        self._buffer = bytearray(remainder)
        if capture is not None: capture(bytes(line) + b'\n')
        if not line.endswith(b'\r') or len(line)-1 > self._policy.reply_line_bytes:
            raise FtpOperationError(EC.PROTOCOL, self._phase)
        return bytes(line[:-1])

    def _reply(self, timeout=None, *, capture=None):
        deadline = time.monotonic() + (timeout or self._policy.control_reply)
        first = self._line(deadline, capture=capture)
        if not re.match(rb'[1-5][0-9]{2}[ -]', first):
            raise FtpOperationError(EC.COMPLETION_UNKNOWN if self._phase == 'completion' else EC.PROTOCOL, self._phase)
        code = int(first[:3])
        lines = [first]
        total = len(first)+2
        if total > self._policy.reply_bytes:
            raise FtpOperationError(EC.PROTOCOL, self._phase)
        if first[3:4] == b'-':
            while True:
                if len(lines) >= self._policy.reply_lines:
                    raise FtpOperationError(EC.PROTOCOL, self._phase)
                line = self._line(deadline, capture=capture)
                total += len(line)+2
                if total > self._policy.reply_bytes:
                    raise FtpOperationError(EC.PROTOCOL, self._phase)
                lines.append(line)
                if line.startswith(first[:3]+b' '):
                    break
        return code, tuple(lines)

    def _send(self, verb, argument=None, *, dispatch=None):
        self._check()
        # Only constant verbs at internal call sites; arguments never diagnostic.
        if verb != 'PASS':
            self._event('command', verb=verb)
        command = verb.encode('ascii')
        if argument is not None:
            command += b' ' + argument
        self._control.settimeout(self._policy.control_reply)
        with dispatch() if dispatch is not None else nullcontext():
            if verb in ('STOR', 'RETR', 'MLSD', 'LIST'):
                # Check cancellation first; mark before sendall because a failed
                # send can still have delivered some command bytes.
                self._submitted = True
            if self._mutation is not None:
                self._mutation = replace(self._mutation, stage_submitted=True,
                                         consequential_submitted=(verb != 'RNFR'))
            self._control.sendall(command + b'\r\n')

    def _command(self, verb, argument=None):
        if self._state in (SessionState.READY, SessionState.TRANSFERRING):
            self._phase = ('stor-' + verb.lower()
                           if self._write is not None and not self._submitted and verb in ('TYPE', 'PASV')
                           else 'control-reply')
        self._send(verb, argument)
        return self._reply()

    def _expect(self, reply, allowed, default=EC.PROTOCOL):
        code, lines = reply
        if code in allowed:
            return reply
        category = default
        if code == 530:
            category = EC.AUTHENTICATION
        elif code == 421:
            category = (EC.SESSION_LIMIT if any(b'too many ftp connections' in line.lower()
                                               for line in lines) else EC.SERVICE_UNAVAILABLE)
        elif code in (500, 502, 504):
            category = EC.UNSUPPORTED
        raise FtpOperationError(category, self._phase, reply_code=code,
                                retryable=code == 421,
                                outcome=Outcome.REJECTED if code >= 400 else Outcome.UNKNOWN)

    def _open(self):
        try:
            self._check()
            # Validate before opening any socket. Do not retain the secret.
            password = self._manager._password_provider(self._binding)
            if not isinstance(password, str) or any(ord(c)<32 or ord(c)==127 for c in password):
                raise FtpOperationError(EC.INVALID_ARGUMENT, 'authentication')
            try:
                encoded = password.encode('utf-8')
            except UnicodeError:
                raise FtpOperationError(EC.INVALID_ARGUMENT, 'authentication') from None
            if len(encoded) > self._policy.reply_line_bytes:
                raise FtpOperationError(EC.INVALID_ARGUMENT, 'authentication')
            del password
            self._state_to(SessionState.CONNECTING)
            # AF_INET is deliberate: no fallback to IPv6/EPSV.
            addresses = socket.getaddrinfo(self._binding.host, self._binding.port,
                                           socket.AF_INET, socket.SOCK_STREAM)
            if not addresses:
                raise FtpOperationError(EC.DNS, 'control-connect')
            address = addresses[0][4]
            self._control = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._control.settimeout(self._policy.control_connect)
            self._control.connect(address)
            self._expect(self._reply(), (220,))
            self._phase = 'authentication'
            self._state_to(SessionState.AUTHENTICATING)
            user = {ContainerPresentation.FILES: b'anonymous',
                    ContainerPresentation.DIRECTORIES: b'dirs',
                    ContainerPresentation.BOTH: b'both'}[self._capabilities.presentation]
            self._expect(self._command('USER', user), (331,), EC.AUTHENTICATION)
            self._send('PASS', encoded)
            del encoded
            self._expect(self._reply(), (230,), EC.AUTHENTICATION)
            self._phase = 'negotiation'
            self._state_to(SessionState.NEGOTIATING)
            reply = self._command('FEAT')
            if reply[0] in (500, 502, 504):
                self._capabilities = replace(self._capabilities, feat=CS.UNSUPPORTED)
            else:
                self._expect(reply, (211,))
                features = []
                for line in reply[1][1:-1]:
                    if not re.fullmatch(rb' [A-Za-z][A-Za-z0-9-]*(?: [\x20-\x7e]+)?', line):
                        raise FtpOperationError(EC.PROTOCOL, 'feat-parse')
                    features.append(line[1:].decode('ascii'))
                names = {feature.split(' ', 1)[0].upper() for feature in features}
                self._capabilities = replace(self._capabilities, feat=CS.VERIFIED,
                    features=tuple(features), **{name.lower(): CS.ADVERTISED
                    for name in ('MLSD','MLST','SIZE','PASV') if name in names})
            if self._policy.known_broken_mlsd:
                self._capabilities = replace(self._capabilities, mlsd=CS.BROKEN,
                                              quirks=('known-broken-mlsd',))
            self._expect(self._command('TYPE', b'I'), (200,))
            self._event('capabilities', feat=self._capabilities.feat.value,
                        mlsd=self._capabilities.mlsd.value)
            self._state_to(SessionState.READY)
        except Exception as exc:
            raise self._failure(exc) from None

    @contextmanager
    def _defer_cancel(self):
        # Only cooperative cancellation is masked. _check still validates binding.
        self._cancel_deferred += 1
        try:yield
        finally:self._cancel_deferred -= 1

    def _mutation_command(self, verb, path, accepted):
        self._mutation = replace(self._mutation, stage=verb, stage_submitted=False,
                                 reply_code=None, reply_lines=(), requested_path=path)
        self._phase = 'mutation-reply'
        self._send(verb, path)
        reply = self._reply()
        self._mutation = replace(self._mutation, reply_code=reply[0], reply_lines=reply[1])
        self._expect(reply, accepted)
        self._mutation = replace(self._mutation,
            acknowledged=self._mutation.acknowledged + ((verb, reply[0]),))

    def _rename_ready(self):
        """Readiness validation without discarding an accepted reply on late cancel."""
        self._manager._check(self._binding)
        return self._invalid_reason is None and self.state == SessionState.READY

    def _begin_owned_rename(self, source, destination, dispatch):
        """Managed-adapter-only additive boundary; legacy rename is unchanged."""
        return _OwnedRenameWire(self, source, destination, dispatch)

    def rename(self, source, destination, *, strict=False):
        with self._operation_scope('rename'):
            checked_path(source);checked_path(destination)
            self._check()  # final cooperative check before RNFR
            with self._defer_cancel():
                self._mutation_command('RNFR', source, (350,) if strict else range(300, 400))
                self._mutation_command('RNTO', destination, (250,) if strict else range(200, 300))
            return self._mutation_complete()

    def _single_mutation(self, verb, path, accepted):
        with self._operation_scope(verb):
            checked_path(path)
            self._check()
            with self._defer_cancel():
                self._mutation_command(verb, path, accepted)
            return self._mutation_complete()

    def _mutation_complete(self):
        self._mutation = replace(self._mutation, outcome=Outcome.COMPLETED)
        self._event('mutation-complete', mutation=self._mutation.as_dict())
        return self._mutation

    @contextmanager
    def _root_context_scope(self):
        # Do not use _operation_scope('MKD'): CWD/PWD are not MKD submission.
        if not self._operation_lock.acquire(blocking=False):
            raise FtpOperationError(EC.BUSY, 'context')
        try:
            self._write = self._mutation = None
            self._submitted = False
            self._operation = 'context'
            self._phase = 'context-reply'
            self._count = 0
            self._check()
            if self._state != SessionState.READY or self._buffer:
                raise FtpOperationError(EC.PROTOCOL, 'context')
            yield
        finally:
            self._operation_lock.release()

    def _root_context_command(self, verb):
        """Fixed internal commands; caller holds the context lock through fsync."""
        from .import_context_evidence import candidate_complete, RAW_LIMIT
        if verb not in ('CWD', 'PWD'):
            raise FtpOperationError(EC.INVALID_ARGUMENT, 'context')
        raw = bytearray(); attempted = False; error = None
        try:
            self._check()
            if self._buffer:
                raise FtpOperationError(EC.PROTOCOL, 'context')
            self._control.settimeout(self._policy.control_reply)
            self._event('command', verb=verb)
            attempted = True  # Before sendall, including a partially delivered send.
            self._control.sendall(b'CWD /\r\n' if verb == 'CWD' else b'PWD\r\n')
            deadline = time.monotonic()+self._policy.control_reply
            while True:
                self._check()
                remaining = deadline-time.monotonic()
                if remaining <= 0: raise TimeoutError()
                self._control.settimeout(remaining)
                block = self._control.recv(min(4096, RAW_LIMIT+1-len(raw)))
                if not block: raise EOFError()
                raw.extend(block)
                if len(raw) == RAW_LIMIT+1 or candidate_complete(raw): break
        except Exception as exc:
            # Capture precedes any invalidation that clears the old parser buffer.
            error = exc
        return bytes(raw), attempted, error

    def _root_context_mkdir(self, path):
        self._check()
        self._operation = 'MKD'
        self._phase = 'mutation-reply'
        self._mutation = MutationEvidence('MKD', 'MKD', requested_path=path)
        try:
            with self._defer_cancel():
                self._mutation_command('MKD', path, range(200, 300))
            return self._mutation_complete()
        except Exception as exc:
            raise self._failure(exc) from None

    def mkdir(self, path):
        return self._single_mutation('MKD', path, range(200, 300))

    def delete(self, path):
        return self._single_mutation('DELE', path, (200, 250))

    def rmdir(self, path):
        return self._single_mutation('RMD', path, range(200, 300))

    def size(self, path):
        path = checked_path(path)
        with self._operation_scope('SIZE'):
            self._expect(self._command('TYPE', b'I'), (200,))
            reply = self._command('SIZE', path)
            if reply[0] in (500, 502, 504):
                self._capabilities = replace(self._capabilities, size=CS.UNSUPPORTED)
                raise FtpOperationError(EC.SIZE_UNAVAILABLE, 'size', reply_code=reply[0],
                                        outcome=Outcome.REJECTED)
            self._expect(reply, (213,), EC.SIZE_UNAVAILABLE)
            if len(reply[1]) != 1 or not re.fullmatch(rb'213 [0-9]{1,20}', reply[1][0]):
                raise FtpOperationError(EC.PROTOCOL, 'size')
            self._capabilities = replace(self._capabilities, size=CS.VERIFIED)
            return int(reply[1][0][4:])

    def _transfer(self, verb, path, *, receive=None, source=None, expected=None,
                  maximum=None, progress=None, budget=None, evidence=None):
        self._expect(self._command('TYPE', b'I'), (200,))
        reply = self._expect(self._command('PASV'), (227,))
        match = re.fullmatch(rb'227 [^\r\n]*\(([0-9,]+)\)\.?', reply[1][-1])
        if not match:
            raise FtpOperationError(EC.PROTOCOL, 'pasv')
        parts = match[1].split(b',')
        if len(parts) != 6 or any(not p or len(p)>3 or int(p)>255 for p in parts):
            raise FtpOperationError(EC.PROTOCOL, 'pasv')
        port = int(parts[4])*256+int(parts[5])
        if port == 0:
            raise FtpOperationError(EC.PROTOCOL, 'pasv')
        self._capabilities = replace(self._capabilities, pasv=CS.VERIFIED)
        self._phase = 'data-connect'
        self._data = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._data.settimeout(self._policy.data_connect)
        # Never trust a PASV-advertised third-party host.
        self._data.connect((self._control.getpeername()[0], port))
        self._phase = 'preliminary-reply'
        self._send(verb, path, dispatch=None if evidence is None else evidence.dispatch)
        reply = (self._reply() if evidence is None else
                 self._publication_reply(evidence, 'stor-preliminary'))
        if reply[0] in (500, 502, 504) and verb == 'MLSD':
            self._data.close()
            self._data = None
            self._submitted = False
            return None
        if source is not None:
            self._write = replace(self._write, submitted=True, preliminary_reply=reply[0])
        self._expect(reply, (125,150), EC.STOR if source is not None else
                     EC.RETR if verb == 'RETR' else EC.LISTING)
        self._state_to(SessionState.TRANSFERRING)
        digest = hashlib.sha256()
        self._event('transfer-start', expected=expected)
        while True:
            self._check()
            if source is not None:
                self._phase = 'local-io'
                block = source.read(8192)
                if not isinstance(block, bytes):
                    raise FtpOperationError(EC.LOCAL_IO, self._phase)
            else:
                self._phase = 'data-io'
                self._data.settimeout(self._policy.data_idle)
                amount = 8192
                if budget is not None:
                    amount = min(amount, budget.remaining)
                    if amount == 0:
                        # Peek only to distinguish exact EOF from excess data. No
                        # excess payload is consumed or passed to the sink.
                        if self._data.recv(1, socket.MSG_PEEK):budget.require(1)
                        block = b''
                    else:block = self._data.recv(amount)
                    budget.consume(len(block))
                else:block = self._data.recv(amount)
            if not block:
                if source is not None:
                    self._write = replace(self._write,
                        sha256=digest.hexdigest() if self._count == expected else None,
                        length_status='exact' if self._count == expected else 'short')
                break
            if maximum is not None and self._count + len(block) > maximum:
                if source is not None:
                    self._write = replace(self._write, length_status='overlong')
                raise FtpOperationError(EC.SIZE_MISMATCH, 'data-bound')
            if source is not None:
                self._phase = 'data-io'
                self._data.settimeout(self._policy.data_idle)
                # Charge possible exposure before sendall: on failure Python
                # cannot tell us how much of this block reached the peer. Never
                # refund it or treat a returned sendall as remote durability.
                if budget is not None:
                    budget.require(len(block))
                    budget.consume(len(block))
                self._write = replace(self._write,
                    attempted_send_bytes=self._write.attempted_bytes + len(block))
                with evidence.dispatch() if evidence is not None else nullcontext():
                    self._data.sendall(block)
            else:
                self._phase = 'local-io'
                receive(block)
            self._count += len(block)
            digest.update(block)
            if progress is not None:
                self._phase = 'local-io'
                progress(self._count)
        self._data.close()
        self._data = None
        self._phase = 'completion'
        if evidence is None:
            self._check()
            reply = self._reply(self._policy.final_reply)
        else:
            reply = self._publication_reply(evidence, 'stor-terminal', self._policy.final_reply)
        if source is not None:
            self._write = replace(self._write, terminal_reply=reply[0])
        # A rejected final reply after STOR is uncertain storage state, even if
        # the server says failure. No automatic cleanup/retry is authorized.
        if reply[0] not in (226,250):
            raise FtpOperationError(EC.COMPLETION_UNKNOWN, 'completion',
                                    reply_code=reply[0], outcome=Outcome.UNKNOWN)
        if expected is not None and self._count != expected:
            raise FtpOperationError(EC.SIZE_MISMATCH, 'verification',
                                    reply_code=reply[0], outcome=Outcome.COMPLETED)
        self._state_to(SessionState.READY)
        self._event('transfer-complete', transferred=self._count, outcome=Outcome.COMPLETED.value)
        # Do not check cancellation after terminal acceptance: late cancellation
        # cannot relabel an accepted write as not having occurred.
        if source is not None:
            self._write = replace(self._write, transferred=self._count, sha256=digest.hexdigest(),
                                  outcome=Outcome.COMPLETED)
        return TransferResult(self._count, digest.hexdigest(), reply[0], transfer=self._write)

    def list_directory(self, path, *, limits=None, budget=None, allow_fallback=True):
        path = checked_path(path)
        limits = limits or ListingLimits()
        with self._operation_scope('MLSD'):
            self._expect(self._command('CWD', path), (250,), EC.LISTING)
            reply = self._expect(self._command('PWD'), (257,), EC.LISTING)
            if len(reply[1]) != 1:
                raise FtpOperationError(EC.PROTOCOL, 'pwd')
            match = re.fullmatch(rb'257 "((?:[^"]|"")*)"(?: [^\r\n]*)?', reply[1][0])
            if not match:
                raise FtpOperationError(EC.PROTOCOL, 'pwd')
            actual_path = checked_path(match[1].replace(b'""', b'"'))
            # Preserve actual octets for the service's existing path/volume
            # revalidation. Never normalize identity or silently assume CWD.
            dialect = 'list' if self._capabilities.mlsd in (CS.UNSUPPORTED, CS.BROKEN) else 'mlsd'
            if dialect == 'list' and not allow_fallback:
                raise FtpOperationError(EC.LISTING, 'listing-no-fallback')
            parser = ListingParser(dialect, limits)
            if dialect == 'mlsd':
                result = self._transfer('MLSD', None, receive=parser.feed, budget=budget)
                if result is None:
                    if not allow_fallback:
                        raise FtpOperationError(EC.LISTING, 'listing-no-fallback')
                    self._capabilities = replace(self._capabilities, mlsd=CS.UNSUPPORTED)
                    dialect = 'list'
                    parser = ListingParser(dialect, limits)
            if dialect == 'list':
                self._event('fallback', reason=self._capabilities.mlsd.value, dialect='list')
                self._operation = 'LIST'
                self._transfer('LIST', None, receive=parser.feed, budget=budget)
            entries = parser.finish()
            self._capabilities = replace(self._capabilities, listing_dialect=dialect,
                mlsd=CS.VERIFIED if dialect == 'mlsd' else self._capabilities.mlsd)
            self._event('listing-complete', entries=len(entries), wire_bytes=parser.total)
            return ListingResult(actual_path, entries, dialect, parser.total)

    def read_into(self, path, sink, *, max_bytes, expected_bytes=None, progress=None, budget=None):
        path = checked_path(path)
        if path == b'/' or not callable(getattr(sink, 'write', None)):
            raise FtpOperationError(EC.INVALID_ARGUMENT, 'sink')
        if (type(max_bytes) is not int or max_bytes < 0 or
                expected_bytes is not None and (type(expected_bytes) is not int or
                                                not 0 <= expected_bytes <= max_bytes)):
            raise FtpOperationError(EC.INVALID_ARGUMENT, 'read-bound')
        def receive(block):
            if sink.write(block) != len(block):
                raise FtpOperationError(EC.LOCAL_IO, 'local-io')
        with self._operation_scope('RETR'):
            return self._transfer('RETR', path, receive=receive, maximum=max_bytes,
                                  expected=expected_bytes, progress=progress, budget=budget)

    def write_from(self, path, source, *, expected_bytes, progress=None, budget=None, _evidence=None):
        """Upload with optional cumulative attempted-byte require/consume budget.

        The caller owns the budget (payload, control or aggregate I/O). Every
        attempted block is charged once, including its unknown suffix on failure.
        """
        path = checked_path(path)
        if path == b'/' or not callable(getattr(source, 'read', None)):
            raise FtpOperationError(EC.INVALID_ARGUMENT, 'source')
        if type(expected_bytes) is not int or expected_bytes < 0:
            raise FtpOperationError(EC.INVALID_ARGUMENT, 'write-bound')
        with self._operation_scope('STOR'):
            self._write = WriteEvidence(expected_bytes, attempted_send_bytes=0)
            if budget is not None:budget.require(expected_bytes)
            return self._transfer('STOR', path, source=source, expected=expected_bytes,
                                  maximum=expected_bytes, progress=progress, budget=budget, evidence=_evidence)

    def _publication_reply(self, evidence, kind, timeout=None):
        # Only post-submission reply capture defers cooperative cancellation.
        raw = bytearray(); truncated = False; complete = False; code = None
        def capture(block):
            nonlocal truncated
            room = 32768-len(raw); raw.extend(block[:room]); truncated |= len(block)>room
        try:
            with self._defer_cancel():
                reply = self._reply(timeout, capture=capture)
            code = reply[0]
            if self._buffer: raise FtpOperationError(EC.PROTOCOL, 'publication-surplus')
            complete = True
            if truncated: raise FtpOperationError(EC.PROTOCOL, 'publication-reply-bound')
            return reply
        finally:
            if not complete: capture(bytes(self._buffer))
            evidence.reply(kind, bytes(raw), code, complete, truncated)


class _OwnedRenameWire:
    """One pending rename on an existing lease, reachable only through its adapter.

    Holds the ordinary operation lock across the evidence boundary. No unrelated
    command can reuse this protocol state. Abandon closes the socket, sends no
    cancellation/rollback command, and leaves all observations with the owner.
    """
    def __init__(self, client, source, destination, dispatch):
        checked_path(source); checked_path(destination)
        if max(len(source), len(destination)) > 2048:
            raise FtpOperationError(EC.INVALID_ARGUMENT, 'rename-bound')
        client._check()
        if client.state != SessionState.READY or not client._operation_lock.acquire(blocking=False):
            raise FtpOperationError(EC.BUSY, 'rename-owner')
        self.client, self.source, self.destination = client, source, destination
        self.dispatch = dispatch
        self.lease = client.identity
        self.thread = threading.get_ident()
        self.active = True
        self.first = self.second = None
        client._operation = 'rename'
        client._phase = 'mutation-reply'
        client._submitted = False
        client._count = 0
        client._write = None
        client._mutation = MutationEvidence('rename', 'RNFR')

    def _command(self, verb, path, expected):
        from .rename_evidence import RenameCommandEvidence
        c = self.client
        raw = bytearray()
        truncated = False
        code = None
        complete = False
        error = ''
        cap = min(c._policy.reply_bytes, 32768)
        def capture(block):
            nonlocal truncated
            room = cap - len(raw)
            raw.extend(block[:room])
            truncated |= len(block) > room
        c._mutation = replace(c._mutation, stage=verb, stage_submitted=False,
                              consequential_submitted=False, reply_code=None, reply_lines=(), requested_path=path)
        try:
            if (not self.active or threading.get_ident() != self.thread or c.identity != self.lease):
                raise FtpOperationError(EC.STALE, 'rename-owner')
            c._check()
            c._send(verb, path, dispatch=self.dispatch)
            # Once submitted, retain the reply before honoring late cancellation.
            # Binding checks remain active; only cooperative cancellation defers.
            with c._defer_cancel():
                code, lines = c._reply(capture=capture)
            if c._buffer:
                # Buffered surplus is ambiguous protocol state, not a later
                # command's acknowledgment. Preserve it through the failure path.
                raise FtpOperationError(EC.PROTOCOL, 'rename-surplus-reply')
            complete = True
            c._mutation = replace(c._mutation, reply_code=code, reply_lines=lines)
        except BaseException as exc:
            error = type(exc).__name__
            # Retain a bounded literal unterminated tail; never synthesize CRLF.
            capture(bytes(c._buffer))
        binding_valid = True
        try:
            c._manager._check(c._binding)
            with c._manager._lock:
                if c._manager._leases.get(self.lease.device_id) is not c:
                    raise FtpOperationError(EC.STALE, 'rename-lease')
            if c._invalid_reason is not None:
                raise FtpOperationError(EC.STALE, 'rename-session')
        except BaseException as exc:
            binding_valid = False
            error = error or type(exc).__name__
        submitted = c._mutation.stage_submitted
        acknowledgment = ('not-started' if not submitted else
            'accepted' if complete and not truncated and code == expected else
            'rejected' if complete and code is not None and 400 <= code <= 599 and code != 421 else 'unknown')
        return RenameCommandEvidence(verb, verb.encode('ascii') + b' ' + path + b'\r\n',
            bytes(raw), code, submitted, acknowledgment, complete, truncated,
            self.lease.device_id, self.lease.core_session_id, self.lease.ftp_session_id, error, binding_valid)

    def rnfr(self):
        if self.first is not None: raise FtpOperationError(EC.STALE, 'rename-used')
        self.first = self._command('RNFR', self.source, 350)
        return self.first

    def rnto(self):
        if self.first is None or not self.first.accepted or self.second is not None:
            raise FtpOperationError(EC.STALE, 'rename-continuation')
        self.second = self._command('RNTO', self.destination, 250)
        return self.second

    def finish(self):
        if self.second is None or not self.second.accepted:
            raise FtpOperationError(EC.STALE, 'rename-incomplete')
        if self.active:
            self.active = False
            self.client._operation_lock.release()

    def abandon(self):
        if self.active:
            self.client._invalidate()
            self.active = False
            self.client._operation_lock.release()
