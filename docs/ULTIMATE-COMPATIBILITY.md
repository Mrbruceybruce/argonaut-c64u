# Ultimate-family compatibility

## Purpose

This document records observed and documented compatibility information for
Ultimate-family hardware used with Argonaut.

Argonaut should not assume that every supported Ultimate identifies itself
exactly like the current C64 Ultimate. Hardware and firmware generations may
differ in REST identity, available capabilities, storage layout, FTP behavior
and other protocol-visible details.

The purpose of this catalog is to distinguish those differences using evidence
rather than accumulating one-off compatibility assumptions.

This document is informational until a compatibility rule is explicitly
adopted by the Argonaut architecture.

## Evidence levels

Compatibility information must identify its source.

### Physically verified

Observed directly by Argonaut development or qualification against the named
hardware and firmware.

### Officially documented

Described by official Ultimate documentation but not necessarily physically
tested by the Argonaut project.

### Community reported

Reported by an Argonaut user or community tester but not yet independently
verified.

### Unknown

Not yet established.

A community report must not silently become a physically verified compatibility
claim.

## Known hardware

| Hardware | Firmware | REST `product` | REST API | Argonaut status | Evidence |
|---|---|---|---|---|---|
| C64 Ultimate — Beige | `1.1.0s2` | `C64 Ultimate` | `0.1` | Physically qualified | Physically verified |
| C64 Ultimate — Founder's Edition | `1.1.0` | `C64 Ultimate` | `0.1` | Physically qualified | Physically verified |
| Ultimate 64 | Official documentation example: `3.12` | `Ultimate 64` | Present | Not physically qualified by Argonaut | Officially documented |
| Ultimate 64 Elite II | Unknown pending tester response | Unknown pending `/v1/info` | REST responds according to user report | Argonaut currently fails identity verification | Community reported |

Do not infer Elite II identity fields from the documented Ultimate 64 response.
Record its actual `/v1/info` response when available.

## Physically verified C64 Ultimate identity

### Beige C64 Ultimate

Observed on the Argonaut development device:

```json
{
  "product": "C64 Ultimate",
  "firmware_version": "1.1.0s2",
  "fpga_version": "122",
  "core_version": "1.49",
  "hostname": "C64-Ultimate-REDACTED",
  "unique_id": "REDACTED",
  "errors": []
}
```

### Founder's Edition C64 Ultimate

Observed on the Argonaut development device:

```json
{
  "product": "C64 Ultimate",
  "firmware_version": "1.1.0",
  "fpga_version": "122",
  "core_version": "1.49",
  "hostname": "C64-Ultimate-REDACTED",
  "unique_id": "REDACTED",
  "errors": []
}
```

## UC-1 read-only REST inspection

Device Details offers **Inspect REST Compatibility** in its collapsible hardware section. Recognition validates both
`/v1/version` and `/v1/info` envelopes and identity field types, accepting API
`0.1` regardless of product spelling. Other API versions require qualification.
This is protocol evidence, not authenticated hardware attestation or a grant to
operate the device. Raw product and firmware identity remain diagnostic data.

Inspection enumerates `/v1/configs` through the existing configuration parser.
It retains up to 64 advertised categories and inspects at most four categories,
256 settings per category, with the existing 64 KiB response and timeout limits.
Unavailable categories/metadata remain unknown. Credential values are never
returned in inspection observations. Existing hidden fields, validation and
qualified read-only exceptions are unchanged. No settings are written or saved.

Inspection never installs an operational Core session, saves credentials or
persists capability grants. Reset/reboot, memory/DMA, cartridge execution, SID
playback, streaming, drive/configuration mutation and FTP publication remain
unqualified by inspection. FTP requires separate qualification. Existing
operational admission and physically verified Beige/Founder's Edition behavior
remain unchanged. Future capability-based command gating needs independent
hardware/firmware and operation-specific evidence. Historical evidence above
remains valid; recognition does not upgrade its qualification level.

### UC-1a inspection diagnostics

Configuration enumeration and each inspected category carry an immutable
observation status: Available, Unsupported, Authentication required,
Communication failed, Invalid response, or Unknown. Unsupported requires
structured endpoint/operation evidence (HTTP 404/405/501); a timeout or invalid
response does not establish lack of support. Error kinds, HTTP status codes and
typed exception causes determine the status; exception messages are neither
parsed nor displayed. Unclassified failures remain Unknown.

Successful category observations survive failures elsewhere. Authentication
failure stops further metadata requests, preserving earlier results and marking
remaining categories Not inspected. Unexpected unclassified exceptions also stop
further inspection. Existing request counts, limits, credential
redaction and operational restrictions remain unchanged. Available describes
read-only inspection evidence and grants no operational compatibility.

### UC-1b compact hardware and REST presentation

The dedicated Capabilities tab proposal is superseded. Device Details now groups
hardware fields and REST inspection in the native **Hardware & REST Information**
expander (the heading was shortened by UI-DD.1a). It starts collapsed, retains expansion while Settings
remains open, and resets after actual destruction. Expansion is not persisted
and does not contact the device. Existing scrolling and native spacing are used;
other Settings pages are unchanged. The accepted UI-DD.1/UI-DD.1a layout adds
independent Advanced Connection Settings and Network Discovery expanders; all
three start collapsed, retain state during Settings reuse and Keep editing, and
reset after actual destruction. Advanced contains the existing REST/FTP ports.
Saved Connections, hostname/password, ordinary actions and shared feedback remain
outside the expanders. Expansion itself performs no device operations.

The summary shows reported product, firmware, API version, REST recognition,
category count, successful metadata inspections, attempted metadata requests,
and sanitized failure states. Failed enumeration shows an unknown count, not
zero. No category list or configuration values are duplicated: Ultimate Menu
remains the configuration browser/editor. REST recognition grants no operational
qualification; the existing qualified-device admission remains unchanged.

Inspection uses the Device Details editor endpoint and password, including valid
unsaved drafts labeled **Unsaved endpoint**, never an unrelated active device.
The endpoint is visible; invalid targets disable inspection. Saved identity and
credential binding remain enforced by Core. One request sequence may be in
flight; duplicate actions are blocked. Editing the endpoint/password, switching
profiles or replacing the session invalidates results without claiming to cancel
running transport work. Actual closure retires callbacks and listeners; Keep
editing does not. No retries, polling, automatic inspection, or new REST requests
were added. No credentials, profiles, or inspection results are saved by inspection.

### UC-1c — supplied read-only acceptance

The supplied final publication review records accepted read-only REST inspection
on the Beige C64 Ultimate and Founder's Edition C64 Ultimate. This is supplied
physical acceptance evidence for those devices; UC-1c performed only offline
regression tests and did not contact hardware. The previously recorded firmware
and identity observations above remain unchanged; no additional firmware or
response details are inferred from this acceptance.

The supplied desktop layout, expansion, keyboard and focus checks are accepted
within their observed scope; see [Device Details acceptance](UI.md#uc-1c--supplied-acceptance-and-publication-reconciliation).
This does not establish universal desktop, font or scaling acceptance. Other
Ultimate hardware retains its outstanding physical and operation-specific
qualification limitations. Read-only REST acceptance does not newly qualify FTP,
Reset/Reboot, memory/DMA, SID, cartridge, drive, streaming or configuration writes.

Recognition diagnostics now use the same structured evidence as capability
inspection: HTTP 404/405/501 are Unsupported, authentication remains distinct,
transport failures remain Communication failed, and malformed-response evidence
is Invalid response. HTTP 500 and unclassified API failures remain Unknown;
error-message wording is not used to infer status. API 0.1 validation and
operational admission are unchanged.
