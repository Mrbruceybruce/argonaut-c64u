# SPDX-License-Identifier: GPL-3.0-or-later
"""Volatile schema-3 evidence allowance. Not filesystem space or I/O insurance."""
from dataclasses import dataclass
import json

from .import_execution import ExecutionJournal, ExecutionOperation, ExecutionAccounting, MAX_REVISIONS
from .import_transaction import canonical, require


def planned_operations(tx):
    return (('snapshot-validation', ''), ('mkdir', tx.directory), ('record', tx.record_path),
            *(('upload', i.staged_path) for i in tx.items),
            *(('readback', i.staged_path) for i in tx.items))


@dataclass(frozen=True)
class EvidenceCapacity:
    checkpoint_bytes: int
    revisions: int
    aggregate_bytes: int


def reserve_capacity(tx):
    """Upper bound every serialized field for every checkpoint, including failure.

    Use the actual canonical JSON encoder options. The sizing document need not
    be a valid execution: all optional fields and counters are simultaneously at
    their largest encoded lengths. It dominates every valid planned prefix.
    Initial/awaiting/staging/verifying/verified checkpoints plus one terminal
    uncertainty checkpoint and two checkpoints per operation bound revision use.
    """
    tx.validate(); plan = planned_operations(tx)
    require(len(plan) <= tx.budgets.operations, 'Insufficient operation capacity.')
    document = canonical(ExecutionJournal(tx))
    document.update(state='awaiting-confirmation', reason='x'*256, revision=MAX_REVISIONS-1,
                    previous_digest='f'*64, checkpoint=len(plan))
    document['operations'] = []
    for n, (kind, path) in enumerate(plan, 1):
        op = canonical(ExecutionOperation('ffffffff-ffff-ffff-ffff-ffffffffffff', n, kind, path))
        op.update(outcome='not-started', size=2**63-1, sha256='f'*64,
                  collision='not-applicable', accounting={k: 2**63-1 for k in canonical(ExecutionAccounting())})
        document['operations'].append(op)
    maximum = len(json.dumps(document, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')) + 1
    slots = 2*len(plan)+6
    total = maximum*slots
    require(slots <= MAX_REVISIONS and total <= tx.budgets.journal_bytes,
            'Insufficient aggregate journal evidence capacity for planned execution and terminal evidence.')
    return EvidenceCapacity(maximum, slots, total)


class _ReservedHistory:
    def __init__(self, tx):
        self.capacity = reserve_capacity(tx)
        self.plan = planned_operations(tx)
        self.used_bytes = 0
        self.used_revisions = 0

    def check(self, journal, data):
        require(len(journal.operations) <= len(self.plan) and all(
            (op.kind, op.path) == expected for op, expected in zip(journal.operations, self.plan)),
            'Reserved evidence cannot be used for unrelated operations.')
        require(journal.revision == self.used_revisions and
                self.used_revisions < self.capacity.revisions and
                len(data) <= self.capacity.checkpoint_bytes,
                'Reserved checkpoint envelope exceeded.')
        # Preserve a full maximum-sized envelope for every remaining slot.
        require(self.used_bytes + len(data) +
                (self.capacity.revisions-self.used_revisions-1)*self.capacity.checkpoint_bytes <=
                self.capacity.aggregate_bytes, 'Reserved evidence exhausted.')

    def charge(self, data):
        self.used_bytes += len(data)
        self.used_revisions += 1
