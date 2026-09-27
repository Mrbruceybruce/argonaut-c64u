# C64U Network Foundation — FTP Slices 1–3A

Status: **Slices 1–2 accepted; Slice 3A physical checks passed on both devices, final review pending**.
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
reconnection, automatic retry, or mutation replay. Core shares one manager across migrated read routes; independent processes/other applications
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
  authorized Core orchestration should use this primitive in later slices.
* Transfer results contain count, SHA-256 of transferred bytes, terminal reply
  code and outcome. A successful STOR is not independent readback verification.
  Existing higher layers retain staging, readback, SIZE, conflict review,
  replacement, deletion and partial-ownership policy. Mutation primitives beyond
  STOR are deferred to their migration slice.

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
This section describes the uncommitted implementation. Authorized physical
checks are recorded below; final review is pending and 3B–3E are not complete.

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
Final human review remains required before commit/push. These results do not
accept or authorize implementation of 3B–3E.

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
