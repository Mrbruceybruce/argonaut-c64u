# R6 — Managed Flash publication

Status: **implementation complete; deterministic verification passed; stopped for
R6 implementation review. Not physically qualified, not committed/pushed**.
The resumed pass used the user-supplied **41% remaining** RU baseline, not a fresh
measurement. Original implementation began at 44%; the design pass used about 45%.
The original design-only wording and implementation stop record below are
historical and preserved. The authorized correction and resumed evidence follow
the stop record; physical qualification and Git publication remain separate gates.

## Authority and decision

Verified 4 October 2026 in the existing `argonaut-network-slice2` checkout:
HEAD = local `origin/development` = `dab627979b9d3bb085c955c6e3bea8cdaff8b338`,
parent `8ac1b24cb70f996b877b3eef81fd1c5817748bff`, subject
`Implement R5 Core-owned headless reads`, divergence `0 0`, clean worktree.
No fetch. Completed R1–R5 documents establish **R6** as the next checkpoint;
historical R2–R6 roadmap references do not assign current scope. R5 publication
is confirmed by the supplied completion record and local authority; its older
pre-publication prose is historical.

Use the completed post-R4 ownership assessment, as recorded in R5, plus the
accepted R5 state: CLI ls/get and headless Test Lab storage are managed;
Profile.client(), browse, ordinary raw listing and raw download fallback are
retired. Flash publication is the remaining supported live raw FTP writer.
This is a thin Flash composite, not another ownership audit or R4-sized project.

**Choice:** keep FileService's existing prepare/review/execute boundary and private
immutable byte snapshot. Replace Flash's raw publisher with a Flash-only managed
publisher using existing adapter listing, MKD, exact-length STOR, readback, SIZE
and rename primitives. Reuse `UploadEvidence` and 3B `MutationResult` semantics.
Do not route through `upload_managed()`: its `files.child/inspect/remote_file`
validation intentionally admits USB/SD only, and it opens a local path rather
than accepting the already-reviewed bytes. No public policy hook or generic
path widening is needed. Preserve diagnostic operation naming.

Source anchors: `native_files.py`, `file_service.py` (native prepare/execute and
private plans), `core.py` (FileService concrete-client provider and session),
`flash_dialog.py`, `transfers.py` (3C/evidence), `ftp_reads.py`, `files.py`,
`deletion.py`; `test_native_files.py` and `test_file_service.py`. All module/test
paths are under `c64u_browser/` and `tests/` respectively.

## Preserved current Flash contract

| Rule | Exact accepted behavior |
|---|---|
| Destination | Only exact `/Flash/roms`, `/Flash/carts`, `/Flash/configs`; no subdirectories or case aliases. |
| Filename | Nonempty single name, not `.`/`..`; reject `/`, backslash, `:`, `*`, `?`, trailing space/dot, characters below U+0020 and DEL. At most 64 UTF-8 bytes; ROM/cart names at most 30 UTF-8 bytes. Preserve case and bytes; do not normalize or silently rename. Leading spaces/dots are not otherwise forbidden. Encoding failure refuses. |
| Payload | Nonempty, at most 16 MiB (16 × 1024 × 1024 bytes), regardless of source. |
| ROM | Casefolded suffix `.bin`, `.rom`, `.64c`; currently no ROM signature, hardware compatibility or fixed-length validation beyond the shared bound. Do not invent such requirements. |
| Cartridge | Casefolded `.crt`, at least 64 bytes, first 16 bytes exactly `b'C64 CARTRIDGE   '` (authorized pre-existing defect correction; see resume record); no deeper CRT parsing currently required. |
| Configuration | Casefolded `.cfg`, at most 256 KiB; parse successfully and end in byte LF. CRLF endings therefore qualify too. |
| Collisions | Casefold comparisons for destination and staging names; any matching entry, regardless of type, refuses. Preserve exact supplied destination case. |
| Staging | Same selected directory, `argonaut-part-` + UUID hex; ordinary filename validation, not ROM/cart extension or 30-byte payload-name rules. One candidate, absence checked; collision refuses, no retry loop. GUI hides this prefix. |

CFG parsing: decode UTF-8 with optional BOM, falling back to Latin-1; use
`splitlines()`. Each resulting line is at most 127 bytes when encoded as Latin-1
with replacement; reject controls below 32 except tab within a line. Empty lines
and lines beginning exactly `#` or `;` are ignored (no whitespace stripping).
Sections are whole `[name]` lines, nonempty and unique, case-sensitive. Settings
require an existing section and `=`, split at the first `=`; names must be
nonempty and unique within that section, case-sensitive. Values, including empty
values, and spacing are preserved. At least one section must contain a setting.
No settings-schema lookup or application occurs during upload.

Current local preparation rejects symlinks/non-files, reads at most MAX_BYTES+1,
and validates before storing immutable bytes in the private expiring single-use
plan. Preview exposes metadata, not bytes. GUI derives the name from the source
basename; Copy selected drive file requires exactly one non-directory/non-`..`
USB/SD selection. `read_remote` also supports files beneath known Flash folders
for other callers; do not widen or retire those unrelated native-read contracts.

Today the raw uploader validates again, opens `transfers.connect()`, lists
`/Flash` through the managed client, creates only the selected known directory
if absent, then checks destination/staging absence. It STORs the snapshot,
independently RETRs and hashes it, verifies exact count and SIZE, rechecks the
destination and renames staging to final. No post-rename read occurs. Root lookup
currently uses the first casefold match, accepting only an exact-spelling `dir`;
R6 must examine all matches and refuse ambiguous duplicates instead of trusting
listing order. This enforces the intended ambiguity refusal, not wider policy.

Current raw failures wrap exception text; after STOR is marked started they
append both candidate paths. The raw connection closes in `finally`; neither
staging nor a created directory is automatically removed. Cancellation is checked
around prepare and before execute, but the raw upload lacks phase-aware job
cancellation/evidence. R6 preserves conservative no-cleanup policy while replacing
raw prose and cancellation gaps with accepted managed evidence semantics.
Uploading never selects a ROM, activates a cartridge, applies configuration,
resets/reboots or mutates active settings. The dialog's separate Preview config
workflow is unrelated and unchanged.

## Source preparation and execution lifetime

A. Local Upload file: retain the bounded local read and content validation into
private plan bytes. Execution revalidates folder/name/content/length and hashes
that snapshot; it never reopens the original path. A source changed/deleted after
review cannot change the upload. Changes during the initial bounded read may
produce a captured valid snapshot, not proof of an atomic filesystem snapshot;
validation applies to exactly those captured bytes. Short/overlong STOR from that
snapshot is a transport/source-length failure and cannot publish.

B. Copy selected drive file: retain the existing accepted bounded managed
`read_remote` composition into the same private bytes (no remote-to-remote raw
copy). Require a managed adapter before reading; pass job/session checks through
one prepare-time managed operation. SIZE → bounded exact-length RETR → SIZE
must complete with nonzero size ≤16 MiB, exact count and stable SIZE. Capture
observed length and SHA-256 of received bytes privately for the plan; report only
safe evidence. Growth/shrinkage fails within the bound; same-length concurrent
rewrites are not an atomic-source guarantee. Execution publishes the reviewed
snapshot, never rereads a mutable remote source. Original source remains intact.

**No local temp is required**: the existing accepted private in-memory snapshot
is smaller and preserves review semantics. Thus private temp paths and temp
cleanup failures are inapplicable on both production paths; plans are discarded
on cancellation/expiry/consumption as today. Do not introduce a filesystem spool
solely to call 3C. If a future implementation proposes one, review it separately:
private bounded source, cleanup on all exits, sanitized secondary cleanup failure
that cannot overwrite remote evidence. The result may use the existing empty
`local_cleanup` convention; it must never imply cleanup reversed publication.

Preserve the scheduled Core device lane, captured DeviceSession, concrete client
and plan TTL/single-use behavior. Recheck session when retrieving that client and
through the operation callback; adapter binding/recovery checks remain independent
of cooperative cancellation. No lease spans user review. Execution owns one
`adapter.operation(check)` across directory validation/MKD, listings, STOR,
readback, SIZE and publication. Nested helpers reuse it; outer exit releases on
every path. Missing adapter refuses; no raw fallback, reconnect, retry or replay.
No raw ftplib object escapes. No new profile/credential architecture.

## Directory and publication sequence

1. Validate snapshot and destination before acquiring a mutation-capable lease.
   Observe `/` to establish a unique exact `Flash` directory; successfully list
   `/Flash` at that exact path. Refuse unavailable root, wrong type, lossy or
   ambiguous identity/case; never create `/Flash` or arbitrary ancestors.
2. Inspect all casefold matches for the selected basename. Exactly one exact
   directory means already-present; wrong type/case/multiple matches refuses.
   If absent, immediately relist `/Flash` and recheck binding/cancellation before
   MKD. If the exact directory appeared, continue as already-present; conflicting
   appearance refuses. Optional means creation only when this approved upload
   needs its selected known directory, not a separate folder-creation workflow.
3. Issue managed MKD once. Record its complete mutation evidence immediately.
   Acknowledged creation survives cancellation or every later failure. Reobserve
   exact directory before writing. Unknown MKD stops for inspection: no replay,
   inferred success, upload continuation or automatic RMD. A rejected MKD also
   stops; do not reinterpret an error as permission to retry/continue.
4. In the execution directory, require destination and one generated staging
   candidate absent case-insensitively. Then bounded exact-length managed STOR
   from snapshot bytes; retain submission, replies, transferred length and hash.
5. Independent bounded managed RETR/hash of staging, exact count equal to snapshot
   length and hash equal to sent/snapshot hash; then SIZE equals that length.
   Preserve 3C's RETR/hash → SIZE order and refuse every mismatch/unavailable SIZE.
6. Fresh destination-absence check immediately before publication, with exact
   directory/type/case still valid; binding/cancellation check, then serialized
   managed RNFR/RNTO. No overwrite/replacement branch. Record both replies and
   consequential submission/outcome. Acknowledged RNTO completes publication;
   no post-publication cancellation check or additional read in the composite.

As with accepted 3C, listing/recheck and RNTO are not an atomic server-side
no-replace primitive. External writers can race the last observation and rename;
this design preserves the existing refusal contract, not an atomic exclusion
claim. Staging absence similarly does not establish exclusive remote ownership.
Do not claim protection against uncoordinated device/external writers.

Cancellation before MKD/STOR leaves those steps unstarted; cancellation after
acknowledged MKD reports the created directory. STOR/readback cancellation stops
with candidate/evidence, never publication. Submitted MKD and the RNFR/RNTO pair
retain 3B's reply-boundary cancellation protection, not a whole-upload mask.
Acknowledged publication remains published despite late cancellation; unknown
publication retains both possible paths. Binding/transport failures always stop.
No automatic remote cleanup, rollback or deletion, even for apparently certain
partials or empty created directories: current Flash policy already retains them.
Inspection and separately reviewed managed deletion need a fresh operation.

## Minimum additive result and UI evidence

Extend NativeUploadResult additively (existing destination/size remain); preserve
an equivalent structured result on FileJobFailure and JobCancelled. Use a small
Flash envelope around UploadEvidence, not a new transfer result framework:

- Phase and sanitized refusal/error category; validation-before-mutation status.
- Directory path/state: unobserved, already-present, acknowledged-created,
  refused, creation-unknown; retain full sanitized 3B MKD mutation evidence.
- UploadEvidence: STOR not-started/no-candidate/staging-candidate, exact count and
  submission/reply/length evidence; readback/SIZE/recheck states; publication
  MutationResult and disposition published/location-unknown. Verified-staged is
  derived from passed readback and SIZE, not guessed from transfer completion.
- Expected count/hash and source observation summary; cancellation phase and
  ordered acknowledged consequences. Published means the verified staged bytes
  were acknowledged renamed, not independently read again at final destination.
- Safe remote candidate paths and inspection guidance; optional secondary local
  cleanup categories, empty for the chosen no-temp workflow.

Preserve evidence before error translation and lease release. GUI failure and
cancelled-job rendering must show the Core-formatted summary, including created
directory even with STOR unstarted and both paths on unknown publication. A
staging candidate is not proof of existence/ownership or cleanup authorization.
No bytes, passwords, private temp paths or unrestricted server/exception prose
in result, diagnostics or UI. Late cancellation cannot turn success into an
assertion that nothing changed.

## Proportionate deterministic contract (later implementation)

Do not run tests in this design pass. Later tests must cover:

- Directory/type/extension/content matrix, case-preserving names and CFG details;
  invalid paths/names/content, empty and >16 MiB refuse before mutation.
- Exact existing directory; absent directory; case/type/duplicate collision;
  immediate pre-MKD race; MKD acknowledged, rejected, unknown, cancellation after
  acknowledgment retaining evidence and zero later writes.
- Local snapshot success with exact STOR, independent RETR/hash, SIZE and
  RNFR/RNTO evidence; destination/staging collision and destination race refusal;
  short/overlong STOR, corruption, unavailable/mismatched SIZE; original local
  changes after review do not alter the validated snapshot.
- Cancellation before STOR, during STOR/readback, and after acknowledged RNTO;
  unknown publication, no replay/reconnect and zero automatic DELE/RMD/rollback.
- Selected-drive source performs bounded managed SIZE/RETR/SIZE then managed
  Flash publication; remote growth/shrinkage refuses, snapshot survives later
  source changes, private bytes never appear in preview/result. Assert no temp
  created, hence no temp cleanup needed; any introduced cleanup seam must have
  secondary-failure coverage preserving acknowledged remote publication.
- Stale prepare/execute session and mid-operation binding/recovery refusal;
  one execution lease, separate preparation lease, zero terminal leases.
- Flash production cannot call raw factory/connect/open_ftp; no ROM/cart
  activation, config application, reset/reboot or settings writes.
- Keep R5/3C/3B/Core/FileService regression contracts unchanged; update obsolete
  raw-Flash mocks only where directly earned. Static secret/private-path scan
  of changed code, result representations, logs and docs.

Use real socket loopback fixtures for submission/reply loss, exact bounds,
MKD/RNTO consequence certainty and cancellation claims; unit mocks suffice for
policy matrix/GUI routing. No giant new audit or unrelated test reorganization.

## Later physical acceptance (separate authorization after implementation review)

Beige then Founder, each through verified Core identity/session. First inspect
current `/Flash` and approved directories read-only. Prefer one already-existing
approved directory, unique disposable filename with no collision. Use the smallest
harmless syntactically valid fixture for that directory: e.g. a one-byte `.bin`
under existing roms, a 64-byte signature-valid `.crt` under carts, or minimal
`[A]`/`X=1` LF-terminated CFG under configs. These are storage fixtures, not images
approved for activation. Never select/activate/apply them or change settings.

Publish once, independently read final file and compare size/hash; inspect
staging residue, session continuity and zero leases. Review deletion of only the
exact disposable file, revalidate exact name/type/content in a fresh bound
operation, issue accepted managed 3B DELE and independently verify absence.
The ordinary reviewed-deletion API currently uses USB/SD-only `files.inspect`;
do not pretend it accepts Flash or broaden it for this checkpoint. The separately
reviewed physical probe must implement that narrow exact-path review around the
existing managed deletion primitive. Approve this cleanup procedure before any
physical write; no new general production Flash deletion feature is needed.

Deterministic coverage is sufficient for missing-directory creation. Do not create
a real approved directory just for qualification; if no suitable directory exists,
stop and request a separately reviewed procedure before altering organization.
Never delete an approved directory in normal qualification. Stop on unknown
publication or cleanup; no retry or automatic destructive recovery. No physical
fault injection or activation/application/reset/reboot/settings mutation.

## Retirement payoff, exclusions and implementation gate

Static call chain: FlashFiles → FileService prepare/execute → concrete Core client
→ native upload → transfers.connect. Replacing that final publisher removes the
remaining supported live production use of transfers.connect and the raw Flash
STOR/RETR/SIZE/rename/session creation path. Remove the superseded raw Flash
publisher body directly; add no Flash fallback branch. The native read fallback
is a separate deferred compatibility branch, not earned dead by this migration.

`transfers.connect` itself remains referenced by deferred legacy upload,
replacement, files/raw mutation, native read, disk and USB compatibility branches;
do not delete those symbols/imports opportunistically. Its dynamic open_ftp arm
remains textually present. FileService supplies the concrete Core client, so
Flash does not reach CoreDeviceOperations.open_ftp; that facade method remains
production-dead and deferred to separately reviewed final compatibility closure.
No general closure starts here.

Exclude Flash activation/application/settings changes, overwrite/replacement,
CLI/Test Lab reads (R5 complete), AI/R4 changes, Streams/Ultimate Menu/cartridge
feature work, packaging and release. Stop implementation if it requires weaker
Flash validation, changing generic 3C USB/SD callers, raw fallback/reconnect/replay,
overwrite, destructive cleanup after uncertainty, activation/reset/settings side
effects, or broad closure. Stop and review any departure from private snapshots.

**Unresolved design questions: none.** Direct implementation approval is appropriate
for this bounded design after review. Implementation, deterministic verification,
and later physical authorization are separate gates. **Stop for design review.**


## Implementation stop record — 4 October 2026

The subsequent user authorization superseded the historical design-only gate.
Authority verified before edits in the existing `argonaut-network-slice2`:
HEAD = local `origin/development` =
`dab627979b9d3bb085c955c6e3bea8cdaff8b338`; parent
`8ac1b24cb70f996b877b3eef81fd1c5817748bff`; subject
`Implement R5 Core-owned headless reads`; divergence `0 0`.
Initial dirt was exactly CURRENT-STATE (24 additions / 10 deletions) plus this
283-line untracked design: combined +307/-10. Authority remained unchanged at stop.
No fetch, branch/worktree creation, hardware contact or Git publication occurred.

### Blocking source contradiction

The committed R5 `native_files.validate_upload` contains:

```python
data[:16] != b'C64 CARTRIDGE   \x00'
```

The compared literal is **17 bytes**, while the slice can contain at most 16.
Consequently the current validator rejects every CRT. This was confirmed directly
from `git show HEAD:c64u_browser/native_files.py` using Python AST inspection; the
working-tree validation function is AST-identical to committed R5. The design's
requirement to preserve this exact validation conflicts with its successful
cartridge-publication matrix and proposed signature-valid physical CRT fixture.
**No CRT validation change was made.** Do not silently change the signature or
slice. Review the intended CRT policy and amend the design before resuming.
The later physical procedure above remains unexecuted; its CRT fixture requires
resolution of this blocker before it can be used.

### Partial draft retained for review

- `c64u_browser/native_files.py`: raw Flash publisher replaced with a draft
  Flash-only managed composite and safe `FlashEvidence` envelope. Existing
  filename/content validation is unchanged. The separate native-read compatibility
  `connect` branch remains. Generic 3C and transport modules are untouched.
- `c64u_browser/file_service.py`: both source workflows target the same publisher;
  remote preparation requires a managed adapter and session/cancellation checks.
  Draft results retain Flash evidence on task failure/cancellation; consumed bytes
  are hidden from private-plan repr and cleared when the task exits.
- `c64u_browser/flash_dialog.py`: failed/cancelled execution renders the result's
  consequence summary when present.
- `tests/test_r6_flash.py` (new): 27 test methods for policy and real loopback
  snapshots, directory creation, verification, cancellation and uncertain outcomes.
- `tests/test_native_files.py`: adapts the existing raw-publisher mock test to
  managed-session refusal; detailed publication coverage moves to R6 loopback.
- `tests/test_file_service.py`: adapts the existing publisher-call assertion to
  added session/cancellation/source-evidence arguments.
- `docs/CURRENT-STATE.md` and this document: preserve R5 publication truth and
  record this stop. No other repository files were changed.

This is an incomplete draft, not an implementation-review acceptance candidate.
Further code review is still required, including queued/pre-task cancellation or
stale-session failure evidence and release of retained private snapshot bytes.
The final ownership claim that no supported live raw writer remains is not yet
certified. Raw Flash calls are absent from the replacement publisher; shared
`transfers.connect`, `CoreDeviceOperations.open_ftp`, and deferred compatibility
branches remain deliberately present.

### Verification attempted before the stop

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python3 -m unittest test_r6_flash test_native_files test_file_service test_core
```

The first sandboxed run could not create loopback sockets (`PermissionError`);
53 methods ran with 50 socket-fixture error subcases. No tests were weakened or
skipped. The authorized elevated rerun used the same command, with stdout/stderr
redirected to `/tmp/r6-focused.log`: 53 methods ran; 50 methods passed and 3 methods
had failures (2 errors and 2 assertion failures across subcases). The two errors
are CRT success cases exposing the blocking contradiction. The two assertions
belong to one immediate-pre-MKD race test whose fixture hook did not inject the
intended race. That test still needs correction: MLSD uses CWD plus an empty
command argument, so its hook cannot identify `/Flash` by the MLSD argument.
Neither problem was hidden with skips or policy changes. Work stopped on the
source contradiction rather than continuing verification of an invalid premise.

Normal/optimized full suites, the broader affected regressions and Offline Test
Lab were **not run** in this implementation pass. The R5 baseline remains 1,123
methods / 1,087 pass +36 existing skips; this draft adds 27 methods, removes and
renames none, and adds no skips (expected discovery total 1,150, not yet run).
The two existing method bodies adapted above keep their original method names.
Tracked and untracked whitespace checks and bounded static draft scans are
recorded in the stop report; they cannot substitute for the missing verification.

**STOP: resolve the CRT policy/design contradiction before implementation resumes.
No physical qualification or Git publication is authorized by this draft.**


## Authorized resumption and implementation review — 4 October 2026

### Authority, preservation and narrowly amended policy

Resumed the existing partial checkout in place, without reset, discard, recreation,
fetch, staging, commit or push. HEAD and local `origin/development` remained
`dab627979b9d3bb085c955c6e3bea8cdaff8b338`, parent
`8ac1b24cb70f996b877b3eef81fd1c5817748bff`, subject
`Implement R5 Core-owned headless reads`, divergence `0 0`.
Initial inventory exactly matched the eight stopped files: six tracked changes
(+259/-79), the 376-line R6 document and 382-line test file, total +1017/-79.
No unrelated dirt was found. Starting RU was user-supplied 41%, not measured.

Explicit review authorized changing only the impossible CRT predicate from
`data[:16] != b'C64 CARTRIDGE   \x00'` to
`data[:16] != b'C64 CARTRIDGE   '`. The latter is exactly the 16-byte space-padded
signature at offsets 0x00–0x0F. Offset 0x10 belongs to the following header-length
field. This corrects a pre-existing unreachable acceptance predicate as an R6
prerequisite; it is not general Flash-policy broadening. No header-length, type,
EXROM/GAME, CHIP-packet, extension, filename, size, path or CFG rule was added,
removed or relaxed. R5 did not implement deeper CRT-header parsing.

Regression coverage accepts the exact signature in a 64-byte fixture, exercises
successful managed cartridge publication, and alters each of the 16 signature
bytes independently to prove refusal before adapter access/mutation. Values 0,
1 and 255 immediately after the signature prove that offset 0x10 is outside the
comparison without introducing a new header-field rule. Existing policy matrix
still rejects short/malformed CRTs and wrong extensions.

The independent immediate-pre-MKD race fixture formerly looked for `/Flash` in
the MLSD argument, but the transport uses CWD followed by argument-free MLSD.
The hook now reads the latest CWD from the loopback command trace and injects the
race after the first `/Flash` listing. Assertions require at least two parent
observations, no MKD, exact-directory appearance accepted as already present,
and wrong-case appearance refused before STOR. Production race checks are intact.

### Completed behavior and lifecycle review

Both local Upload file and remote Copy selected drive file converge on immutable,
private, nonempty snapshots of at most 16 MiB and the same managed Flash publisher.
Remote preparation requires a captured-session adapter and bounded SIZE/RETR/SIZE;
execution never rereads either source. No filesystem spool is introduced.

Publication validates the exact Flash parent/selected directory, optionally issues
one managed MKD after immediate revalidation, checks final/staging absence,
performs exact-length STOR, independent RETR/hash then SIZE, rechecks destination
and directory identity, and publishes with managed RNFR/RNTO. Acknowledged MKD,
unknown creation, staging candidates, unknown publication and acknowledged RNTO
retain structured evidence. No overwrite, automatic cleanup, retry, reconnect,
replay, raw publication fallback, activation, application, reset or settings change.
One execution lease spans the composite and is released on all terminal paths.
The documented external-writer race and same-length source-rewrite limits remain.

The raw body of `native_files._upload_flash` is directly replaced. Flash publication
has no `transfers.connect`, `open_ftp`, raw STOR/RETR/SIZE/rename route. Remote Flash
preparation explicitly refuses a missing adapter before the separate native-read
compatibility fallback could be reached. Shared `transfers.connect`, `open_ftp`,
and deferred native/disk/USB/upload/replacement compatibility remain for later
closure. Generic 3C defaults and accepted behavior are unchanged.

Completed the stopped draft's outstanding pre-task lifecycle review: FileService
uses the existing CoreJob failure-result seam for queued cancellation and stale
session rejection, preserving structured unstarted evidence without changing
CoreJob or scheduler semantics. Consumed snapshot bytes are cleared on task exit,
pre-task failure and failed scheduler admission. GUI result formatting preserves
consequence summaries on failure/cancellation, success and connection changes.

### Verification commands, failures and corrected reruns

All consequential transport tests used real loopback control/data sockets, never
hardware. The original stopped iteration above is preserved: 53 methods, 50 passed,
three methods with failing subcases (two CRT errors and two race assertions).

On resumption the first sandboxed focused run executed 54 methods but encountered
49 socket-fixture error subcases (`PermissionError`). The authorized loopback
rerun of the identical command passed all 54 methods after the two corrections.
Following lifecycle completion, the same focused command passed all 56 methods:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python3 -m unittest test_r6_flash test_native_files test_file_service test_core
```

Directly affected regressions, final result **274 passed, zero skips**:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python3 -m unittest test_c64u_ftp test_ftp_mutations test_ftp_uploads test_ftp_streaming test_ftp_reads test_ftp_folder_steps test_ftp_replacements test_ftp_replacement_corrections test_empty_upload test_upload_cleanup test_native_files test_r5_headless_reads
```

Its first run had one obsolete boundary assertion in
`test_deferred_composites_keep_explicit_legacy_routes`: it required raw
`ftp.rename` in `native_files`. The initial normal and optimized full runs each
had the same single failure (1,153 run, 36 existing skips). Updated that assertion
to require managed Flash rename and absence of raw publisher calls, retaining
all checks for deferred transfers/replacement/native-read routes and `open_ftp`.
No production behavior or policy was changed to satisfy it; no method was removed,
renamed, weakened into a skip or deleted. All three corrected reruns passed.

Full normal and optimized suites, **each 1,153 run: 1,117 passed +36 existing skips**:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 python3 -O -m unittest discover -s tests -p 'test_*.py'
```

Offline Test Lab: **17 checks, all pass**:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m c64u_browser.test_lab --suite offline
```

Accounting against committed R5: 1,123 discovered methods / 1,087 passed +36 skips,
plus 30 new R6 test methods (27 retained from the stop, three added on resume).
No removals/renames and no new skips. AST definition enumeration includes the
existing non-test helper `test_core.FakeClient.test_connection`, so raw definitions
are 1,124 → 1,154; actual unittest discovery is 1,123 → 1,153.

### Ownership, privacy and whitespace review

- AST comparison of every pre-existing native policy/read/config function against
  R5 passes after substituting only the authorized CRT literal. Publisher functions
  are the deliberate managed replacement. No other native policy change.
- Generic transfers/3C, FTP adapter, files/deletion/replacement/folder-copy,
  Core/jobs/scheduler and deferred disk/USB modules remain unchanged from R5.
- Static publisher and GUI routing assertions plus raw-factory traps verify the
  two source paths converge without raw Flash publication. Loopback tests retain
  mutation/transfer evidence, prohibit cleanup, check no replay and zero leases.
- Bounded scans of all changed/new files found no credential/private-key/token or
  private home-path additions. Runtime result checks exclude source payload bytes
  and untrusted server prose. Results contain safe remote candidates and hashes;
  no new private temporary path exists. User-selected source metadata in the
  existing review preview is retained.
- Syntax checks and trailing-whitespace checks include untracked files;
  `git diff --check` and no-index checks of both new files pass.

**No unresolved source/design contradiction or design deviation remains.** The
extra ownership-test adjustment is directly earned by the approved raw Flash
retirement. Final compatibility closure is deferred. Stop for R6 implementation
review. Physical qualification is pending and was not performed; no physical
device contact or Git publication occurred.

## Exact-path cleanup prerequisite — implementation and focused review

4 October 2026: **READY for the already-approved controlled R6 physical
qualification**, based on deterministic evidence only. Starting RU baseline was
user-supplied **38% remaining**, not a fresh measurement. The supplied pre-physical
review approved R6 itself subject only to this separately reviewed cleanup method.
Authority remains HEAD = local origin/development =
`dab627979b9d3bb085c955c6e3bea8cdaff8b338`, parent
`8ac1b24cb70f996b877b3eef81fd1c5817748bff`, subject
`Implement R5 Core-owned headless reads`, divergence `0 0`, empty index.
The initial nine-file R6 worktree (+1267/-87 including untracked files) was preserved.

Ordinary USB/SD reviewed deletion remains unchanged and still refuses Flash.
The new internal FileService `prepare_flash_cleanup(path, expected_size,
expected_sha256)` / `execute_flash_cleanup(plan_id)` delegates to
`flash_cleanup.py`; it is not exposed through a GUI. Exactly one ordinary basename
under an existing exact `/Flash/roms`, `/Flash/carts`, or `/Flash/configs` is
accepted. Caller-supplied size is a nonempty integer bounded by the existing
16 MiB Flash limit; SHA-256 is mandatory. This is fixture identity checking, not
content approval for activation. No directory creation/deletion, recursion,
multiple targets, wildcard expansion, overwrite, raw transport, reconnect,
mutation replay, settings or activation operation exists in this helper.

Preparation captures the verified Core session, bound profile and managed
connection binding; exact parent/type/case checks and SIZE → bounded full
RETR/hash → SIZE → parent/target/type/size recheck must pass. No lease spans review.
The frozen preview identifies a private expiring, discardable, single-use plan;
execution accepts only its ID. Execution repeats the complete verification in
one managed operation, checks session/binding/cancellation, then issues exactly
one `adapter.mutate('delete', exact_path)`. The safe mutation dictionary is retained
before subsequent checks. Unknown reply stops for independent inspection without
retry. After acknowledgement, independent parent/target observation must establish
absence; cancellation or failure retains acknowledgement and reports verification
incomplete. All tested terminal paths release their leases. Public evidence holds
only exact path, expected/observed counts/hashes, device/session/plan IDs, phases,
mutation reply evidence and inspection guidance, never bytes or server prose.

**External-writer limitation:** listing, hash verification and DELE are not atomic
compare-and-delete. A same-size rewrite after the last RETR, or replacement with
indistinguishable observed metadata/content, cannot be reliably detected. The new
suite includes an explicit same-size race witness; it does not claim exclusion of
external writers. Physical qualification still requires controlled disposable
fixtures and stopping for inspection on uncertainty.

Focused/direct regression command (authorized localhost fixtures only):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python3 -m unittest test_flash_cleanup test_file_service test_core test_jobs test_scheduler test_deletion test_files test_ftp_mutations test_c64u_ftp test_ftp_reads test_ftp_streaming test_ftp_uploads test_r6_flash test_native_files test_fresh_folder
```

**293 tests passed, zero skips**, including **18 new cleanup tests**. Coverage
includes all three parents, invalid path/type/size/hash, case ambiguity, changed
or missing targets, repeat hash, stale/reconnected/recovering bindings, queued and
pre-DELE cancellation, cancellation after acknowledgement, lost/rejected replies,
failed absence verification, release failure, expiry/discard/single use, payload
and server-prose privacy, prohibited mutations, ordinary Flash-delete refusal,
and existing R6 publication. The first 15-test run had one fixture assumption
failure: idle manager invalidation alone does not change the Core session. The
fixture now marks recovery explicitly; actual same-device reconnect is separately
tested. No socket restriction occurred; loopback execution was authorized directly.

No broad full-suite rerun was necessary: the only shared-file additions are the
cleanup plan registry lifecycle and two FileService delegates. Existing deletion,
publication, FTP adapter, Core, scheduler and job behavior were not modified.
Relevant lifecycle and transport regression families passed. Syntax, static
mutation/ownership and secret scans, `git diff --check`, and whitespace checks
including every untracked file passed. The new helper contains exactly one
mutation call, literal `delete`, and no raw/fallback/reconnect path.

This pass changed only `c64u_browser/flash_cleanup.py`, the small integration in
`c64u_browser/file_service.py`, `tests/test_flash_cleanup.py`, and this appended
section. Existing R6 policy/publisher and its other files were preserved.
**Physical qualification has not been performed. No physical device contact,
commit, push, branch, tag, package, release or final compatibility closure occurred.**


## Controlled physical qualification — both devices passed

4 October 2026: **R6 physically qualified on Beige, then Founder; stop for final
R6 review. Uncommitted and unpushed.** Starting RU baseline: user-supplied 36%
remaining, not a fresh usage measurement. The explicit request authorized device
contact and exactly one harmless disposable publication/readback/verified deletion
per device. Beige's acknowledged deletion and independent final absence completed
before Founder was contacted. No preparation handle or session was reused.

### Authority and preserved implementation

Before contact and after both runs, cwd was the existing
`argonaut-network-slice2` repository; HEAD = local `origin/development` =
`dab627979b9d3bb085c955c6e3bea8cdaff8b338`, parent
`8ac1b24cb70f996b877b3eef81fd1c5817748bff`, subject
`Implement R5 Core-owned headless reads`, divergence `0 0`, empty index.
No fetch or Git publication occurred. The pre-contact worktree reconciled to
eleven files: seven tracked modifications (+327/-89) and four untracked files
(1,521 lines), total +1,848/-89. These were the completed R6 implementation and
cleanup prerequisite: no unrelated dirt. All implementation/test files were
preserved; this pass changes documentation only. Tracked and untracked whitespace
checks passed before contact and after documentation.

### Execution safeguards and validation

A temporary qualification wrapper loaded the exact saved Development profiles
with `ARGONAUT_DEVELOPMENT=1`, then called normal Core `connect(require_bound=True,
initial_browse=False)` without saving/binding profiles or remembering credentials.
Only REST GET info/version was allowed. Actual FileService
`prepare_native_upload` / `execute_native_upload` published the private validated
snapshot. Actual `prepare_flash_cleanup` / `execute_flash_cleanup` performed the
reviewed exact-path cleanup. Independent observations used the same Core-owned
managed adapter and fresh operation leases. No raw FTP shortcut/fallback was used.

The wrapper refused every mutation except the one exact staging STOR, staging
RNFR, disposable-destination RNTO, and later exact disposable DELE. Adapter and
managed send-boundary guards blocked MKD/RMD and unauthorized commands before
submission. The selected parent was revalidated immediately before execution and
again before STOR; actual R6 also performed its directory and destination checks.
No guard was triggered on either device. No missing directory was created.

A real loopback rehearsal of the wrapper passed before hardware, observing exactly
STOR/RNFR/RNTO/DELE and successful final absence. The initial sandboxed rehearsal
could not open its loopback socket (PermissionError); the authorized unsandboxed
rerun passed. Prior accepted deterministic evidence remains 293/293 focused and
affected tests for the cleanup prerequisite, with earlier R6 suite evidence above.
No production source changed, so no redundant full-suite rerun was performed.

### Per-device evidence

**Beige — passed**

- Saved profile: `03abf121-7fee-4af4-937c-e1f7375f6124` / `C64-Ultimate-7F01C9`.
  Current host `192.168.68.70`; reported and bound ID `25EA78`;
  firmware `1.1.0s2`; API `0.1`; managed FTP port 21.
- Approved child observations: roms: exact existing directory; configs: exact existing directory; carts: exact existing directory. No case/type ambiguity.
  Selected existing `/Flash/roms`; directory disposition `already-present`.
- Exact disposable path: `/Flash/roms/r6-1131e03e908085725de0.bin`.
  Harmless ROM storage fixture: 1 byte (`x`), SHA-256
  `2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881`. Destination absent case-insensitively before publication;
  no overwrite/replacement was performed.
- Exact staging path: `/Flash/roms/argonaut-part-7b3df6ebba484839a7e684c32a849087`. Candidate absent before STOR.
  Validation and private snapshot passed; STOR exact length 1, replies 150/226,
  sent hash matched. Independent staged readback/hash and SIZE passed; fresh
  destination absence recheck passed. Managed RNFR 350 / RNTO 250 acknowledged
  publication, disposition `published`; no unknown result.
- A fresh managed operation independently read the final file: exact count 1 and
  expected SHA-256 matched; SIZE matched. Listing proved the recorded staging
  name absent and found no `argonaut-part-` candidate in the selected directory.
- Cleanup plan `436ec195d5ba402c927bf9b3c0352f15`: managed parent/target/type/case observation,
  SIZE/full RETR SHA-256/SIZE and metadata recheck passed. Expected and observed
  size/hash were identical. Exact target and this evidence were reported before
  execution; no lease spanned review. The single-use execution repeated complete
  verification in the captured binding/session and passed `pre_delete`.
- Exactly one managed DELE of that path: reply 250, outcome `completed`,
  consequential submission acknowledged. Cleanup's independent absence check
  passed. A subsequent fresh managed final parent listing again proved the
  disposable name and recorded staging name absent, with no staging candidates.
- Core session/connection epoch: `98f633a778f845be95409d47d4f5bbf8`,
  device key `id:25EA78`. The same captured session and
  connection binding persisted throughout; this implementation has no separate
  numeric epoch. Active leases were zero at connection, preparation, publication,
  independent readback, cleanup preparation/execution and final observation.
- Managed command diagnostics independently confirm totals: STOR 1, RNFR 1,
  RNTO 1, DELE 1, MKD 0, RMD 0. Cleanup issued no STOR/RNFR/RNTO/MKD/RMD or second
  DELE. No forbidden-operation attempt, automatic retry or uncertainty occurred.

**Founder — passed**

- Saved profile: `950b2e81-64cc-4a92-a159-4dd5f0c2c712` / `C64-Ultimate-2B02C3-eth`.
  Current host `192.168.68.69`; reported and bound ID `25BE71`;
  firmware `1.1.0`; API `0.1`; managed FTP port 21.
- Approved child observations: roms: exact existing directory; configs: absent; carts: exact existing directory. No case/type ambiguity.
  Selected existing `/Flash/roms`; directory disposition `already-present`.
- Exact disposable path: `/Flash/roms/r6-42bd369c03b23919fbec.bin`.
  Harmless ROM storage fixture: 1 byte (`x`), SHA-256
  `2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881`. Destination absent case-insensitively before publication;
  no overwrite/replacement was performed.
- Exact staging path: `/Flash/roms/argonaut-part-ac2847b3640445a7a0cc6266d4a2b4a6`. Candidate absent before STOR.
  Validation and private snapshot passed; STOR exact length 1, replies 150/226,
  sent hash matched. Independent staged readback/hash and SIZE passed; fresh
  destination absence recheck passed. Managed RNFR 350 / RNTO 250 acknowledged
  publication, disposition `published`; no unknown result.
- A fresh managed operation independently read the final file: exact count 1 and
  expected SHA-256 matched; SIZE matched. Listing proved the recorded staging
  name absent and found no `argonaut-part-` candidate in the selected directory.
- Cleanup plan `85c215b96f984ee1976d3cd0db3a513a`: managed parent/target/type/case observation,
  SIZE/full RETR SHA-256/SIZE and metadata recheck passed. Expected and observed
  size/hash were identical. Exact target and this evidence were reported before
  execution; no lease spanned review. The single-use execution repeated complete
  verification in the captured binding/session and passed `pre_delete`.
- Exactly one managed DELE of that path: reply 250, outcome `completed`,
  consequential submission acknowledged. Cleanup's independent absence check
  passed. A subsequent fresh managed final parent listing again proved the
  disposable name and recorded staging name absent, with no staging candidates.
- Core session/connection epoch: `32a2253ac4a04f34a8262222dc880dfe`,
  device key `id:25BE71`. The same captured session and
  connection binding persisted throughout; this implementation has no separate
  numeric epoch. Active leases were zero at connection, preparation, publication,
  independent readback, cleanup preparation/execution and final observation.
- Managed command diagnostics independently confirm totals: STOR 1, RNFR 1,
  RNTO 1, DELE 1, MKD 0, RMD 0. Cleanup issued no STOR/RNFR/RNTO/MKD/RMD or second
  DELE. No forbidden-operation attempt, automatic retry or uncertainty occurred.

### Scope, limitations and final stop

Both devices completed all required publication/readback/exact cleanup/absence
steps. Missing-directory MKD remains **deterministic-only**. Founder's absent
`configs` directory was left absent. No ROM/cartridge selection or activation,
configuration application, reset/reboot or settings mutation occurred. No
directory deletion, recursive/wildcard cleanup, overwrite, reconnect/replay after
failure, raw FTP fallback, physical fault injection or compatibility work occurred.
Fresh operation-scoped FTP connections are normal managed leases, not failed
operation reconnect/replay; Core session identity remained unchanged.

Evidence is managed send/reply-boundary instrumentation, **not packet capture**.
It proves commands and replies in this process, not firmware-internal activity
or exclusion of outside writers. Listing/recheck plus rename is not atomic
no-replace; hash verification plus DELE is not atomic compare-and-delete. The
same-size external-writer window remains. Physical coverage used a one-byte ROM
storage fixture in existing roms only; CFG/CRT validation, missing-directory MKD,
cancellation and fault/uncertainty paths retain deterministic coverage.

The qualification wrapper and safe detailed transport logs remain temporary
local evidence; this record contains no secrets or raw CRT payload. Documentation
updated: this record, CURRENT-STATE.md and the directly affected current Flash
ownership note in C64U-FTP.md. No implementation/test files changed in this pass.
No commit, push, tag, package, release, branch/worktree creation or next checkpoint
work. **Stop for final R6 review.**
