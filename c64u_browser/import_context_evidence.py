# SPDX-License-Identifier: GPL-3.0-or-later
"""Schema-5 forensic observations. Serialized evidence is never authority."""
from dataclasses import dataclass, replace, fields
import re

from .import_transaction import require, integer, text
from .import_execution import uuid
from .import_mkd_proof import destination

RAW_LIMIT = 16384


def hex_bytes(value, maximum):
    require(type(value) is str and len(value) <= 2*maximum and
            re.fullmatch(r'(?:[0-9a-f]{2})*', value) is not None, 'Invalid bounded hex.')
    return bytes.fromhex(value)


def reply_code(raw):
    return int(raw[:3]) if re.match(rb'[1-5][0-9]{2}[ -]', raw) else None


def candidate_complete(raw):
    """Candidate framing only; syntax acceptance is a separate decision."""
    if not raw or not raw.endswith(b'\n'): return False
    first = raw.split(b'\n', 1)[0]
    if re.match(rb'[1-5][0-9]{2}-', first):
        return any(line.startswith(first[:3]+b' ') for line in raw.split(b'\n')[1:-1])
    return True


def parsed_directory(raw, verb, availability):
    if verb != 'PWD' or availability != 'complete' or len(raw) > 4098: return None
    match = re.fullmatch(rb'257 "([^"\x00-\x1f\x7f]*)"(?: [\x20-\x21\x23-\x7e]*)?\r\n', raw)
    return match[1].hex() if match else None


def classification(o, verb):
    raw = bytes.fromhex(o.reply_wire_hex)
    if o.submission == 'not-attempted': return 'not-started'
    if not (o.binding_before and o.binding_after): return 'binding-invalid'
    if o.availability != 'complete': return 'incomplete'
    if (not raw.endswith(b'\r\n') or len(raw)-2 > 4096 or
            any(c < 32 or c == 127 for c in raw[:-2]) or reply_code(raw) is None or raw[3:4] != b' '):
        return 'malformed'
    if o.transport_outcome == 'rejected': return 'refused'
    if o.reply_code != (250 if verb == 'CWD' else 257): return 'wrong-code'
    if verb == 'CWD':
        if not re.fullmatch(rb'250 [\x20-\x7e]*\r\n', raw): return 'malformed'
    else:
        if o.parsed_directory_hex is None: return 'malformed'
        if o.parsed_directory_hex != '2f': return 'wrong-directory'
    if o.transport_outcome != 'completed': return 'incomplete'
    return 'accepted'


@dataclass(frozen=True)
class CommandObservation:
    command_hex: str
    path_hex: str | None
    transport_outcome: str
    submission: str
    reply_code: int | None
    reply_wire_hex: str
    reply_octets_observed: int | None
    reply_octets_retained: int
    availability: str
    parsed_directory_hex: str | None
    completion: str
    binding_before: bool
    binding_after: bool

    def validate(self, verb):
        require(verb in ('CWD', 'PWD'), 'Unsupported context command.')
        require(self.command_hex == (b'CWD /\r\n' if verb == 'CWD' else b'PWD\r\n').hex() and
                self.path_hex == ('2f' if verb == 'CWD' else None), 'Wrong context request.')
        raw = hex_bytes(self.reply_wire_hex, RAW_LIMIT)
        integer(self.reply_octets_retained, 0, RAW_LIMIT)
        require(self.reply_octets_retained == len(raw), 'Retained count mismatch.')
        n = self.reply_octets_observed
        if n is not None: integer(n, 0, RAW_LIMIT+1)
        require(self.availability in ('complete', 'partial', 'truncated', 'unavailable'), 'Invalid availability.')
        if self.availability == 'unavailable': require(not raw, 'Unavailable bytes invented.')
        elif self.availability == 'truncated':
            require(n == RAW_LIMIT+1 and len(raw) == RAW_LIMIT, 'Missing overflow witness.')
        else:
            require(n == len(raw) and n > 0, 'Captured count mismatch.')
            require(candidate_complete(raw) == (self.availability == 'complete'), 'Wrong candidate completeness.')
        require(type(self.binding_before) is bool and type(self.binding_after) is bool, 'Invalid bindings.')
        require(self.submission in ('not-attempted', 'attempted') and
                self.transport_outcome in ('not-started', 'completed', 'rejected', 'unknown'), 'Invalid transport state.')
        require((self.transport_outcome == 'not-started') == (self.submission == 'not-attempted'), 'Submission contradiction.')
        if self.submission == 'not-attempted':
            require(n == 0 and self.availability == 'unavailable', 'Unsubmitted reply.')
        if self.reply_code is not None: integer(self.reply_code, 100, 599)
        require(self.reply_code == reply_code(raw), 'Code not derived from raw evidence.')
        if self.transport_outcome in ('completed', 'rejected'):
            require(self.availability == 'complete' and self.reply_code is not None, 'Incomplete transport completion.')
            require(200 <= self.reply_code <= 299 if self.transport_outcome == 'completed' else
                    400 <= self.reply_code <= 599 and self.reply_code != 421, 'Wrong transport completion.')
        if self.parsed_directory_hex is not None: hex_bytes(self.parsed_directory_hex, 4096)
        require(self.parsed_directory_hex == parsed_directory(raw, verb, self.availability), 'Fabricated parsed directory.')
        require(self.completion == classification(self, verb), 'Contradictory context completion.')
        return self


def observation(verb, raw, *, attempted, before, after, interrupted=False):
    require(type(raw) is bytes and len(raw) <= RAW_LIMIT+1, 'Transport exceeded capture bound.')
    availability = ('unavailable' if not raw else 'truncated' if len(raw) > RAW_LIMIT else
                    'complete' if candidate_complete(raw) else 'partial')
    retained = raw[:RAW_LIMIT]; code = reply_code(retained)
    outcome = ('not-started' if not attempted else 'unknown' if interrupted else
               'completed' if availability == 'complete' and code is not None and 200 <= code <= 299 else
               'rejected' if availability == 'complete' and code is not None and 400 <= code <= 599 and code != 421 else 'unknown')
    o = CommandObservation((b'CWD /\r\n' if verb == 'CWD' else b'PWD\r\n').hex(),
        '2f' if verb == 'CWD' else None, outcome, 'attempted' if attempted else 'not-attempted',
        code, retained.hex(), len(raw), len(retained), availability,
        parsed_directory(retained, verb, availability), '', before, after)
    return replace(o, completion=classification(o, verb)).validate(verb)


@dataclass(frozen=True)
class Context:
    transaction_id: str
    operation_id: str
    encoding: str
    destination_hex: str
    core_session_id: str
    device_id: str
    ftp_session_id: str
    adapter_owner_id: str
    physical_id: str
    product: str
    firmware: str
    api_version: str
    provenance: str
    cwd: CommandObservation | None = None
    pwd: CommandObservation | None = None
    mkd_lease_id: str | None = None
    mkd_owner_valid: bool | None = None

    def validate(self, tx, oid):
        uuid(self.transaction_id); uuid(self.operation_id)
        require((self.transaction_id, self.operation_id, self.core_session_id, self.device_id) ==
                (tx.id, oid, tx.session_id, tx.library.device_id), 'Context belongs to another operation/session.')
        require(self.encoding in ('utf-8', 'latin-1'), 'Invalid context encoding.')
        require(self.destination_hex == destination(tx, self.encoding).hex(), 'Wrong exact MKD destination.')
        for value in (self.ftp_session_id, self.adapter_owner_id):
            require(len(hex_bytes(value, 16)) == 16, 'Invalid ownership observation.')
        for value in (self.core_session_id, self.device_id): text(value, 256)
        for value in (self.physical_id, self.product, self.firmware, self.api_version):
            text(value, 128, empty=True)
            require(len(value.encode('utf-8', errors='strict')) <= 128, 'Identity byte bound exceeded.')
        require(self.provenance in ('live-rest', 'unavailable'), 'Invalid provenance.')
        if self.provenance == 'live-rest':
            require(self.physical_id == self.device_id.removeprefix('id:'), 'Live device identity mismatch.')
        if self.provenance == 'unavailable':
            require(not any((self.physical_id, self.product, self.firmware, self.api_version)), 'Unavailable identity invented.')
        for verb, o in (('CWD', self.cwd), ('PWD', self.pwd)):
            if o is not None:
                require(type(o) is CommandObservation, 'Invalid context observation.'); o.validate(verb)
        if self.pwd is not None:
            require(self.cwd is not None and self.cwd.completion == 'accepted', 'PWD without accepted CWD.')
        require((self.mkd_lease_id is None) == (self.mkd_owner_valid is None), 'Incomplete MKD ownership.')
        if self.mkd_lease_id is not None:
            require(len(hex_bytes(self.mkd_lease_id, 16)) == 16 and type(self.mkd_owner_valid) is bool,
                    'Invalid MKD ownership.')
        return self

    @property
    def verified(self):
        return self.provenance == 'live-rest' and all(o is not None and o.completion == 'accepted' for o in (self.cwd, self.pwd))


def immutable_successor(old, new):
    require(type(old) is type(new) is Context, 'Context type changed.')
    for field in fields(Context):
        a, b = getattr(old, field.name), getattr(new, field.name)
        require(a == b or a is None and field.name in ('cwd', 'pwd', 'mkd_lease_id', 'mkd_owner_valid'),
                'Captured context changed.')
