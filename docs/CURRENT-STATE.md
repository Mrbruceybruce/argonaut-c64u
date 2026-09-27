# Current development state

## Authority and workspace

This document describes the current accepted development state and next work.
[C64U-FTP.md](C64U-FTP.md) and [SERVER-FIRST.md](SERVER-FIRST.md) provide detailed
subsystem and Core architecture/contracts. Older roadmap/pass documents,
including NEXT-PASS.md, remain useful context, but sequencing demonstrably
superseded by completed development and release history does not override the
current state recorded here.

- Stable 1.9 is released as `v1.9`. Its release artifacts are immutable.
- `main` and `v1.9` are not the 1.10 development workspace. Current 1.10 work
  belongs on `development`.
- Accepted development baseline: `bcd9ea94aee5d6af1a77378c0c0877ea0a5cfae7`
  — `Migrate C64U read paths to aware FTP client`.
- Argonaut 1.10 direction: **C64U Network Foundation**.

## Completed FTP work

**Slice 1 — dedicated compatibility layer:** `C64UFtpClient` provides typed
capabilities/errors and session lifecycle, IPv4/classic PASV, explicit binary
behavior, FEAT negotiation, bounded byte-oriented MLSD and controlled LIST
fallback. A real socket-level fake C64U FTP server exercises the protocol.
Transport objects and credentials do not escape to clients.

**Slice 2 — read-only production migration and physical acceptance complete:**
ordinary listings, raw/octet-preserving identity listings and bounded remote
reads use the new client. Full-volume fingerprint traversal reuses one
operation-scoped lease. Mutation/write paths and remaining streaming downloads
retain their legacy implementation. The Development package self-test now
enforces channel-specific credential behavior; credential implementations are
unchanged.

Accepted automated baseline: normal and optimized suites each ran 791 tests
with 36 opt-in display skips; 78 focused FTP/adapter/credential tests passed.
See C64U-FTP.md for migration boundaries and detailed acceptance evidence.

## Architectural decisions to preserve

- Use specialized protocol clients, not a generic `C64UNetworkClient`.
- Core owns physical-device identity and connection-session binding. An FTP
  session is not a Core connection epoch; opening a lease must not regenerate it.
- Prefer negotiated and observed/verified capabilities over firmware-version
  assumptions. Advertisement alone is not verification.
- Use IPv4/classic PASV with no EPSV dependency. Prefer MLSD; permit only the
  narrowly defined LIST fallback.
- Preserve raw filename octets independently from display text.
- Default to one operation-scoped FTP lease per device, no idle FTP pool.
  Nested helpers reuse the existing lease; do not retain it across user review.
- Never automatically replay an uncertain mutation.
- Transport completion is distinct from higher-level content integrity,
  conflict/replacement policy and destructive authorization.
- Keep device rules, credentials, scheduling and safety in headless Core;
  user interfaces remain clients.

## Physical FTP acceptance

Both devices passed on their currently installed firmware; no firmware changes
were required. FEAT, MLSD, PASV, SIZE and RETR were verified without LIST fallback.

| Device | Address | Physical ID | Firmware | API | Accepted evidence |
|---|---|---|---|---|---|
| Beige C64 Ultimate | `192.168.68.70` | `25EA78` | `1.1.0s2` | `0.1` | GUI/root/PWD/USB1/USB2 browsing; deterministic full USB1 fingerprint; SID catalog validation and repeated 8,952-byte reads; cancellation/reconnect |
| Founder's Edition C64 Ultimate | `192.168.68.69` | `25BE71` | `1.1.0` | `0.1` | Root, USB1 and SD browsing; `/SD/test.txt`; repeated SIZE → RETR → SIZE and exact four-byte reads |

Beige full USB1 scans used **34 directory listings through one control
connection, one authentication and one FEAT negotiation**. Repeated digest:

`40922faa550ffb0beab47992263af1167d015db10512cbfd5a5bae1792b899f5`

Elapsed times were approximately **10.992 s / 10.943 s**. Cancellation after
five directory listings, fresh reconnect and post-cancel root browsing passed.
No relevant FTP behavioral difference or compatibility quirk was observed on
the Founder's Edition; the firmware strings do not establish materially
different FTP implementations.

## Known observations and planned improvements

- An advertised storage root may lack accessible media; startup-root selection
  can therefore receive FTP 550. The external acceptance probe's assumption that
  connecting with `/` would remain there was corrected separately. Acceptance
  used the corrected probe; production initial-folder behavior is unchanged.
- No Stable 1.9 physical fingerprint timing benchmark exists. Do not claim a
  measured wall-clock speedup. Reduced connection churn is physically proven by
  the complete 34-directory traversal using a single session.
- Cancellation during blocking I/O can remain bounded by the socket timeout.
- Improved Reset/Reboot recovery UX remains future work.
- Quick Connect → Reconnect is planned.
- A System/Light/Dark theme preference is planned.

## Next: Slice 3 — transfer/mutation migration

**Before implementation, inspect and review remaining mutation/streaming
contracts and direct-client ownership. Slice 3 is not yet implemented.**

Expected eventual scope: STOR/upload, remaining download paths,
SIZE/STOR/RETR verification, rename/move, MKD/RMD, DELE, replacement primitives,
partial-upload ownership/cleanup and operation-scoped lease reuse.

Preserve staging, readback hashing, conflict review, replacement rules and
explicit destructive authorization. Do not accidentally redesign higher-level
service orchestration while migrating transport. A transport primitive's
success is not permission to discard existing verification or cleanup ownership.

## Later Network Foundation boundaries

Likely specialized boundaries are `C64URestClient`, `C64UStreamService`, a DMA
client where justified, and the existing Ident discovery capability. Shared
concepts may include identity, connection epoch, capabilities, credentials,
recovery, cancellation and structured diagnostics. Protocol-specific behavior
and consequence-specific safety remain explicit.
