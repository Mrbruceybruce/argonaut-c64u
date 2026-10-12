# SPDX-License-Identifier: GPL-3.0-or-later
"""Schema-4 bounded MKD observations. Evidence never grants execution authority."""
from dataclasses import dataclass, replace

import re
from .import_transaction import require, integer, text, canonical

RULE = 'c64u-25ea78-1.1.0s2-api0.1-staging-usb0-mkd-extra-two-slashes-v1'
REASONS = ('strict-path', 'qualified-firmware', 'unqualified-reply', 'binding-invalid',
           'wire-unavailable', 'wire-truncated')
OUTCOMES = ('not-started', 'rejected', 'unknown', 'completed')
IDENTITY_FIELDS = ('physical_id', 'product', 'firmware', 'api_version')


def checked_request(path):
    require(type(path) is bytes and path.startswith(b'/') and b'\\' not in path and
            not any(c < 32 or c == 127 for c in path) and
            (path == b'/' or all(part not in (b'', b'.', b'..') for part in path.split(b'/')[1:])),
            'Invalid MKD request path.')


@dataclass(frozen=True)
class MkdObservation:
    """Pure scalar projection; no transport types, handles or permission.

    The schema-4 interpretation is pinned here for historical decoding. The
    adapter copies actual MutationEvidence fields without normalizing bytes.
    """
    operation: str
    stage: str
    outcome: str
    stage_submitted: bool
    consequential_submitted: bool
    reply_code: int | None
    acknowledged: tuple[tuple[str, int], ...]
    reply_lines: tuple[bytes, ...]
    requested_path: bytes | None

    @property
    def acknowledgment(self):
        if not self.consequential_submitted:return 'not-started'
        if self.reply_code is not None and 400 <= self.reply_code <= 599 and self.reply_code != 421:
            return 'rejected'
        if self.stage == 'MKD' and self.reply_code == 257 and ('MKD',257) in self.acknowledged:
            return 'completed'
        return 'unknown'

    @property
    def created_path(self):
        if self.operation != 'MKD' or self.acknowledgment != 'completed' or len(self.reply_lines) != 1:return None
        match = re.fullmatch(rb'257 "((?:[^"\r\n]|"")*)"(?: [^"\r\n]*)?', self.reply_lines[0])
        return None if match is None else match[1].replace(b'""',b'"')

    def mkdir_path_status(self, expected):
        checked_request(expected)
        if self.operation != 'MKD' or self.acknowledgment != 'completed' or self.created_path is None:
            return 'unavailable'
        try:checked_request(self.created_path)
        except ValueError:return 'invalid'
        return 'matched' if self.created_path == expected and self.requested_path == expected else 'mismatch'


def destination(tx, encoding):
    require(encoding in ('utf-8', 'latin-1'), 'Unsupported MKD encoding.')
    try: return (tx.library.path+'/'+tx.directory).encode(encoding, errors='strict')
    except UnicodeError as exc: raise ValueError('Unencodable MKD destination.') from exc


def unhex(value, maximum):
    require(type(value) is str and len(value) <= 2*maximum and len(value)%2 == 0 and
            all(c in '0123456789abcdef' for c in value), 'Invalid MKD hex bytes.')
    return bytes.fromhex(value)


@dataclass(frozen=True)
class MkdProof:
    operation_id: str
    encoding: str
    request_hex: str | None
    operation: str = 'MKD'
    stage: str = 'MKD'
    transport_outcome: str = 'not-started'
    stage_submitted: bool = False
    consequential_submitted: bool = False
    reply_code: int | None = None
    acknowledged: tuple[tuple[str, int], ...] = ()
    acknowledgment: str = 'not-started'
    reply_lines_hex: tuple[str, ...] = ()
    availability: str = 'unavailable'
    path_status: str = 'unavailable'
    decision: str = 'unqualified'
    compatibility_rule: str | None = None
    reason: str = 'wire-unavailable'
    physical_id: str = ''
    product: str = ''
    firmware: str = ''
    api_version: str = ''
    provenance: str = 'unavailable'
    core_session_id: str = ''
    binding_device_id: str = ''
    binding_valid: bool = False

    def wire(self, tx):
        maximum = len(destination(tx, self.encoding))
        request = None if self.request_hex is None else unhex(self.request_hex, maximum)
        require(type(self.reply_lines_hex) is tuple and len(self.reply_lines_hex) <= 64,
                'Too many MKD lines.')
        lines = tuple(unhex(line, 4096) for line in self.reply_lines_hex)
        require(sum(len(line)+2 for line in lines) <= 16384, 'MKD reply aggregate exceeded.')
        return MkdObservation(self.operation, self.stage, self.transport_outcome,
            self.stage_submitted, self.consequential_submitted, self.reply_code,
            acknowledged=self.acknowledged, reply_lines=lines, requested_path=request)

    def classification(self, tx, wire):
        path = destination(tx, self.encoding)
        status = wire.mkdir_path_status(path)
        if self.availability != 'complete':
            return status, 'unqualified', None, 'wire-'+self.availability
        if not self.binding_valid:
            return status, 'unqualified', None, 'binding-invalid'
        accepted = (wire.outcome == 'completed' and wire.stage_submitted and
                    wire.consequential_submitted and wire.acknowledgment == 'completed' and
                    wire.reply_code == 257 and wire.requested_path == path and
                    all(not any(c < 32 or c == 127 for c in line) for line in wire.reply_lines))
        if accepted and status == 'matched':
            return status, 'strict', None, 'strict-path'
        qualified = (self.provenance == 'live-rest' and
            (self.physical_id, self.product, self.firmware, self.api_version) ==
            ('25EA78', 'C64 Ultimate', '1.1.0s2', '0.1') and
            self.binding_device_id == 'id:25EA78' and tx.library.root == '/USB0' and
            tx.library.path == '/USB0/ARGONAUT_LIBRARY')
        if (accepted and qualified and wire.reply_lines == (b'257 "//'+path+b'" created.',)
                and wire.created_path == b'//'+path):
            return status, 'firmware-compatible', RULE, 'qualified-firmware'
        return status, 'unqualified', None, 'unqualified-reply'

    def validate(self, tx, operation_id):
        require(type(self) is MkdProof and self.operation_id == operation_id,
                'Wrong MKD proof operation identity.')
        require(self.operation == self.stage == 'MKD', 'Wrong MKD proof stage.')
        require(self.transport_outcome in OUTCOMES and self.acknowledgment in OUTCOMES,
                'Invalid MKD transport outcome.')
        for value in (self.stage_submitted, self.consequential_submitted, self.binding_valid):
            require(type(value) is bool, 'Invalid MKD boolean.')
        require(self.stage_submitted == self.consequential_submitted, 'Contradictory MKD submission.')
        # MKD has one consequential command: not-started is equivalent to no
        # attempted submission. Unknown may retain an observed reply after a
        # later transport/binding failure, but must not claim non-submission.
        require((self.transport_outcome == 'not-started') == (not self.consequential_submitted),
                'Contradictory MKD transport/submission outcome.')
        if self.reply_code is not None: integer(self.reply_code, 100, 599)
        require(type(self.acknowledged) is tuple and len(self.acknowledged) <= 1 and all(
            type(a) is tuple and len(a) == 2 and a[0] == 'MKD' and type(a[1]) is int and
            200 <= a[1] <= 299 and a[1] == self.reply_code for a in self.acknowledged),
            'Invalid MKD acknowledgment observations.')
        require(self.availability in ('complete', 'unavailable', 'truncated'), 'Invalid MKD availability.')
        require(self.path_status in ('matched', 'mismatch', 'invalid', 'unavailable'), 'Invalid MKD path status.')
        require(self.decision in ('strict', 'firmware-compatible', 'unqualified'), 'Invalid MKD decision.')
        require(self.compatibility_rule in (None, RULE) and self.reason in REASONS, 'Unknown MKD rule/reason.')
        for name in IDENTITY_FIELDS:
            value = getattr(self, name); text(value, 128, empty=True)
            require(len(value.encode('utf-8')) <= 128, 'Oversized MKD identity.')
        require(self.provenance in ('live-rest', 'unavailable'), 'Invalid identity provenance.')
        if self.provenance == 'unavailable':
            require(not any(getattr(self, f) for f in IDENTITY_FIELDS), 'Unproven identity.')
        text(self.core_session_id, 256, empty=True); text(self.binding_device_id, 256, empty=True)
        if self.binding_valid:
            require(self.core_session_id == tx.session_id and self.binding_device_id == tx.library.device_id,
                    'Wrong MKD session/device binding.')
        wire = self.wire(tx)
        require(wire.requested_path is None or wire.requested_path == destination(tx, self.encoding),
                'Wrong MKD proof destination.')
        require(self.acknowledgment == wire.acknowledgment, 'Contradictory MKD acknowledgment.')
        if self.availability == 'unavailable': require(not wire.reply_lines, 'Unavailable reply contains lines.')
        if self.availability == 'complete':
            require(bool(wire.reply_lines) and self.reply_code is not None and
                    wire.reply_lines[0][:3] == str(self.reply_code).encode('ascii'), 'Incomplete MKD reply.')
        if not self.consequential_submitted:
            require(self.transport_outcome == 'not-started' and self.reply_code is None and
                    not self.acknowledged and self.availability == 'unavailable', 'Unsubmitted MKD claims reply.')
        if self.transport_outcome == 'completed':
            require(self.consequential_submitted and self.reply_code is not None and
                    200 <= self.reply_code <= 299 and self.acknowledged == (('MKD', self.reply_code),),
                    'Completed transport lacks acknowledgment.')
        if self.transport_outcome == 'rejected':
            require(self.acknowledgment == 'rejected', 'Rejected transport lacks negative reply.')
        require((self.path_status, self.decision, self.compatibility_rule, self.reason) ==
                self.classification(tx, wire), 'Contradictory MKD classification.')
        return self


def capture(tx, operation_id, evidence, *, encoding, identity, binding, binding_valid):
    """Copy bounded actual observations; no normalization or synthetic success."""
    path = destination(tx, encoding); checked_request(path)
    require(type(evidence) is MkdObservation, 'Missing MKD transport observation.')
    lines = evidence.reply_lines
    availability = 'complete' if lines else 'unavailable'
    if (type(lines) is not tuple or any(type(line) is not bytes or len(line) > 4096 for line in lines)
            or len(lines) > 64 or sum(len(line)+2 for line in lines) > 16384):
        # A nonconforming transport cannot allocate unbounded durable evidence.
        lines = (); availability = 'truncated'
    reported = {}
    if identity is not None:
        reported = dict(physical_id=identity.physical_id.removeprefix('id:'),
                        product=identity.product, firmware=identity.firmware, api_version=identity.api_version)
        try:
            for value in reported.values():
                text(value, 128, empty=True)
                require(len(value.encode('utf-8')) <= 128, 'Oversized identity.')
        except (ValueError, TypeError): reported = {}
    proof = MkdProof(operation_id, encoding,
        None if evidence.requested_path is None else evidence.requested_path.hex(),
        operation=evidence.operation, stage=evidence.stage, transport_outcome=evidence.outcome,
        stage_submitted=evidence.stage_submitted, consequential_submitted=evidence.consequential_submitted,
        reply_code=evidence.reply_code, acknowledged=evidence.acknowledged,
        acknowledgment=evidence.acknowledgment, reply_lines_hex=tuple(line.hex() for line in lines),
        availability=availability, provenance='live-rest' if reported else 'unavailable',
        core_session_id=binding.core_session_id, binding_device_id=binding.device.physical_id,
        binding_valid=binding_valid, **reported)
    status, decision, rule, reason = proof.classification(tx, proof.wire(tx))
    return replace(proof, path_status=status, decision=decision, compatibility_rule=rule,
                   reason=reason).validate(tx, operation_id)


def maximum_document(tx):
    """Encoding envelope, intentionally not a valid proof; dominates all fields.

    64 line envelopes plus 32768 hex characters overestimate the framed aggregate.
    UTF-8 identity bytes are <=128; 128 escaped backslashes dominate each.
    Session/device strings allow 256 codepoints, bounded by four UTF-8 bytes each
    (controls are forbidden; quote/backslash escaping costs only two).
    """
    d = canonical(MkdProof('f'*36, 'latin-1', 'f'*(2*len(destination(tx, 'utf-8')))))
    d.update(transport_outcome='not-started', stage_submitted=False, consequential_submitted=False,
             reply_code=None, acknowledged=[['MKD', 299]], acknowledgment='not-started',
             reply_lines_hex=['f'*8192]*4+['']*60, availability='unavailable', path_status='unavailable',
             decision='firmware-compatible', compatibility_rule=RULE, reason=max(REASONS, key=len),
             provenance='unavailable', core_session_id='\U00010000'*256, binding_device_id='\U00010000'*256,
             binding_valid=False)
    for name in IDENTITY_FIELDS: d[name] = '\\'*128
    return d
