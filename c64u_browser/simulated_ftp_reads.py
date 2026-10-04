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
