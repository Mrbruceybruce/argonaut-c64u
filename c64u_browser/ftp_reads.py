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
from .c64u_ftp_types import ErrorCode as EC, FtpOperationError, MutationEvidence, WriteEvidence, Outcome, ConnectionBinding, DeviceIdentity, checked_path
from .diagnostics import diagnostic_event
from .jobs import JobCancelled


CREATION_MKD_RULE = 'c64u-25ea78-1.1.0s2-api0.1-usb0-mkd-triple-slash-v1'
CREATION_ROOT = b'/USB0/ARGONAUT_LIBRARY'
CREATION_MKD_PATHS = (CREATION_ROOT, CREATION_ROOT+b'/games', CREATION_ROOT+b'/metadata', CREATION_ROOT+b'/artwork')


def _compatible_creation_mkdir(evidence, path, target, binding, live_identity):
    qualified = DeviceIdentity('id:25EA78', 'C64 Ultimate', '1.1.0s2', '0.1')
    if (not isinstance(binding, ConnectionBinding) or not binding.core_session_id
            or binding.device != qualified or live_identity != qualified
            or target.device_id != binding.device.physical_id
            or target.session_id != binding.core_session_id
            or target.root != '/USB0' or target.path != CREATION_ROOT.decode('ascii')
            or path not in CREATION_MKD_PATHS):
        return False
    checked_path(path)
    return (isinstance(evidence, MutationEvidence)
            and evidence.operation == evidence.stage == 'MKD'
            and evidence.outcome == Outcome.COMPLETED
            and evidence.stage_submitted and evidence.consequential_submitted
            and evidence.reply_code == 257
            and evidence.acknowledgment == Outcome.COMPLETED
            and evidence.requested_path == path
            and evidence.reply_lines == (b'257 "//'+path+b'" created.',)
            and evidence.created_path == b'//'+path)


def creation_outcome(operation,path,*,result=None,error=None):
    """Initializer-only classification. No wire types/handles escape this seam.

    Successful generic mutations are insufficient for creation ownership.
    Unknown observations never authorize cleanup. Raw reply/path bytes remain
    bounded and are encoded losslessly for JSON-compatible Core evidence.
    """
    failure=error if isinstance(error,FtpOperationError) else getattr(error,'ftp_error',None)
    evidence=(getattr(result,'transfer',None) if operation=='STOR' else result)
    if isinstance(failure,FtpOperationError):
        evidence=failure.transfer if operation=='STOR' else failure.mutation
    outcome=Outcome.UNKNOWN
    valid_type=isinstance(evidence,WriteEvidence if operation=='STOR' else MutationEvidence)
    if error is None and valid_type:
        if evidence.acknowledgment==Outcome.COMPLETED:
            outcome=Outcome.COMPLETED
            if operation=='MKD':
                try:evidence.require_mkdir_path(path.encode('ascii'))
                except FtpOperationError:outcome=Outcome.UNKNOWN
    elif error is not None:
        if valid_type:
            ack=evidence.acknowledgment
            # A lost RNFR reply is uncertain protocol state even without RNTO.
            submitted=(evidence.submitted if isinstance(evidence,WriteEvidence)
                       else evidence.stage_submitted or evidence.consequential_submitted)
            if ack==Outcome.REJECTED and evidence.outcome==Outcome.REJECTED:
                outcome=Outcome.REJECTED
            elif not submitted and evidence.outcome==Outcome.NOT_STARTED:
                outcome=Outcome.NOT_STARTED
        elif isinstance(failure,FtpOperationError) and failure.outcome==Outcome.NOT_STARTED:
            outcome=Outcome.NOT_STARTED
    wire=evidence.as_dict() if valid_type else {}
    if isinstance(evidence,MutationEvidence):
        wire.update(reply_lines_hex=tuple(line.hex() for line in evidence.reply_lines),
            requested_path_hex=None if evidence.requested_path is None else evidence.requested_path.hex(),
            created_path_hex=None if evidence.created_path is None else evidence.created_path.hex())
        if operation=='MKD':wire['path_status']=evidence.mkdir_path_status(path.encode('ascii'))
    return outcome.value,tuple(wire.items())


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
    cancellation_observed: bool = False
    rename_owner: object = None

    def cancelled(self):
        try:
            for check in self.checks:
                if check is not None:
                    try:check()
                    except Exception as exc:
                        if self.cancel_deferred and getattr(exc, 'cancelled', False):
                            self.cancellation_observed = True
                            continue
                        raise
        except Exception as exc:
            self.failure = exc
            return True
        return False

    def check(self):
        if self.cancelled():raise self.failure

    def check_required(self):
        """Additive boundary: observed cancellation is sticky, never deferred."""
        if self.cancellation_observed:
            raise JobCancelled()
        for check in self.checks:
            if check is not None:
                try:
                    check()
                except BaseException as exc:
                    if getattr(exc, 'cancelled', False):
                        self.cancellation_observed = True
                    raise


class _FtpOperations:
    """Private fixed-binding lifetime, shared by nested FTP helpers."""
    def __init__(self, manager, binding, *, encoding='utf-8', check=None, creation_identity=None):
        self._manager = manager
        self.binding = binding
        self._creation_identity = creation_identity
        self._encoding = encoding
        self._check = check
        self._context = ContextVar('argonaut_ftp_operation', default=None)
        self._lock = threading.Lock()
        self.capability_evidence = None
        from uuid import uuid4
        self._owner_id = uuid4().hex
        self._rename_owners = {}
        self._evidence_blocked = False

    def classify_library_creation(self, operation, path, target, *, result=None, error=None):
        outcome, wire = creation_outcome(operation, path, result=result, error=error)
        if operation != 'MKD':
            return outcome, wire
        details = dict(wire)
        details['path_acceptance_rule'] = 'exact-path' if outcome == 'completed' else None
        details['compatibility_rule'] = None
        if error is None and outcome == 'unknown':
            # Revalidate the captured live binding at classification, not merely
            # at command submission. A stale response cannot acquire ownership.
            try:
                self._manager._check(self.binding)
            except FtpOperationError:
                pass
            else:
                if _compatible_creation_mkdir(result, path.encode('ascii'), target,
                                    self.binding, self._creation_identity):
                    outcome = 'completed'
                    details['path_acceptance_rule'] = 'firmware-compatibility'
                    details['compatibility_rule'] = CREATION_MKD_RULE
        return outcome, tuple(details.items())

    def classify_staging_mkdir(self, transaction, operation_id, *, result=None, error=None,
                               context_valid=True):
        """Staging-only observation, not authority; destination is transaction-derived."""
        from .import_execution_v4 import ExecutionTransactionV4
        from .import_mkd_proof import capture, MkdObservation
        from .import_transaction import require
        from .import_execution_v5 import ExecutionTransactionV5
        require(type(transaction) in (ExecutionTransactionV4, ExecutionTransactionV5), 'Versioned staging transaction required.')
        transaction.validate()
        valid = context_valid is True
        try:
            self._manager._check(self.binding)
        except FtpOperationError:
            valid = False
        valid = (valid and self.binding.core_session_id == transaction.session_id and
                 self.binding.device.physical_id == transaction.library.device_id and
                 (self._creation_identity is None or self._creation_identity == self.binding.device))
        wire_error = error if isinstance(error, FtpOperationError) else getattr(error, 'ftp_error', None)
        evidence = wire_error.mutation if wire_error is not None else result
        if type(evidence) is not MutationEvidence:return None
        observation = MkdObservation(evidence.operation, evidence.stage, evidence.outcome.value,
            evidence.stage_submitted, evidence.consequential_submitted, evidence.reply_code,
            evidence.acknowledged, evidence.reply_lines, evidence.requested_path)
        return capture(transaction, operation_id, observation, encoding=self._encoding,
                       identity=self._creation_identity, binding=self.binding, binding_valid=valid)

    @contextmanager
    def operation(self, check=None, *, reject_busy=False):
        if self._evidence_blocked:
            raise BrowserError('Required rename evidence blocked this adapter; no reconnect.')
        existing = self._context.get()
        if existing is not None:
            if reject_busy:raise BrowserError('FTP operation already owned.')
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
            if reject_busy:
                acquired = self._lock.acquire(blocking=False)
                if not acquired:raise BrowserError('FTP operation already owned.')
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
                    if state.rename_owner is not None:state.rename_owner._scope_ended()
                    if state.client is not None:self.capability_evidence = state.client.capabilities
        except FtpOperationError as exc:
            self._raise_failure(state, exc)
        finally:
            if token is not None:self._context.reset(token)
            if acquired:self._lock.release()

    @contextmanager
    def defer_cancellation(self):
        """Private composite boundary; never a binding/transport mask."""
        state = self._context.get()
        self._manager._check(self.binding)
        state.check()
        state.cancel_deferred += 1
        try:yield state
        finally:state.cancel_deferred -= 1

    def staging_context_binding(self, transaction, operation_id):
        from .import_context_evidence import Context
        from .import_mkd_proof import destination
        from .import_transaction import require
        from .import_execution_v5 import ExecutionTransactionV5
        require(type(transaction) is ExecutionTransactionV5, 'Schema-5 context required.')
        client = self._client()
        identity = self._creation_identity
        values = dict(physical_id='', product='', firmware='', api_version='', provenance='unavailable')
        if identity is not None:
            values.update(physical_id=identity.physical_id.removeprefix('id:'), product=identity.product,
                          firmware=identity.firmware, api_version=identity.api_version, provenance='live-rest')
        return Context(transaction.id, operation_id, self._encoding, destination(transaction, self._encoding).hex(),
            transaction.session_id, transaction.library.device_id, client.identity.ftp_session_id,
            self._owner_id, **values).validate(transaction, operation_id)

    @contextmanager
    def staging_context(self, context):
        from .import_transaction import require
        state = self._context.get()
        require(state is not None, 'Context requires managed operation owner.')
        state.check()
        client = self._client()
        state.mutation_used = True  # CWD prohibits releasing/reacquiring a read lease.
        guard = _StagingContextGuard(self, state, client, context)
        with client._root_context_scope():
            if not guard.valid(): raise FtpOperationError(EC.STALE, 'context')
            yield guard

    def begin_evidenced_rename(self, source, destination, evidence):
        """Explicit continuation inside an already owned operation, no new lease."""
        from .managed_rename import ManagedRename
        state = self._context.get()
        if state is None or state.rename_owner is not None:
            raise BrowserError('An exclusive managed operation is required.')
        state.check()
        safe_argument(source); safe_argument(destination)
        try:
            source_bytes = source.encode(self._encoding)
            destination_bytes = destination.encode(self._encoding)
        except UnicodeError:
            raise BrowserError('Filename encoding failed.') from None
        from .c64u_ftp_types import checked_path
        checked_path(source_bytes); checked_path(destination_bytes)
        if max(len(source_bytes), len(destination_bytes)) > 2048 or source_bytes == destination_bytes:
            raise BrowserError('Invalid bounded rename paths.')
        client = self._client()
        owner = ManagedRename(self, state, client, source_bytes, destination_bytes, evidence)
        self._rename_owners[id(owner)] = owner
        state.rename_owner = owner
        state.mutation_used = True
        return owner._begin()

    def mutate(self, operation, path, destination=None):
        return self.mutate_evidence(operation, path, destination).as_dict()

    def mutate_evidence(self, operation, path, destination=None, *, strict_rename=False):
        """Private wire evidence; safe legacy dictionaries omit paths/peer prose."""
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
            options={'strict':True} if operation=='rename' and strict_rename else {}
            return getattr(self._client(), operation)(*args,**options)

    def write_publication_json(self, path, data, evidence):
        """Bounded sealed bytes and mandatory evidence, on an existing owned lease."""
        from .required_evidence import RequiredEvidence
        import hashlib
        state = self._context.get()
        if state is None or state.rename_owner is not None or type(evidence) is not RequiredEvidence:
            raise BrowserError('Owned publication operation and shared evidence required.')
        if type(data) is not bytes or not 0 < len(data) <= 4096 or not data.endswith(b'\n'):
            raise BrowserError('Bounded sealed JSON bytes required.')
        import json
        json.loads(data)
        wire = self._path(path)
        if len(wire) > 2048 or path.lower().endswith('.d64'):
            raise BrowserError('Publication control path required.')
        client = self._client(); lease = client.identity; thread = threading.get_ident()
        state.mutation_used = True
        adapter = self
        def check():
            if (adapter._context.get() is not state or state.client is not client or
                    client.identity != lease or threading.get_ident() != thread or adapter._evidence_blocked):
                raise BrowserError('Publication upload owner changed.')
            adapter._manager._check(adapter.binding)
            with adapter._manager._lock:
                if adapter._manager._leases.get(lease.device_id) is not client:
                    raise BrowserError('Publication upload lease changed.')
            state.check_required(); client._check()
        binding = dict(device_id=lease.device_id,core_session_id=lease.core_session_id,
                       ftp_session_id=lease.ftp_session_id,adapter_owner=self._owner_id)
        class Boundary:
            def dispatch(self): return evidence.dispatch(check)
            def reply(self, kind, raw, code, complete, truncated):
                evidence.save(kind, dict(**binding,request_hex=(b'STOR '+wire+b'\r\n').hex(),
                    reply_hex=raw.hex(),reply_code=code,framing_complete=complete,truncated=truncated))
        try:
            check()
            evidence.save('stor-intent',dict(**binding,path=path,request_hex=(b'STOR '+wire+b'\r\n').hex(),
                size=len(data),sha256=hashlib.sha256(data).hexdigest()))
            result = client.write_from(wire,io.BytesIO(data),expected_bytes=len(data),_evidence=Boundary())
            evidence.save('stor-outcome',dict(**binding,**result.transfer.as_dict()))
            check()
            return result
        except BaseException as exc:
            self._evidence_blocked = True
            state.failure = state.failure or (translate(exc) if isinstance(exc,FtpOperationError) else exc)
            if isinstance(exc,FtpOperationError):state.failure.ftp_error = exc
            failure = getattr(exc,'transfer',None)
            if not evidence.blocked:
                evidence.save('stor-failure',dict(**binding,error_type=type(exc).__name__,
                    transfer=None if failure is None else failure.as_dict(),possible_path=path))
            client.close()
            raise state.failure from None

    def write_from(self, path, source, expected_bytes, progress=None, *, budget=None):
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
            class BudgetGuard:
                def require(self, amount):
                    try:budget.require(amount)
                    except Exception as exc:
                        state.failure = exc
                        raise
                def consume(self, amount):
                    try:budget.consume(amount)
                    except Exception as exc:
                        state.failure = exc
                        raise
            return self._client().write_from(self._path(path), source,
                expected_bytes=expected_bytes, progress=update,
                **({'budget': BudgetGuard()} if budget is not None else {}))

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
        if self._evidence_blocked:
            raise BrowserError('Required rename evidence blocked this adapter.')
        if state.rename_owner is not None:
            raise BrowserError('Pending evidenced rename owns this FTP connection.')
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

    def read_into(self, path, sink, *, progress=None, check=None, finish=None,
                  expected_bytes=None, budget=None):
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
            if expected_bytes is not None and expected != expected_bytes:
                raise BrowserError('Remote source size differs from the approved snapshot.')
            if budget is not None:budget.require(expected)
            class BudgetGuard:
                @property
                def remaining(self):return budget.remaining
                def require(self, amount):
                    try:budget.require(amount)
                    except Exception as exc:
                        state.failure = exc;raise
                def consume(self, amount):
                    try:budget.consume(amount)
                    except Exception as exc:
                        state.failure = exc;raise
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
                                      expected_bytes=expected, progress=update,
                                      **({'budget': BudgetGuard()} if budget is not None else {}))
            if finish is not None:finish()
            state.check()
            if client.size(wire_path) != expected:
                raise BrowserError('Remote size changed or transfer was incomplete; no verified result accepted.')
            state.check()
            return result

    def list_directory(self, path='/', *, identity=False, budget=None, allow_fallback=True):
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
                result = self._client().list_directory(wire_path, **(
                    {'budget': budget, 'allow_fallback': allow_fallback} if budget is not None or not allow_fallback else {}))
                if identity:
                    return result.actual_path, [IdentityEntry(e.name, e.kind, e.size) for e in result.entries]
                entries = [Entry(e.name.decode(self._encoding), e.kind, e.size) for e in result.entries]
                return result.actual_path.decode(self._encoding), sorted(
                    entries, key=lambda e: (e.kind != 'dir', e.name.casefold()))
        except UnicodeError:
            # Preserve the prior ordinary-listing contract. Only identity reads
            # can carry arbitrary octets; never invent a lossy user filename.
            raise BrowserError('Filename encoding failed. Retry with --encoding latin-1; byte mapping needs hardware verification.') from None

    def read(self, path, maximum, *, progress=None, check=None, allowed_sizes=None, budget=None):
        try:wire_path = path.encode(self._encoding)
        except UnicodeError:
            raise BrowserError('Filename encoding failed.') from None
        with self.operation(check):
            state = self._context.get()
            client = self._client()
            expected = client.size(wire_path)
            if budget is not None:budget.require(expected)
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
            # Restore the caller's typed budget failure through transport cleanup.
            class BudgetGuard:
                @property
                def remaining(self):return budget.remaining
                def require(self, amount):
                    try:budget.require(amount)
                    except Exception as exc:
                        state.failure = exc
                        raise
                def consume(self, amount):
                    try:budget.consume(amount)
                    except Exception as exc:
                        state.failure = exc
                        raise
            client.read_into(wire_path, output, max_bytes=maximum,
                             expected_bytes=expected, progress=update,
                             **({'budget': BudgetGuard()} if budget is not None else {}))
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


class _StagingContextGuard:
    def __init__(self, adapter, state, client, context):
        self.adapter, self.state, self.client, self.context = adapter, state, client, context
        self.socket = client._control
        self.step = 0

    def valid(self):
        a, c = self.adapter, self.client
        try:
            a._manager._check(a.binding)
            with a._manager._lock:
                owned = a._manager._leases.get(a.binding.device.physical_id) is c
            return (owned and a._context.get() is self.state and self.state.client is c and
                    c._control is self.socket and self.socket is not None and c._invalid_reason is None and
                    c.identity.ftp_session_id == self.context.ftp_session_id and
                    a._owner_id == self.context.adapter_owner_id and
                    a.binding.core_session_id == self.context.core_session_id and
                    a.binding.device.physical_id == self.context.device_id and
                    a._creation_identity == a.binding.device)
        except Exception: return False

    def observe(self, verb):
        from .import_context_evidence import observation
        from .import_transaction import require
        require((self.step, verb) in ((0, 'CWD'), (1, 'PWD')), 'Context commands cannot repeat.')
        self.state.check()
        before = self.valid()
        if not before: raise FtpOperationError(EC.STALE, 'context')
        raw, attempted, error = self.client._root_context_command(verb)
        after = self.valid()
        result = observation(verb, raw, attempted=attempted, before=before, after=after, interrupted=error is not None)
        self.step += 1
        if result.completion != 'accepted':
            self.step = -1
            self.client.close()
        return result, self.state.failure if error is not None and self.state.failure is not None else error

    def mkdir(self):
        from .import_transaction import require
        require(self.step == 2 and self.valid(), 'MKD requires same context lease.')
        self.state.check()
        self.step = 3
        return self.client._root_context_mkdir(bytes.fromhex(self.context.destination_hex))
