# SPDX-License-Identifier: GPL-3.0-or-later
"""Schema-3 execution evidence only. No authorization, transport or snapshot access."""
from dataclasses import dataclass, fields, replace
import hashlib

from .import_transaction import (TransactionError, require, integer, text, digest,
    identity, immutable, MAX_OPERATIONS, MAX_JOURNAL_BYTES, MiB)
from .import_policy import ImportPolicy, TransactionV2, MAX_IO_BYTES
from .managed_library import LibraryIdentity, LibraryError, relative_path, uuid_text
from .import_plan import LIMITS

SCHEMA_VERSION = 3
TERMINAL = ('verified-staged', 'canceled', 'failed', 'uncertain')
STATES = ('prepared', 'awaiting-confirmation', 'staging', 'verifying') + TERMINAL
MAX_REVISIONS = 2 * MAX_OPERATIONS + 8


def uuid(value):
    try: uuid_text(value)
    except (LibraryError, TypeError, ValueError) as exc:
        raise TransactionError('Invalid execution UUID.') from exc


@dataclass(frozen=True)
class ExecutionLimits:
    snapshot_validation_reads: int
    control_upload_bytes: int
    control_read_bytes: int

    def validate(self):
        integer(self.snapshot_validation_reads, 1, MAX_IO_BYTES)
        integer(self.control_upload_bytes, 1, MAX_JOURNAL_BYTES)
        integer(self.control_read_bytes, 1, 16 * MiB)


@dataclass(frozen=True)
class ExecutionItem:
    staged_path: str
    final_path: str
    format: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ExecutionTransaction:
    id: str
    plan_digest: str
    library: LibraryIdentity
    session_id: str
    manifest_revision: int
    manifest_digest: str
    snapshot_evidence_sha256: str
    budgets: ImportPolicy
    limits: ExecutionLimits
    items: tuple[ExecutionItem, ...]
    policy_version: int = 2
    execution_policy_version: int = 1

    @property
    def directory(self): return 'argonaut-import-' + self.id

    @property
    def record_path(self): return self.directory + '/transaction.json'

    def validate(self):
        immutable(self); uuid(self.id); identity(self.library)
        require(self.library.path.startswith('/') and '\\' not in self.library.path and
                all(part not in ('', '.', '..') for part in self.library.path.split('/')[1:]),
                'Aliased library path.')
        text(self.session_id, 256); integer(self.manifest_revision, 0, 2**63-1)
        for value in (self.plan_digest, self.manifest_digest, self.snapshot_evidence_sha256): digest(value)
        require(type(self.policy_version) is int and self.policy_version == 2, 'Unsupported captured policy.')
        require(type(self.execution_policy_version) is int and self.execution_policy_version in (1, 2), 'Unsupported execution policy.')
        require(type(self.budgets) is ImportPolicy and type(self.limits) is ExecutionLimits, 'Invalid execution limits.')
        self.budgets.validate(); self.limits.validate()
        require(type(self.items) is tuple, 'Immutable items required.')
        integer(len(self.items), 1, self.budgets.files)
        names = set(); content = set()
        for n, item in enumerate(self.items, 1):
            require(type(item) is ExecutionItem and item.format in LIMITS, 'Invalid execution item.')
            integer(item.size, 1, LIMITS[item.format]); digest(item.sha256)
            require(item.staged_path == f'{self.directory}/item-{n:04d}.{item.format.lower()}', 'Invalid staging path.')
            text(item.final_path, 261)
            try: relative_path(item.final_path, 'games')
            except LibraryError as exc: raise TransactionError('Invalid final path.') from exc
            require(item.final_path.count('/') == 1 and item.final_path.lower().endswith('.'+item.format.lower()), 'Invalid final filename.')
            require(item.final_path.casefold() not in names and (item.size, item.sha256) not in content, 'Duplicate execution item.')
            names.add(item.final_path.casefold()); content.add((item.size, item.sha256))
        payload = sum(item.size for item in self.items)
        require(payload == self.budgets.planned_upload_bytes == self.budgets.planned_readback_bytes, 'Payload differs from captured policy.')
        require(self.limits.snapshot_validation_reads >= payload, 'Snapshot validation allowance insufficient.')
        return self


def execution_transaction(transaction, *, snapshot_evidence_sha256, limits):
    """Explicit redacted projection, never an upgrade or a claim of live ownership."""
    require(type(transaction) is TransactionV2, 'New schema-2 transaction required.')
    transaction.validate()
    return ExecutionTransaction(transaction.id, transaction.plan_digest, transaction.library,
        transaction.session_id, transaction.manifest_revision, transaction.manifest_digest,
        snapshot_evidence_sha256, transaction.budgets, limits,
        tuple(ExecutionItem(i.staged_path, i.final_path, i.format, i.size, i.sha256)
              for i in transaction.items)).validate()


@dataclass(frozen=True)
class ExecutionAccounting:
    snapshot_validation_reads: int = 0
    attempted_upload_bytes: int = 0
    confirmed_sender_bytes: int = 0
    uncertain_send_bytes: int = 0
    readback_bytes: int = 0
    control_upload_bytes: int = 0
    control_read_bytes: int = 0

    def validate(self):
        require(type(self) is ExecutionAccounting, 'Invalid accounting type.')
        for field in fields(self): integer(getattr(self, field.name), 0, 2**63-1)
        require(self.confirmed_sender_bytes + self.uncertain_send_bytes == self.attempted_upload_bytes,
                'Attempted upload must partition sender bytes and uncertain exposure.')
        return self

    def plus(self, other):
        self.validate(); other.validate()
        return ExecutionAccounting(**{f.name: getattr(self, f.name)+getattr(other, f.name)
                                      for f in fields(self)}).validate()


@dataclass(frozen=True)
class ExecutionOperation:
    id: str
    sequence: int
    kind: str
    path: str
    outcome: str = 'intent'
    size: int = 0
    sha256: str = ''
    accounting: ExecutionAccounting = ExecutionAccounting()
    collision: str = 'not-applicable'

    def __post_init__(self):
        self.validate_hash()

    def validate_hash(self):
        require(type(self.sha256) is str, 'Operation SHA-256 must be an exact string.')
        if self.sha256 != '':
            digest(self.sha256)
        if (self.outcome in ('intent', 'not-started') or self.collision == 'present' or
                self.kind in ('snapshot-validation', 'mkdir', 'final-validation')):
            require(self.sha256 == '', 'This operation requires an absent hash.')
        elif self.outcome == 'completed' and self.kind in ('record', 'upload', 'readback', 'record-upload', 'record-readback'):
            digest(self.sha256)


@dataclass(frozen=True)
class ExecutionJournal:
    transaction: ExecutionTransaction
    state: str = 'prepared'
    operations: tuple[ExecutionOperation, ...] = ()
    checkpoint: int = 0
    reason: str = ''
    revision: int = 0
    previous_digest: str = ''
    schema_version: int = SCHEMA_VERSION

    @property
    def accounting(self):
        total = ExecutionAccounting()
        for op in self.operations: total = total.plus(op.accounting)
        return total

    def validate(self):
        immutable(self)
        require(type(self.schema_version) is int and self.schema_version == SCHEMA_VERSION, 'Unsupported execution schema.')
        require(type(self.transaction) is ExecutionTransaction, 'Execution projection required.')
        self.transaction.validate(); tx = self.transaction
        require(self.state in STATES, 'Invalid execution state; publication is excluded.')
        integer(self.revision, 0, MAX_REVISIONS-1)
        if self.revision: digest(self.previous_digest)
        else: require(self.previous_digest == '' and self.state == 'prepared', 'Invalid initial checkpoint.')
        text(self.reason, 256, empty=True)
        require(all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in self.reason), 'Bounded reason code required.')
        require(type(self.operations) is tuple, 'Immutable operations required.')
        integer(len(self.operations), 0, tx.budgets.operations)
        integer(self.checkpoint, 0, len(self.operations))
        if self.state in ('prepared', 'awaiting-confirmation'):
            require(not self.operations and not self.reason, 'Pre-execution evidence is not execution.')
        if tx.execution_policy_version == 2:
            from .import_execution_policy2 import validate_operations
            return validate_operations(self)
        items = {i.staged_path: i for i in tx.items}
        uploaded = set(); verified = set(); ids = set(); snapshot = mkdir = record = False
        stopped = None; acknowledged = 0
        for n, op in enumerate(self.operations, 1):
            require(type(op) is ExecutionOperation, 'Invalid operation type.')
            uuid(op.id); require(op.id not in ids, 'Duplicate operation identity.'); ids.add(op.id)
            require(type(op.sequence) is int and op.sequence == n, 'Missing/misordered operation.')
            require(stopped is None, 'No work after unresolved/rejected operation.')
            require(op.outcome in ('intent', 'completed', 'not-started', 'rejected', 'unknown'), 'Invalid outcome.')
            integer(op.size, 0, 2**63-1)
            op.validate_hash()
            require(type(op.accounting) is ExecutionAccounting, 'Invalid accounting.'); op.accounting.validate()
            require(op.collision in ('not-applicable', 'absent', 'present'), 'Invalid collision evidence.')
            if op.collision == 'present': require(op.outcome == 'rejected', 'Collision cannot authorize a mutation.')
            if op.outcome == 'intent':
                require(op.size == 0 and op.sha256 == '' and op.accounting == ExecutionAccounting(), 'Intent claims I/O.')
            if op.outcome == 'not-started':
                require(op.size == 0 and op.sha256 == '' and
                        replace(op.accounting, control_read_bytes=0) == ExecutionAccounting(),
                        'Unsubmitted operation claims payload I/O.')
            a = op.accounting
            if op.collision == 'present':
                require(op.size == 0 and op.sha256 == '' and a.attempted_upload_bytes == 0 and
                        a.control_upload_bytes == 0, 'Collision refusal cannot claim a write.')
            allowed = {'control_read_bytes'}
            if op.kind == 'snapshot-validation':
                require(n == 1 and op.path == '' and op.collision == 'not-applicable', 'Invalid snapshot validation.')
                require(op.sha256 == '', 'Per-item hashes reside in snapshot evidence reference.')
                allowed.add('snapshot_validation_reads')
                require(op.size == a.snapshot_validation_reads, 'Snapshot observation/count mismatch.')
                if op.outcome == 'completed':
                    require(op.size == tx.budgets.planned_upload_bytes and a.snapshot_validation_reads == op.size, 'Incomplete snapshot validation.')
                    snapshot = True
            elif op.kind == 'mkdir':
                require(snapshot and n == 2 and op.path == tx.directory, 'Invalid directory intent.')
                require(op.collision in ('absent', 'present') and op.size == 0 and op.sha256 == '', 'Missing collision/invalid directory evidence.')
                mkdir = op.outcome == 'completed'
            elif op.kind == 'record':
                require(mkdir and n == 3 and op.path == tx.record_path and op.collision in ('absent', 'present'), 'Invalid record intent.')
                allowed.add('control_upload_bytes')
                if op.outcome == 'completed':
                    integer(op.size, 1, tx.budgets.journal_bytes); digest(op.sha256)
                    require(a.control_upload_bytes == op.size and a.control_read_bytes >= op.size, 'Record needs independent readback.')
                    record = True
            elif op.kind in ('upload', 'readback'):
                require(record and op.path in items, 'Unowned payload path.')
                item = items[op.path]
                if op.kind == 'upload':
                    require(not verified and op.path not in uploaded, 'Duplicate or late upload.')
                    require(op.collision in ('absent', 'present'), 'Upload requires absence check.')
                    allowed.update(('attempted_upload_bytes', 'confirmed_sender_bytes', 'uncertain_send_bytes'))
                    require(op.size == a.confirmed_sender_bytes, 'Sender observation/count mismatch.')
                    if op.outcome == 'completed':
                        require(a.attempted_upload_bytes == a.confirmed_sender_bytes == item.size and a.uncertain_send_bytes == 0, 'Incomplete sender evidence.')
                        uploaded.add(op.path)
                else:
                    require(uploaded == set(items) and op.path not in verified and op.collision == 'not-applicable', 'Invalid readback order.')
                    require(self.state != 'staging', 'Readback requires verifying phase.')
                    allowed.add('readback_bytes')
                    require(op.size == a.readback_bytes, 'Readback observation/count mismatch.')
                    if op.outcome == 'completed':
                        require(a.readback_bytes == item.size, 'Incomplete readback accounting.'); verified.add(op.path)
                if op.outcome == 'completed': require((op.size, op.sha256) == (item.size, item.sha256), 'Content mismatch.')
            else: raise TransactionError('Unsupported operation; cleanup/publication excluded.')
            require(all(getattr(a, f.name) == 0 for f in fields(a) if f.name not in allowed), 'Accounting does not match operation.')
            if op.outcome == 'completed': acknowledged = n
            else: stopped = op.outcome
        require(self.checkpoint == acknowledged, 'Checkpoint must match completed prefix.')
        if stopped in ('unknown', 'rejected', 'not-started'):
            require(self.state in ('uncertain',) if stopped == 'unknown' else self.state in ('failed', 'canceled'), 'Outcome requires terminal state.')
        if self.state == 'uncertain': require(bool(self.reason), 'Uncertainty requires reason.')
        if stopped == 'intent': require(self.state in ('staging', 'verifying', 'uncertain'), 'Pending intent cannot claim definite termination.')
        if self.state in ('verifying', 'verified-staged'):
            require(uploaded == set(items), 'Verification before uploads.')
        if self.state == 'verified-staged':
            require(verified == set(items) and stopped is None and not self.reason, 'Incomplete staged verification.')
        total = self.accounting
        if self.state not in ('failed', 'canceled', 'uncertain'):
            require(total.snapshot_validation_reads <= tx.limits.snapshot_validation_reads and
                    total.attempted_upload_bytes <= tx.budgets.upload_allowance and
                    total.readback_bytes <= tx.budgets.readback_allowance and
                    total.control_upload_bytes <= tx.limits.control_upload_bytes and
                    total.control_read_bytes <= tx.limits.control_read_bytes, 'Execution accounting exceeds policy.')
        return self


def next_checkpoint(previous, **changes):
    """Pure evidence construction. Only the live writer can persist progress."""
    from .import_journal import encode
    require(previous.state not in TERMINAL, 'Terminal journals cannot resume.')
    return replace(previous, revision=previous.revision+1,
                   previous_digest=hashlib.sha256(encode(previous)).hexdigest(), **changes).validate()


def transition(previous, state, *, reason=''):
    routes = {'prepared': ('awaiting-confirmation', 'canceled', 'failed'),
              'awaiting-confirmation': ('staging', 'canceled', 'failed'),
              'staging': ('verifying', 'canceled', 'failed', 'uncertain'),
              'verifying': ('verified-staged', 'canceled', 'failed', 'uncertain')}
    require(state in routes.get(previous.state, ()), 'Invalid execution transition.')
    return next_checkpoint(previous, state=state, reason=reason)


def intent(previous, operation_id, kind, path, *, collision='not-applicable'):
    verification = ('readback', 'record-readback', 'final-validation') if previous.transaction.execution_policy_version in (2, 3) else ('readback',)
    require(previous.state == ('verifying' if kind in verification else 'staging'), 'Wrong operation phase.')
    require(not previous.operations or previous.operations[-1].outcome == 'completed', 'Unresolved operation.')
    from .import_execution_v4 import ExecutionOperationV4
    operation_type = ExecutionOperationV4 if previous.schema_version == 4 else ExecutionOperation
    op = operation_type(operation_id, len(previous.operations)+1, kind, path, collision=collision)
    return next_checkpoint(previous, operations=previous.operations+(op,))


def outcome(previous, operation_id, status, *, size=0, sha256='', accounting=ExecutionAccounting(), reason='', collision=None, terminal_state=None, mkd_proof=None):
    require(previous.operations and previous.operations[-1].outcome == 'intent', 'Missing durable intent.')
    op = previous.operations[-1]
    require(op.id == operation_id and status in ('completed', 'not-started', 'rejected', 'unknown'), 'Mismatched outcome identity/status.')
    state = previous.state if status == 'completed' else 'uncertain' if status == 'unknown' else 'failed'
    if terminal_state is not None:
        require(terminal_state in ('failed', 'canceled', 'uncertain') and
                (status != 'unknown' or terminal_state == 'uncertain'), 'Invalid terminal outcome state.')
        state = terminal_state
    require(collision is None or (collision == 'present' and status == 'rejected'), 'Invalid collision update.')
    require(mkd_proof is None or previous.schema_version == 4, 'Historical journal cannot carry MKD proof.')
    proof = {'mkd_proof': mkd_proof} if previous.schema_version == 4 else {}
    updated = replace(op, **proof, outcome=status, size=size, sha256=sha256, accounting=accounting,
                      collision=op.collision if collision is None else collision)
    return next_checkpoint(previous, operations=previous.operations[:-1]+(updated,), state=state,
                           checkpoint=len(previous.operations) if status == 'completed' else previous.checkpoint, reason=reason)


def validate_successor(previous, current):
    previous.validate(); current.validate()
    require(type(previous) is type(current) and previous.schema_version == current.schema_version and
            previous.transaction == current.transaction, 'Execution identity changed.')
    if len(current.operations) == len(previous.operations)+1:
        op = current.operations[-1]
        expected = intent(previous, op.id, op.kind, op.path, collision=op.collision)
    elif current.operations != previous.operations:
        require(len(current.operations) == len(previous.operations) and bool(current.operations), 'Invalid operation replacement.')
        op = current.operations[-1]
        expected = outcome(previous, op.id, op.outcome, size=op.size, sha256=op.sha256,
                           accounting=op.accounting, reason=current.reason, mkd_proof=getattr(op, 'mkd_proof', None),
                           collision=None if op.collision == previous.operations[-1].collision else op.collision,
                           terminal_state=current.state if current.state in ('failed', 'canceled', 'uncertain') else None)
    else: expected = transition(previous, current.state, reason=current.reason)
    require(current == expected, 'Invalid expected-previous transition.')


def decode_execution(document, field_reader):
    raw = field_reader(document, ExecutionJournal)
    tx = field_reader(raw['transaction'], ExecutionTransaction)
    tx['library'] = LibraryIdentity(**field_reader(tx['library'], LibraryIdentity))
    tx['budgets'] = ImportPolicy(**field_reader(tx['budgets'], ImportPolicy))
    tx['limits'] = ExecutionLimits(**field_reader(tx['limits'], ExecutionLimits))
    require(type(tx['items']) is list and len(tx['items']) <= 64, 'Invalid items.')
    tx['items'] = tuple(ExecutionItem(**field_reader(i, ExecutionItem)) for i in tx['items'])
    raw['transaction'] = ExecutionTransaction(**tx)
    require(type(raw['operations']) is list and len(raw['operations']) <= MAX_OPERATIONS, 'Invalid operations.')
    operations = []
    for value in raw['operations']:
        op = field_reader(value, ExecutionOperation)
        op['accounting'] = ExecutionAccounting(**field_reader(op['accounting'], ExecutionAccounting))
        operations.append(ExecutionOperation(**op))
    raw['operations'] = tuple(operations)
    return ExecutionJournal(**raw).validate()


def initial_journal(transaction):
    from .import_execution_v4 import ExecutionTransactionV4, ExecutionJournalV4
    require(type(transaction) in (ExecutionTransaction, ExecutionTransactionV4), 'Explicit execution projection required.')
    return (ExecutionJournalV4 if type(transaction) is ExecutionTransactionV4 else ExecutionJournal)(transaction)
