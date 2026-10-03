# C64U Network Foundation — FTP Slices 1–3D

Status: **Slices 1–3C accepted and committed; 3D physically qualified, uncommitted, final review pending**.
Baseline: released Stable 1.9 `3acb9be310560f69df5a80619e192585a7e87155`.

## Boundary and ownership

`c64u_ftp_types.py` contains immutable device, Core binding, FTP-session,
capability, policy, listing and transfer contracts. `c64u_ftp.py` owns the wire
protocol. Neither imports GTK, `UltimateClient`, nor `ftplib`.

Core supplies a `C64UFtpLeaseManager` with a current-binding provider and a
private password provider. Providers are not exposed through the client. Obtain
a client only through `manager.lease(binding, presentation=..., cancelled=...)`.
A manager permits one operation-scoped lease per physical device. A second
acquisition fails promptly with `lease-busy`; it never waits behind itself.
Nested helpers must pass the existing lease. There is no idle pool, automatic
reconnection, automatic retry, or mutation replay. Core shares one manager across migrated read and standalone mutation routes; independent processes/other applications
cannot be counted by an in-process manager. The firmware's four-session ceiling
is not a parallelism target.

Core session and FTP session IDs are distinct. Opening another FTP connection
never changes the supplied Core session ID. The current binding is checked
before commands and between transfer blocks. Explicit invalidation closes live
sockets; recovery state blocks new leases until the recovery owner clears it.
This slice does not implement REST readiness or automatic recovery.

Lifecycle: disconnected → connecting → authenticating → negotiating → ready ↔
transferring; failure/invalidation prevents reuse. Lease exit closes sockets.
An incomplete reply, cancellation, parser failure or uncertain completion
poisons the lease. There is no ABOR/QUIT dependency on an unsynchronized stream.

## Wire contract

* IPv4 only, including IPv4 hostname resolution. IPv6 literals are rejected;
  IPv6-only DNS results fail rather than selecting EPSV.
* Fresh FILES mode uses `USER anonymous`, DIRECTORIES uses `USER dirs`, BOTH
  uses `USER both`. The latter modes are wire-tested only, not physically
  qualified or enabled in application behavior. Each mode uses a fresh session.
* The Network Password is UTF-8 encoded literally: empty, `-`, and surrounding
  spaces are preserved. C0/DEL and unencodable values are rejected before a
  socket is opened. No anonymous-password substitution or ACCT fallback occurs.
* FEAT is issued once after authentication. Multiline replies have independent
  line, byte and line-count bounds. Unsupported FEAT leaves other commands
  unknown. Advertisement is not successful verification.
* TYPE I is explicit at negotiation and before listing/data/SIZE operations.
  Listing bytes use the same binary data path, never a helper that sends TYPE A.
* Classic PASV only. Data connects to the verified control socket's IPv4 peer;
  the advertised third-party IP is not trusted. No EPSV, EPRT, PORT, REST, APPE,
  MDTM, TLS or NLST dependency.
* Timeouts are separate: control connect/reply 10 seconds, data connect 4
  seconds, data idle 10 seconds, terminal completion 10 seconds. These are
  constructor-configurable. The data-connect budget fits inside the nominal
  firmware window; it is not a whole-transfer deadline or performance promise.
  DNS and caller-provided local streams are synchronous; caller resources must
  be prepared before transfer. Cancellation during a blocking socket operation
  is bounded by its timeout, or explicit manager invalidation.

## Client operations

* `list_directory(path: bytes, limits=...) -> ListingResult`: CWD/PWD followed
  by MLSD (or controlled LIST). Result includes **actual raw PWD path**, entries,
  dialect and wire byte count. The owning service must compare actual path to
  the reviewed location using its existing policy; the transport does not
  invent physical-volume identity.
* `size(path: bytes) -> int`: explicit unsupported/unavailable result; never
  invents a size or substitutes a listing's value silently.
* `read_into(path, sink, max_bytes=..., expected_bytes=..., progress=...)`:
  prepared binary sink, hard byte bound and optional exact length check.
* `write_from(path, source, expected_bytes=..., progress=...)`: prepared binary
  source and exact length bound. **Not a staged/no-overwrite upload API.** Only
  authorized Core orchestration uses this primitive; approved 3C additions are
  the first migrated production consumers.
* Transfer results contain count, SHA-256 of transferred bytes, terminal reply
  code and outcome. A successful STOR is not independent readback verification.
  Existing higher layers retain staging, readback, SIZE, conflict review,
  replacement, deletion and partial-ownership policy. Slice 3B adds the mutation
  primitives described below; the 3C section records the bounded STOR migration.

Completion requires data closure and terminal 226/250. Data callbacks alone are
not success. No further cancellation check relabels a terminally accepted
transfer. Errors carry category, phase, FTP code where available, transferred
count, availability retryability and outcome certainty. Retryability never
permits replay of an uncertain mutation. A known C64U “too many FTP connections”
421 is distinguished from generic service-unavailable 421. No peer prose is
included in public errors.

## Listings and capabilities

MLSD facts are parsed separately from exact filename octets. Type, nonnegative
size and modification timestamp are validated; unknown well-formed facts are
retained. cdir/pdir count toward bounds but are not returned as children. Missing
size remains `None`. Unknown types, duplicate identities/facts and ambiguous
records fail closed. Display decoding uses escaped invalid octets and is never
used to reconstruct identity. Entries sort by raw name bytes.

Defaults: 4,096 bytes per record, 8 MiB aggregate listing bytes, 100,000 records.
All are injectable; these are protocol safety bounds, not new GUI preferences
or replacements for existing traversal limits.

MLSD→LIST is allowed only on an initial 500/502/504 rejection or an explicitly
supplied known-broken-MLSD profile. The fallback accepts only the supported Unix
LIST dialect. No fallback occurs after data, malformed facts, truncation, bounds,
530/550, disconnect or timeout. Partial listings never escape or merge. Raw
non-UTF-8 names survive both dialects. Physical container semantics, exact
firmware profiles and default presentation changes remain future work.

Capabilities distinguish unknown, advertised, verified, unsupported and broken.
They retain binding-supplied firmware/product/API evidence, FEAT features,
MLSD/MLST, SIZE, PASV, selected presentation and listing dialect. This slice does
not independently probe REST identity or claim universal firmware compatibility.

## Diagnostics and tests

An optional sink receives structured events with timestamps, session correlation,
lifecycle, command **verb only** (PASS omitted), capability/fallback decisions,
counts, phase, duration and outcome. Paths, payloads, password values, tokens and
unrestricted peer replies are never emitted. A failing diagnostic sink cannot
interrupt or resend a command.

`tests/c64u_ftp_server.py` is a loopback-only control/data socket fixture. It
records synthetic command arguments privately for assertions and supports split
and coalesced replies, errors, data delays and lost/failing completion. The data
connect timeout test injects that specific socket failure while retaining real
control/PASV traffic: OS-dependent network blackholes are not deterministic tests.

No real device operations are part of these tests. Architecture tests permit
protocol imports only in Core and the transitional read adapter; GTK and feature
clients receive no new transport access.

## Slice 2 migration and removal boundary

Baseline: `44dc2045995b9bf96df98c6e557bd8f97d7867c3`.
`ftp_reads.py` translates byte listings into existing `Entry`/`IdentityEntry`
results and bounded reads into bytes. Core privately attaches it to its verified
`UltimateClient`; the existing Core device facade delegates without publishing
a lease. Presentation remains anonymous/FILES, directories first then casefolded
names. Existing entries expose no timestamp field. Identity remains raw octets;
ordinary display preserves the selected strict encoding (including the existing
latin-1 opt-in). An invalid UTF-8 display name is not silently replaced.

Core reserves its connection UUID after REST/profile identity checks and commits
that same UUID after initial browsing. Reconnect changes the UUID; health checks
and fresh FTP leases do not. The FTP layer does not prove physical identity;
Core's existing profile fallback remains explicitly unverified if REST supplies
no physical identifier. Disconnect invalidates live migrated leases.

Each read uses one lease for SIZE → bounded RETR → terminal completion → SIZE.
Existing native-file, SID and Game Library size limits remain in their owning
services (including the separate 64 MiB CRT entry point). Disk-image acquisition
uses the same adapter before the unchanged DMA submission. Full-volume
fingerprinting wraps its entire existing traversal in one read operation;
path/PWD comparisons, raw length-delimited digest, bounds, cancellation and
before/after safety policies remain unchanged. SID still validates exact content
and submits attached bytes; Game Launch and USB retain full-volume protection.

Nested read helpers reuse the operation context. Independent reads serialize
at the adapter boundary; there is no idle pool and no lease across a review
or user think-time. Core jobs supply cancellation through a scoped context,
reset on job completion. Failures release/poison the lease. An explicit caller
fallback after a rejected preferred folder opens a fresh lease; the adapter does
not replay a failed operation. Streaming cancellation remains bounded by the
transport timeout while a socket is blocked.

Structured transport errors become existing `ConnectionFailure`/`BrowserError`
contracts, with sanitized `ftp_code`, reply code and phase retained internally.
Authentication, session change, network/timeout, malformed/incomplete listing,
size and completion errors remain distinguishable. FTP 550 is **missing or
inaccessible**, not proof of absence. Existing catalog services may retain their
coarser unavailable-state presentation. No malformed listing becomes an empty
successful directory. Strict unsupported/ambiguous MLSD records fail closed;
only explicit command-unsupported responses permit LIST fallback.

Latest immutable capability evidence is retained privately on the adapter and
safe structured transport events enter the existing diagnostic context/job ID.
FEAT occurs once per fresh lease; advertised MLSD is distinct from verified
MLSD, SIZE and PASV. No capability UI is added.

### Legacy consumers retained at the Slice 2 checkpoint

The following records the Slice 2 boundary; the 3A changes below supersede its
streaming-download and USB hashing entries for Core-bound clients.

- `transfers.py`: streaming download plus upload/readback, staging and cleanup.
- `replacement.py`: replacement/readback and its original-content protection.
- `native_files.py`: Flash write/readback; bounded-read fallback for unbound clients.
- `disk_run.py`: unbound compatibility-client read fallback; DMA is unchanged.
- `usb_backup.py`: backup streaming downloads and restore/source readback hashing;
  only identity enumeration/full-volume fingerprints migrate here.
- `api.py`: unbound `UltimateClient` listing implementations for the existing CLI,
  direct profile clients and test doubles, which do not own a verified Core epoch.
- `CoreDeviceOperations.open_ftp`: existing legacy helper used by these operations;
  no additional public raw escape route was introduced.

Remove the adapter and legacy read fallback when those direct clients enter the
Core identity/session boundary and remaining transfer/mutation workflows migrate
together with their staging/readback/ownership rules. Do not delete legacy code
before that contract migration. Slice 3 should address that boundary explicitly,
not simply swap STOR into existing mutation helpers.

## Reproducible performance evidence

Run `python3 -B tests/benchmark_ftp_reads.py --repeats 5` (loopback only).
Measured on Debian 13, Python 3.13.5, Linux 6.12.107+deb13-amd64.
Five alternating old/new trials; medians below. Identical synthetic trees, exact
same digest algorithm, four 513-byte bounded file reads per workload. Every
old/new digest and downloaded byte buffer matched. Timing is not a physical
C64U performance guarantee. Fixture control sockets use TCP_NODELAY equally on
both paths to avoid a synthetic delayed-ACK artifact.

| Workload (files / directories) | Fingerprint old → new ms | Change | Total old → new ms | Total change | Connections old → new (fingerprint only) |
|---|---:|---:|---:|---:|---:|
| many-small-files (1600 / 17) | 23.41 → 25.27 | +7.9% | 27.74 → 32.61 | +17.5% | 21 → 5 (17 → 1) |
| nested-directories (72 / 25) | 26.01 → 14.23 | -45.3% | 29.42 → 20.84 | -29.1% | 29 → 5 (25 → 1) |
| mixed-game-sid (384 / 33) | 35.39 → 20.53 | -42.0% | 38.64 → 27.28 | -29.4% | 37 → 5 (33 → 1) |
| non-utf8-identities (128 / 9) | 11.11 → 7.44 | -33.1% | 14.41 → 13.75 | -4.6% | 13 → 5 (9 → 1) |

Negative percentages mean faster. Authentications equal total connections in
both implementations. Legacy FEAT count is zero; Slice 2 is five per workload
(one fingerprint plus four independent reads). Each side performs eight SIZE
commands and four RETRs. Listings and wire byte counts are unchanged:

| Workload | Listings | Bytes transferred |
|---|---:|---:|
| many-small-files | 17 | 56756 |
| nested-directories | 25 | 4956 |
| mixed-game-sid | 33 | 15716 |
| non-utf8-identities | 9 | 7452 |

Many-small-files fingerprinting regressed about 8% (1.86 ms) on localhost;
strict fact parsing, bounds/binding checks and negotiation add work. Nested/mixed
fixtures benefit more from eliminating handshakes. Four independent reads take
about 5.5–6.2 ms versus 3.8–4.4 ms median on this fixture, including fresh FEAT and
protocol validation. These are aggregate observations, not a profiler attribution.
The repeatable structural improvement is fingerprint connections: 17/25/33/9 → 1.
Hardware timing is still needed; no latency simulation was used to inflate gains.

## Proposed read-only physical acceptance (not executed)

Repeat on beige `192.168.68.70`, firmware `1.1.0s2`, then Founder's Edition using
its configured profile/current firmware. Use an isolated Development state and
existing files only; do not upload, launch/play, rename, delete or restore.

1. Record physical identity, firmware, profile and Core session. Browse root,
   USB/SD roots and several nested folders; compare names/types/sizes and current
   directory with the accepted baseline. Keep FILES presentation unchanged.
2. Capture internal capability/diagnostic evidence: one FEAT per fresh lease,
   MLSD advertised versus verified, PASV and SIZE; record any controlled fallback.
3. Perform full-volume identity scans on unchanged media, including the existing
   Schatzj\x84ger paths where present. Repeated digests must agree; record counts,
   elapsed time and one control authentication per complete scan. Compare with
   the baseline against the same unchanged tree, three alternating trials.
4. Validate existing Game Library D64/CRT and SID records without launching them.
   Check content identity/metadata; review preparation may fingerprint but must
   not execute a launch. Verify one SIZE/RETR/SIZE lease per bounded read and
   current native/CRT/SID limits. Cancel a scan/read and confirm release.
5. Disconnect/reconnect manually; old plans/bindings must be rejected, the new
   epoch must work, and folder browsing alone must not change the Core epoch.
6. Record operation counts and timings separately for both devices. Unexpected
   listing format, PWD, timeout or validation errors stop acceptance for diagnosis;
   do not weaken completeness checks or retry consequential work.

Physical acceptance and any mutation migration require separate approval.

## Slice 2 automated verification

Baseline: 761 tests in each complete normal/optimized suite, 36 opt-in display
skips. Slice 2: **779 tests in each suite, 36 identical display skips, no
failures**. Focused protocol/adapter run: **66 passed** (48 protocol, 18 production
integration). Additional transfer/Core/session/scheduler/recovery/USB/Game
Library/Bulk Import/launch/SID/disk/native/hardware-check/cleanup group: **211
passed**. Compilation and AST checks passed for 212 Python files; whitespace
validation passed. Hardware-check tests use test doubles, not real hardware.
No physical device, packaging, commit or publication operation was performed.

## Slice 2 physical acceptance — PASS (27 September 2026)

Bruce accepted both devices using Development `1.10-network-slice2.1+ac.2`,
SHA-256 `c60f9777ff7d7f0ebcb266ebf4b3f72e7127bd3b1c3b1d413d86e2afbe2811ab`.
The candidate contains the reviewed uncommitted Slice 2 implementation and the
approved channel-aware package credential self-test correction. Credential
implementations were not changed. ac.1 remains preserved failed qualification
evidence (`ded16a0ec325ccc0a324fe8bdaff2855232afbe3664eaf980e2cdb3f32632551`);
it is not retroactively accepted.

### Beige primary device

- Address `192.168.68.70`; C64 Ultimate; physical ID `25EA78`;
  firmware `1.1.0s2`; API `0.1`.
- ac.2 GUI browsing, FEAT, MLSD, PASV, root/PWD semantics and USB1/USB2 browsing
  passed. No LIST fallback.
- Repeated full USB1 fingerprints agreed:
  `40922faa550ffb0beab47992263af1167d015db10512cbfd5a5bae1792b899f5`.
  Each scan used 34 directory listings, one FTP control connection,
  one authentication and one FEAT negotiation. Elapsed times were approximately
  10.992 s and 10.943 s. These are absolute physical measurements, not a claimed
  speedup over Stable; no comparable Stable timing is recorded here.
- SIZE, RETR, SID catalog validation and repeated 8,952-byte bounded reads passed.
- Cancellation after five directory listings, fresh reconnect and subsequent
  root browse passed.

### Founder's Edition secondary compatibility device

- Address `192.168.68.69`; C64 Ultimate; physical ID `25BE71`;
  firmware `1.1.0`; API `0.1`.
- FEAT, MLSD, PASV, root/USB1/SD browsing and `/SD/test.txt` listing passed.
- SIZE and RETR verified; repeated SIZE → RETR → SIZE produced exact four-byte
  bounded reads. No fallback or FTP compatibility quirk was observed.
- Relevant observed protocol behavior was equivalent to the beige device.
  Different firmware strings alone do not establish different FTP implementations.
  No firmware change or obsolete-firmware testing was required.

### External probe correction and existing root behavior

The initial external probe incorrectly assumed `core.connect(remote_folder='/')`
would remain at root. Existing `storage.initial_directory()` instead discovers
storage roots and chooses the first when the preferred folder is not one of
those roots. A root listing can advertise an unavailable storage entry, whose
subsequent CWD receives 550. This was an acceptance-probe startup defect, not a
Slice 2 root/PWD or MLSD failure. The corrected external probe explicitly used
known-accessible `/USB2` for beige connection/reconnect, then independently
performed the requested browse. Eight synthetic probe regressions passed.
The corrected probe was used for accepted physical evidence. It remains outside
Argonaut source. Production initial-folder behavior was not changed.

### Final automated verification scope

The approved credential correction adds 12 regressions to the 779-test Slice 2
suite: complete normal and optimized suites now contain 791 tests, with the
same 36 opt-in display skips. Focused FTP protocol/adapter/credential coverage
contains 78 tests (48 protocol, 18 adapter, 12 credential). Candidate package
self-tests previously passed 45/45 in both modes. Final pre-commit rerun results
are retained with the external qualification evidence.

Acceptance was read-only. This record does not authorize mutation migration,
Slice 3, new package builds or further device operations.


## Slice 3A — shared operation lifetime and streaming reads

Implementation baseline: `4f7a86745239e60b3c6f4e2287d94af8b3c00508`.
Slice 3A was physically accepted, committed and pushed to `development` as
`0f5b77f88f4fac6bddac0fa5e3cc2f5929ab544a`. Authorized physical checks are
recorded below. This section records the 3A boundary; 3B changes follow it.

`ftp_reads.py` separates the private `_FtpOperations` lifetime from
`FtpReadAdapter` read behavior. Existing Core attachment and identity/epoch
ownership are unchanged. The lifetime owns a lazy lease, nested checks and
failure evidence; nested listings, bounded reads and streams reuse it.
Outermost exit closes the lease without a new cancellation check. Independent
read contexts retain serialization. Binding/recovery validation is separate
from cooperative cancellation and cannot be masked by a pending cancellation.
No mutation-specific result types or cancellation-deferral mechanism is added.

A failed lease (including failed acquisition) stays failed within its operation.
There is no automatic reopening in the client accessor. Only the existing
caller-selected preferred-directory fallback explicitly ends the failed read
attempt before choosing its fallback directory. New independent operations can
acquire fresh leases; none replays failed work automatically.

Translated errors retain the original sanitized `FtpOperationError`, outcome,
transferred count, phase, reply code and availability retryability. Restored
caller/cancellation exceptions also retain transport evidence where a transport
failure occurred. No raw FTP object or lease is returned by a read operation.

### Streaming contracts

For a Core-bound client, `transfers.download()` uses a prepared local staging
sink and the adapter's exact SIZE → RETR → SIZE stream. Received bytes are hashed
by the transport. Flush/fsync runs after RETR and before the final SIZE check;
publication still refuses an existing or concurrently created destination.
Failure/cancellation removes only the local staging file. Zero-byte streams are
supported without changing the nonempty bounded native-file read contract.

Overlong streams are now rejected at the reported SIZE bound, before excess
bytes enter the sink, rather than after downloading the entire stream. Short
reads, unavailable/changing SIZE and missing terminal completion never publish.
This is transfer validation, not a new source-snapshot guarantee. The local
staging file is prepared before FTP acquisition and is removed on early errors.

`UsbBackupService._remote_hash()` uses the same exact streaming operation with a
discard sink and the transport's received-byte digest. Backup execution encloses
each file's listing, download, local hash and separate remote verification read
in one operation. Preview still reads the source once, execution still reads it
twice, and all digests must agree. No observation is replaced with a cached hash.
Preview/execution, independent files and full-volume fingerprint traversals keep
separate operation boundaries; each fingerprint still uses one lease.

### Retained boundary

STOR/upload, replacement's original-content protection/exchange, Flash uploads,
rename/MKD/DELE/RMD, partial-upload cleanup policy, the raw compatibility helper
and unbound-client fallbacks are unchanged. Composite callers can benefit from
the migrated download helper without migrating their mutation behavior. No
physical devices were accessed during implementation/deterministic testing.
The separately authorized physical pass is recorded below.

### Deterministic verification

`tests/test_ftp_streaming.py` adds 15 socket-fixture/integration regressions for
nested reuse and authentication/FEAT counts; lazy acquisition and release;
failed-lease/acquisition non-reopening; exact/empty streams and terminal errors;
staging, fsync and destination protection; cancellation isolation and late exit;
stale binding and structured failure evidence; and independent USB observations.
Existing preferred-folder fallback, bounded-read, fingerprint, protocol and
legacy mutation tests remain in place.

Focused protocol/adapter/streaming/transfer/cancellation/USB/file-service/
diagnostics run: **139 tests passed**. Complete normal and optimized suites:
**806 tests each, 36 opt-in display skips each, no failures**. This is the
accepted 791-test baseline plus 15 new tests, with no removals or skip changes.
Socket tests required permission to create loopback sockets in the execution
sandbox; the first restricted attempt could not create sockets and was rerun
successfully with that permission. `git diff --check` passed.


## Slice 3A physical acceptance — PASS (27 September 2026)

Executed against the reviewed, uncommitted source at base
`4f7a86745239e60b3c6f4e2287d94af8b3c00508`. No production code or tests changed
in this pass. Only this document and CURRENT-STATE.md were updated afterward.
Final human review subsequently accepted 3A, which was committed and pushed as
`0f5b77f88f4fac6bddac0fa5e3cc2f5929ab544a`. These physical results qualify
3A only; they do not constitute physical acceptance of later checkpoints.

The external probe used isolated Development Core state, identity-bound profiles,
and existing empty-password configuration. No saved user configuration changed.
Core REST identity checks preceded FTP reads; distinct IDs were required.
No STOR, RNFR, RNTO, MKD, DELE, RMD or APPE was issued. No active transfer was
interrupted and no destructive fault was induced. No FTP error or LIST fallback
was observed.

| Device | Address / physical ID | Firmware / API | Existing source | Bytes |
|---|---|---|---|---:|
| Beige C64 Ultimate | `192.168.68.70` / `25EA78` | `1.1.0s2` / `0.1` | `/USB1/sid/arcademem.sid` | 8,952 |
| Founder's Edition C64 Ultimate | `192.168.68.69` / `25BE71` | `1.1.0` / `0.1` | `/SD/test.txt` | 4 |

SHA-256 values agreed across the ordinary local download, nested repeat download,
independent remote hash, backup manifest/local payload, and post-reconnect read.
They also match the previously recorded Slice 2 content evidence:

- Beige: `a4e2341064d1ef072ddc9d20c2131eb42fdc15027c4330bd9f87c3c0e0d8bb84`
- Founder's: `9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08`

### Operations and connection evidence

On each device:

1. FileService copy preview and execution downloaded the existing file to a new
   Core-host directory. Published bytes and hashes matched; no `.c64u-*` staging
   artifact remained. The transfer's observed wire sequence was SIZE/RETR/SIZE.
2. A scheduled Core read operation enclosed a listing, streaming download and
   independent USB hash. Exactly one FTP session, one USER/authentication and
   one FEAT covered both SIZE/RETR/SIZE sequences (two RETRs, four SIZEs).
3. UsbBackupService preview read the selected file once; execution downloaded
   it and performed a separate remote verification read. Existing local reread
   and hash comparison completed. Manifest state was `complete`, with one file,
   correct size/hash, no unfinished entries and matching independently reread
   local payload. Preview and execution were separate jobs/lease lifetimes.
4. An idle `core.reconnect()` preserved physical identity and changed the Core
   epoch. The previous adapter was rejected as stale without a wire event. A
   subsequent nested download/hash succeeded with the same bytes and digest.

Every measured operation ended with zero active managed leases, including
before Core shutdown. Epochs remained unchanged during ordinary reads. Each
FTP session negotiated FEAT once; there was no nested self-contention.

| Measurement | Beige | Founder's |
|---|---:|---:|
| Ordinary copy execution sessions | 2 | 2 |
| Nested listing + download + independent hash sessions | 1 | 1 |
| Backup preview RETRs / SIZEs | 1 / 2 | 1 / 2 |
| Backup execution RETRs / SIZEs | 2 / 4 | 2 / 4 |
| Backup preview total sessions | 4 | 3 |
| Backup execution total sessions | 3 | 2 |
| Per-file backup execution session (listing + two reads) | 1 | 1 |
| Post-reconnect nested download/hash sessions | 1 | 1 |

Ordinary copy execution keeps its existing separate preflight-listing and
streaming-transfer boundaries; two sessions do not mean two transfer leases.
Backup totals include separate volume fingerprint/enumeration work. Beige also
has the selected file's `sid` ancestor directory. Neither entire copy jobs nor
entire backup jobs are claimed to use one session.

The current beige volume fingerprint used 35 listings per traversal and was
`29e6bcc6674a42651a5aa1bf2fe8609a22b085c961c156504d0c327a6735b243`.
Founder's SD fingerprint was
`4ed3be35d76a8a1fa7c34326fbc4d7c47c9c002e55bce8b1bcf94bee3f020c4b`.
Preparation/execution comparisons passed. The beige tree differs from the
historical Slice 2 34-listing tree; no unchanged-tree performance comparison
is claimed.

### Limits and retained evidence

- No zero-byte file was present in the inspected source directories (`/USB1/sid`
  and `/SD`). No empty file was created; physical zero-byte coverage remains
  unexercised, with deterministic coverage retained.
- These were small known files and selected-file backups, not large-file or
  whole-volume payload backup qualification.
- FTP diagnostics establish SIZE/RETR/SIZE ordering and session reuse. They do
  not independently trace local flush/fsync calls. Those calls ran through the
  unchanged reviewed download path; ordering is established by code review and
  deterministic tests, with successful publication observed physically.
- Reconnect was performed between completed operations, not during transfer.
- This was headless Core source acceptance, not a new package or GUI qualification.

External evidence is retained beside the repository in
`argonaut-qualification/network-slice3a-physical/`: the probe, source SHA-256
manifest, reviewed diff, console logs, downloaded files, complete backup
manifests and per-session diagnostic events. Device reports are
`beige-20260927-102522/report.json` and
`founder-20260927-102608/report.json`.


## Slice 3B — managed mutations and directory operations

Status: **physically accepted, committed and pushed** as
`fd0e205deece43865293d2a61d64bdc3834b3c05`.
Base: `0f5b77f88f4fac6bddac0fa5e3cc2f5929ab544a` (accepted Slice 3A).
No physical devices were accessed during implementation/deterministic testing.
The separately authorized physical pass is recorded below.

### Explicit migration boundary

The existing private operation owner in `ftp_reads.py` now also dispatches
managed mutations. There is no second mutation lease manager or transaction
framework. Core binding, lazy acquisition, nested reuse, outermost release,
and no cancellation check on context exit remain unchanged. Diagnostics use
neutral `transport` naming instead of `read-transport`.

`files.operate_managed` shares validation with the existing operation helper,
but is entered explicitly by standalone FileService folder creation, reviewed
remote deletion, and the new scheduled `FileService.rename`. Remote GTK rename
submits that Core job; local GIO rename is unchanged. Core returns structured
mutation results on failure/partial completion and preserves the existing
successful folder-creation FileLocation result.

The legacy `files.operate` route remains for folder-copy and replacement
staging MKD. Fresh-folder upload MKD, staged-upload publication rename,
replacement exchange/cleanup, Flash MKD/publication, STOR, and unbound clients
are not migrated. A managed failure never falls back to raw FTP. Existing
compatibility FTP facilities remain available to those deferred consumers.

### Certainty and serialization

Immutable internal `MutationEvidence` records operation, stage, whether the
current command's send was attempted, whether the consequential command's send
was attempted, actual reply code, sanitized error category, and acknowledged
prior command/reply pairs. Core-facing results carry ordinary data only.
Submission is marked immediately before sendall: neither a failed send nor a
successful send proves the server's resulting filesystem state.

- NOT_STARTED: no consequential submission attempted. Lost RNFR replies retain
  RNFR submission evidence while RNTO remains unsubmitted.
- UNKNOWN: consequential submission attempted without definitive completion or
  refusal. Do not report the target as definitely changed/removed.
- COMPLETED: successful terminal reply received.
- REJECTED: explicit negative reply received. FTP 550 does not prove absence.

Failures poison the lease, including refusals. No outcome automatically retries
or replays a mutation. FileService mutation failures are nonretryable; transport
availability metadata is not permission to repeat a command. The explicit read
fallback cannot reset an operation that has entered mutation dispatch.

Reply compatibility preserves legacy acceptance: RNFR accepts 3xx, RNTO/MKD/RMD
accept 2xx, and DELE accepts 200/250. Canonical expected replies remain
350/250/257/250/250 respectively. Actual codes are retained. Peer prose and
server-returned MKD paths are not exposed or used to infer filesystem identity.

RNFR and RNTO run under one transport lock. After a final cooperative check,
cancellation is deferred through both commands; no unrelated command interleaves.
RNFR refusal/lost reply prevents RNTO. RNTO refusal or uncertain completion stops
without rollback/replay. MKD/DELE/RMD likewise resolve their reply despite a newly
pending cooperative cancellation. Network timeouts, binding invalidation and
recovery failures remain effective during every protected section.

### Caller contracts and results

Ordinary rename retains same-parent USB/SD policy, exact source/type validation,
case-insensitive collision refusal and same-name no-op. It adds no post-rename
verification. Case-only rename retains the checked unique temporary name and
both rename steps under one lease. Cooperative cancellation is deferred across
both pairs, then restored before the existing exact-name listing check.

A case-only result records completed primitive evidence, temporary/destination
paths, stopped primitive evidence if present, and verification as not-required,
unperformed, failed or passed. If cancellation stops verification after both
renames, the cancelled job retains both acknowledged steps; it does not claim
nothing changed. The verification still checks only requested-name presence.
No automatic rollback or cleanup is introduced.

Reviewed deletion retains consumed/expiring/session-bound plans, exact-path
confirmation, root protection, traversal bounds, complete re-enumeration,
metadata snapshots, per-item/parent revalidation, child-before-parent ordering,
empty-folder checking, and stop-on-failure. Preview gets a separate operation;
execution reuses one lease for revalidation and all deletion primitives.
`DeleteResult` additively records stopped_target, mutation evidence, and
not_attempted paths. Only acknowledged deletions enter removed. Typed cancellation
replaces English-message matching on the managed remote path. Reviewed deletion
of a Core-observed partial upload keeps the existing session/ownership policy.

FTP cannot make preflight checks atomic against external writers. Remote deletion
snapshots still compare type/size rather than content identity. Ordinary rename
and MKD remain acknowledgement-based. No stronger stability guarantee is claimed.

### Deterministic verification

`test_ftp_mutations.py` adds 38 tests covering reply refusals/loss, send failure,
timeout/malformed completion, RNFR/RNTO ordering, cancellation deferral, binding
and recovery invalidation, case-only partial results/verification, deletion
ordering and uncertainty, lease reuse/release, session binding, sanitized results
and diagnostics, GUI scheduling, local GIO routing, and deferred-caller routing.
The socket fixture models mutations independently of terminal-reply delivery.
The existing USB restore in-memory test was adapted only at its reviewed managed
cleanup boundary; a new socket integration test covers session-bound partial
cleanup. Existing read, upload, replacement and Flash tests remain in place.

Focused run: **218 tests passed**. Complete normal and optimized suites each
ran **844 tests, 36 opt-in display skips, no failures** (12.019 s normal;
13.259 s optimized). This is the accepted 806-test baseline plus 38 new tests.
No tests were removed and skip policy is unchanged. `git diff --check` passed.
The initial sandbox attempt could not create loopback sockets; subsequent runs
used loopback-socket permission. No device qualification is implied.

The approved GUI session-guard correction captures the submitted job's device
and session IDs and intended folder. It guards completion, asynchronous refresh
start, and result/error application even when the compatibility facade is
unchanged. Five added GUI regressions exercise delayed callbacks, normal
completion, changed sessions/folders, and stale errors. Local GIO is unchanged.
Final deterministic results after this correction: **7 GUI/routing tests passed;
223 focused tests passed; normal and optimized suites each ran 849 tests with
36 skips and no failures** (11.383 s / 12.869 s). This supersedes the earlier
844-test run: five tests added, no removals or skip changes.


## Slice 3B physical qualification — PASS (27 September 2026)

Authorized checks ran against the reviewed uncommitted 3B source, including the
GUI session-guard correction, at base
`0f5b77f88f4fac6bddac0fa5e3cc2f5929ab544a`. Production/test source SHA-256 values
were unchanged throughout qualification. Only development documentation changed
afterward. Final human review accepted 3B, which was committed and pushed as
`fd0e205deece43865293d2a61d64bdc3834b3c05`. Later checkpoint status is recorded
separately below.

### Devices and disposable data

REST identity was verified before mutations in each Core/GUI/cleanup phase.
Both devices used their existing empty Network Password configuration. Isolated
Development Core/GUI preferences were stored with external qualification data;
saved user profiles and credentials were not changed.

| Device | Address / physical ID | Reported firmware / API | Disposable parent |
|---|---|---|---|
| Beige C64 Ultimate | `192.168.68.70` / `25EA78` | `1.1.0s2` / `0.1` | `/USB2` |
| Founder's C64 Ultimate | `192.168.68.69` / `25BE71` | `1.1.0` / `0.1` | `/SD` |

Exact disposable trees, both verified absent after reviewed cleanup:

- Beige: `/USB2/argonaut-3b-accept-744e223ec6c744c1955e53f132ccc23c`
- Founder's: `/SD/argonaut-3b-accept-c8d84ea3525e449ebf10e76768126f80`

The unique name was checked absent before managed creation. All subsequent
qualification mutations were confined to the recorded tree. Before destructive
steps, the target was checked against that tree and the phase's Core binding.

Each tree contained a new 53-byte disposable text file and one empty directory.
The local payload was `Argonaut Slice 3B disposable acceptance data.` followed by
LF, the device's six-character physical ID, and LF. Existing staged upload was
used only for setup, not as STOR/3C qualification.

SHA-256 agreed with received-byte hashes and independently read local download
bytes after ordinary rename, case-only rename and the GUI rename:

- Beige: `096e72c32e8cf435740c422c471b5a533102dcf84201b38285efe51743b23e70`
- Founder's: `dde7426ec2f40e94ebb901480011a88609d1b2780e960e32b43def4b66fd2f7a`

### Mutation and reviewed-deletion results

Both devices passed the same sequence:

1. Managed standalone creation of the acceptance directory and `EmptyOne` child:
   correct FileLocation, MKD 257 acknowledgement evidence and resulting listings.
2. Scheduled ordinary file rename `sample.txt` → `Renamed.txt`, and directory
   rename `EmptyOne` → `EmptyTwo`: completed results and correct listings.
3. Case-only file rename `Renamed.txt` → `renamed.txt`, and directory rename
   `EmptyTwo` → `emptytwo`: two completed rename primitives, exact-case
   verification passed, and no temporary rename name remained in the listing.
4. Actual GTK rename `renamed.txt` → `GuiChecked.txt`: one completed Core rename
   job, correct resulting filename and successful post-operation refresh.
5. Separate reviewed deletion of `GuiChecked.txt`, then the verified-empty
   `emptytwo` directory, then the verified-empty acceptance directory. Every
   preview contained exactly the intended single target/type. Every execution
   recorded that target in removed, with empty failure/unattempted fields.
   Subsequent listings confirmed absence. Cleanup never bypassed review.

All RNFR acknowledgements were 350 and RNTO acknowledgements 250. DELE and RMD
returned 250. There were no unknown/refused mutation results, unexpected remote
states, FTP errors or LIST fallbacks. No retries, rollbacks or uncertain-state
cleanup occurred.

### GUI/display and connection observations

An external driver instantiated the real Development GTK application on display
`:0`, with isolated Core preferences and the actual production prompt/job/refresh
methods. It populated the real entry and submitted the dialog response, rather
than running an extracted or mocked GUI method. On each device it observed:

- mapped `Rename` dialog, expected initial filename and enabled confirmation;
- busy state, disabled busy controls and enabled cancellation control at job
  submission (no cancellation was requested);
- `file.rename` in the device's Core lane, with matching device/session IDs;
- `Completed: <disposable tree>/GuiChecked.txt` and refreshed rows containing
  exactly `GuiChecked.txt` and `emptytwo`;
- zero active managed leases after completion/refresh.

This was automated actual-display qualification, not human visual sign-off or
manual mouse/keyboard coverage. The stale-session presentation race was not
induced physically; approved deterministic delayed-callback regressions remain
authoritative for that race. No active RNFR/RNTO pair was interrupted.

| Per-operation managed measurement | Beige | Founder's |
|---|---:|---:|
| Each standalone MKD: sessions / USER / FEAT | 1 / 1 / 1 | 1 / 1 / 1 |
| Each ordinary file/directory rename: sessions / USER / FEAT | 1 / 1 / 1 | 1 / 1 / 1 |
| Each case-only rename, both pairs: sessions / USER / FEAT | 1 / 1 / 1 | 1 / 1 / 1 |
| GUI rename mutation: sessions / USER / FEAT | 1 / 1 / 1 | 1 / 1 / 1 |
| Each reviewed deletion execution: sessions / USER / FEAT | 1 / 1 / 1 | 1 / 1 / 1 |
| Active leases after measured operations | 0 | 0 |

Validation listings reused each operation's lease. Review, execution and
post-operation observation retained separate lifetimes. The GUI refresh is a
separate read session, not part of its mutation lease. Core connection epochs
remained unchanged within each phase. Core, GUI and cleanup used fresh isolated
connections with new expected epochs; no mid-operation reconnect was tested.
Legacy setup-upload sessions are not counted as managed 3B qualification.

### Probe limitations and retained evidence

The first external Core probe stopped before mutation because its serializer
could not handle an immutable mapping in the connection result. Only the
external serializer was corrected. An initial external GUI launch used the
application's overloaded `run` method incorrectly and failed before device
access; the launcher was corrected to use `Gio.Application.run`. Both failed
probe records are retained. Neither was a production/device mutation failure.
The GTK driver emitted a deprecation warning for `Gtk.Dialog.response`; the
actual dialog, job and refresh checks passed.

No dropped replies, send failures, active-transfer disconnects, uncertain
mutations or other destructive fault conditions were induced. Those remain
socket-fixture coverage. This qualification used small disposable data, not
large uploads, replacement, Flash writes or later Slice 3 checkpoints.

External evidence is in `argonaut-qualification/network-slice3b-physical/`, outside
the repository: probes, reviewed diff, source hash manifest, operation/GUI logs,
local readbacks, reports and structured diagnostic events. Accepted device
reports are `beige-20260927-110054/report.json` and
`founder-20260927-110125/report.json`, with `gui-report.json` alongside each.


## Slice 3C — managed normal staged uploads and partial lifecycle

Status: **physically accepted, committed and pushed** as
`6a09af5b8559df73d83e12db3eeeeba3d8106a1a`.
Base: accepted 3B `fd0e205deece43865293d2a61d64bdc3834b3c05`.
No physical devices were accessed during implementation or deterministic tests.

### Explicit consumer boundary

`transfers.upload_managed` is selected only for FileService Core-host → C64U
addition-file steps and USB restore addition files. Folder-plan file additions
use it too; directory creation retains its existing route. The managed branch
consumes a structured return, not a parsed success message. Missing managed
context fails without a raw FTP fallback.

Legacy `upload()` remains unchanged for replacement staging, remote-to-remote
composite copying and AI installation/provisioning. Flash `upload_flash`, CLI
`upload_new_folder`, replacement exchange/cleanup and unbound compatibility
remain deferred. Restore replacements still call the original replacement
route. No generic transaction framework or replacement cancellation scope is
introduced.

### Lifetime, source and verification

One `_FtpOperations` lifetime owns each file's plan validation, destination/temp
inspection, STOR staging, RETR/hash staging, SIZE staging, destination recheck
and RNFR/RNTO publication. Nested helpers reuse its lazy lease; outermost exit
releases it without a cancellation check. Absolute paths prevent listing CWD
changes from redirecting transfers. STOR dispatch marks the operation as
consequential, preventing explicit read fallback from reopening a failed write.
No lease spans a whole batch, review or later cleanup.

Staging uses the existing checked `c64u-part-<uuid>` name and case-insensitive
collision refusal. Existing path/source validation remains. The source opens
once in binary mode; `os.fstat(stream.fileno()).st_size` supplies exact expected
length to `write_from` on that same stream. There are no locks, immutable
snapshots, spools, second source opens or mtime/inode checks. A same-length
concurrent rewrite can still pass: verification concerns bytes actually sent.

Zero-byte uploads are supported. Short and overlong local streams fail without
publication. A short stream can receive a positive terminal STOR reply and
still fail exact-length validation. An overlong block is rejected before send.
Successful sent bytes are independently read back and hashed; RETR is bounded
by the sent count, rejecting an overflowing block before accepting it. This
approved failure-timing change does not add an initial SIZE or post-publication
read. Verification remains RETR/hash → SIZE, then the final destination recheck.
FTP cannot make that recheck and RNTO an atomic no-replace publication against
external writers.

### Evidence, cancellation and partial reporting

`WriteEvidence` records expected length, attempted submission, preliminary and
terminal replies when observed, counted whole successful sends, full sent hash
when EOF established the exact length, transport outcome, length status and
sanitized error category. A failed send may have delivered additional bytes;
the count is a local observation, not exact remote storage size. No partial-prefix
hash is exported. A positive terminal reply survives subsequent length failure.
A negative terminal STOR reply retains unknown storage outcome and its actual
reply code. No error authorizes replay; failures poison the lease.

`UploadEvidence` separates workflow phase, both paths, STOR evidence, readback
and SIZE status, publication mutation evidence and disposition. Copy/restore
results add an `uploads` tuple without removing existing fields. Successful
per-file results retain path, bytes, SHA-256 and verified status. Managed errors
are nonretryable at the service/job boundary; peer prose is not exposed.

- `not-started`: no consequential upload submission is established; no partial.
- `no-candidate`: preliminary STOR refusal, without asserting file creation.
- `staging-candidate`: possible Core-associated staging residual, not proof of
  current existence or exclusive ownership. Failures during transfer, after
  accepted STOR, during verification, on final conflict or refused publication
  retain this candidate when supported by the recorded evidence.
- `location-unknown`: consequential RNTO submission lacks a definitive result.
  Both staging/final paths are inspection evidence, neither is selected for
  cleanup, and `partial_path`/`partial_upload` are absent.
- `published`: RNTO acknowledged; the file is recorded completed, not partial.

Cancellation is honored before submission and during streaming/verification.
Accepted STOR evidence survives subsequent cancellation. RNFR/RNTO uses the
existing 3B serialized deferral; binding/recovery/socket failures remain effective.
No cancellation check follows acknowledged publication or context exit. A batch
can then cancel before its next item while retaining the published prefix.

Partial cleanup remains `PartialUpload → prepare_partial_delete → fresh review
→ managed reviewed deletion`, with original device/session binding, reconnect
invalidation, expiring/consumed plans and execution revalidation. Cleanup preview
and execution use new operation leases after the failed upload has released its
lease. Nothing is automatically deleted. `PartialUpload` remains a constructible
session-bound record, not a provenance registry or unforgeable authorization
token. Unknown publication requires ordinary inspection and independently
reviewed deletion of an explicitly selected existing item.

### Deterministic validation

`test_ftp_uploads.py` adds 29 tests (with additional phase/fault subcases) for
exact/empty/short/overlong sources, descriptor identity, mutable same-length
sources, preflight refusal, submission and completion failures, send-prefix
counts, callback/cancellation/binding behavior, bounded readback, SIZE failures,
destination races, RNFR/RNTO refusal/loss, acknowledged late cancellation,
per-file lease reuse and release, stale bindings, batch cancellation isolation,
FileService/restore evidence, reviewed cleanup and deferred consumer routing.

The loopback fixture adds per-transfer completion/readback hooks so STOR faults
do not accidentally fail preceding MLSD. The existing protocol round-trip test
compares common transfer fields separately from additive STOR evidence. Existing
in-memory USB restore tests provide an explicit managed-upload/lifetime seam;
new real-socket Core tests establish the production behavior independently.
No existing test was removed. **229 focused tests passed**. Complete normal and
optimized suites each ran **878 tests, 36 opt-in display skips, no failures**
(14.137 s normal; 14.168 s optimized). The accepted 849-test / 36-skip baseline
plus 29 new tests accounts for the total; no skip policy changed.

The first restricted protocol run could not open loopback sockets. Authorized
loopback-capable runs supplied the reported results. Full-suite logs are external
in `/tmp/argonaut-3c-normal.log` and `/tmp/argonaut-3c-optimized.log`, with focused
results in `/tmp/argonaut-3c-focused.log`. `git diff --check` passed. Physical
acceptance was pending at that deterministic checkpoint; see the physical
qualification record below.


### Pre-physical evidence correction

TYPE/PASV refusal before STOR submission now leaves `WriteEvidence.outcome` as
not-started. The enclosing sanitized transport failure retains its own outcome,
category and reply code; phases `stor-type`, `stor-pasv` and `data-connect`
distinguish setup failures. `UploadEvidence.transport_error` carries that safe
error record through copy/restore results. Actual preliminary STOR refusal
remains submitted/rejected, with no asserted staging cleanup candidate.
No transfer, publication, cancellation, cleanup or deferred-routing policy changed.

Five added regressions cover TYPE refusal, PASV refusal, data-connect failure,
actual STOR refusal, and upload verification RETR terminal loss. The latter
required no transfer behavior change: completed STOR evidence survives, expected
received bytes do not establish verification completion, and publication stays
unattempted with a staging candidate retained. All five targeted tests passed.

Final correction validation supersedes the earlier totals: **234 focused tests
passed; normal and optimized suites each ran 883 tests with 36 skips and no
failures** (13.116 s normal; 13.789 s optimized). This is 878 + 5, or the accepted
849-test baseline + 34; no tests were removed or skip policy changed.
Logs are external `/tmp/argonaut-3c-correction-focused.log`,
`/tmp/argonaut-3c-correction-normal.log` and
`/tmp/argonaut-3c-correction-optimized.log`. `git diff --check` passed.
No physical device was used for the correction tests. Subsequent authorized
physical qualification is recorded below; subsequent acceptance and commit/push
are complete.


### Slice 3C physical qualification — 27 September 2026

Authorized checks passed independently on both devices using the uncommitted
reviewed implementation at base `fd0e205deece43865293d2a61d64bdc3834b3c05`.
Identity and firmware/API were verified before mutation. Final acceptance review
subsequently passed, followed by commit/push as
`6a09af5b8559df73d83e12db3eeeeba3d8106a1a` (parent is the base above).

| Device | Address | Physical ID | Firmware | API | Disposable parent |
|---|---|---|---|---|---|
| Beige | `192.168.68.70` | `25EA78` | `1.1.0s2` | `0.1` | `/USB2` |
| Founder's | `192.168.68.69` | `25BE71` | `1.1.0` | `0.1` | `/SD` |

Exact disposable trees (both subsequently removed and verified absent):

- Beige: `/USB2/argonaut-3c-accept-8ac84231104c444f93392b3b3c31f9c5`
- Founder's: `/SD/argonaut-3c-accept-6f5b18250cf74df18bbdeb8643568dd6`

Each tree contained only `empty.bin` and `known.bin`. Managed FileService
zero-byte uploads reported expected/sent counts of zero, exact length, STOR
150/226, passed RETR/hash and SIZE verification, and published RNFR/RNTO
350/250 evidence. Fresh listings confirmed size zero and no staging residue.
The empty SHA-256 was
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Known-content files were 1,076 bytes each, incorporating the device identity:

- Beige SHA-256: `32334cbb34f975096cbbb98465a3cf34f3711d4feed94de522d8412b242ca260`
- Founder's SHA-256: `e7592a1b649cdd17be47fd7e893217edc1b1fca3be1e7ae3d83f2c26153f0093`

Expected/sent counts and sent hashes matched the local sources. Both uploads
reported completed STOR, passed bounded independent RETR/hash and SIZE checks,
and acknowledged publication, with no partial result or staging residue.
Independent Core downloads of the published files matched counts and hashes.
These extra acceptance reads add no production verification requirement.

A local `KNOWN.BIN` conflicted with existing `known.bin` on both devices.
FileService preview reported the conflict and skip preserved it; a separately
scheduled bound managed-upload attempt refused it before STOR/publication,
returning not-started evidence without a partial cleanup candidate. Subsequent
listings and independent downloads confirmed no residue and unchanged content.

Existing diagnostic session IDs correlated each successful normal upload's
preflight listings, STOR, RETR, SIZE, destination recheck and RNFR/RNTO with
**one FTP session, one USER authentication and one FEAT**. Each recorded four
MLSD listings, one STOR, one RETR, one SIZE, one RNFR and one RNTO. All measured
operations ended with zero active leases and unchanged Core device/session epoch;
subsequent independent operations acquired normally. No transport error or
LIST fallback occurred. No temporary production instrumentation was added.

Each device supplied a real selected-file USB backup of `known.bin`, including
normal preview, execution verification and a complete manifest. Reviewed deletion
of that disposable source made it an addition. Restore preview classified exactly
one addition, with no replacements/conflicts; execution recorded one published
addition, 1,076 bytes, no remaining items and no partial result. The restore
file's upload diagnostics again showed one session/USER/FEAT and one each of
STOR/RETR/SIZE/RNFR/RNTO. Independent restored-file downloads matched the hashes
above, and fresh listings found no staging residue. Full-volume fingerprinting,
preview and execution retain their distinct operation lifetimes; the complete
backup/restore workflow is not claimed to use one FTP session.

Final independent inspection found only the two expected files in each tree.
Accepted reviewed deletion removed those files and their directory; fresh parent
listings confirmed absence, with zero active leases. Directory setup and cleanup
used accepted 3B mechanisms and are not new 3C qualification claims.

Physical cooperative cancellation/partial cleanup was intentionally omitted:
there was no controlled timing procedure that could separate ordinary cancellation
from transport uncertainty. No lost-reply, socket/setup/data failure, active
binding invalidation or external-writer race was induced. Those cases remain
qualified by deterministic fixtures. These were headless Core/FileService checks,
not additional GUI qualification. Flash, CLI fresh-folder uploads, replacement/
composites, AI provisioning and compatibility retirement remain deferred.

The final deterministic baseline remains **883 tests / 36 skips**, normal and
optimized, no failures; no production/test source changed during qualification
(as verified against pre-run hashes). Only the two authoritative development
documents were updated. External scripts, reports, diagnostics, local sources,
readbacks and backup manifests remain outside the repository under
`../argonaut-qualification/network-slice3c-physical/`, with device records in
`beige-20260927-120502/` and `founder-20260927-120630/`. They are excluded from
the proposed commit.


## Slice 3D — managed replacement and composite replacement

Status: **physically qualified, uncommitted; final review pending**.
Base: accepted 3C `6a09af5b8559df73d83e12db3eeeeba3d8106a1a`.
No physical devices were accessed for implementation or deterministic tests.

### Explicit consumer boundary

`managed_replacement.replace_managed` is a separate Core orchestration entry.
FileService and USB restore explicitly select it through `execute_plan`'s
`managed_replacements` option for remote-destination replacement steps only.
Its enclosing lifetime includes the existing source/ancestor/destination execution
validation. Legacy `replacement.replace_file`, local-destination replacement,
remote-to-remote additions, general folder-plan directory creation, Flash, CLI
fresh-folder uploads and AI installation/upgrade/provisioning retain their routes.
Missing managed context fails without a raw FTP fallback. Accepted 3C additions
remain unchanged. Neither compatibility retirement nor all of Slice 3 is complete.

### One file, one managed operation

Sequence:

1. Check cancellation, validate the execution step and compare the reviewed
   remote signature (exact filename/listing size).
2. Create the checked unique sibling `c64u-replace-<uuid>` directory using 3B
   managed MKD; generate a distinct sibling `c64u-old-<uuid>` backup path.
3. Independently observe the original using SIZE → RETR/hash → SIZE.
4. Stage the source through 3C managed upload, retaining its complete evidence.
5. Check cancellation, revalidate the reviewed signature, independently observe
   the original again with SIZE → RETR/hash → SIZE and compare the hashes.
6. Inspect the backup name for collision; check binding/cancellation immediately
   before exchange.
7. Under operation-level cooperative-cancellation deferral: original → backup,
   staged → final, DELE backup, RMD staging directory.
8. Leave deferral and release the outer lease without an exit cancellation check;
   record completion. Local temporary resources are cleaned on exit.

Nested listings, reads, uploads and mutations use the same captured adapter and
lazy lease. Absolute remote paths survive listing CWD changes. No operation
holds a lease across user review or across the whole batch. A remote-source
replacement prepares a private local temporary directory, downloads through the
accepted 3A count/hash/fsync/no-replace path, then uploads that file through 3C,
all under the replacement lease. Local temporary files are removed on success,
failure and cancellation; remote failure state is never automatically removed.

Staging upload retains destination/temp inspection → STOR → bounded RETR/hash →
SIZE → destination recheck → staging publication. Its internal rename is separate
from both exchange renames: there are three rename pairs on the successful path.
A nested UploadEvidence `published` value describes the file inside staging,
not the replacement final. No extra final read is added to production replacement.

### Approved original-read behavior change and retained limits

Legacy original RETRs were unbounded. Both now use the existing exact 3A stream
with a discard sink and received-byte SHA-256, including empty files. Unusable,
malformed or changing SIZE and short/overlong RETR stop replacement. The two
observations remain independent; normal upload verification is a third RETR,
not a substitute for either original observation.

The generic reviewed remote signature remains name/size, not a reviewed hash.
Same-size change during staging is detected by the two original observations;
same-size change before the first execution read, changes after the second,
change-and-revert and external-writer races remain outside the guarantee. There
is no snapshot or atomic compare-and-exchange. Source uploads retain 3C's exact
opened-descriptor length contract, without source locking or stability guarantees.

USB restore retains consumed/session-bound plans, backup-storage identity,
manifest verification, volume fingerprints, reclassification and explicit
replacement selection. Equal-size comparison retains its existing preview and
execution hashes; different-size classification may remain size-based. Generic
replacement does not inherit a stronger review promise. Unselected replacements
remain skipped; additions keep 3C routing; unrelated files are not removed.

### Cancellation, failures and evidence

The existing private operation-level deferral now records when it observes and
suppresses cooperative cancellation. It spans both exchange renames and all
successful-path remote cleanup. Transport primitive serialization is unchanged.
Binding invalidation, recovery, socket/protocol failures, timeout, validation and
unrelated callback failures remain effective. No cancellation-sensitive progress
callback is invoked in this protected section. Pending cancellation cannot erase
an acknowledged publication or substitute for a real failure. A successful last
replacement may finish its job successfully despite late cancellation; a following
item checks cancellation and preserves the completed prefix.

ReplacementEvidence is ordinary structured data, returned separately in
Report/CopyResult/RestoreResult `replacements`. It records phase and relevant
paths; staging MKD and nested UploadEvidence; both signatures/original hash/count
observations; protection status; both exchange mutations, DELE and RMD evidence;
ordered acknowledged steps; stopped/uncertain step; publication/cleanup states;
candidate and uncertain paths; observed/deferred cancellation; sanitized failure
category and transport evidence. None denotes an unattempted primitive or an
observation not completed. Failure phase/evidence distinguishes those cases.
Cancellation flags describe observations, not an assertion that no later request
exists: in particular, no new check is inserted after successful RMD.

- RNFR uncertainty retains submitted RNFR evidence but unsubmitted consequential
  RNTO. It does not claim a completed filesystem rename.
- Unknown first RNTO records final/backup alternatives; replacement publication
  has not completed. After acknowledged first rename, the backup is the original's
  last acknowledged location, even if the second rename is refused/unsubmitted.
- Unknown second RNTO records staged/final alternatives and unknown publication.
- Completed second rename fixes publication as completed even if DELE/RMD fail.
  Backup removal and directory cleanup retain independent certainty.
- Full acknowledged exchange/cleanup is success. A later local temporary cleanup
  error retains acknowledged remote success rather than changing its certainty.

Whole-workflow completed/remaining accounting is retained. A cleanup failure can
leave an item unfinished, but the message explicitly says publication completed
and cleanup is incomplete. Replacement failures are nonretryable; transport
availability metadata never authorizes mutation replay. Partial replacement
state is not exported as an ordinary PartialUpload cleanup shortcut, including
when a nested upload has a staging candidate. No automatic remote cleanup,
rollback or recovery transaction is introduced.

Every failed managed lease is released without reconnecting/reacquiring,
continuing cleanup or resetting through read fallback. Any later inspection is
a new independent operation. Candidate paths are neither proof of existence nor
exclusive ownership. Fresh inspection and explicit reviewed deletion are required;
never delete possible original/backup/final data or both uncertain rename
alternatives merely from failure evidence. A refusal, including 550, does not
prove path absence.

### Deterministic validation

`tests/test_ftp_replacements.py` adds **48 tests**, including additional parameterized
subcases. Real loopback/Core coverage establishes:

- Stale signatures/bindings; original content/size changes; unusable/malformed SIZE;
  short/overlong original reads; zero-byte originals and replacements.
- MKD refusal/lost reply, staged upload/readback failure and staged-publication
  uncertainty; backup collision; independent original observations.
- First/second rename non-submission, refusals, RNFR/RNTO loss and acknowledged
  prefixes; DELE/RMD refusals/lost replies; completed publication versus cleanup.
- Cancellation before/during staging and original reads, immediately before
  exchange, during exchange/cleanup and after the final RMD; real Core job success
  or completed-prefix cancellation as appropriate; no cancellation leakage.
- Binding/recovery/network/protocol failure precedence and unrelated callbacks;
  one authentication/FEAT/lease, release, stable epoch and failed-lease non-reopening.
- FileService local/remote-source replacement, local temporary cleanup on all
  exits, USB skip/replace/stale-content review and cleanup-failure accounting;
  sanitized nonretryable evidence and deferred routing.

The fixture adds a path-aware pre-command response hook; existing post-mutation
hooks distinguish a mutation's effect from loss of its reply. Tests select the
specific path/rename pair, rather than accidentally faulting staging publication.
The existing in-memory USB policy suite supplies an explicit replacement seam;
its behavior remains tested, while real managed ownership/evidence is established
by the independent socket integration suite. No existing tests were removed.

**258 focused tests passed**. Complete normal and optimized suites each ran
**931 tests with 36 opt-in display skips and no failures** (14.821 s normal;
15.479 s optimized). This is the committed 883-test baseline plus 48 new tests;
skip policy is unchanged. The initial restricted run could not open loopback
sockets; authorized loopback-capable runs supplied these results. Logs remain
outside the repository at `/tmp/argonaut-3d-focused.log`,
`/tmp/argonaut-3d-normal.log` and `/tmp/argonaut-3d-optimized.log`.

Physical acceptance was pending at this deterministic checkpoint. The subsequent
authorized two-device qualification is recorded below. Lost replies, exchange
interruption and uncertain destructive outcomes remain deterministic scenarios.


### 3D pre-physical review corrections

Remote-source temporary cleanup is now explicit and runs after primary
replacement errors/cancellation have been normalized. A secondary cleanup
exception cannot replace remote mutation certainty, acknowledged steps, nested
upload evidence, path alternatives or the primary cancellation classification.
`ReplacementEvidence.local_cleanup` additively records attempted/failed cleanup
with the sanitized `local-cleanup-failed` category; raw local exception text and
private temporary paths are not exposed. If remote replacement and remote cleanup
succeeded, a subsequent local cleanup error remains a reported failure with
remote publication/cleanup still completed. No remote continuation or recovery
is triggered by a local cleanup error.

`ReplacementEvidence.inspection_message()` supplies the Core-formatted failure
summary. It distinguishes intended final paths, staging candidates, uncertain
location alternatives, last acknowledged original backup locations, and completed
publication with unresolved cleanup. Acknowledged removed backups/directories
are not offered as cleanup candidates. Every summary includes an inspection-only
warning: paths do not authorize replay, rollback or cleanup; fresh inspection
and explicit review are required before destructive action.

CopyResult.details() and RestoreResult.details() render these summaries. GTK
passes through the restore details and also opens its existing copy report for
cancelled jobs carrying replacement evidence. It does not reconstruct mutation
state or create cleanup actions. Existing accounting and ordinary upload partial
reporting remain unchanged; replacement paths never populate PartialUpload.

Eight correction regressions exercise unknown final RNTO, nested upload
uncertainty, cancellation and full remote success combined with local cleanup
failure; visible copy/USB summaries for unknown/refused publication and cleanup
failure; actual headless GUI report callbacks; and retained ordinary partial-path
presentation. No earlier test is removed. These corrections do not change the
3D operation boundary, original observations, staging, exchange deferral or
mutation/replacement authorization semantics. Physical qualification is recorded below.

Correction validation supersedes the earlier totals: **8 targeted tests and
266 focused tests passed**. Normal and optimized suites each ran **939 tests,
36 skips, no failures** (15.164 s normal; 14.677 s optimized). This is the
931-test pre-review result plus eight tests; no tests were removed or skip
policy changed. `git diff --check` passed. External logs are
`/tmp/argonaut-3d-corrections-targeted.log`,
`/tmp/argonaut-3d-corrections-focused.log`,
`/tmp/argonaut-3d-corrections-normal.log` and
`/tmp/argonaut-3d-corrections-optimized.log`. No physical testing, commit or push
was performed in this correction pass.


### Slice 3D physical qualification — PASS (27 September 2026)

The approved uncommitted implementation at base
`6a09af5b8559df73d83e12db3eeeeba3d8106a1a` passed on both machines, with
65 recorded checks per device. HEAD and origin/development matched that base;
only the reviewed 12-file change set was present, nothing was staged and
`git diff --check` passed before qualification. Production/test SHA-256 snapshots
were unchanged afterward. Only development documentation was edited in this pass.

| Device | Address / physical ID | Firmware / API | Disposable tree (now removed) |
| --- | --- | --- | --- |
| Beige | `192.168.68.70` / `25EA78` | `1.1.0s2` / `0.1` | `/USB2/argonaut-3d-accept-4ebe584be1aa4058b3e16ff902ef77ad` |
| Founder’s | `192.168.68.69` / `25BE71` | `1.1.0` / `0.1` | `/SD/argonaut-3d-accept-1a5dc86335ef406892d98aa4ed328d07` |

Identity and firmware/API were reverified before mutations. Parents were selected
independently: `/USB2` on beige, `/SD` on Founder’s. Already accepted mkdir and
normal upload supplied disposable setup data. All initial and replacement files
were 640 bytes; differing same-size content exercised content verification.

For each device, FileService reviewed local-source replacement passed both
independent original SIZE/RETR/SIZE observations, staging upload verification,
signature revalidation, exchange and cleanup. Remote-source replacement also
passed its managed source download and preserved the source. Its private local
temporary directory was empty afterward: the external probe selected an isolated
process temporary root without modifying production code.

A genuine USB backup of `restore.bin` completed with verified manifest handling.
A separate reviewed replacement deliberately changed that disposable destination.
Restore preview identified exactly that file as a replacement, with no additions
or conflicts. Explicit `replace=True` execution restored it, with one completed
replacement, no remaining items and successful publication/cleanup evidence.
Independent final downloads verified all five known files. The sentinel was
checked after every scenario and remained unchanged, outside replacement plans.

The following initial and final SHA-256 values were verified independently;
every entry is **640 bytes**. Remote destination final equals preserved source;
restore final equals the genuine backup original.

| Device | File | Initial SHA-256 | Final SHA-256 |
| --- | --- | --- | --- |
| Beige | `local.bin` | `00646e2dadcb166b62b2deb1abfc469fbd1e09b465de1d96e30329cd0bd708a3` | `6f2abc4cf883443e9d5c374a8c4506e4555503941f449c44a588bee44432a186` |
| Beige | `remote.bin` | `8484cddea910021b34ef969de6e7efd600e546c13ddb1c49a000bcfc7a957e32` | `473315b7b001ead4f73d5391194f3574f516b3b341ed193e8bb970f44a869df4` |
| Beige | `restore.bin` | `59c9f0e76dfd7b9f09c7081e5e1789ceb2b0750295a31cbaf38756a314aff8c9` | `59c9f0e76dfd7b9f09c7081e5e1789ceb2b0750295a31cbaf38756a314aff8c9` |
| Beige | `sentinel.bin` | `04f5d261dfee3b3fb8c21cfad03d7c26148f49c561f307490b3c0acae4afb457` | `04f5d261dfee3b3fb8c21cfad03d7c26148f49c561f307490b3c0acae4afb457` |
| Beige | `source/remote.bin` | `473315b7b001ead4f73d5391194f3574f516b3b341ed193e8bb970f44a869df4` | `473315b7b001ead4f73d5391194f3574f516b3b341ed193e8bb970f44a869df4` |
| Founder’s | `local.bin` | `69197b2c342bc29826d386ff121b168cede00a17c7f1003e1930dd3b622bc652` | `00ff9d80637de950131830771ed51e112f04f073b559109127411a17f0221c82` |
| Founder’s | `remote.bin` | `14b9bfc2b2df4bd705f299ac94f5922e2384c2945617d3f98a25c3bf59177084` | `cb376415d256dde71c980cf41b3ee3a84dd1af414896196fc83e1b3f2ea69cb5` |
| Founder’s | `restore.bin` | `4b4ea0ecad0e23e350381971db1c202d702fea1dd92887edefe34bd336470ce0` | `4b4ea0ecad0e23e350381971db1c202d702fea1dd92887edefe34bd336470ce0` |
| Founder’s | `sentinel.bin` | `a37d771e0724b4cb6911e5a61a2a6b11140a9bd11df5cc5bc0312427dd0c3b9a` | `a37d771e0724b4cb6911e5a61a2a6b11140a9bd11df5cc5bc0312427dd0c3b9a` |
| Founder’s | `source/remote.bin` | `cb376415d256dde71c980cf41b3ee3a84dd1af414896196fc83e1b3f2ea69cb5` | `cb376415d256dde71c980cf41b3ee3a84dd1af414896196fc83e1b3f2ea69cb5` |

Existing diagnostic events showed one FTP session, one USER and one FEAT per
replacement, including remote-source download plus upload. Local-source and USB
file replacement each used three RETRs/five SIZE commands; remote-source used
four RETRs/seven SIZE commands. Each included one STOR and three acknowledged
RNFR/RNTO pairs: nested upload publication inside staging, original → backup,
and staged → final, followed by acknowledged DELE backup and RMD staging.
Structured evidence confirmed the exact paths, original observations, completed
publication and completed cleanup. No fallback/error diagnostic, self-contention
or unexpected session change occurred. All measured operations ended with zero
active leases and a stable Core epoch. USB preview/fingerprinting and execution
are separate lifetimes; the one-session claim concerns each file replacement,
not the entire USB job.

Independent listings confirmed no generated backup/staging artifacts remained.
After all checks passed, a fresh reviewed deletion removed exactly five files
and two directories per device. A subsequent parent listing verified acceptance
tree absence; zero active leases remained. No blanket/failure cleanup was used.

This was headless Core/service qualification using existing diagnostics, not a
physical GUI interaction test. Normal successful exchange is physically proven;
cancellation, lost replies, binding invalidation, network interruption, local
cleanup failure and external-writer races were intentionally not induced and
remain deterministic fixture responsibilities. No reconnect or mutation replay
was required. The existing normal/optimized baseline remains **939 tests / 36
opt-in display skips, no failures**; suites were not repeated because production
and test content did not change during qualification.

External probe, diagnostics, initial/final manifests, readbacks and genuine
backups remain outside the repository in
`../argonaut-qualification/network-slice3d-physical/`, under
`beige-20260927-124324/` and `founder-20260927-124328/`. They are not proposed
commit contents. No commit, push, package or release was performed.

Deferred consumers remain remote-to-remote nonreplacement additions, general
folder-plan directory creation, Flash, CLI fresh-folder uploads, AI installation/
upgrade/provisioning, general compatibility/raw-FTP retirement and final ownership
audit. Local-destination replacement remains unchanged. This qualifies 3D only;
Slice 3 as a whole is not complete. Final review and commit/push authorization
remain pending.


## Current consumer checkpoint — R2 physically qualified, 3 October 2026

The preceding Slice 3D status is historical. R1's accepted managed folder
composites are recorded in R1-MANAGED-FOLDER-COMPOSITES.md. Production CLI
put-new now uses the R2 Core/FileService fresh-folder prepare/execute boundary;
see [R2-MANAGED-CLI-FRESH-FOLDER.md](R2-MANAGED-CLI-FRESH-FOLDER.md) for the full
contract, deterministic evidence and physical acceptance record. The R2
implementation is uncommitted and ready for final review and normal commit/push.

Loopback fixtures establish one execution connection, USER and FEAT across
validation/MKD/staged upload/readback/SIZE/publication, stable Core epoch and
zero leases on terminal paths. Connect and preparation are counted separately.
The nonempty regular-descriptor policy is opt-in for R2; default 3C zero-byte
uploads and accepted 3D/R1 semantics are unchanged. Uncertain consequences retain
inspection evidence and do not permit replay or implicit cleanup. Final focused
R2 verification passed 66 methods; 276 affected regressions and 17 offline Test
Lab checks passed. Normal and optimized suites each ran 1025 methods: 989 passed,
36 existing display skips and zero failures.

Authorized physical qualification passed independently on Beige `25EA78` using
`/USB2` and Founder's `25BE71` using `/SD` through the actual CLI put-new path.
Independent readback verified exact byte counts and SHA-256 hashes, no staging
artifacts remained, Core epochs stayed stable and active leases returned to zero.
Reviewed cleanup removed each disposable acceptance tree and fresh-session
listings independently verified absence.

Legacy read CLI, compatibility upload_new_folder, Flash and AI remain unchanged;
general raw-FTP retirement remains deferred. No R3 work has begun.
