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
- Accepted development baseline: `fd0e205deece43865293d2a61d64bdc3834b3c05`
  — `Implement managed mutation primitives for FTP Slice 3B`.
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
operation-scoped lease. At that checkpoint, mutation/write paths and remaining
streaming downloads retained their legacy implementation. The Development
package self-test now enforces channel-specific credential behavior; credential
implementations are unchanged.

Slice 2 automated baseline: normal and optimized suites each ran 791 tests
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

## Slice 3A — accepted, committed and pushed

Slice 3A was physically accepted on both C64Us and committed/pushed to
`development` as `0f5b77f88f4fac6bddac0fa5e3cc2f5929ab544a`, with parent
`4f7a86745239e60b3c6f4e2287d94af8b3c00508`. Authorized read-only physical
checks passed on 27 September 2026; final review and the approved commit/push
are complete.

Core-bound streaming downloads and USB content hashing now use the managed FTP
client. Their SIZE → RETR → SIZE observations preserve exact counts and received
hashes, including zero-byte files. Downloads retain local staging, flush/fsync,
no-replace publication and failure/cancellation cleanup. USB backup retains its
preview read, execution download, local reread and independent remote reread;
the execution listing and two remote reads share one per-file lease. Preview
and execution remain separate lifetimes.

The private operation lifetime is shared by nested read helpers: fixed Core
binding, lazy acquisition, outermost release and operation-owned cancellation.
Structured transport outcome/count evidence survives translation. Binding and
recovery checks remain independent of cooperative cancellation. Context exit
does not itself check cancellation. A failed lease cannot implicitly reconnect;
the existing preferred-directory fallback explicitly ends its read attempt.
Bounded reads and full-volume fingerprints preserve their existing contracts.

3A automated verification: **139 focused tests passed**; complete normal and
optimized suites each ran **806 tests with 36 opt-in display skips**, no failures.
The increase over the accepted 791-test baseline is 15 new integration tests;
no existing tests were removed and the skip count is unchanged.

Physical 3A coverage: normal Core file-copy download, nested streaming download
and independent USB hash, selected-file backup preview/execution, local reread
verification, idle Core reconnect and rejection of the old binding before wire
access. Beige `25EA78` (`192.168.68.70`, firmware `1.1.0s2`) used the existing
8,952-byte `/USB1/sid/arcademem.sid`; Founder's `25BE71` (`192.168.68.69`, firmware
`1.1.0`) used the existing four-byte `/SD/test.txt`. Both retain API `0.1`.

Nested listing/download/hash and each backup file's execution verification used
one FTP session, one authentication and one FEAT. Preview and execution retained
separate observations; no active leases remained after measured operations.
Hashes matched the existing Slice 2 file evidence and local backup manifests.
No zero-byte file existed in the inspected source directories; none was created.
No remote mutation, active-transfer interruption or production code change was
performed during acceptance. See C64U-FTP.md for counts, hashes and limitations.

## Slice 3B — accepted, committed and pushed

Slice 3B was physically accepted on both C64Us and committed/pushed to
`development` as `fd0e205deece43865293d2a61d64bdc3834b3c05`, with parent
`0f5b77f88f4fac6bddac0fa5e3cc2f5929ab544a`. Authorized physical checks passed
on 27 September 2026, including automated actual-display GTK rename
qualification. Final acceptance review and the approved commit/push are complete.

Managed RNFR/RNTO, MKD, DELE and RMD retain structured mutation certainty,
submission evidence, actual reply codes and acknowledged prior steps. No result
authorizes replay. Remote rename now enters a dedicated FileService device job.
Standalone FileService folder creation and reviewed remote deletion explicitly
use the same private operation owner as reads; nested validation listings reuse
one lease. Deletion preview and execution remain separate operations.

Cooperative cancellation is deferred through each submitted mutation's reply,
through RNFR/RNTO as one serialized pair, and across both case-only rename pairs.
Binding/recovery and transport failures remain effective. Case verification
restores cancellation and retains both completed steps if verification stops.
Reviewed deletion records only acknowledged removals, the stopped target and
its mutation evidence, and unattempted reviewed items. Existing review, expiry,
session, revalidation, ordering, bounds and root protections remain in force.

After the approved GUI session-guard correction, deterministic verification is
**7 GUI/routing tests and 223 focused tests passed**. Complete normal and
optimized suites each ran **849 tests, 36 opt-in display skips, no failures**.
The original 38 mutation tests plus five GUI regressions add 43 tests to the
accepted 806-test / 36-skip baseline. The existing in-memory USB partial
cleanup test now supplies the managed cleanup seam; socket coverage verifies
real managed partial cleanup. No prior test was removed.

Physical results: beige `192.168.68.70` / `25EA78`, firmware `1.1.0s2`, and
Founder's `192.168.68.69` / `25BE71`, firmware `1.1.0`, both API `0.1`, passed
managed standalone MKD, ordinary and case-only file/directory rename, content
readback, and reviewed DELE/RMD. Unique disposable trees under beige `/USB2`
and Founder's `/SD` were emptied and removed through reviewed deletion only.

Each managed mutation operation used one session, one authentication and one
FEAT, including both case-only rename pairs and nested validation. Leases were
released and connection epochs stayed unchanged within each phase. The real GTK
prompt, busy controls, completion and refreshed name were exercised by an
external driver on display `:0`; this is automated GUI qualification, not human
visual sign-off. The stale-session GUI race remains deterministically covered;
no active mutation was interrupted and no uncertain-outcome fault was induced.
Production/test source hashes were unchanged throughout qualification. Details,
hashes, disposable paths and external probe limitations are in C64U-FTP.md.

## Slice 3C — physically qualified, uncommitted; final review pending

The approved 3C implementation is based on accepted 3B commit
`fd0e205deece43865293d2a61d64bdc3834b3c05`. It migrates normal FileService
Core-host → C64U file additions, including folder-plan files, and USB restore
addition files. Explicit routing leaves legacy `upload()` consumers unchanged.
Authorized physical 3C checks passed on both devices on 27 September 2026.
Final acceptance review and commit/push remain pending; no package or release
has been created.

Each file's plan validation and preflight listings, STOR, independent bounded
RETR/hash, SIZE, destination recheck and publication rename reuse one managed
operation lease. Files do not share a batch-wide lease. Publication uses 3B
RNFR/RNTO; no post-publication read or cancellation check is added.

The source is opened once and sized with fstat on the transferred descriptor.
Short/overlong sources fail; same-length rewrites remain outside the guarantee.
No source locking, snapshot, second source open or mtime/inode stability check
is introduced. Verification RETR is bounded by the sent count and rejects an
excess block before accepting it. Its order remains RETR/hash → SIZE.

Structured results retain STOR submission/replies/count/length evidence,
verification states and publication evidence. A lost RNTO reply yields
location-unknown evidence with both possible paths, without a staging-only
cleanup shortcut. Acknowledged publication remains completed despite late
cancellation. Staging candidates still require fresh, session-bound reviewed
deletion; they are not proof of existence or exclusive ownership. No automatic
retry, rollback or remote cleanup is introduced.

After the pre-physical evidence correction, **234 focused tests passed**; normal
and optimized suites each ran **883 tests with 36 opt-in display skips, no
failures**. This is the accepted 849-test baseline plus 34 new tests (29 initial
3C tests and five correction regressions); no existing tests were removed.
Pre-STOR setup failures now retain STOR not-started evidence separately from
the sanitized setup failure, including its phase and reply code.
Details are recorded in C64U-FTP.md. Implementation/pre-physical review and
the evidence correction were approved before physical qualification.

Both devices passed zero-byte and 1,076-byte known-content FileService uploads,
independent published-file readback, case-insensitive collision refusal, and a
genuine USB backup/restore addition with verified manifest and result accounting.
Beige `25EA78` used `/USB2` (firmware `1.1.0s2`); Founder's `25BE71` used `/SD`
(firmware `1.1.0`); both reported API `0.1`. Each normal upload and each restore
file upload used one session/authentication/FEAT across preflight, STOR, RETR,
SIZE, recheck and publication. All measured operations released their leases
and preserved the Core epoch. Independently inspected disposable trees were
removed through accepted reviewed deletion and verified absent.

Physical cancellation/partial cleanup was intentionally not attempted: no safe
controlled timing boundary was available. Fault injection and uncertain outcomes
remain qualified by deterministic fixtures. Production/test source hashes were
unchanged during qualification; only this document and C64U-FTP.md were updated.
C64U-FTP.md records exact paths, hashes, external evidence and limitations.

**Deferred:** replacement staging/exchange/cleanup and USB restore replacements;
remote-to-remote composite copy; Flash staged uploads; CLI fresh-folder uploads;
AI-client installation/provisioning; general unbound-client retirement.
Folder-plan directory creation retains its existing route. No 3D work or
replacement-exchange cancellation scope is implemented. Reviewed cleanup retains
the accepted 3B deletion primitives and existing authorization policy.

## Later Network Foundation boundaries

Likely specialized boundaries are `C64URestClient`, `C64UStreamService`, a DMA
client where justified, and the existing Ident discovery capability. Shared
concepts may include identity, connection epoch, capabilities, credentials,
recovery, cancellation and structured diagnostics. Protocol-specific behavior
and consequence-specific safety remain explicit.
