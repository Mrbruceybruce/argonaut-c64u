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
- Verified post-R5 development authority:
  `dab627979b9d3bb085c955c6e3bea8cdaff8b338`
  (`Implement R5 Core-owned headless reads`), parent
  `8ac1b24cb70f996b877b3eef81fd1c5817748bff`. R5 is accepted, committed and pushed.
  On 4 October 2026, HEAD and local `origin/development` matched with divergence
  `0 0` and a clean worktree before the R6 documentation-only design pass.
  R2–R5 physical acceptance evidence remains recorded below and in their docs.
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

## Slice 3C — accepted, committed and pushed

The approved 3C implementation is based on accepted 3B commit
`fd0e205deece43865293d2a61d64bdc3834b3c05`. It migrates normal FileService
Core-host → C64U file additions, including folder-plan files, and USB restore
addition files. Explicit routing leaves legacy `upload()` consumers unchanged.
Authorized physical 3C checks passed on both devices on 27 September 2026.
Final acceptance review passed; 3C was committed and pushed as
`6a09af5b8559df73d83e12db3eeeeba3d8106a1a`, with parent
`fd0e205deece43865293d2a61d64bdc3834b3c05`. No package or release was created.

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

At the 3C checkpoint, replacement, composites, Flash, CLI and AI provisioning
remained deferred. The implemented 3D boundary and remaining exceptions follow.

## Slice 3D — accepted, committed and pushed

The approved 3D implementation is based on the accepted 3C commit above.
`managed_replacement.replace_managed` is selected explicitly for FileService
reviewed local-source and remote-source replacements with a C64U destination,
and USB restore replacement steps. Legacy `replace_file()` is unchanged; AI
upgrade and local-destination replacement do not silently migrate.

Each replacement owns one managed lifetime across execution validation, staging
MKD, original observation, staged copy, signature revalidation, independent
original observation, backup inspection and protected exchange/cleanup. Nested
listings, 3A reads/downloads, 3C uploads and 3B mutations reuse its fixed-binding
lease. A failed operation cannot reconnect, replay, reset as a read fallback or
continue cleanup. Preview and subsequent failure inspection are separate operations.

Both original observations now use exact SIZE → RETR/hash → SIZE. This approved
change rejects unavailable/malformed/changing SIZE and short/overlong reads.
Generic remote review still contains name/size only; these two execution reads
provide neither a review-time hash nor a source snapshot or atomic exchange.
USB restore retains content-bound comparison only where its existing equal-size
classification hashes the destination; different-size classification remains
size-based. Independent observations are never replaced with cached hashes.

Local sources use managed upload into the unique staging directory. Remote
sources first use managed download into a private local temporary directory,
then managed upload; local temporary cleanup runs on all exits. The nested
upload's published state means publication inside staging, not final replacement.

After backup-name inspection, a final binding/cooperative-cancellation check
precedes the protected original→backup, staged→final, DELE backup, RMD staging
sequence. Cooperative cancellation alone is deferred across that finite sequence.
There is no exit cancellation check or automatic rollback. Completed replacements
remain completed; pending cancellation takes effect before the next item.
Binding/recovery/transport failures and unrelated exceptions still stop work.

Ordered replacement evidence is carried separately in copy/restore results:
staging MKD/upload, original observations/signatures, each exchange/cleanup
mutation, acknowledged prefix, uncertain paths and publication versus cleanup
status. Publication-completed/cleanup-failed is explicitly reported, even though
whole-workflow accounting leaves that item unfinished. Replacement evidence never
authorizes cleanup and does not become an ordinary PartialUpload shortcut.
Later inspection and explicitly selected reviewed deletion require new operations.

The pre-physical corrections preserve normalized remote/cancellation evidence
before local temporary cleanup. A cleanup error is recorded separately with a
sanitized category; acknowledged remote success remains success in the remote
state even when local cleanup fails. Core-formatted inspection summaries now
reach copy and USB reports, including cancelled copy jobs with replacement
evidence. They identify relevant paths and uncertainty without granting replay,
rollback or cleanup authorization. Ordinary PartialUpload behavior is unchanged.

After the pre-physical corrections, **8 targeted and 266 focused tests passed**.
Complete normal and optimized suites each ran **939 tests with 36 opt-in display
skips, no failures** (931 reviewed tests + 8 correction regressions; equivalently
883 accepted tests + 48 replacement tests + 8 corrections; no removals/skip changes).
The separately authorized physical pass passed on both C64Us on 27 September
2026, with 65 recorded checks per device. Beige `25EA78` (`192.168.68.70`,
firmware `1.1.0s2`, API `0.1`) used a unique disposable tree under `/USB2`;
Founder’s `25BE71` (`192.168.68.69`, firmware `1.1.0`, API `0.1`) used `/SD`.
Reviewed local-source and remote-source replacement and genuine USB backup/restore
replacement passed with independent 640-byte SHA-256 readbacks. Remote source
and sentinel were preserved; backup/staging artifacts and local temporary data
were removed. Each replacement reused one FTP session, one USER and one FEAT;
leases released and Core epochs stayed stable. Final reviewed deletion removed
each disposable tree and absence was independently verified. Cancellation and
fault injection were intentionally omitted. Source/test hashes are unchanged
from the reviewed implementation; the deterministic baseline remains 939/36.
See C64U-FTP.md for exact paths, hashes, evidence and physical-test limitations.
No commit, push, package or release was performed.

**At the 3D checkpoint, deferred:** Flash; CLI fresh-folder uploads;
AI installation/upgrade/provisioning; general compatibility/raw-FTP retirement
and final ownership audit. R1 has since migrated remote-to-remote nonreplacement
additions and general folder-plan directory creation; R2 has migrated CLI
fresh-folder uploads, as recorded below.
Local-destination replacement retains its existing behavior. Slice 3 as a whole
is not complete. Slice 3D is accepted, physically qualified, committed and
pushed at `8315985317086e52460c981a8135bffb359da958`.

## Later Network Foundation boundaries

Likely specialized boundaries are `C64URestClient`, `C64UStreamService`, a DMA
client where justified, and the existing Ident discovery capability. Shared
concepts may include identity, connection epoch, capabilities, credentials,
recovery, cancellation and structured diagnostics. Protocol-specific behavior
and consequence-specific safety remain explicit.
## Current checkpoint

R1 — Managed Folder Composites is implemented and physically qualified on both
C64 Ultimates. The authoritative contract and detailed physical acceptance
record are in
[R1-MANAGED-FOLDER-COMPOSITES.md](R1-MANAGED-FOLDER-COMPOSITES.md).

R1 migrates remote folder-plan MKD and same-device remote-to-remote
nonreplacement additions while preserving the accepted 3C addition and 3D
replacement boundaries. Implementation review added truthful pre-validation
`setup` evidence and explicit ancestor-change and genuine USB restore
missing-directory coverage.

Authorized physical qualification passed on 29 September 2026. Beige `25EA78`
used `/USB2`; Founder's `25BE71` used `/SD`. Both devices passed managed nested
directory creation, normal and zero-byte same-device remote-to-remote additions,
source preservation, independent destination verification, genuine backup and
missing-directory restore, stable Core epoch, zero remaining leases, reviewed
cleanup and independent absence verification.

Immediately after physical qualification, the focused R1 suite passed **20/20**,
the USB backup/restore regression suite passed **19/19**, and the FTP regression
family passed **186/186**. `git diff --check` was clean.

R1 is committed and pushed at
`d0e605ebdc29cca15558d7fb6c5bf2dcfc6690bc`.

R2 — Managed CLI Fresh-Folder Upload is implemented and physically qualified
on both C64 Ultimates as of 3 October 2026. The approved contract, implementation
boundary, deterministic evidence and physical acceptance record are in
[R2-MANAGED-CLI-FRESH-FOLDER.md](R2-MANAGED-CLI-FRESH-FOLDER.md).
Only production CLI put-new now uses saved bound profile authority and the
Core/FileService fresh-folder composite. Legacy read CLI, compatibility
upload_new_folder, Flash and AI routes remain unchanged. The opt-in nonempty
source descriptor guard preserves default 3C zero-byte support.

Final pre-physical deterministic verification passed **66 focused R2 methods**,
**276 affected regression methods**, and **17 offline Test Lab checks**. Normal
and optimized full suites each ran **1025 methods: 989 passed, 36 existing opt-in
display skips, zero failures**. No existing test was removed or renamed and
`git diff --check` passed.

Authorized physical qualification then passed independently on Beige `25EA78`
using `/USB2` and Founder's `25BE71` using `/SD` through the actual CLI put-new
path and saved identity-bound profiles. Independent readback verified the exact
byte counts and SHA-256 hashes, no staging artifacts remained, Core epochs stayed
stable, and active leases returned to zero. Reviewed cleanup removed exactly each
disposable acceptance tree and fresh-session listings independently verified
absence.

R2 is complete, committed and pushed at
`13bbc8a85d02cf75b1e58efde4e20b35d575e0df`. Pre-commit language in the R2
append-only design/acceptance record describes historical stages, not its
current status.

The post-R2 ownership assessment found four live raw-FTP consumer groups:
legacy CLI `ls`/`browse`/`get`, headless Test Lab `hardware.storage`, native Flash
writes, and AI installation/upgrade. CLI `info` remains an unmanaged REST read,
not a raw-FTP consumer. Their ownership is unchanged by R3.

**R3 — Compatibility Retirement is complete, committed and pushed.**
See [R3-COMPATIBILITY-RETIREMENT.md](R3-COMPATIBILITY-RETIREMENT.md) for the
approved contract, static audit and deterministic evidence. Removed
`transfers.upload_new_folder`, `_upload_new_folder`, `ConnectionDialog.credential`,
`file_copy.conflicts` and `CoreDeviceOperations.info`; renamed the Core resolver
to private `_credential_for` with unchanged signature/body and exactly four
internal callers. Only the explicitly commented saved-report diagnostic label
retains the old fresh-folder name in application source.

The four unreachable raw read fallbacks and folder-copy compatibility closure
remain deferred. The four live raw consumer groups listed above remain unchanged.
Physical qualification is not required because no live transfer workflow changed;
no C64U was contacted. R3 was committed and pushed as
`a081b01c4a62198b35b88199c4c8e48f9c535f90`; no package or release was created.

R3 deterministic acceptance: **162 focused methods** (including all 66 R2),
**257 FTP/USB regression methods**, and **17/17 offline checks** passed.
Normal and optimized suites each ran **1032 methods: 996 passed, 36 existing
opt-in display skips, zero failures/errors**. Three obsolete helper-only methods
were removed and ten added; useful assertions were re-homed or strengthened.
`git diff --check` passed. Earlier final-review/uncommitted wording in the R3
record describes historical stages, not current status.

## R4 — accepted, committed and pushed

The following qualification record preserves the pre-commit evidence; the
post-R4 authority above supersedes its former final-review stop.

[R4 — Managed C64 AI Installation](R4-MANAGED-C64-AI-INSTALL.md) now routes AI
file work through a single-use Core capability and the captured device's scheduler
lane. Exact-current verification uses full bytes at execution. Missing files use
3C; recognized same-config ai.1 uses 3D with full-byte predicates at both original
observations. Generic 3D defaults remain unchanged.

Private pending configuration precedes file work; publication, pairing, service
activation and health enablement require trustworthy file evidence and matching
configuration/session immediately before each new consequential command and the
active-config publication. File success and bridge failure remain separate, with
safe bridge command outcomes. Eligible retained pending configuration is reviewed
and reused before token generation; ambiguous/stale/context-mismatched candidates
stop safely. Every explicit re-entry has fresh Core binding/classification.
Successful verified commit consumes the private pending copy. Pre-submission
errors have safe phase categories and no private exception text/chains. Neither
remote rollback nor automatic replay is introduced. The accepted final-observation-to-rename external-writer window remains.

Corrected deterministic R4 evidence: 160 focused methods, 257 FTP/USB regressions,
normal and optimized suites each 1093 methods (1057 passed, 36 existing display
skips), and 17/17 offline checks. This pass adds 17 methods and renames two to
accurately describe session-field invalidation and mutation-before-reply
cancellation; no methods were retired and no skips added. Total additions since
R3 are 61. Historical implementation and review evidence remains in the R4
record, including failed iterations and exact commands. Static ownership/privacy
and whitespace checks pass, including untracked files.

`CoreDeviceOperations.open_ftp` is retained: automatic approval review rejected
its conditional removal because the production `transfers.connect` dynamic call
remains. AI has no raw/facade transport route. This leaves the conditional
retirement proof for review, without expanding into other consumers. Flash,
legacy CLI, headless Test Lab and broader ownership closure remain deferred.
Authorized controlled physical qualification passed on 4 October 2026: Beige
`25EA78` under `/USB2`, then Founder `25BE71` under `/SD`. Both passed actual Core
missing installation, exact-current no-op with zero mutation commands, synthetic
ai.1 upgrade with both authoritative full-byte matches, foreign/directory
refusals, independent byte/hash verification, stable session/epoch, zero leases,
exact reviewed cleanup and fresh absence verification. No staging/backup residue
remained. See the R4 physical record for exact roots, identities and hashes.
Only disposable files and synthetic private configuration were used; deployed
client, production bridge configuration, pairing/services/health and launch
were untouched. No commit, push, branch/worktree, package or release was performed.
The final review and subsequent R4 commit/push are complete (authority above).

## R5 — Core-owned headless reads: accepted, committed and pushed

[R5 implementation record](R5-CORE-OWNED-HEADLESS-READS.md) records the approved
saved-bound-profile CLI ls/get migration, retirement of browse, REST-only info,
and managed headless Test Lab storage. Core now supports optional initial browsing
without changing default GUI connection behavior. Identity establishes the session;
storage performs the first FTP read. Directly obsolete raw listing/download and
`Profile.client()` are retired; Flash and broader compatibility remain deferred.

Starting implementation RU baseline: **55% remaining**. Deterministic verification:
normal and optimized suites each **1,123 methods = 1,087 pass + 36 existing skips**;
104 focused tests, 120 affected regressions, and 17 Offline Test Lab checks passed.
R5 adds 30 methods to the R4 baseline, with no new skips. See the R5 record for
commands, corrected iterations, ownership proof and complete changed-file inventory.

**Read-only physically qualified on Beige and Founder on 4 October 2026;
subsequently accepted, committed and pushed at the authority above.** Actual bound-profile CLI ls/get
and all four headless hardware checks passed on both devices. Separate local
readbacks matched historical sizes/hashes (8,952 and 4 bytes), followed by local
cleanup. No initial FTP browse, stable per-run sessions, zero terminal leases
and successful shutdown were observed. No remote writes occurred; evidence is
send-boundary diagnostics, not packet capture. See the R5 physical record for
exact profiles, paths, hashes and observer limitations. The R5 document's older
final-review/unpublished wording records the pre-publication checkpoint; the
verified R5 authority above supersedes it. Flash and Network Foundation remain
incomplete.

## R6 — Managed Flash publication: published

[R6 design, historical stop and resumed evidence](R6-MANAGED-FLASH-PUBLICATION.md)
records the original approved design, the stopped partial implementation and the
explicitly authorized resumption at user-supplied RU baseline 41% remaining.
The original stop history is preserved: a 16-byte CRT slice was compared against
a 17-byte literal, rejecting every CRT. Review authorized only correction to the
exact 16-byte space-padded signature. All other Flash validation rules remain.
The independent directory-race fixture now models CWD plus argument-free MLSD.

Both source workflows now use private bounded immutable snapshots and one managed
Flash publisher, including optional known-directory MKD, exact-length STOR,
independent readback/hash/SIZE and destination recheck before managed rename.
Structured consequences survive job cancellation/failure and GUI rendering;
queued refusal releases consumed snapshot bytes. The raw Flash publisher is
retired. Shared/deferred compatibility and generic 3C behavior remain unchanged.

Deterministic verification passed: 56 focused methods; 274 affected regressions;
normal and optimized suites each 1,153 methods / 1,117 passed +36 existing skips;
Offline Test Lab 17 checks. Thirty added methods, none removed/renamed, no new
skips. R6 records the sandbox socket failures, original stopped iteration and
later obsolete raw-Flash ownership assertion correction, with passing reruns.
Ownership/policy, bounded privacy and tracked/untracked whitespace checks passed.

R6 is **physically qualified, accepted, committed and published** at
`f9457acd3bcef4269d9d98e95ef3c6dc33f90ff1`, parent R5
`dab627979b9d3bb085c955c6e3bea8cdaff8b338`, subject
`Implement R6 managed Flash publication`. The final-closure starting inspection
verified HEAD = local `origin/development`, divergence `0 0`, clean worktree.
The exact-path cleanup prerequisite added 18 tests after the 1,153-test run above:
published R6 contains 1,171 discovered test methods (1,135 plus 36 display skips).
Its focused/affected verification passed 293/293 tests. Older unpublished wording
in the R6 checkpoint record describes history, superseded by this authority.

Controlled physical qualification passed on 4 October 2026, Beige fully finished
before Founder. Saved bound Development profiles reported Beige `25EA78` at
`192.168.68.70` / firmware `1.1.0s2`, and Founder `25BE71` at `192.168.68.69` /
firmware `1.1.0`, both API `0.1`. Each used existing `/Flash/roms` and one unique
one-byte disposable `.bin`: actual FileService R6 publication, independent full
readback/hash, staging inspection, reviewed exact-path cleanup with one acknowledged
DELE, cleanup absence and fresh final absence all passed. Stable separate Core
sessions and zero terminal leases were verified. No fixture or staging remained.
Missing-directory MKD stayed deterministic-only; Founder's absent configs was not
created. No activation/application/reset/reboot/settings mutation occurred.

The R6 physical record contains exact paths, hashes, identities, sessions, managed
send/reply evidence and limitations (not packet capture; external-writer races
remain). Implementation/tests were preserved through publication.

## Final FTP ownership closure — implementation for final review

The final bounded compatibility deletion and fixture conversion is implemented
against published R6, with starting user-supplied RU baseline 32% remaining.
Supported live FTP has one owner: `C64UFtpLeaseManager` / `C64UFtpClient`, through
managed adapters and accepted primitives. Missing managed context refuses; raw
factories, remote alternatives, and raw-selecting switches are removed. Offline
fixtures remain explicit and cannot be selected as a production fallback.

[Closure evidence and complete inventory](FTP-OWNERSHIP-CLOSURE.md) records exact
commands, test accounting, corrected iterations and ownership checks. Verification:
125 closure/affected tests and 466 managed/R4/R5/R6 tests passed; normal and
optimized full suites each ran 1,177 tests (1,141 passed, 36 unchanged display
skips); Offline Test Lab passed 17/17 checks. Six methods added, none deleted,
four renamed. Syntax, ownership, whitespace and bounded privacy/secret scans pass.
No supported
managed wire sequencing or policy changed, so no new physical qualification was
needed or performed. This work remains uncommitted for compact final review.
FTP ownership closure does not complete all Network Foundation/product work:
Streams, Ultimate Menu and cartdumper remain separate roadmap features.
