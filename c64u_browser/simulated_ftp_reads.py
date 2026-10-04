# SPDX-License-Identifier: GPL-3.0-or-later
"""Network-free managed read fixture for Offline Test Lab, never a live backend.

Transport behavior is tested separately against the loopback wire server. This
fixture exercises the real adapter, listing parser and local download publisher.
"""
from contextlib import contextmanager
import hashlib
from .api import UltimateClient
from .ftp_reads import FtpReadAdapter
from .c64u_ftp_types import (C64UFtpCapabilities, ConnectionBinding, DeviceIdentity,
    ContainerPresentation, ErrorCode, FtpOperationError, ListingLimits, ListingParser, ListingResult,
    TransferResult)


class MemoryReads:
    def __init__(self, *, rows=b'', dialect='mlsd', files=None, failure=None,
                 interrupted=False, after_read=None, actual=None):
        self.rows, self.dialect = rows, dialect
        self.files = {} if files is None else files
        self.failure, self.interrupted = failure, interrupted
        self.after_read, self.actual = after_read, actual
        self.capabilities = C64UFtpCapabilities(ContainerPresentation.FILES,
            DeviceIdentity('fixture', 'C64 Ultimate', '1', 'v1'))
        self.calls = []
        self.active = self.acquired = self.released = 0

    def _check(self, binding):
        pass

    @contextmanager
    def lease(self, binding, **kwargs):
        self.acquired += 1
        self.active += 1
        try:
            if self.failure:raise FtpOperationError(self.failure, 'fixture')
            yield self
        finally:
            self.active -= 1
            self.released += 1

    def list_directory(self, path):
        from .c64u_ftp_types import checked_path
        checked_path(path)
        self.calls.append(('list', path))
        parser = ListingParser(self.dialect, ListingLimits())
        parser.feed(self.rows)
        return ListingResult(self.actual or path, parser.finish(), self.dialect, len(self.rows))

    def size(self, path):
        self.calls.append(('size', path))
        return len(self.files[path])

    def read_into(self, path, sink, *, max_bytes, expected_bytes, progress=None):
        self.calls.append(('read', path))
        data = self.files[path]
        if self.interrupted:
            sink.write(data[:1])
            raise FtpOperationError(ErrorCode.NETWORK, 'fixture')
        sink.write(data)
        if progress:progress(len(data))
        if self.after_read:self.after_read()
        return TransferResult(len(data), hashlib.sha256(data).hexdigest(), 226)

    def attach(self, client=None):
        client = client or UltimateClient('fixture.invalid')
        binding = ConnectionBinding(DeviceIdentity('fixture', 'C64 Ultimate', '1', 'v1'),
                                    'fixture-session', 'fixture.invalid', 21)
        client._ftp_reads = FtpReadAdapter(self, binding)
        return client


class MemoryFilesystem(MemoryReads):
    """Explicit offline filesystem using the real managed adapter/primitives.

    Evidence is simulated; loopback suites establish actual wire behavior.
    Paths and names remain bytes. No sockets or live transport factories exist.
    """
    def __init__(self, *, files=None, directories=()):
        super().__init__(files={} if files is None else files)
        self.directories = {b'/', b'/USB2', *directories}
        self.before_write = self.before_read = self.before_mutation = None

    def list_directory(self, path):
        from .c64u_ftp_types import FtpEntry
        import posixpath
        from .c64u_ftp_types import checked_path
        checked_path(path)
        self.calls.append(('list', path))
        if path not in self.directories:
            raise FtpOperationError(ErrorCode.LISTING, 'fixture-list')
        entries = [FtpEntry(posixpath.basename(p), 'dir', None)
                   for p in self.directories if p != path and posixpath.dirname(p) == path]
        entries += [FtpEntry(posixpath.basename(p), 'file', len(data))
                    for p, data in self.files.items() if posixpath.dirname(p) == path]
        return ListingResult(path, tuple(entries), 'mlsd', 0)

    def read_into(self, path, sink, **kwargs):
        if self.before_read:self.before_read(path)
        return super().read_into(path, sink, **kwargs)

    def write_from(self, path, source, *, expected_bytes, progress=None):
        from .c64u_ftp_types import WriteEvidence, Outcome
        self.calls.append(('write', path))
        if self.before_write:self.before_write(path)
        data = source.read(expected_bytes + 1)
        self.files[path] = data
        digest = hashlib.sha256(data).hexdigest()
        if len(data) != expected_bytes:
            raise FtpOperationError(ErrorCode.SIZE_MISMATCH, 'fixture-write')
        evidence = WriteEvidence(expected_bytes, True, 150, 226, len(data),
                                 digest, Outcome.COMPLETED, 'exact')
        if progress:
            try:progress(len(data))
            except Exception as exc:
                raise FtpOperationError(ErrorCode.CANCELLED, 'fixture-write', transfer=evidence) from exc
        return TransferResult(len(data), digest, 226, transfer=evidence)

    def _mutation(self, verb, path, destination=None):
        from .c64u_ftp_types import MutationEvidence, Outcome
        self.calls.append((verb, path, destination))
        if self.before_mutation:self.before_mutation(verb, path, destination)
        if verb == 'mkdir':self.directories.add(path)
        elif verb == 'rmdir':self.directories.remove(path)
        elif verb == 'delete':del self.files[path]
        elif path in self.files:self.files[destination] = self.files.pop(path)
        else:
            self.directories.remove(path);self.directories.add(destination)
        stage = 'rnto' if verb == 'rename' else verb
        return MutationEvidence(verb, stage, Outcome.COMPLETED, True, True, 250)

    def mkdir(self, path):return self._mutation('mkdir', path)
    def rmdir(self, path):return self._mutation('rmdir', path)
    def delete(self, path):return self._mutation('delete', path)
    def rename(self, path, destination):return self._mutation('rename', path, destination)
