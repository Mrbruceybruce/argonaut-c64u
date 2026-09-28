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
