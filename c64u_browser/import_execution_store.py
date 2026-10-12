# SPDX-License-Identifier: GPL-3.0-or-later
"""Core-internal append-only execution checkpoints, never execution permission.

No resume API exists. Only a newly created live writer can append evidence.
Each durable intent remains on disk even if outcome replacement/sync fails.
"""
import os
import stat
from threading import Lock
from uuid import uuid4

from .import_journal import JournalStore, encode, decode
from .import_transaction import require, MAX_JOURNAL_BYTES, MAX_RECOVERY_JOURNALS
from .import_execution import (ExecutionJournal, ExecutionTransaction, MAX_REVISIONS,
    uuid, transition, intent, outcome, validate_successor, initial_journal)
from .import_execution_v4 import ExecutionJournalV4


# Internal identity marker, never serialized or interpreted as execution authority.
_DEFINITE_REFUSAL = object()


def _definite_creation_refusal(error):
    return getattr(error, '_execution_persistence_disposition', None) is _DEFINITE_REFUSAL


class ExecutionJournalStore(JournalStore):
    @staticmethod
    def _prefix(transaction_id):
        uuid(transaction_id)
        return transaction_id + '.execution-'

    @classmethod
    def _filename(cls, transaction_id, revision):
        return cls._prefix(transaction_id) + f'{revision:06d}'

    @staticmethod
    def _read_execution(directory, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                    stat.S_IMODE(info.st_mode) & 0o077 == 0 and info.st_nlink == 1,
                    'Unsafe execution checkpoint.')
            require(info.st_size <= MAX_JOURNAL_BYTES, 'Oversized execution checkpoint.')
            result = decode(stream.read(MAX_JOURNAL_BYTES+1))
        require(type(result) in (ExecutionJournal, ExecutionJournalV4), 'Expected execution checkpoint.')
        return result

    def _chain(self, directory, transaction_id):
        prefix = self._prefix(transaction_id)
        names = []
        for name in os.listdir(directory):
            if name.startswith(prefix):
                require(len(names) < MAX_REVISIONS, 'Execution checkpoint quota exceeded.')
                names.append(name)
        names.sort(); previous = None
        retained_bytes = sum(os.stat(n, dir_fd=directory, follow_symlinks=False).st_size for n in names)
        require(retained_bytes <= MAX_JOURNAL_BYTES, 'Retained execution history exceeds hard byte limit.')
        for revision, name in enumerate(names):
            require(name == self._filename(transaction_id, revision), 'Missing or malformed execution checkpoint.')
            current = self._read_execution(directory, name)
            require(retained_bytes <= current.transaction.budgets.journal_bytes,
                    'Retained execution history exceeds captured byte limit.')
            require(current.transaction.id == transaction_id and current.revision == revision,
                    'Checkpoint filename identity mismatch.')
            if previous is None:
                require(current == initial_journal(current.transaction), 'Invalid initial execution checkpoint.')
            else: validate_successor(previous, current)
            previous = current
        return previous

    def load(self, transaction_id):
        """Inspection only; even a fully verified record is not a live writer."""
        with self._locked() as directory:
            result = self._chain(directory, transaction_id)
        if result is None: raise FileNotFoundError(transaction_id)
        return result

    def save(self, *args, **kwargs):
        raise ValueError('Loaded execution evidence cannot be saved or resumed; create a new attempt.')

    def create(self, transaction):
        journal = initial_journal(transaction).validate()
        self._append(journal, previous=None)
        return _ExecutionJournalWriter(self, journal)

    def create_reserved(self, transaction):
        from .import_capacity import _ReservedHistory
        try:
            reservation = _ReservedHistory(transaction)
            journal = initial_journal(transaction).validate()
            data = encode(journal); reservation.check(journal, data)
        except BaseException as exc:
            # These builders perform no persistence at all.
            exc._execution_persistence_disposition = _DEFINITE_REFUSAL
            raise
        self._append(journal, previous=None)
        reservation.charge(data)
        return _ExecutionJournalWriter(self, journal, reservation=reservation)

    def _append(self, journal, *, previous):
        effects_possible = False
        try:
            data = encode(journal)
            if previous is None:
                require(journal == initial_journal(journal.transaction), 'Initial execution journal must be prepared.')
            else: validate_successor(previous, journal)
            name = self._filename(journal.transaction.id, journal.revision)
            with self._locked() as directory:
                current = self._chain(directory, journal.transaction.id)
                require(current == previous, 'Existing or changed execution attempt; no replay.')
                retained_bytes = sum(os.stat(n, dir_fd=directory, follow_symlinks=False).st_size
                    for n in os.listdir(directory) if n.startswith(self._prefix(journal.transaction.id)))
                require(retained_bytes + len(data) <= journal.transaction.budgets.journal_bytes,
                        'Retained execution history exceeds the captured journal byte allowance.')
                if previous is None:
                    try: os.stat(journal.transaction.id+'.json', dir_fd=directory, follow_symlinks=False)
                    except FileNotFoundError: pass
                    else: raise ValueError('Historical transaction exists; no journal conversion or adoption.')
                    attempts = {n.split('.execution-', 1)[0] for n in os.listdir(directory) if '.execution-' in n}
                    require(len(attempts) < MAX_RECOVERY_JOURNALS, 'Execution attempt quota exceeded.')
                # All read-only refusals precede the first persistence boundary.
                # The permanent advisory lock is coordination, not checkpoint data.
                # Set before the syscall: a raised error does not prove no effects.
                effects_possible = True
                os.fsync(directory)
                temporary = 'execution-write-' + uuid4().hex
                primary = None
                try:
                    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(data); stream.flush(); os.fsync(stream.fileno())
                    # A new revision name under the cooperating-process lock. Never
                    # replace the prior intent checkpoint, even on outcome failure.
                    try: os.stat(name, dir_fd=directory, follow_symlinks=False)
                    except FileNotFoundError: pass
                    else: raise ValueError('Execution checkpoint already exists.')
                    os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
                    os.fsync(directory)
                except BaseException as exc:
                    primary = exc
                    raise
                finally:
                    try: os.unlink(temporary, dir_fd=directory)
                    except FileNotFoundError: pass
                    except OSError:
                        if primary is None: raise
                        primary.add_note('Execution checkpoint temporary cleanup failed; inspection required.')
        except BaseException as exc:
            exc._execution_persistence_disposition = None if effects_possible else _DEFINITE_REFUSAL
            raise


class _ExecutionJournalWriter:
    """Live local persistence owner only; no Core job, consent or transport access."""
    def __init__(self, store, journal, *, reservation=None):
        self._reservation = reservation
        self._store = store
        self._current = journal
        self._blocked = False
        self._lock = Lock()

    @property
    def current(self): return self._current

    @property
    def blocked(self): return self._blocked

    def _record(self, builder, previous, *args, **kwargs):
        with self._lock:
            require(not self._blocked, 'Persistence is uncertain; writer cannot continue.')
            require(previous is self._current, 'Expected the live previous checkpoint; loaded evidence cannot resume.')
            candidate = builder(previous, *args, **kwargs)
            if self._reservation is not None:
                data = encode(candidate)
                self._reservation.check(candidate, data)
            try: self._store._append(candidate, previous=previous)
            except BaseException:
                self._blocked = True
                raise
            if self._reservation is not None:self._reservation.charge(data)
            self._current = candidate
            return candidate

    def transition(self, state, *, previous, reason=''):
        return self._record(transition, previous, state, reason=reason)

    def intent(self, operation_id, kind, path, *, previous, collision='not-applicable'):
        return self._record(intent, previous, operation_id, kind, path, collision=collision)

    def outcome(self, operation_id, status, *, previous, **evidence):
        return self._record(outcome, previous, operation_id, status, **evidence)
