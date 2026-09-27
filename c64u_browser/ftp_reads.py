# SPDX-License-Identifier: GPL-3.0-or-later
"""Private Core FTP operation lifetime and read adapter.

Preserves Entry/IdentityEntry/bytes contracts. No lease or socket leaves this
module. Approved standalone mutations share this lifetime; legacy composites remain separate.
"""
from contextlib import contextmanager, nullcontext, ExitStack
from contextvars import ContextVar
from dataclasses import dataclass, field
import io
import threading

from .api import BrowserError, ConnectionFailure, Entry, IdentityEntry, safe_argument
from .c64u_ftp_types import ErrorCode as EC, FtpOperationError
from .diagnostics import diagnostic_event


def transport_event(event):
    # Client events contain only safe fields. Existing diagnostic context adds
    # the Core job ID; no peer prose, path, password, or payload is copied.
    diagnostic_event('ftp', 'transport', 'session',
                     'error' if event['kind'] == 'error' else 'ok', details=event)


def translate(error):
    code = error.code
    kind = ('authentication' if code == EC.AUTHENTICATION else
            'host' if code == EC.DNS else
            'network' if code in (EC.NETWORK, EC.CONTROL_REFUSED, EC.CONTROL_TIMEOUT,
                                  EC.DATA_CONNECT_TIMEOUT, EC.DATA_IDLE_TIMEOUT,
                                  EC.SERVICE_UNAVAILABLE, EC.SESSION_LIMIT, EC.BUSY) else
            'session' if code in (EC.STALE, EC.RECOVERING) else 'ftp')
    # 550 means unavailable, not necessarily nonexistent; retain that ambiguity.
    detail = ('path-unavailable' if error.reply_code == 550 else code.value)
    messages = {
        'authentication': 'C64U FTP authentication failed. Check the Network Password.',
        'host': 'The C64U address could not be resolved.',
        'network': 'C64U FTP is unavailable or timed out. Check the connection.',
        'session': 'The C64U connection changed. Review the operation again.',
    }
    message = messages.get(kind, {
        'path-unavailable': 'The C64U path is missing or inaccessible. Refresh and check the path.',
        EC.MALFORMED_LISTING.value: 'The C64U directory listing is malformed; no partial directory was accepted.',
        EC.INCOMPLETE_LISTING.value: 'The C64U directory listing is incomplete; refresh before continuing.',
        EC.LISTING_BOUNDS.value: 'The C64U directory listing exceeds the safety bound.',
        EC.SIZE_UNAVAILABLE.value: 'The C64U did not provide a usable file size; reading stopped.',
        EC.SIZE_MISMATCH.value: 'File changed or download was incomplete.',
        EC.COMPLETION_UNKNOWN.value: 'The C64U did not confirm completion; reading stopped.',
    }.get(detail, 'C64U FTP operation failed; no unverified result was accepted.'))
    if error.mutation is not None:
        message = ('C64U mutation ' + error.mutation.outcome.value +
                   '; refresh and review the recorded result before another attempt.')
    result = ConnectionFailure(kind, message)
    result.ftp_code = detail
    result.reply_code = error.reply_code
    result.phase = error.phase
    result.outcome = error.outcome
    result.transferred = error.transferred
    result.retryable = error.retryable
    result.ftp_error = error
    result.mutation = error.mutation
    return result


@dataclass
class _FtpOperation:
    checks: list = field(default_factory=list)
    failure: Exception | None = None
    client: object = None
    stack: object = None
    transport_error: FtpOperationError | None = None
    cancel_deferred: int = 0
    mutation_used: bool = False

    def cancelled(self):
        try:
            for check in self.checks:
                if check is not None:
                    try:check()
                    except Exception as exc:
                        if self.cancel_deferred and getattr(exc, 'cancelled', False):continue
                        raise
        except Exception as exc:
            self.failure = exc
            return True
        return False

    def check(self):
        if self.cancelled():raise self.failure


class _FtpOperations:
    """Private fixed-binding lifetime, shared by nested FTP helpers."""
    def __init__(self, manager, binding, *, encoding='utf-8', check=None):
        self._manager = manager
        self.binding = binding
        self._encoding = encoding
        self._check = check
        self._context = ContextVar('argonaut_ftp_operation', default=None)
        self._lock = threading.Lock()
        self.capability_evidence = None

    @contextmanager
    def operation(self, check=None):
        existing = self._context.get()
        if existing is not None:
            existing.checks.append(check)
            try:
                self._manager._check(self.binding)
                existing.check()
                yield
            except FtpOperationError as exc:
                self._raise_failure(existing, exc)
            finally:existing.checks.pop()
            return
        state = _FtpOperation([self._check, check])
        acquired = False
        token = None
        try:
            # Serialize independent read contexts; nested helpers reuse context.
            # This runs on a worker, never waits while holding another FTP lease.
            while not acquired:
                self._manager._check(self.binding)
                state.check()
                acquired = self._lock.acquire(timeout=.1)
            state.check()
            with ExitStack() as stack:
                state.stack = stack
                token = self._context.set(state)
                try:yield
                finally:
                    if state.client is not None:self.capability_evidence = state.client.capabilities
        except FtpOperationError as exc:
            self._raise_failure(state, exc)
        finally:
            if token is not None:self._context.reset(token)
            if acquired:self._lock.release()

    @contextmanager
    def defer_cancellation(self):
        """Private case-only rename boundary; never a binding/transport mask."""
        state = self._context.get()
        self._manager._check(self.binding)
        state.check()
        state.cancel_deferred += 1
        try:yield
        finally:state.cancel_deferred -= 1

    def mutate(self, operation, path, destination=None):
        with self.operation():
            state = self._context.get()
            state.mutation_used = True
            safe_argument(path)
            try:
                args = [path.encode(self._encoding)]
                if destination is not None:
                    safe_argument(destination)
                    args.append(destination.encode(self._encoding))
            except UnicodeError:
                raise BrowserError('Filename encoding failed.') from None
            if operation not in ('rename', 'mkdir', 'delete', 'rmdir'):
                raise BrowserError('Unknown mutation operation.')
            return getattr(self._client(), operation)(*args).as_dict()

    def write_from(self, path, source, expected_bytes, progress=None):
        with self.operation():
            state = self._context.get()
            state.mutation_used = True
            def update(count):
                try:
                    state.check()
                    if progress is not None:progress(count)
                except Exception as exc:
                    state.failure = exc
                    raise
            return self._client().write_from(self._path(path), source,
                expected_bytes=expected_bytes, progress=update)

    def readback(self, path, expected_bytes):
        """One bounded RETR observation; upload owns the subsequent SIZE."""
        class Discard:
            def write(self, block):return len(block)
        with self.operation():
            return self._client().read_into(self._path(path), Discard(),
                max_bytes=expected_bytes, expected_bytes=expected_bytes)

    def size(self, path):
        with self.operation():
            return self._client().size(self._path(path))

    def _path(self, path):
        safe_argument(path)
        try:return path.encode(self._encoding)
        except UnicodeError:raise BrowserError('Filename encoding failed.') from None

    @staticmethod
    def _raise_failure(state, error):
        state.transport_error = error
        # Keep wire evidence even when restoring the original callback/cancel
        # exception. Binding invalidation must not be masked by cancellation.
        if state.failure is not None and error.code not in (EC.STALE, EC.RECOVERING):
            state.failure.ftp_error = error
            raise state.failure from None
        raise translate(error) from None

    def _client(self):
        state = self._context.get()
        if state.transport_error is not None:
            raise state.transport_error
        if state.client is None:
            state.client = state.stack.enter_context(
                self._manager.lease(self.binding, cancelled=state.cancelled))
        return state.client


class FtpReadAdapter(_FtpOperations):
    def end_read_attempt(self):
        """Explicit caller-selected fallback boundary, never automatic recovery."""
        state = self._context.get()
        if state is None:return
        if state.mutation_used:
            raise BrowserError('A mutation operation cannot restart as a read fallback.')
        self._manager._check(self.binding)
        state.check()
        if state.client is not None:
            self.capability_evidence = state.client.capabilities
        state.stack.close()
        state.client = None
        state.transport_error = None

    def read_into(self, path, sink, *, progress=None, check=None, finish=None):
        """Stream one exact SIZE/RETR/SIZE observation, including empty files.

        The caller prepares/owns the sink and any publication or fsync policy.
        Optional finish runs after RETR and before the final SIZE observation.
        The returned transfer evidence contains no transport/session handle.
        """
        safe_argument(path)
        try:wire_path = path.encode(self._encoding)
        except UnicodeError:
            raise BrowserError('Filename encoding failed.') from None
        with self.operation(check):
            state = self._context.get()
            client = self._client()
            expected = client.size(wire_path)
            class Sink:
                def write(self, block):
                    try:
                        state.check()
                        return sink.write(block)
                    except Exception as exc:
                        state.failure = exc
                        raise
            def update(count):
                state.check()
                if progress is not None:
                    try:progress(count)
                    except Exception as exc:
                        state.failure = exc
                        raise
            result = client.read_into(wire_path, Sink(), max_bytes=expected,
                                      expected_bytes=expected, progress=update)
            if finish is not None:finish()
            state.check()
            if client.size(wire_path) != expected:
                raise BrowserError('Remote size changed or transfer was incomplete; no verified result accepted.')
            state.check()
            return result

    def list_directory(self, path='/', *, identity=False):
        if identity:
            if not isinstance(path, bytes) or not path.startswith(b'/'):
                raise BrowserError('Identity directory paths must be absolute bytes.')
            wire_path = path
        else:
            safe_argument(path)
            if not path.startswith('/'):
                raise BrowserError('Directory path must be absolute, beginning with /.')
            try:wire_path = path.encode(self._encoding)
            except UnicodeError:
                raise BrowserError('Filename encoding failed. Check the selected filename encoding.') from None
        try:
            with self.operation():
                result = self._client().list_directory(wire_path)
                if identity:
                    return result.actual_path, [IdentityEntry(e.name, e.kind, e.size) for e in result.entries]
                entries = [Entry(e.name.decode(self._encoding), e.kind, e.size) for e in result.entries]
                return result.actual_path.decode(self._encoding), sorted(
                    entries, key=lambda e: (e.kind != 'dir', e.name.casefold()))
        except UnicodeError:
            # Preserve the prior ordinary-listing contract. Only identity reads
            # can carry arbitrary octets; never invent a lossy user filename.
            raise BrowserError('Filename encoding failed. Retry with --encoding latin-1; byte mapping needs hardware verification.') from None

    def read(self, path, maximum, *, progress=None, check=None, allowed_sizes=None):
        try:wire_path = path.encode(self._encoding)
        except UnicodeError:
            raise BrowserError('Filename encoding failed.') from None
        with self.operation(check):
            state = self._context.get()
            client = self._client()
            expected = client.size(wire_path)
            if not 0 < expected <= maximum:
                raise BrowserError(f'File must contain between 1 byte and {maximum:,} bytes.')
            if allowed_sizes is not None and expected not in allowed_sizes:
                raise BrowserError('Unsupported D64 size; use a standard 35, 40 or 42-track image.')
            output = io.BytesIO()
            def update(count):
                state.check()
                if progress is not None:
                    try:progress(count, expected)
                    except Exception as exc:
                        state.failure = exc
                        raise
            client.read_into(wire_path, output, max_bytes=maximum,
                             expected_bytes=expected, progress=update)
            state.check()
            if client.size(wire_path) != expected:
                raise BrowserError('File changed or download was incomplete.')
            state.check()
            return output.getvalue()


def adapter_for(client):
    adapter = getattr(client, '_ftp_reads', None)
    return adapter if isinstance(adapter, FtpReadAdapter) else None


def read_operation(client, check=None):
    adapter = adapter_for(client)
    return adapter.operation(check) if adapter is not None else nullcontext()


def end_read_attempt(client):
    adapter = adapter_for(client)
    if adapter is not None:adapter.end_read_attempt()
