# R5 — Core-owned headless reads

Status: **implemented, deterministically verified, and read-only physically qualified
on Beige and Founder; final R5 review pending**.
**Not committed or pushed.** Implementation authorized
explicitly on 4 October 2026, with starting RU **55% remaining**.

The design below was reviewed and approved before implementation. Its historical
57% design baseline and design-only stop language are superseded by that explicit
implementation authorization. R4 remains accepted, committed and pushed. This
checkpoint does not complete Flash or Network Foundation.

## Authority and scope

Verified 4 October 2026 in the existing `argonaut-network-slice2` checkout:
HEAD and local `origin/development` both
`8ac1b24cb70f996b877b3eef81fd1c5817748bff`; parent
`a081b01c4a62198b35b88199c4c8e48f9c535f90`; divergence `0 0`;
clean worktree; subject `Implement R4 managed C64 AI installation`.
No fetch or device access was needed. R1–R4 occupy the existing doc sequence.

The completed post-R4 reassessment is the starting evidence: remaining live raw
FTP groups are CLI ls/browse/get, headless Test Lab storage, and Flash. Existing
managed listing and 3A download suffice. This pass resolves their application
boundary, not another ownership audit. Source anchors: `__main__.py`,
`fresh_folder_cli.py`, `core.py`, `hardware_checks.py`, `test_lab_cli.py`,
`api.py`, `transfers.py`, and their existing parser/read/streaming tests, all
under `c64u_browser/` or `tests/`.

## A. Exact CLI compatibility decision

Require **one explicit saved bound `--profile-id` for ls/get**. Do not accept a
host form, infer a device identity, or silently use the selected profile. Reuse
R2's profile validation and private prompt helpers; retain put-new's existing
selected-profile behavior and structured output unchanged.

| Command | Accepted invocation and behavior |
|---|---|
| `info` | Keep `--host HOST [--password] [--port N] [--timeout S] [--encoding utf-8\|latin-1] info`; reject `--profile-id`. Keep current defaults (21, 10, utf-8), validation, optional ignored positionals, REST `info()` JSON and errors. Port/encoding remain accepted legacy constructor options with no FTP activity; timeout still controls REST. Do not load/connect Core. |
| `ls` | `--profile-id ID [--password] ls [PATH]`; default `/`, absolute path required, no destination positional. Return existing JSON `{path, entries}` with name/kind/size records, managed presentation ordering and server PWD. No remembered-folder substitution. |
| `get` | `--profile-id ID [--password] get SOURCE DESTINATION`; both positionals required. Keep existing remote-file validation (file below supported USB/SD storage), local destination interpretation, stderr byte progress and success JSON `{path, bytes, sha256}`. |
| `browse` | Remove from command choices, help and dispatch; remove interactive loop and `display`. Invocation is an unsupported-command parser error, exit 2, stderr only, no prompt/network. No alias. |

For ls/get reject `--host`, `--port`, `--timeout`, `--encoding` even when equal to
old defaults. Use saved HTTP/FTP ports, Core defaults and utf-8 display decoding;
no per-command overrides. This intentionally retires the legacy tuning forms
rather than pretending they configure the managed transport. Global help must
state command-specific option scope. Keep existing option placement/`--`
handling; reject repeated profile selectors, missing selectors, mixed host/profile
forms, and extra positionals before credentials or network. Parser failures use
a fixed safe usage message (no echo of supplied values), exit 2 and empty stdout.
Unknown, corrupt, ambiguous or unbound saved profiles are runtime failures, exit 1.

ls/get success exits 0; operational/cleanup failure exits 1; interrupt/EOF exits
130. Failures have safe category-based stderr and no success JSON. Do not print
arbitrary exception/peer prose. Drain cancellation before closing Core, and do
not claim that an already published destination was removed if interruption
arrives after publication. Keep info's existing 0/1/2/130 behavior.

For ls/get `--password` means private terminal prompting via R2's guarded
`getpass`: refuse echoing fallback, never read a piped password implicitly, enforce
existing length/control-character bounds. Without the flag, never prompt: use
Core's private entered/session/stored/empty credential resolution. Empty entered
input retains that existing fallback behavior. No password argument value, new
stdin switch, environment credential, save, remember, profile binding or preference
write. Authentication failure ends the run; no retry prompt. Secrets must not
appear in output, parser errors, events or history.

## B. One Core connection path, optional initial browse

Add keyword-only `initial_browse=True` to `Core.connect`. Default/GUI and R2
behavior stay unchanged. With `False`, perform the same credential resolution,
REST test, saved identity verification, `_prepare_read_session` adapter setup
and `_begin_session` commit, but skip `initial_directory` and all FTP acquisition.
Return `ConnectionResult` with `remote_path=''`, `entries=()` meaning **unbrowsed**,
not a verified empty root. Reject simultaneous explicit `remote_folder` in this
mode. No second connection implementation; no change to reconnect behavior.
Headless callers use `require_bound=True`, `bind_identity=False`, `persist=False`,
`remember=False`. CLI info never enters this path.

Expose thin Core read operations for listing and download, returning data/jobs,
not `UltimateClient`, `device_operations`, adapters, leases or FTP facades.
Capture `device_session()` at submission, use the existing scheduler's device
lane and verify that same session at execution and through the operation's
check callback. Inside Core, use `_require_client`, `read_operation`, existing
managed listing and `transfers.download`/3A; do not build a second FileService or
FTP primitive. Download retains the accepted 3A staging, SIZE/RETR/SIZE, exact
count/hash, flush/fsync, atomic no-replace publication and cleanup contract,
including existing destination/symlink/concurrent publication refusal.

One lazy operation-scoped lease; nested helpers share it; outer exit releases
on success, failure or cancellation. `_ftp_password(binding)` remains the private
credential supplier. Stale/recovering bindings fail before further access and
before publication; never rebind, reconnect, replay or fall back to raw FTP.
Managed MLSD and narrowly permitted LIST fallback, display decoding and separate
raw-octet identity semantics remain unchanged. ls/storage list exactly their
requested path, with no startup-directory fallback.

## Headless Test Lab integration

Keep the four existing IDs/order/meaning: `hardware.identity`, `hardware.drives`,
`hardware.storage`, `hardware.version_stability`. Add a Core-backed runner (or
thin callbacks into the existing check builder), keeping the already-managed GUI
entry valid. Headless identity check itself performs the no-browse connection;
do not connect before `run_checks` and turn device failures into setup failures.
Firmware/API assertions use that connection's verified info without an extra
REST test. Drives/version remain REST checks behind the verified prerequisite;
storage lists `/` through the captured Core session. Keep execution synchronous
within the check/event collector, using the shared managed operation body rather
than losing thread-local diagnostic events in a worker.

No profile: identity skips `not_connected`; unbound profile: `identity_unbound`,
both without network. REST/identity failure: identity fails, subsequent checks
skip `identity_prerequisite`. FTP refused/authentication failure/timeout or root
550: identity may pass, **storage fails**, other REST checks still run. Preserve
safe `error_kind` categories (including Core `code` to existing identity/network
kind mapping), not arbitrary exception class changes. Storage 550 is unavailable,
not assumed nonexistent. Keep reports/history and exits pass=0, fail=1, skip=2,
setup/history failure=3, and existing selector/Development preference rules.

Retain Test Lab's `--password-stdin` bounded private input and no interactive
prompt; pass it into Core, without persistence. Retain `--timeout` 1–30/default 10
for hardware: add an optional Core construction-time network timeout that sets
REST timeout and the lease manager's existing FtpPolicy control-connect/reply,
data-connect/idle and final-reply limits to this value. Omission leaves all Core
defaults unchanged. Configure once before connecting; no mutation of active leases
or new transport options. Fleet invokes this same per-profile runner; watch and
background continue through that route. Close Core in every outcome, after active
work drains; no retained lease between checks/runs. Offline suite remains offline.

## Migration and retirement boundary

The narrow caller scan agrees with the reassessment; historical evidence stays.

| Facility | Decision and bounded consequence |
|---|---|
| CLI ls/get | Migrate to the above Core operations; no raw imports/ownership in their route. |
| Headless storage | Migrate shared hardware runner and its fleet/watch/background entry; GUI behavior retained. |
| `Profile.client()` | **INCLUDE NOW**: sole production caller is `test_lab_cli`; remove after migration. |
| `api._list_directory` and ordinary-listing FTP construction | **INCLUDE NOW**: headless callers are the last live ordinary raw users. `list_directory` requires managed adapter and fails closed otherwise. Adapt direct listing simulations/tests to managed fixtures. This factory is inline, not a shared standalone function. |
| Raw `_download` branch | **INCLUDE NOW**: CLI get is the last live raw download; other production downloads already carry adapters. Missing adapter fails closed. Adapt the two download simulations and affected raw mocks without reducing assertions. Remove download's dependency on `connect`, not the module's factory. |
| CLI browse loop/`display`, now-unused imports | **INCLUDE NOW**, directly obsolete. |
| `CoreDeviceOperations.open_ftp()` | **DEFER**: reassessment finds it production-unreachable, but its dynamic `transfers.connect` branch and USB compatibility doubles remain. Its deletion is not necessary for headless migration; avoid coupling their retirement to R5. |
| `transfers.connect()` | **DEFER**, Flash still uses it. No shared factory deletion. |
| Raw identity listing/`parse_list`/api ftplib import | **DEFER** where still needed by identity compatibility and offline parser checks; ordinary listing removal does not prove these dead. |
| Upload/replacement/mutation/native/disk/USB fallbacks | **DEFER**; do not remove shared simulation upload helpers or broaden compatibility cleanup. |

## Deterministic test contract (implementation phase only)

- Split `test_fresh_folder_cli`'s legacy four-command assertion: preserve info
  invocation/output and R2 tests; cover new ls/get parser matrix, missing/duplicate/
  ambiguous/unbound profile, host conflicts, tuning-option rejection, default `/`,
  extra/missing positionals and browse absent from help/dispatch with exit 2.
- Prove info REST success/failure independent of FTP with Core connect and all
  FTP creation forbidden. No-browse Core connect verifies identity and commits
  one epoch with zero FTP connections; default initial browsing remains unchanged.
- Use existing `FakeC64UFtp`, `test_ftp_reads` and `test_ftp_streaming` fixtures
  for managed listing JSON/order, strict encoding, MLSD/LIST fallback, get exact
  bytes/hash (including empty), no overwrite/race, cancellation and local cleanup.
  Cover stale binding before execution and during transfer, no replay, unchanged
  epoch, one lease per operation and zero active leases afterward.
- Exercise private prompt refusal without terminal, stored/empty credentials,
  bad authentication, cancellation and poisoned exception/parser values. Assert
  credential absence in stdout/stderr/events/history, including failure paths.
- Preserve hardware IDs/statuses/skips/error kinds/exits with identity mismatch,
  FTP unavailable and storage 550; drives/version still run after storage failure.
  Assert history/event collection, timeout propagation and lease release. Cover
  fleet plus watch/background routing to the same managed runner without
  `Profile.client`; keep existing GUI immediate hardware behavior.
- Add narrow static assertions for no raw FTP construction/factory/facade access
  in migrated routes and absence of included retired helpers. Adapt
  `simulated_c64u` listing/download checks with managed in-memory seams; keep
  offline execution network-free and preserve check IDs/meaning. Use loopback
  fixtures for transport assertions, not physical endpoints.
- Run affected CLI/Core/FTP/hardware/automation/simulation tests and existing
  normal/optimized regression suites plus Offline Test Lab. Retain Flash and
  unrelated compatibility regression coverage; no R4-scale fault matrix.

## Later physical acceptance and stop conditions

Only after implementation review and separate physical authorization: one short
read-only run on each Beige `25EA78` and Founder `25BE71`. Actual CLI ls of known
storage, actual get of an existing harmless file to a fresh local destination,
independent local bytes/hash comparison with accepted evidence, and headless
`hardware.storage` through the managed path. Prefer previously accepted Beige
`/USB1/sid/arcademem.sid` and Founder `/SD/test.txt` if still available. Verify
stable captured session and zero active leases after each operation. No remote
writes, file preparation, device resets or fault injection; absent/changed files
require another agreed existing file or separately authorized setup.

Stop implementation for review if authority changed, unrelated edits appear,
identity/credentials/session guarantees cannot be maintained, a proposed deletion
has a live caller, or fixture adaptation requires broad compatibility redesign.
Do not silently enlarge R5; defer a retirement and report it if its bounded proof
fails. The historical design pass ran no tests and contacted no devices; no staging, commit,
push, merge, tag, branch/worktree, package or release activity.

Expected payoff: all supported CLI and headless Test Lab FTP reads become
Core/session-owned; browse and directly obsolete raw read facilities disappear.
Flash remains the next live raw writer; broader compatibility retirement and
final closure remain separate. No unresolved design choice blocks direct bounded
implementation approval after this document is reviewed. **Historical design-review stop; superseded by implementation authorization.**


## R5 implementation record — 4 October 2026

**Stop for R5 implementation review.** No physical acceptance or Git publication
was performed. No unresolved implementation issue or design deviation is known.
The later acceptance procedure above remains design-only and requires separate
physical authorization; no setup file or remote write was needed or attempted.

### Authority and scope

The existing checkout is
`/home/bruce/Documents/ChatGPT/Local Projects/argonaut-network-slice2`.
Before and after implementation, HEAD and local `origin/development` are
`8ac1b24cb70f996b877b3eef81fd1c5817748bff`, with parent
`a081b01c4a62198b35b88199c4c8e48f9c535f90`, subject
`Implement R4 managed C64 AI installation`, and divergence `0 0`.
Initial dirt was exactly modified `docs/CURRENT-STATE.md` (+21/-7) and the
196-line untracked R5 design: combined **+217/-7**. The index stayed unchanged.
No fetch, commit, push, merge, tag, branch/worktree, package or release occurred.

### Implemented behavior

- `info` retains its REST-only constructor, JSON, optional ignored operands,
  defaults, meaningful options and 0/1/2/130 exits. It never connects Core or
  acquires FTP. `--profile-id` is rejected. Its legacy explicit password prompt
  remains unchanged.
- `ls/get` require exactly one explicit saved bound `--profile-id`. Unknown,
  ambiguous, corrupt and unbound profiles fail with exit 1 before FTP. Missing
  or repeated selectors, mixed host/profile forms, any legacy host/port/timeout/
  encoding option, malformed arguments, and extra/missing operands fail with
  exit 2, fixed safe stderr and empty stdout. Option-aware routing, abbreviations,
  attached values, option values/operands named after commands, and `--` remain
  supported. `put-new` keeps selected-profile fallback and structured errors.
- `ls` defaults to `/`, requires an absolute path, performs exactly the requested
  listing, returns server PWD and managed sorted `{path, entries}` JSON, and
  never substitutes a remembered folder. `get` requires source/destination and
  validates the existing USB/SD remote-file scope. Its managed 3A download keeps
  SIZE/RETR/SIZE, exact count/hash, fsync, no-replace publication, local staging
  cleanup, byte progress, and `{path, bytes, sha256}` JSON.
- For `ls/get`, only explicit `--password` invokes R2's guarded private prompt.
  Without it, Core resolves entered/session/stored/empty credentials without
  prompting. No password value, stdin credential option, persistence or retry
  prompt was added. Operational and cleanup failures exit 1 with bounded
  category stderr and no success JSON; cancellation/EOF exits 130 and drains
  active work before closing Core. Late cancellation after publication preserves
  success; cleanup failures warn to inspect the destination rather than claiming
  an already published file was removed.
- `browse` and its `display`/interactive loop are absent from command choices,
  help and dispatch. Invocation deliberately exits 2 without credentials/network.
- `ArgonautCore.connect(initial_browse=False)` performs the existing private
  credential resolution, REST identity verification, `_prepare_read_session`
  setup and normal session commit, but skips `initial_directory` and all initial
  FTP acquisition. It returns `remote_path=''`, `entries=()` and rejects any
  explicit `remote_folder` before connection. Default connect and reconnect
  browsing remain unchanged. Optional construction-time `network_timeout`
  configures REST and all five FTP timeout fields; omission preserves defaults.
- New thin Core `list_directory`/`download` operations capture `DeviceSession`
  at submission and use the existing device scheduler lane. The shared `_read`
  body validates the captured session and retains one lazy operation-scoped
  lease through nested helpers and download publication. No reconnect/replay or
  raw fallback is introduced. FTP failure alone leaves the REST session valid.
- Headless Test Lab connects inside `hardware.identity`, using verified returned
  information without another identity request. First FTP acquisition is in
  `hardware.storage`; authentication/network/550 errors fail that check while
  drives and later version REST checks retain their meaning. Missing/unbound
  profiles and identity-prerequisite skips retain their existing IDs and kinds.
  Core/scheduler `code` is explicitly translated into the collector's `kind`.
  Synchronous diagnostic reads share `_read`; a FIFO scheduler reservation keeps
  them in the collector thread while serializing against device jobs. Reservations
  release/drain on every outcome and cancellation cannot execute an unreserved
  read. Existing GUI checks still use the same check builder. Fleet/watch/background
  continue through the per-profile runner; history, exits and private stdin input
  are preserved, and Core closes after each run.

### Retirements and static proof

Removed `Profile.client()`, the ordinary raw `UltimateClient._list_directory`
implementation/inline factory, the raw download branch and its use of `connect`,
and browse-only code. Ordinary listing/download without a managed adapter fail
closed. No dead production alias or shim remains. Production has no `.client()`
call, and migrated CLI/Test Lab modules have no raw FTP/facade access.

Offline simulations use an explicit network-free managed adapter/lease fixture;
real protocol negotiation, MLSD/LIST fallback and transfer behavior remain covered
by loopback transport tests. Existing API/download mocks were migrated. USB backup
policy tests needed only a 13-line explicit read seam; their mutation fixtures
and production compatibility code were not converted. Raw identity byte listing,
`CoreDeviceOperations.open_ftp()`, `transfers.connect()`, raw/managed upload bodies,
and Flash/native_files/disk_run/USB/replacement/local-copy production modules
were compared with HEAD and remain unchanged. Static import ownership allows the
new offline fixture to import only FTP contract types, not the live transport.

### Deterministic verification and exact accounting

Commands run from the checkout with Python 3.13 and authorized loopback access:

```sh
PYTHONPATH=tests python3 -m unittest test_r5_headless_reads test_fresh_folder_cli test_core test_hardware_checks test_test_lab_cli test_test_lab_fleet test_test_lab_watch test_test_lab_alert
PYTHONPATH=tests python3 -m unittest test_api test_transfers test_cancel_copy test_diagnostics test_ftp_reads test_ftp_streaming test_scheduler test_file_service test_usb_backup test_replacement_source test_test_lab test_test_lab_probe
python3 -m unittest discover -s tests
python3 -O -m unittest discover -s tests
python3 -m c64u_browser.test_lab --suite offline
git diff --check
# For each untracked file, without adding it to the index:
git diff --no-index --check /dev/null FILE
```

| Final verification | Result |
|---|---|
| Focused R5 / CLI / Core / Test Lab / automation | 104 passed |
| Directly affected reads / streaming / downloads / scheduler / compatibility | 120 passed |
| Complete normal suite | 1,123 methods: 1,087 passed, 36 existing skips |
| Complete optimized suite | 1,123 methods: 1,087 passed, 36 existing skips |
| Offline Test Lab | 17 checks passed; exit 0; empty stderr |
| Whitespace, including untracked files | Passed |
| Static ownership, deferred-route comparison and output secret-marker scans | Passed |

R4 baseline was **1,093 = 1,057 pass + 36 existing skips**. R5 adds exactly
**30 methods** in `tests/test_r5_headless_reads.py`. The old combined legacy
info/ls/browse/get test was renamed/revised as `test_legacy_info_route_unchanged`;
its old ls/get/browse expectations are replaced by the new R5 coverage. No other
method was removed, and no new skip was added. Final total: **1,093 + 30 = 1,123**.

Corrected development iterations, retained here rather than hidden:

1. First exploratory normal run: 1,093 tests, 42 failures and 32 errors,
   36 skips. Failures included expected raw-read fixture fallout and a removed
   import still needed by `Profile.validate`; that import was restored. A wrong
   connection-result attribute was also corrected before focused verification.
2. Second exploratory run: 1,064 discovered entries, 1 failure and 8 errors,
   36 skips. A removed simulation fixture still imported by the diagnosis probe
   prevented several test modules from loading; its managed fixture migration
   restored discovery. One remaining download mock and the static import rule
   were corrected. The lower transient count was not accepted as final accounting.
3. First focused run: 99 tests, 1 failed assertion. The help assertion matched
   `browse` inside `browser`; it now tests a whole word. The corrected 99-test
   run and 120-test affected regression run passed.
4. Additional cancellation/cleanup coverage passed at 103 focused tests, then
   both full suites passed at 1,122 (1,086 pass + 36 skips); offline passed 17.
   Final review found a cancelled diagnostic reservation could fall through.
   The guard/cancellation check was added with the 30th R5 method, and every
   verification group above was rerun successfully on the final code.
5. An initial untracked-whitespace wrapper expected `git diff --no-index` exit 0;
   its normal exit 1 for a differing new file was correctly accepted when output
   was empty. No whitespace defect was present.

No loopback sandbox denial occurred; loopback runs used the approved execution
permission. Secret tests cover CLI stdout/stderr, parser errors, Core/job results,
Test Lab events and saved history with synthetic markers. Scans found no such
markers in final suite/offline outputs. These are deterministic checks, not
physical C64U qualification.

### Complete changed-file inventory and final diff

Repository-relative paths; `new` means untracked, not staged. The R5 design was
already untracked at the starting authority check. All other new files below
were created during implementation. No synced ChatGPT project source was edited.

| Status | File |
|---|---|
| modified | `c64u_browser/__main__.py` |
| modified | `c64u_browser/api.py` |
| modified | `c64u_browser/core.py` |
| modified | `c64u_browser/hardware_checks.py` |
| new | `c64u_browser/headless_reads_cli.py` |
| modified | `c64u_browser/profiles.py` |
| modified | `c64u_browser/scheduler.py` |
| modified | `c64u_browser/simulated_c64u.py` |
| new | `c64u_browser/simulated_ftp_reads.py` |
| modified | `c64u_browser/test_lab_cli.py` |
| modified | `c64u_browser/test_lab_probe.py` |
| modified | `c64u_browser/transfers.py` |
| modified | `docs/CURRENT-STATE.md` |
| new | `docs/R5-CORE-OWNED-HEADLESS-READS.md` |
| modified | `docs/TEST-LAB.md` |
| modified | `tests/test_api.py` |
| modified | `tests/test_c64u_ftp.py` |
| modified | `tests/test_cancel_copy.py` |
| modified | `tests/test_diagnostics.py` |
| modified | `tests/test_fresh_folder_cli.py` |
| modified | `tests/test_hardware_checks.py` |
| new | `tests/test_r5_headless_reads.py` |
| modified | `tests/test_replacement_source.py` |
| modified | `tests/test_test_lab_cli.py` |
| modified | `tests/test_test_lab_fleet.py` |
| modified | `tests/test_transfers.py` |
| modified | `tests/test_usb_backup.py` |

Final diff including untracked files: **27 files, +1,427/-341**. This includes the inherited
R5 design/current-state dirt; the R5 pass remains substantially smaller than R4's
recorded +2,922/-218 implementation/review total.

Final static/authority scan command: `python3 /tmp/r5-ownership-scan.py`. Its
record is `/tmp/r5-ownership-verified.log`. Final verification logs are
`/tmp/r5-focused-verified.log`, `/tmp/r5-regressions-verified.log`,
`/tmp/r5-normal-verified.log`, `/tmp/r5-optimized-verified.log`, and
`/tmp/r5-offline-verified.json` (empty `/tmp/r5-offline-verified.err`). These local
verification artifacts were not added to the repository.


## R5 read-only physical qualification — 4 October 2026

**Both devices qualified. Stop for final R5 review. R5 remains uncommitted and
unpushed.** Starting physical-pass RU baseline: **48% remaining**. The preceding
implementation record is historical. The implementation review verdict was
**APPROVE READ-ONLY PHYSICAL QUALIFICATION — no blocker**; the user separately
authorized the exact read-only sequence. Beige completed before Founder began.

### Authority

Before contact, pwd was the existing checkout named above. HEAD and local
`origin/development` were `8ac1b24cb70f996b877b3eef81fd1c5817748bff`, parent
`a081b01c4a62198b35b88199c4c8e48f9c535f90`, subject
`Implement R4 managed C64 AI installation`, divergence `0 0`, empty index.
The reviewed delta matched exactly: 23 modified tracked files plus four untracked
files, **27 files, +1,427/-341**. Tracked and all four untracked whitespace checks
were clean. No unrelated dirt was present. No production code or tests were
changed during physical qualification; only these three existing R5 documents
were updated afterward. No fetch or Git publication operation was performed.

### Execution and safe identities

Used the saved Development profiles from
`/home/bruce/.config/argonaut-development/config.json`, with
`ARGONAUT_DEVELOPMENT=1`. Each process performed Core's identity-bound,
no-initial-browse connection with binding/persistence/remember disabled.

| Device | Saved profile ID / name | Current host | Verified ID | Firmware | API |
|---|---|---|---|---|---|
| Beige | `03abf121-7fee-4af4-937c-e1f7375f6124` / `C64-Ultimate-7F01C9` | `192.168.68.70` | `25EA78` | `1.1.0s2` | `0.1` |
| Founder | `950b2e81-64cc-4a92-a159-4dd5f0c2c712` / `C64-Ultimate-2B02C3-eth` | `192.168.68.69` | `25BE71` | `1.1.0` | `0.1` |

Both reported FPGA `122`, core `1.49`. Identity matched in each precheck, ls,
get and hardware run; host alone was never treated as authority.

Actual parser/entry points were executed through `runpy.run_module(...,
run_name='__main__')` in separate Python processes by the temporary observer
`/tmp/r5-physical-run.py`. This ran the repository's actual CLI and hardware
suite, not substitute listing/download functions. CLI argv was
`--profile-id ID ls PATH` and `--profile-id ID get SOURCE DESTINATION`;
hardware argv was `--suite hardware --profile-id ID`. No credential argument,
password prompt, AI explanation, configuration write or remote setup was used.

| Device | Actual ls (exit 0) | Actual get source (exit 0) | Independent local byte count | SHA-256, equal to CLI and historical evidence |
|---|---|---|---:|---|
| Beige | `/USB1/sid`, one entry, `arcademem.sid` size 8,952 | `/USB1/sid/arcademem.sid` | 8,952 | `a4e2341064d1ef072ddc9d20c2131eb42fdc15027c4330bd9f87c3c0e0d8bb84` |
| Founder | `/SD`, two entries, `test.txt` size 4 | `/SD/test.txt` | 4 | `9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08` |

A newly created unique local directory `/tmp/r5-physical-d9SCCXSC` held
`beige.sid` and later `founder.txt`. Each destination was checked absent before
invocation. After each CLI exited, a separate Python process reread the local
file using `Path.read_bytes()` and independently calculated length and
`hashlib.sha256`, asserting exact historical matches. Each verified local file
was then unlinked; the directory was checked empty after each cleanup. No
staging residue or downloaded-file leak remained. No overwrite/race experiment
was run physically; the unchanged managed 3A implementation and reviewed
loopback tests establish the broader no-overwrite contract.

### Headless Test Lab and process lifetime

Both hardware suite processes exited **0**, overall **pass**, with history saved.
`hardware.identity`, `hardware.drives`, `hardware.storage` and
`hardware.version_stability` all passed on each device; no skips or forced passes.
Identity/drives/version diagnostics contained zero FTP events. All 21 FTP events
in each report belonged to `hardware.storage`, which listed `/` via managed MLSD
and returned five entries on Beige and four on Founder. Each storage run used
one FTP session and disconnected
at its terminal boundary. First FTP access therefore occurred in storage after
the no-browse identity setup, not in an initial directory browse.

The observer checked no FTP send during connect and zero active leases afterward.
Every `_read` terminal boundary retained its captured Core session and had zero
active leases; all six actual CLI/hardware processes recorded zero leases before
close and successful Core shutdown with zero afterward. Separate process session
IDs intentionally differ:

| Device | ls Core session | get Core session | hardware Core session |
|---|---|---|---|
| Beige | `97c47a6c8d674771b422077e887b447f` | `fce505dc914945ebad07c6cc6e1e3b6b` | `753d6f1365a644b8b42a04e9e6442fda` |
| Founder | `503530ff639d48cda9a3dfa7c9fc5377` | `29b56e1f8e8b40af9efbffc057418277` | `06228b66f99d4ffaa38ccf9f095d8b28` |

The original managed send path checks the current connection binding before
sending each command; the observer delegated to that path unchanged. Successful
reads and stable per-run session IDs support binding continuity. These are
application/transport observations, not packet capture or device-wide telemetry.

### No remote mutation: evidence and limits

**No remote writes occurred in this qualification.** The temporary observer
allowlisted read/session FTP verbs before the managed `_send` boundary, rejected
non-GET REST requests, and forbade `ftplib.FTP.connect` raw fallback. No guard
was triggered. It recorded verb names only, never command arguments/passwords.
Observed listing verbs were `USER PASS FEAT TYPE CWD PWD TYPE PASV MLSD`;
download verbs were `USER PASS FEAT TYPE TYPE SIZE TYPE PASV RETR TYPE SIZE`.
No MKD/STOR/RNFR/RNTO/DELE/RMD or other mutation was attempted or observed.
CWD changes the transient FTP working directory, not remote storage. The actual
managed SIZE/RETR/SIZE route completed; no raw listing/download fallback ran.
Static inspection additionally confirmed the reviewed Core-owned routes and
absence of `Profile.client()`. No remote cleanup was needed or issued.

This instrumentation is local send-boundary evidence and normal Test Lab
transport diagnostics, **not packet-level proof**. It does not observe unrelated
processes or firmware-internal activity. The wrapper adds observation/guards and
is not a repository change or a replacement transport. No fault injection,
reset/reboot, Flash/AI/configuration/service writes, cartridge/Streams work,
packaging, branch/worktree creation or next-checkpoint work occurred.

Two preliminary local issues were resolved transparently: the sandbox denied
socket creation before the first contact, then authorized execution reached
Beige identity successfully but the observer could not serialize Core's immutable
mapping. That diagnostic failure also interrupted its close hook before Core.close;
there had been zero FTP acquisition, and the process exited. Only the temporary
observer's JSON handling was corrected. A fresh REST-only precheck then passed
and closed normally before ls began. No managed read failed or became uncertain,
no remote state changed, and no different source was substituted.

Safe raw evidence remains in `/tmp/r5-{beige,founder}-precheck.json`,
`/tmp/r5-{beige,founder}-{ls,get,hardware}.json`, and
`/tmp/r5-{beige,founder}-{ls,get,hardware}-audit.json`; the temporary observer is
`/tmp/r5-physical-run.py`. These local diagnostic artifacts are intentionally
retained for final review; downloaded payloads were removed. Broad deterministic
suites were not rerun for these documentation-only updates.

Final authority recheck after documentation updates matched the opening HEAD,
local origin/development, parent, subject and divergence exactly; the index stayed
empty and the same 27-file inventory remained. Tracked and untracked whitespace
checks passed. Only R5-CORE-OWNED-HEADLESS-READS.md, CURRENT-STATE.md and TEST-LAB.md
were edited in this physical pass. Physical qualification is complete; no Git
publication or next-checkpoint work follows this record.
