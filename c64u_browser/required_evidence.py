# SPDX-License-Identifier: GPL-3.0-or-later
"""Synchronous private evidence receipts, not authorization or recovery tokens."""
from dataclasses import dataclass
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from threading import RLock

MAX_RECORD = 262144


class EvidenceFailure(RuntimeError):
    """Required persistence failed; the controlling owner must remain retained."""


def encode_record(value):
    def bounded(item, depth=0):
        if depth > 12: raise EvidenceFailure('Evidence nesting exceeded.')
        if item is None or type(item) is bool: return
        if type(item) is int and -(2**63) <= item < 2**63: return
        if type(item) is str and len(item) <= 65536: return
        if type(item) in (tuple, list) and len(item) <= 256:
            for child in item: bounded(child, depth + 1)
            return
        if type(item) is dict and len(item) <= 128 and all(type(k) is str and len(k) <= 128 for k in item):
            for child in item.values(): bounded(child, depth + 1)
            return
        raise EvidenceFailure('Unsupported evidence value.')
    bounded(value)
    result = (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                         allow_nan=False) + '\n').encode('ascii')
    if len(result) > MAX_RECORD: raise EvidenceFailure('Evidence record exceeds bound.')
    return result


@dataclass(frozen=True)
class EvidenceReceipt:
    name: str
    sha256: str
    synchronized: bool = True


class RequiredEvidence:
    """One poisoned-on-error channel to a synchronous durable sink.

    A sink's save(kind, value) must exclusively store the canonical {kind,value}
    record and synchronize it before returning EvidenceReceipt. This is a trusted
    internal Python contract, not a security boundary against a dishonest sink.
    """
    def __init__(self, sink):
        self.sink = sink
        self.blocked = False
        self.receipts = []
        self._saving = 0
        self._dispatching = False
        self._lock = RLock()

    @contextmanager
    def transition(self):
        """Serialize an owner action (including its saves) against wire submission."""
        with self._lock:
            if self.blocked or self._dispatching:
                raise EvidenceFailure('Required evidence owner cannot transition.')
            yield

    @contextmanager
    def dispatch(self, validate):
        """Linearize submission after validation under the persistence lock.

        Diagnostics must run BEFORE entry. The transport marks submitted and
        calls sendall immediately after entry, holding this lock until sendall
        returns/raises. Later persistence failures cannot retract that submission.
        No reply wait, sink or diagnostic callback belongs inside this section.
        """
        with self._lock:
            if self.blocked or self._saving or self._dispatching:
                raise EvidenceFailure('Required evidence does not permit dispatch.')
            validate()
            if self.blocked or self._saving:
                raise EvidenceFailure('Required evidence revoked during validation.')
            self._dispatching = True  # submission linearization boundary
            try:
                yield
            finally:
                self._dispatching = False

    def save(self, kind, value):
        with self._lock:
            if self.blocked: raise EvidenceFailure('Required evidence owner is blocked.')
            self._saving += 1
            try:
                if self._dispatching:
                    raise EvidenceFailure('Persistence cannot reenter active submission.')
                if type(kind) is not str or not re.fullmatch('[a-z][a-z0-9-]{0,63}', kind):
                    raise EvidenceFailure('Invalid evidence kind.')
                data = encode_record(dict(kind=kind, value=value))
                result = self.sink.save(kind, value)
                if (type(result) is not EvidenceReceipt or result.synchronized is not True or
                        result.sha256 != hashlib.sha256(data).hexdigest()):
                    raise EvidenceFailure('Required synchronized receipt missing.')
                self.receipts.append(result)
                return result
            except BaseException:
                self.blocked = True
                raise
            finally:
                self._saving -= 1


class EvidenceDirectory:
    """Small bounded evidence store. No publication journal, resume or cleanup API."""
    def __init__(self, directory, *, byte_limit=16 * 1024 * 1024, record_limit=256):
        if type(byte_limit) is not int or not 0 < byte_limit <= 16 * 1024 * 1024:
            raise EvidenceFailure('Invalid evidence allowance.')
        if type(record_limit) is not int or not 0 < record_limit <= 256:
            raise EvidenceFailure('Invalid record allowance.')
        self.path = Path(directory)
        if not self.path.is_absolute() or self.path.resolve() != self.path:
            raise EvidenceFailure('Fresh absolute unaliased evidence directory required.')
        from .import_snapshots import open_directory
        parent = open_directory(self.path.parent)
        self.fd = None
        self.blocked = False
        self.used = self.sequence = 0
        self.byte_limit, self.record_limit = byte_limit, record_limit
        self._lock = RLock()
        try:
            os.mkdir(self.path.name, 0o700, dir_fd=parent)
            self.fd = os.open(self.path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            self.identity = os.fstat(self.fd)
            os.fsync(self.fd); os.fsync(parent)
            self.parent = os.dup(parent)
            self.parent_identity = os.fstat(parent)
        except BaseException:
            if self.fd is not None: os.close(self.fd)
            raise
        finally:
            os.close(parent)

    @staticmethod
    def _same(left, right):
        return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)

    def _validate_location(self):
        from .import_snapshots import open_directory
        # Rewalk the absolute parent path with O_NOFOLLOW on every component;
        # a held descriptor alone survives a rename and cannot bind the pathname.
        fresh = open_directory(self.path.parent)
        try:
            parent = os.fstat(self.parent)
            if not self._same(parent, self.parent_identity) or not self._same(os.fstat(fresh), parent):
                raise EvidenceFailure('Evidence parent identity changed.')
            held = os.fstat(self.fd)
            named = os.stat(self.path.name, dir_fd=fresh, follow_symlinks=False)
            if (not self._same(held, self.identity) or not self._same(named, held) or
                    not stat.S_ISDIR(named.st_mode) or held.st_uid != os.getuid() or
                    stat.S_IMODE(held.st_mode) != 0o700):
                raise EvidenceFailure('Evidence directory identity changed.')
        finally:
            os.close(fresh)

    def _validate_record(self, fd, name, size):
        held = os.fstat(fd)
        named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        if (not self._same(held, named) or not stat.S_ISREG(held.st_mode) or
                held.st_uid != os.getuid() or stat.S_IMODE(held.st_mode) != 0o600 or
                held.st_nlink != 1 or held.st_size != size):
            raise EvidenceFailure('Evidence record identity or properties changed.')

    def save(self, kind, value):
        with self._lock:
            if self.blocked: raise EvidenceFailure('Evidence directory is blocked.')
            try:
                self._validate_location()
                if not re.fullmatch('[a-z][a-z0-9-]{0,63}', kind):
                    raise EvidenceFailure('Invalid evidence kind.')
                data = encode_record(dict(kind=kind, value=value))
                if self.sequence >= self.record_limit or self.used + len(data) > self.byte_limit:
                    raise EvidenceFailure('Evidence capacity exhausted.')
                name = f'{self.sequence:06d}-{kind}.json'
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
                try:
                    self._validate_record(fd, name, 0)
                    offset = 0
                    while offset < len(data):
                        count = os.write(fd, data[offset:])
                        if type(count) is not int or not 0 < count <= len(data) - offset:
                            raise EvidenceFailure('Incomplete evidence write.')
                        offset += count
                    os.fsync(fd)
                    os.fsync(self.fd); os.fsync(self.parent)
                    # Detect substitution during write or any fsync before a
                    # receipt can grant the caller permission to continue.
                    self._validate_location()
                    self._validate_record(fd, name, len(data))
                finally:
                    os.close(fd)
                self.sequence += 1; self.used += len(data)
                return EvidenceReceipt(name, hashlib.sha256(data).hexdigest())
            except BaseException:
                self.blocked = True
                raise

    def close(self):
        """Close local descriptors only; never deletes retained evidence."""
        with self._lock:
            if self.fd is not None:
                os.close(self.fd); os.close(self.parent); self.fd = None
