# C64U Network Foundation — FTP Slice 1

Status: **unused transport foundation; not connected to production callers**.
Baseline: released Stable 1.9 `3acb9be310560f69df5a80619e192585a7e87155`.

## Boundary and ownership

`c64u_ftp_types.py` contains immutable device, Core binding, FTP-session,
capability, policy, listing and transfer contracts. `c64u_ftp.py` owns the wire
protocol. Neither imports GTK, `UltimateClient`, nor `ftplib`.

Core will supply a `C64UFtpLeaseManager` with a current-binding provider and a
private password provider. Providers are not exposed through the client. Obtain
a client only through `manager.lease(binding, presentation=..., cancelled=...)`.
A manager permits one operation-scoped lease per physical device. A second
acquisition fails promptly with `lease-busy`; it never waits behind itself.
Nested helpers must pass the existing lease. There is no idle pool, automatic
reconnection, automatic retry, or mutation replay. Future Core integration must
share one manager across all routes; independent processes/other applications
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

No real device operations are part of these tests. Existing production imports
are checked to exclude the new module. The next proposed slice is ordinary and
raw-identity directory browsing/bounded reads through adapters that preserve
service path checks, limits and result shapes. USB fingerprints, Game Launch and
SID authorized-content policies must remain unchanged.
