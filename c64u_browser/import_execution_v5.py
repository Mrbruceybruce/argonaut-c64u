# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated schema-5 types and codec. Historical schema-3 bytes stay unchanged."""
from dataclasses import dataclass, fields, replace

from .import_execution import (ExecutionTransaction, ExecutionOperation, ExecutionJournal,
    ExecutionAccounting, ExecutionItem, ExecutionLimits, STATES, MAX_REVISIONS)
from .import_mkd_proof import MkdProof
from .import_context_evidence import Context, CommandObservation, immutable_successor
from .import_policy import ImportPolicy
from .import_transaction import require, integer, text, digest, immutable, MAX_OPERATIONS
from .managed_library import LibraryIdentity


@dataclass(frozen=True)
class ExecutionTransactionV5(ExecutionTransaction):
    execution_policy_version: int = 4

    def validate(self):
        require(type(self.execution_policy_version) is int and self.execution_policy_version == 4,
                'Schema 5 requires execution policy 4.')
        historical_projection(self).validate()
        return self


def historical_projection(tx):
    # Validation-only view, never serialized, dispatched, loaded or upgraded.
    return ExecutionTransaction(**{f.name: 2 if f.name == 'execution_policy_version' else getattr(tx, f.name)
                                   for f in fields(ExecutionTransaction)})


def new_transaction(tx):
    require(type(tx) is ExecutionTransaction, 'Explicit new execution projection required.')
    tx.validate()
    return ExecutionTransactionV5(**{f.name: 4 if f.name == 'execution_policy_version' else getattr(tx, f.name)
                                     for f in fields(ExecutionTransaction)}).validate()


@dataclass(frozen=True)
class ExecutionOperationV5(ExecutionOperation):
    mkd_proof: MkdProof | None = None
    context: Context | None = None
    context_phase: str | None = None


@dataclass(frozen=True)
class ExecutionJournalV5(ExecutionJournal):
    schema_version: int = 5

    def validate(self):
        require(type(self.schema_version) is int and self.schema_version == 5, 'Unsupported schema-5 version.')
        require(type(self.transaction) is ExecutionTransactionV5, 'Policy-4 projection required.')
        self.transaction.validate(); tx = self.transaction
        require(self.state in STATES, 'Invalid execution state.')
        integer(self.revision, 0, MAX_REVISIONS)
        if self.revision: digest(self.previous_digest)
        else: require(self.previous_digest == '' and self.state == 'prepared', 'Invalid initial checkpoint.')
        text(self.reason, 256, empty=True)
        require(all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in self.reason), 'Bounded reason required.')
        require(type(self.operations) is tuple, 'Immutable operations required.')
        integer(len(self.operations), 0, tx.budgets.operations)
        integer(self.checkpoint, 0, len(self.operations))
        if self.state in ('prepared', 'awaiting-confirmation'):
            require(not self.operations and not self.reason, 'Pre-execution evidence claims I/O.')
        for op in self.operations:
            require(type(op) is ExecutionOperationV5, 'Schema-5 operation required.')
            # Validate ordinary fields with unchanged historical bounds. Only the
            # dedicated proof validator admits hex strings larger than 4096.
            immutable(ExecutionOperation(**{f.name: getattr(op, f.name) for f in fields(ExecutionOperation)}))
            validate_context(op, tx)
            if op.mkd_proof is not None:
                require(op.kind == 'mkdir' and op.outcome != 'intent' and op.collision != 'present',
                        'MKD proof on an unrelated/unsubmitted operation.')
                require(type(op.mkd_proof) is MkdProof, 'Invalid MKD proof type.')
                op.mkd_proof.validate(tx, op.id)
                accepted = op.mkd_proof.decision != 'unqualified'
                require((op.outcome == 'completed') == accepted, 'MKD outcome differs from proof.')
                if not accepted:
                    expected = ('not-started' if not op.mkd_proof.consequential_submitted else
                                'rejected' if op.mkd_proof.acknowledgment == 'rejected' else 'unknown')
                    require(op.outcome == expected, 'Unresolved MKD cannot claim definite failure.')
            elif op.kind == 'mkdir':
                require(op.outcome != 'completed', 'Completed MKD requires proof.')
        from .import_execution_policy4 import validate_operations
        return validate_operations(self)


def decode_execution_v5(document, field_reader):
    raw = field_reader(document, ExecutionJournalV5)
    tx = field_reader(raw['transaction'], ExecutionTransactionV5)
    tx['library'] = LibraryIdentity(**field_reader(tx['library'], LibraryIdentity))
    tx['budgets'] = ImportPolicy(**field_reader(tx['budgets'], ImportPolicy))
    tx['limits'] = ExecutionLimits(**field_reader(tx['limits'], ExecutionLimits))
    require(type(tx['items']) is list and len(tx['items']) <= 64, 'Invalid items.')
    tx['items'] = tuple(ExecutionItem(**field_reader(i, ExecutionItem)) for i in tx['items'])
    raw['transaction'] = ExecutionTransactionV5(**tx)
    require(type(raw['operations']) is list and len(raw['operations']) <= MAX_OPERATIONS, 'Invalid operations.')
    operations = []
    for value in raw['operations']:
        op = field_reader(value, ExecutionOperationV5)
        op['accounting'] = ExecutionAccounting(**field_reader(op['accounting'], ExecutionAccounting))
        if op['context'] is not None:
            context = field_reader(op['context'], Context)
            for key in ('cwd', 'pwd'):
                if context[key] is not None:
                    context[key] = CommandObservation(**field_reader(context[key], CommandObservation))
            op['context'] = Context(**context)
        if op['mkd_proof'] is not None:
            proof = field_reader(op['mkd_proof'], MkdProof)
            require(type(proof['acknowledged']) is list and len(proof['acknowledged']) <= 1 and
                    all(type(a) is list for a in proof['acknowledged']), 'Invalid acknowledgments.')
            require(type(proof['reply_lines_hex']) is list and len(proof['reply_lines_hex']) <= 64,
                    'Invalid MKD lines.')
            proof['acknowledged'] = tuple(tuple(a) for a in proof['acknowledged'])
            proof['reply_lines_hex'] = tuple(proof['reply_lines_hex'])
            op['mkd_proof'] = MkdProof(**proof)
        operations.append(ExecutionOperationV5(**op))
    raw['operations'] = tuple(operations)
    return ExecutionJournalV5(**raw).validate()


PHASES = ('context-intent', 'cwd-observed', 'pwd-observed', 'mkd-intent', 'mkd-observed', 'stopped')


def validate_context(op, tx):
    if op.kind != 'mkdir':
        require(op.context is None and op.context_phase is None, 'Context on unrelated operation.')
        return
    require(type(op.context) is Context and op.context_phase in PHASES, 'Missing mkdir context.')
    c = op.context.validate(tx, op.id)
    phase = op.context_phase
    if phase == 'context-intent': require(c.cwd is c.pwd is None, 'Premature observation.')
    if phase == 'cwd-observed':
        require(c.cwd is not None and c.cwd.completion == 'accepted' and c.pwd is None, 'Invalid CWD barrier.')
    if phase in ('pwd-observed', 'mkd-intent', 'mkd-observed'):
        require(c.verified, 'MKD requires verified root context.')
    if phase not in ('mkd-observed', 'stopped'):
        require(c.mkd_lease_id is None and op.mkd_proof is None and op.outcome == 'intent', 'Premature MKD proof.')
    if phase == 'stopped': require(op.outcome != 'intent' and op.outcome != 'completed', 'Failure must terminate.')
    if op.outcome == 'completed':
        require(op.mkd_proof is not None and op.mkd_proof.binding_valid and phase == 'mkd-observed' and c.mkd_lease_id == c.ftp_session_id and c.mkd_owner_valid is True,
                'Completed MKD lacks same-lease ownership.')
    if op.mkd_proof is not None:
        p = op.mkd_proof
        require(c.verified and c.mkd_lease_id is not None and
                (p.encoding, p.request_hex, p.core_session_id, p.binding_device_id,
                 p.physical_id, p.product, p.firmware, p.api_version, p.provenance) ==
                (c.encoding, c.destination_hex, c.core_session_id, c.device_id,
                 c.physical_id, c.product, c.firmware, c.api_version, c.provenance), 'Context/MKD binding mismatch.')
    elif phase == 'stopped':
        require(op.outcome == ('rejected' if op.collision == 'present' else 'not-started'), 'Context failure is not filesystem mutation.')


def context_checkpoint(previous, context, phase, *, accounting=None, status='intent',
                       terminal_state=None, reason='', mkd_proof=None, collision=None):
    from .import_execution import next_checkpoint, ExecutionAccounting
    require(previous.schema_version == 5 and previous.operations, 'Missing context intent.')
    op = previous.operations[-1]
    require(op.kind == 'mkdir' and op.outcome == 'intent', 'Context operation already resolved.')
    immutable_successor(op.context, context)
    routes = {'context-intent': ('cwd-observed', 'stopped'), 'cwd-observed': ('pwd-observed', 'stopped'),
              'pwd-observed': ('mkd-intent', 'stopped'), 'mkd-intent': ('mkd-observed', 'stopped')}
    require(phase in routes.get(op.context_phase, ()), 'Wrong durable context order.')
    old = op.context
    previous_phase = op.context_phase
    require(context.provenance == 'live-rest' or phase == 'stopped', 'Unavailable identity cannot progress.')
    if previous_phase == 'context-intent':
        require(context.pwd is None and context.mkd_lease_id is None and mkd_proof is None,
                'Evidence skips durable CWD barrier.')
    if previous_phase == 'cwd-observed':
        require(context.mkd_lease_id is None and mkd_proof is None, 'Evidence skips durable PWD barrier.')
    if previous_phase == 'pwd-observed':
        require(context == old and mkd_proof is None, 'MKD before durable dispatch intent.')
    if previous_phase == 'mkd-intent':
        require(context.cwd == old.cwd and context.pwd == old.pwd, 'Context changed at MKD outcome.')
    if phase == 'cwd-observed': require(context.pwd is None, 'PWD before CWD persistence.')
    if phase == 'mkd-intent': require(context == old, 'Intent changed observations.')
    if phase in ('mkd-observed', 'stopped'):
        require(status != 'intent', 'Terminal observation requires outcome.')
    else: require(status == 'intent' and terminal_state is None and not reason, 'Invalid continuing barrier.')
    a = op.accounting if accounting is None else accounting
    require(a.control_read_bytes >= op.accounting.control_read_bytes, 'Context accounting regressed.')
    if phase not in ('mkd-observed', 'stopped'):
        require(replace(a, control_read_bytes=0) == ExecutionAccounting(), 'Context claims payload I/O.')
    state = previous.state if status in ('intent', 'completed') else ('uncertain' if status == 'unknown' else 'failed')
    if terminal_state is not None:
        require(terminal_state in ('failed', 'canceled', 'uncertain') and
                (status != 'unknown' or terminal_state == 'uncertain'), 'Invalid terminal state.')
        state = terminal_state
    updated = replace(op, context=context, context_phase=phase, accounting=a, outcome=status,
                      mkd_proof=mkd_proof, collision=op.collision if collision is None else collision)
    return next_checkpoint(previous, operations=previous.operations[:-1]+(updated,), state=state, reason=reason,
                           checkpoint=len(previous.operations) if status == 'completed' else previous.checkpoint)


def validate_context_successor(previous, current):
    require(previous.operations[:-1] == current.operations[:-1], 'Earlier evidence changed.')
    op = current.operations[-1]
    expected = context_checkpoint(previous, op.context, op.context_phase, accounting=op.accounting,
        status=op.outcome, terminal_state=current.state if current.state in ('failed','canceled','uncertain') else None,
        reason=current.reason, mkd_proof=op.mkd_proof,
        collision=None if op.collision == previous.operations[-1].collision else op.collision)
    require(current == expected, 'Invalid context successor.')
