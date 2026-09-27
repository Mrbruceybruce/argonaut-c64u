# C64U Network Foundation — FTP Slices 1–2

Status: **Slice 2 read-only Core integration and Linux physical acceptance complete**.
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

### Deliberately retained legacy consumers

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
