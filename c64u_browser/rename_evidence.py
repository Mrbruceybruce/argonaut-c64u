# SPDX-License-Identifier: GPL-3.0-or-later
"""Additive private command evidence; deliberately separate from legacy projections."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RenameCommandEvidence:
    verb: str
    request: bytes = field(repr=False)
    reply: bytes = field(repr=False)
    reply_code: int | None
    submitted: bool
    acknowledgment: str
    framing_complete: bool
    truncated: bool
    device_id: str
    core_session_id: str
    ftp_session_id: str
    error_type: str = ''
    binding_valid: bool = True

    @property
    def accepted(self):
        return (self.binding_valid and self.submitted and self.framing_complete and not self.truncated and
                self.acknowledgment == 'accepted' and
                self.reply_code == {'RNFR': 350, 'RNTO': 250}.get(self.verb))

    @property
    def remote_effects_possible(self):
        return self.verb == 'RNTO' and self.submitted and self.acknowledgment != 'rejected'

    def private_record(self):
        return dict(verb=self.verb, request_hex=self.request.hex(), reply_hex=self.reply.hex(),
                    reply_code=self.reply_code, submitted=self.submitted,
                    acknowledgment=self.acknowledgment, framing_complete=self.framing_complete,
                    truncated=self.truncated, binding_valid=self.binding_valid,
                    evidence_complete=self.framing_complete and not self.truncated,
                    transport_outcome=('completed' if self.accepted else self.acknowledgment
                        if self.acknowledgment in ('rejected', 'not-started') else 'unknown'),
                    device_id=self.device_id,
                    core_session_id=self.core_session_id, ftp_session_id=self.ftp_session_id,
                    remote_effects_possible=self.remote_effects_possible, error_type=self.error_type)
