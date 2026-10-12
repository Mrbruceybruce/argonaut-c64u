# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated schema-4 types and codec. Historical schema-3 bytes stay unchanged."""
from dataclasses import dataclass, fields

from .import_execution import (ExecutionTransaction, ExecutionOperation, ExecutionJournal,
    ExecutionAccounting, ExecutionItem, ExecutionLimits, STATES, MAX_REVISIONS)
from .import_mkd_proof import MkdProof
from .import_policy import ImportPolicy
from .import_transaction import require, integer, text, digest, immutable, MAX_OPERATIONS
from .managed_library import LibraryIdentity


@dataclass(frozen=True)
class ExecutionTransactionV4(ExecutionTransaction):
    execution_policy_version: int = 3

    def validate(self):
        require(type(self.execution_policy_version) is int and self.execution_policy_version == 3,
                'Schema 4 requires execution policy 3.')
        historical_projection(self).validate()
        return self


def historical_projection(tx):
    # Validation-only view, never serialized, dispatched, loaded or upgraded.
    return ExecutionTransaction(**{f.name: 2 if f.name == 'execution_policy_version' else getattr(tx, f.name)
                                   for f in fields(ExecutionTransaction)})


def new_transaction(tx):
    require(type(tx) is ExecutionTransaction, 'Explicit new execution projection required.')
    tx.validate()
    return ExecutionTransactionV4(**{f.name: 3 if f.name == 'execution_policy_version' else getattr(tx, f.name)
                                     for f in fields(ExecutionTransaction)}).validate()


@dataclass(frozen=True)
class ExecutionOperationV4(ExecutionOperation):
    mkd_proof: MkdProof | None = None


@dataclass(frozen=True)
class ExecutionJournalV4(ExecutionJournal):
    schema_version: int = 4

    def validate(self):
        require(type(self.schema_version) is int and self.schema_version == 4, 'Unsupported schema-4 version.')
        require(type(self.transaction) is ExecutionTransactionV4, 'Policy-3 projection required.')
        self.transaction.validate(); tx = self.transaction
        require(self.state in STATES, 'Invalid execution state.')
        integer(self.revision, 0, MAX_REVISIONS-1)
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
            require(type(op) is ExecutionOperationV4, 'Schema-4 operation required.')
            # Validate ordinary fields with unchanged historical bounds. Only the
            # dedicated proof validator admits hex strings larger than 4096.
            immutable(ExecutionOperation(**{f.name: getattr(op, f.name) for f in fields(ExecutionOperation)}))
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
        from .import_execution_policy3 import validate_operations
        return validate_operations(self)


def decode_execution_v4(document, field_reader):
    raw = field_reader(document, ExecutionJournalV4)
    tx = field_reader(raw['transaction'], ExecutionTransactionV4)
    tx['library'] = LibraryIdentity(**field_reader(tx['library'], LibraryIdentity))
    tx['budgets'] = ImportPolicy(**field_reader(tx['budgets'], ImportPolicy))
    tx['limits'] = ExecutionLimits(**field_reader(tx['limits'], ExecutionLimits))
    require(type(tx['items']) is list and len(tx['items']) <= 64, 'Invalid items.')
    tx['items'] = tuple(ExecutionItem(**field_reader(i, ExecutionItem)) for i in tx['items'])
    raw['transaction'] = ExecutionTransactionV4(**tx)
    require(type(raw['operations']) is list and len(raw['operations']) <= MAX_OPERATIONS, 'Invalid operations.')
    operations = []
    for value in raw['operations']:
        op = field_reader(value, ExecutionOperationV4)
        op['accounting'] = ExecutionAccounting(**field_reader(op['accounting'], ExecutionAccounting))
        if op['mkd_proof'] is not None:
            proof = field_reader(op['mkd_proof'], MkdProof)
            require(type(proof['acknowledged']) is list and len(proof['acknowledged']) <= 1 and
                    all(type(a) is list for a in proof['acknowledged']), 'Invalid acknowledgments.')
            require(type(proof['reply_lines_hex']) is list and len(proof['reply_lines_hex']) <= 64,
                    'Invalid MKD lines.')
            proof['acknowledged'] = tuple(tuple(a) for a in proof['acknowledged'])
            proof['reply_lines_hex'] = tuple(proof['reply_lines_hex'])
            op['mkd_proof'] = MkdProof(**proof)
        operations.append(ExecutionOperationV4(**op))
    raw['operations'] = tuple(operations)
    return ExecutionJournalV4(**raw).validate()
