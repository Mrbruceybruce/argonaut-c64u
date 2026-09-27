# SPDX-License-Identifier: GPL-3.0-or-later
"""Core-internal C64U FTP contracts. No GUI, credentials or transport handles."""
from dataclasses import dataclass
from enum import Enum
import re


class ContainerPresentation(str, Enum):
    FILES = 'files'
    DIRECTORIES = 'directories'
    BOTH = 'both'


class CapabilityState(str, Enum):
    UNKNOWN = 'unknown'
    ADVERTISED = 'advertised'
    VERIFIED = 'verified'
    UNSUPPORTED = 'unsupported'
    BROKEN = 'broken'


class SessionState(str, Enum):
    DISCONNECTED = 'disconnected'
    CONNECTING = 'connecting'
    AUTHENTICATING = 'authenticating'
    NEGOTIATING = 'negotiating'
    READY = 'ready'
    TRANSFERRING = 'transferring'
    RECOVERING = 'recovering'
    FAILED = 'failed'


class ErrorCode(str, Enum):
    DNS = 'dns-failed'
    NETWORK = 'network-unreachable'
    CONTROL_REFUSED = 'control-refused'
    CONTROL_TIMEOUT = 'control-timeout'
    AUTHENTICATION = 'authentication-failed'
    UNSUPPORTED = 'command-unsupported'
    SESSION_LIMIT = 'session-limit'
    SERVICE_UNAVAILABLE = 'service-unavailable'
    DATA_CONNECT_TIMEOUT = 'data-connect-timeout'
    DATA_IDLE_TIMEOUT = 'data-idle-timeout'
    STOR = 'stor-failed'
    RETR = 'retr-failed'
    COMPLETION_UNKNOWN = 'completion-unknown'
    LISTING = 'listing-failed'
    MALFORMED_LISTING = 'listing-malformed'
    INCOMPLETE_LISTING = 'listing-incomplete'
    LISTING_BOUNDS = 'listing-bounds-exceeded'
    SIZE_UNAVAILABLE = 'size-unavailable'
    SIZE_MISMATCH = 'size-mismatch'
    INTEGRITY_MISMATCH = 'integrity-mismatch'
    RECOVERING = 'device-recovering'
    STALE = 'stale-session'
    CANCELLED = 'cancelled'
    BUSY = 'lease-busy'
    INVALID_ARGUMENT = 'invalid-argument'
    PROTOCOL = 'protocol-error'
    LOCAL_IO = 'local-io-failed'


class Outcome(str, Enum):
    NOT_STARTED = 'not-started'
    REJECTED = 'rejected'
    UNKNOWN = 'unknown'
    COMPLETED = 'completed'


class FtpOperationError(Exception):
    """Safe to present/serialize: never embeds command arguments or peer text.

    retryable describes availability only; it NEVER authorizes mutation replay.
    """
    def __init__(self, code, phase, *, reply_code=None, retryable=False,
                 outcome=Outcome.NOT_STARTED, transferred=0, mutation=None):
        self.code = ErrorCode(code)
        self.phase = phase
        self.reply_code = reply_code
        self.retryable = retryable
        self.outcome = outcome
        self.transferred = transferred
        self.mutation = mutation
        super().__init__(f'C64U FTP {self.code.value} ({phase}).')

    def as_dict(self):
        result = dict(code=self.code.value, phase=self.phase,
                    reply_code=self.reply_code, retryable=self.retryable,
                    outcome=self.outcome.value, transferred=self.transferred)
        if self.mutation is not None:result['mutation'] = self.mutation.as_dict()
        return result


@dataclass(frozen=True)
class MutationEvidence:
    """Wire acknowledgement, never permission to replay a mutation.

    Submission means send was attempted, not that the peer received the bytes.
    RNFR can have uncertain protocol state without RNTO ever being submitted.
    """
    operation: str
    stage: str
    outcome: Outcome = Outcome.NOT_STARTED
    stage_submitted: bool = False
    consequential_submitted: bool = False
    reply_code: int | None = None
    error_category: str | None = None
    acknowledged: tuple[tuple[str, int], ...] = ()

    def as_dict(self):
        return dict(operation=self.operation, stage=self.stage,
                    outcome=self.outcome.value, stage_submitted=self.stage_submitted,
                    consequential_submitted=self.consequential_submitted,
                    reply_code=self.reply_code, error_category=self.error_category,
                    acknowledged=self.acknowledged)


@dataclass(frozen=True)
class DeviceIdentity:
    physical_id: str
    product: str = ''
    firmware: str = ''
    api_version: str = ''


@dataclass(frozen=True)
class ConnectionBinding:
    device: DeviceIdentity
    core_session_id: str
    host: str
    port: int = 21


@dataclass(frozen=True)
class FtpSessionIdentity:
    device_id: str
    core_session_id: str
    ftp_session_id: str


@dataclass(frozen=True)
class C64UFtpCapabilities:
    presentation: ContainerPresentation
    device: DeviceIdentity
    features: tuple[str, ...] = ()
    feat: CapabilityState = CapabilityState.UNKNOWN
    mlsd: CapabilityState = CapabilityState.UNKNOWN
    mlst: CapabilityState = CapabilityState.UNKNOWN
    size: CapabilityState = CapabilityState.UNKNOWN
    pasv: CapabilityState = CapabilityState.UNKNOWN
    listing_dialect: str = 'unknown'
    quirks: tuple[str, ...] = ()


@dataclass(frozen=True)
class FtpPolicy:
    control_connect: float = 10
    control_reply: float = 10
    data_connect: float = 4
    data_idle: float = 10
    final_reply: float = 10
    reply_line_bytes: int = 4096
    reply_bytes: int = 16384
    reply_lines: int = 64
    # Explicit, externally evidenced profile input; never inferred from bad data.
    known_broken_mlsd: bool = False

    def __post_init__(self):
        import math
        for value in (self.control_connect, self.control_reply, self.data_connect,
                      self.data_idle, self.final_reply):
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Timeouts must be finite and positive.')
        for value in (self.reply_line_bytes, self.reply_bytes, self.reply_lines):
            if type(value) is not int or value < 1:
                raise ValueError('Reply bounds must be positive integers.')


@dataclass(frozen=True)
class ListingLimits:
    line_bytes: int = 4096
    total_bytes: int = 8 * 1024 * 1024
    entries: int = 100000

    def __post_init__(self):
        if any(type(n) is not int or n < 1 for n in
               (self.line_bytes, self.total_bytes, self.entries)):
            raise ValueError('Listing bounds must be positive integers.')


@dataclass(frozen=True)
class FtpEntry:
    name: bytes  # Core-internal identity, never a decoded display round trip.
    kind: str
    size: int | None = None
    modify: str | None = None
    facts: tuple[tuple[str, bytes], ...] = ()

    @property
    def display_name(self):
        # Escapes preserve readability without pretending an octet is Unicode.
        return self.name.decode('utf-8', 'backslashreplace')


@dataclass(frozen=True)
class ListingResult:
    actual_path: bytes
    entries: tuple[FtpEntry, ...]
    dialect: str
    wire_bytes: int


@dataclass(frozen=True)
class TransferResult:
    transferred: int
    sha256: str
    reply_code: int
    outcome: Outcome = Outcome.COMPLETED


def checked_path(path):
    if (not isinstance(path, bytes) or not path.startswith(b'/') or
            any(c < 32 or c == 127 for c in path) or b'\\' in path):
        raise FtpOperationError(ErrorCode.INVALID_ARGUMENT, 'path')
    if path != b'/' and any(part in (b'.', b'..', b'') for part in path.split(b'/')[1:]):
        raise FtpOperationError(ErrorCode.INVALID_ARGUMENT, 'path')
    return path


def _bad():
    raise FtpOperationError(ErrorCode.MALFORMED_LISTING, 'listing-parse')


def _name(name, kind):
    if not name or any(c < 32 or c == 127 for c in name) or b'/' in name or b'\\' in name:
        _bad()
    if name in (b'.', b'..') and kind not in ('cdir', 'pdir'):
        _bad()


def parse_mlsd_line(line):
    """Parse facts in ASCII; preserve the entire filename suffix as octets."""
    prefix, separator, name = line.partition(b' ')
    if not separator or not prefix.endswith(b';'):
        _bad()
    facts = {}
    for field in prefix[:-1].split(b';'):
        key, equals, value = field.partition(b'=')
        if (not equals or not re.fullmatch(rb'[A-Za-z0-9.-]+', key) or
                not value or any(c < 33 or c > 126 for c in value)):
            _bad()
        key = key.decode('ascii').lower()
        if key in facts:
            _bad()
        facts[key] = value
    kind = facts.get('type', b'').lower()
    if kind not in (b'file', b'dir', b'cdir', b'pdir'):
        _bad()
    kind = kind.decode('ascii')
    _name(name, kind)
    size = None
    if 'size' in facts:
        if not re.fullmatch(rb'[0-9]{1,20}', facts['size']):
            _bad()
        size = int(facts['size'])
    modify = None
    if 'modify' in facts:
        value = facts['modify']
        if not re.fullmatch(rb'[0-9]{14}(?:\.[0-9]{1,9})?', value):
            _bad()
        from datetime import datetime
        try:
            datetime.strptime(value[:14].decode('ascii'), '%Y%m%d%H%M%S')
        except ValueError:
            _bad()
        modify = value.decode('ascii')
    return FtpEntry(name, kind, size, modify, tuple(sorted(facts.items())))


def parse_list_line(line):
    """Only the deliberately supported C64U Unix LIST dialect; no guessing."""
    match = re.fullmatch(
        rb'([d-])[rwx-]{9} +[0-9]+ +[^ ]+ +[^ ]+ +([0-9]{1,20}) +'
        rb'[A-Za-z]{3} +[0-9]{1,2} +(?:[0-9]{2}:[0-9]{2}|[0-9]{4}) (.+)', line)
    if not match:
        _bad()
    mode, size, name = match.groups()
    kind = 'dir' if mode == b'd' else 'file'
    _name(name, kind)
    return FtpEntry(name, kind, int(size))


class ListingParser:
    """Incremental bounded records; partial results never escape on failure."""
    def __init__(self, dialect, limits):
        self._parse = parse_mlsd_line if dialect == 'mlsd' else parse_list_line
        self._limits = limits
        self._pending = bytearray()
        self._entries = []
        self._names = set()
        self.total = 0
        self.count = 0

    def feed(self, block):
        self.total += len(block)
        if self.total > self._limits.total_bytes:
            raise FtpOperationError(ErrorCode.LISTING_BOUNDS, 'listing-read')
        self._pending.extend(block)
        while b'\n' in self._pending:
            line, _, remainder = self._pending.partition(b'\n')
            self._pending = bytearray(remainder)
            if not line.endswith(b'\r'):
                _bad()
            line = bytes(line[:-1])
            if len(line) > self._limits.line_bytes:
                raise FtpOperationError(ErrorCode.LISTING_BOUNDS, 'listing-read')
            self.count += 1
            if self.count > self._limits.entries:
                raise FtpOperationError(ErrorCode.LISTING_BOUNDS, 'listing-read')
            entry = self._parse(line)
            if entry.kind in ('cdir', 'pdir'):
                continue
            if entry.name in self._names:
                _bad()
            self._names.add(entry.name)
            self._entries.append(entry)
        if len(self._pending) > self._limits.line_bytes + 1:
            raise FtpOperationError(ErrorCode.LISTING_BOUNDS, 'listing-read')

    def finish(self):
        if self._pending:
            raise FtpOperationError(ErrorCode.INCOMPLETE_LISTING, 'listing-read')
        return tuple(sorted(self._entries, key=lambda e: e.name))
