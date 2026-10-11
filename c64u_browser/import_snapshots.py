# SPDX-License-Identifier: GPL-3.0-or-later
"""Non-resumable host snapshots. No remote mutation or execution authority."""
from dataclasses import dataclass
import hashlib
import os
import stat
from uuid import uuid4

from .api import BrowserError
from .import_policy import TransactionV2, ResourceAccounting
from .jobs import JobProgress

CHUNK_BYTES = 8192


class SnapshotError(BrowserError):
    retryable = False
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def refuse(ok, code, message):
    if not ok:raise SnapshotError(code, message)


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def open_directory(path):
    """Walk from / using descriptors; no symlink in any path component."""
    path = os.fspath(path)
    refuse(path == '/' or (path.startswith('/') and all(p not in ('', '.', '..') for p in path.split('/')[1:])),
           'snapshot-path', 'Choose a canonical absolute host directory.')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in ([] if path == '/' else path.split('/')[1:]):
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd);fd = new
        return fd
    except BaseException:
        os.close(fd);raise


@dataclass(frozen=True)
class SnapshotFailure:
    phase: str
    primary_error: str
    cleanup_error: str
    directory: str = ''
    directory_identity: tuple | None = None
    owned_files: tuple = ()
    cleanup_errno: int | None = None


@dataclass(frozen=True)
class SnapshotEvidence:
    transaction_id: str
    status: str
    files_completed: int
    files_total: int
    accounting: ResourceAccounting
    cleanup_complete: bool
    snapshot_id: str = ''
    host_bytes_written: int = 0
    disk_accounting: str = 'allocated-blocks'
    failure: SnapshotFailure | None = None


class ReadAllowance:
    """Charged at the reader, including bytes rejected by a sink or cancellation."""
    def __init__(self, limit):
        self.limit = limit
        self.consumed = 0

    @property
    def remaining(self):return self.limit - self.consumed

    def require(self, amount):
        refuse(type(amount) is int and 0 <= amount <= self.remaining,
               'snapshot-read-budget', 'Snapshot source-read allowance exceeded.')

    def consume(self, amount):
        self.require(amount);self.consumed += amount


class OwnedSnapshots:
    """Private POSIX descriptor ownership. Cleanup never recursively follows paths."""
    def __init__(self, parent, transaction):
        self.parent = self.directory = None
        self.name = 'argonaut-snapshots-' + uuid4().hex
        self.files = {}
        self.identity = None
        self.peak = 0
        self.written = 0
        self.conservative = False
        self.limit = transaction.budgets.temporary_disk_limit
        self.closed = False
        self.created = False
        self.parent_path = os.fspath(parent)
        try:
            self.parent = open_directory(parent)
            info = os.fstat(self.parent)
            refuse(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0,
                   'snapshot-ownership', 'Snapshot parent must be private and owned by this user.')
            os.mkdir(self.name, 0o700, dir_fd=self.parent)
            self.created = True
            self.directory = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.parent)
            info = os.fstat(self.directory)
            self.identity = (info.st_dev, info.st_ino)
            self.measure()
        except BaseException as exc:
            # Publish ownership/uncertainty before cleanup can itself fail.
            exc.snapshot_owner = self
            exc.snapshot_cleanup_complete = False
            exc.snapshot_cleanup_error = None
            try:exc.snapshot_cleanup_complete = self.cleanup()
            except BaseException as cleanup_error:
                exc.snapshot_cleanup_error = cleanup_error
            # Bare raise preserves the primary setup failure, including cancellation.
            raise

    def _allocation_unit(self):
        fs = os.fstatvfs(self.directory)
        unit = fs.f_frsize or fs.f_bsize
        refuse(type(unit) is int and unit > 0, 'snapshot-disk-accounting',
               'Filesystem allocation unit is unavailable; preparation stopped.')
        return fs, unit

    def _footprint(self, info, unit):
        blocks = getattr(info, 'st_blocks', None)
        allocated = blocks * 512 if type(blocks) is int and blocks >= 0 else 0
        if blocks is None or type(blocks) is not int or blocks < 0 or allocated < info.st_size:
            # Sparse/compressed/delayed allocation or absent block evidence:
            # reserve rounded logical size, never call it exact physical usage.
            self.conservative = True
            return max(allocated, ((info.st_size + unit - 1) // unit) * unit)
        return max(info.st_size, allocated)

    def measure(self):
        unused, unit = self._allocation_unit()
        total = self._footprint(os.fstat(self.directory), unit)
        logical = 0
        for name, identity in self.files.items():
            info = os.stat(name, dir_fd=self.directory, follow_symlinks=False)
            refuse(stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == identity and info.st_nlink == 1,
                   'snapshot-ownership', 'Snapshot ownership changed; preserve unexpected content.')
            total += self._footprint(info, unit)
            logical += info.st_size
        # Append-only files also reveal bytes written before an exception.
        self.written = max(self.written, logical)
        self.peak = max(self.peak, total)
        refuse(total <= self.limit, 'snapshot-disk-budget', 'Temporary disk allowance exceeded.')
        return total

    def create(self, ordinal):
        name = f'item-{ordinal:04d}.snapshot'
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.directory)
        info = os.fstat(fd);self.files[name] = (info.st_dev, info.st_ino)
        return fd

    def write(self, fd, block):
        current = self.measure()
        fs, unit = self._allocation_unit()
        info = os.fstat(fd)
        refuse((info.st_dev, info.st_ino) in self.files.values() and
               os.lseek(fd, 0, os.SEEK_CUR) == info.st_size,
               'snapshot-ownership', 'Snapshot writes must append to an owned file.')
        allocated = self._footprint(info, unit)
        projected = ((info.st_size + len(block) + unit - 1) // unit) * unit
        reserve = max(0, projected - allocated)
        refuse(current + reserve <= self.limit, 'snapshot-disk-budget', 'Temporary disk allowance exceeded.')
        refuse(fs.f_bavail * unit >= reserve, 'snapshot-disk-full', 'Insufficient temporary disk space.')
        view = memoryview(block)
        try:
            while view:
                written = os.write(fd, view)
                refuse(0 < written <= len(view), 'snapshot-write', 'Snapshot write did not complete.')
                self.written += written
                view = view[written:]
                self.measure()
        finally:
            # Include partial allocation even if write raises after a side effect.
            # Preserve the primary failure; its caller records peak/byte evidence.
            import sys
            if sys.exc_info()[0] is None:self.measure()
            else:
                try:self.measure()
                except Exception:pass

    def cleanup(self):
        if self.closed:return getattr(self, 'cleaned', False)
        complete = not (self.created and self.directory is None)
        try:
            if self.directory is not None:
                for name, identity in self.files.items():
                    try:
                        info = os.stat(name, dir_fd=self.directory, follow_symlinks=False)
                        if stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == identity and info.st_nlink == 1:
                            os.unlink(name, dir_fd=self.directory)
                        else:complete = False
                    except FileNotFoundError:pass
                    except OSError:complete = False
                try:
                    info = os.stat(self.name, dir_fd=self.parent, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == self.identity:
                        os.rmdir(self.name, dir_fd=self.parent)
                    else:complete = False
                except OSError:complete = False
        except BaseException:
            complete = False
            raise
        finally:
            if self.directory is not None:os.close(self.directory)
            if self.parent is not None:os.close(self.parent)
            self.closed = True;self.cleaned = complete
        return complete


def local_stream(item, sink, budget, check):
    parent, name = os.path.split(item.source.path)
    directory = open_directory(parent)
    fd = None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        refuse(stat.S_ISREG(before.st_mode) and file_identity(before) == item.local_identity,
               'snapshot-source-changed', 'Local source identity changed. Prepare a new plan.')
        budget.require(before.st_size)
        count = 0
        while count < item.size:
            check()
            block = os.read(fd, min(CHUNK_BYTES, item.size-count, budget.remaining))
            budget.consume(len(block))
            if not block:break
            sink.write(block);count += len(block)
        check()
        after = os.fstat(fd)
        path_info = os.stat(name, dir_fd=directory, follow_symlinks=False)
        refuse(count == item.size and file_identity(before) == file_identity(after) == file_identity(path_info),
               'snapshot-source-changed', 'Local source changed while preparing snapshots.')
    finally:
        if fd is not None:os.close(fd)
        os.close(directory)


def prepare_snapshots(transaction, parent, remote_stream, check, report):
    """Internal worker body; Core owns admission and the returned directory handle."""
    refuse(type(transaction) is TransactionV2, 'snapshot-policy', 'Schema-2 transaction required.')
    transaction.validate()
    budget = ReadAllowance(transaction.budgets.snapshot_read_allowance)
    owned = None;completed = 0;current = '';initializing = False
    def evidence(status, cleaned=False, failure=None):
        return SnapshotEvidence(transaction.id, status, completed, len(transaction.items),
            ResourceAccounting(snapshot_read_bytes=budget.consumed,
                               temporary_disk_peak_bytes=owned.peak if owned else 0), cleaned,
            host_bytes_written=owned.written if owned else 0,
            disk_accounting='conservative-rounded' if owned and owned.conservative else 'allocated-blocks',
            failure=failure)
    def progress(phase):
        report(JobProgress(phase, completed, len(transaction.items), 'files',
            'Preparing verified host snapshots; no game import.',
            (('current_source',current),('bytes_read',budget.consumed),
             ('bytes_total',transaction.budgets.planned_upload_bytes))))
    try:
        check();initializing = True
        owned = OwnedSnapshots(parent, transaction)
        initializing = False;progress('preparing-snapshots')
        for ordinal, item in enumerate(transaction.items, 1):
            check();current = item.source.path
            fd = owned.create(ordinal);digest = hashlib.sha256();count = 0
            class Sink:
                def write(self, block):
                    nonlocal count
                    check()
                    refuse(type(block) is bytes and len(block) <= CHUNK_BYTES and count+len(block) <= item.size,
                           'snapshot-size', 'Source exceeds approved size or stream bound.')
                    owned.write(fd,block);digest.update(block);count += len(block)
                    progress('preparing-snapshots')
                    return len(block)
            try:
                if item.source.scope == 'core-host':local_stream(item,Sink(),budget,check)
                else:remote_stream(item,Sink(),budget,check)
                check();progress('verifying-snapshot')
                refuse(count == item.size and digest.hexdigest() == item.sha256,
                       'snapshot-content', 'Source size or SHA-256 changed. Prepare a new plan.')
                os.fsync(fd);owned.measure();check()
            finally:os.close(fd)
            completed += 1
        check();progress('snapshots-ready')
        return owned, evidence('snapshots-ready')
    except BaseException as exc:
        secondary = None
        if initializing:
            owned = getattr(exc, 'snapshot_owner', None)
            # Constructor already attempted cleanup. Never retry it or infer success.
            cleaned = getattr(exc, 'snapshot_cleanup_complete', False)
            secondary = getattr(exc, 'snapshot_cleanup_error', None)
        else:
            if owned:
                try:owned.measure()
                except Exception:pass
            try:cleaned = owned.cleanup() if owned else True
            except BaseException as cleanup_error:
                cleaned = False;secondary = cleanup_error
        failure = SnapshotFailure(
            'initialization' if initializing else 'preparation',
            type(exc).__name__, type(secondary).__name__ if secondary is not None else '',
            os.path.join(owned.parent_path, owned.name) if owned and owned.created else '',
            owned.identity if owned else None,
            tuple(owned.files.items()) if owned else (),
            cleanup_errno=getattr(secondary,'errno',None))
        if not cleaned:exc.snapshot_owner = owned
        exc.snapshot_evidence = evidence('canceled' if getattr(exc,'cancelled',False) else 'failed',cleaned,failure)
        raise
