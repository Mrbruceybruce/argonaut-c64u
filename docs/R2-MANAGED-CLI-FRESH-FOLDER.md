# R2 — Managed CLI Fresh-Folder Upload

## Status and authority

Approved design implemented on 3 October 2026; **stopped for pre-physical
implementation review**. Deterministic verification is complete as recorded
below. Physical qualification has NOT begun. No commit or push was performed.

Verified development authority: `3f7dace0b2c5b80316919db832dc583d4a19392a`,
with R1 parent `d0e605ebdc29cca15558d7fb6c5bf2dcfc6690bc`.
HEAD equals origin/development, divergence is 0/0, and the worktree was clean
before this design pass. R1 is committed and pushed; accepted 3D is committed
at `8315985317086e52460c981a8135bffb359da958`.

Preserve [SERVER-FIRST.md](SERVER-FIRST.md), the accepted 3C/3D contracts in
[C64U-FTP.md](C64U-FTP.md), and
[R1-MANAGED-FOLDER-COMPOSITES.md](R1-MANAGED-FOLDER-COMPOSITES.md).
Some older status headers in C64U-FTP.md still describe pre-commit checkpoints;
they do not override the accepted commit history. No mandatory Network
Foundation fix has been established as a prerequisite to R2. A discovered
contract conflict must be reported, not silently resolved by changing safety.

## Scope and repository findings

Migrate ONLY production CLI `put-new` mutation ownership to ArgonautCore and
FileService. Retain legacy `upload_new_folder()` as a compatibility primitive;
production put-new must no longer call it. Do not globally convert its callers.

At the approved design baseline, `c64u_browser/__main__.py` constructed a raw UltimateClient, required
`--host`, and called `transfers.upload_new_folder()`. That helper owns
CWD/MKD/STOR/RETR/SIZE directly and requires a nonempty regular local file.
It does not use saved profiles or REST identity verification.

Existing reusable boundaries are:

- `core.py`: profiles, selected_profile(), credential_for(), connect(), captured
  device/session ownership, managed adapter and Core scheduler.
- `profiles.py`: selected_id, exact profile IDs, profile validation and
  verify_identity(require_bound=True), including accepted MAC fallback.
- `file_service.py`: FileLocation, device-bound _job(), captured-session checks,
  consumed/expiring bounded review plans, FileJobFailure and result propagation.
- `files.py`: child(), inspect() and operate_managed() with MutationResult.
- `transfers.py`: upload_managed() and UploadEvidence, including no-candidate.
- `ftp_reads.py`: adapter.operation() uses ContextVar state for synchronous
  nested reuse, lazy acquisition and outermost release.
- `folder_steps.py`: R1 normalization of mutation/upload evidence and secondary
  local cleanup failures before propagating the primary result.
- `jobs.py`: terminal snapshots, JobCancelled(result=...), cooperative
  cancellation and acknowledged late-success behavior.

Test Lab's exact profile-ID resolution and bounded password input are useful
precedents, but its profile.client() route is not a Core-managed mutation path.
No Test Lab networking is substituted for Core ownership.

## CLI contract and intentional compatibility break

The implemented invocation retains positional source and destination-parent syntax:

```text
python -m c64u_browser [--profile-id PROFILE_ID] [--password] put-new SOURCE PARENT
```

This is an in-process Core client under the existing server-first policy; R2
neither requires nor implements a new persistent server or HTTP API. SOURCE
belongs to the Core host and is represented as FileLocation.core_host().

| Input | R2 put-new decision |
|---|---|
| No --profile-id | Resolve exactly the saved selected_id in the current Stable/Development configuration namespace. No first-profile or discovery fallback. |
| --profile-id | Exact, case-sensitive saved ID; one match required. Nonempty bounded input (120 characters), safe-argument validation; reject repeated selectors, malformed IDs, missing matches or ambiguity. Do not select by name, host or device ID. |
| Missing selection / corrupt preferences | Structured refusal before mutation, including duplicate IDs or a dangling selected_id. Never invent a profile. |
| Unbound profile | Refuse before connection/mutation. Require device_id or device_mac and Core's existing require_bound identity verification; do not auto-bind. |
| --host | Reject for put-new, even if it equals a saved address. The profile alone selects mutation authority. |
| --port | Reject explicit use for put-new, even 21. Saved ftp_port and http_port govern Core connection creation. |
| --timeout / --encoding | Reject explicit use for put-new, even legacy defaults. Use normal Core/client/managed transport settings; per-invocation overrides are deferred. |
| --password | One private bounded prompt, at most 1024 characters, validated before passing entered_password to Core. No password value in arguments, output or diagnostics. Abort if private input is unavailable; EOF/interrupt cancels. |
| No --password | Core credential_for(): existing session credential, then remembered credential, then empty password. No new automatic prompt or authentication retry. |

An empty entered password follows existing Core fallback semantics; it does not
force clearing a remembered credential. A supplied nonempty password is used
for this connection only. Use connect(require_bound=True, bind_identity=False,
persist=False, remember=False). Do not save/select/rebind profiles, remember
new passwords, rewrite preferences, or change credentials. In a fresh CLI
process, in-memory session passwords from another process are not available.
Production FTP USER remains anonymous.

Core connect performs REST connection/identity testing, session preparation and
initial FTP browsing. This intentional change can refuse targets that old raw
FTP put-new accepted. Core's initial-directory fallback must not redirect the
requested parent: preparation validates the exact PARENT independently.

Parser handling must distinguish absent options from explicitly supplied legacy
options. `info`, `ls`, `browse`, and `get` retain their existing required --host,
password behavior, defaults, output and raw read-oriented routes. --profile-id
is put-new-only. This is a deliberate put-new CLI break, not a silent remapping.

## Reviewed intent and one composite boundary

FileService now exposes prepare_fresh_folder_upload() and
execute_fresh_folder_upload(), with thin ArgonautCore forwarding methods.
The requirements below remain the approved implementation contract.

Preparation is nonmutating. It validates SOURCE as a nonempty regular file and
its basename using existing path rules, resolves and verifies the bound Core
session, and reviews the exact remote parent. Require an absolute supported
USB/SD storage directory, either its accessible root or a descendant. Reject
`/`, traversal components, unsupported storage, missing/non-directory parents,
ambiguous case/spelling and unsupported ancestors. Never create the parent.
Store its reviewed path/kind/ancestor observations, not an assumed CWD.

Generate one checked `c64u-transfer-<uuid>` child and intended final path using
child()/remote_file() rules. Review case-insensitive absence of the child.
A collision fails; do not adopt it or loop through automatic mutation attempts.
The file's name is the source basename, not a user-selected replacement name.

Return an immutable preview with opaque plan ID, Core-host source, observed
nonzero size, parent, generated child, final path and non-secret binding.
Keep the captured session and private plan in the FileService bounded,
expiring registry. Execution consumes the plan once. Expired, consumed or
stale plans require new preparation and review. No lease spans this boundary.
The CLI's explicit put-new invocation supplies intent for this constrained
addition; it may prepare then execute without an extra interactive confirmation.
It cannot alter paths or the binding between those calls.

Execute as ONE device-bound Core job. It must not schedule create_folder().wait()
then upload().wait(), nor await separate public jobs while holding a lease.
Inside the worker, synchronously:

1. Initialize evidence before validation; revalidate the source and captured
   FileService session, pair the client with that session, require the managed
   adapter, and honor pre-mutation cancellation.
2. Enter ONE outer adapter.operation(job.check_cancel).
3. Revalidate the reviewed parent/ancestors and absent unique child through
   managed listings. Recheck the session before consequential work.
4. Call operate_managed(client, 'mkdir', child, check=job.check_cancel).
   Immediately retain completed/stopped MutationResult evidence.
5. Only acknowledged MKD permits continuation. Record directory-created before
   checking cancellation or entering the nested upload.
6. Honor cancellation before STOR, then call upload_managed() for SOURCE into
   that child, preserving 3C preflight, checked staging name, exact-length STOR,
   bounded independent RETR/hash, SIZE, destination recheck and RNFR/RNTO.
7. Retain the upload return or exception evidence, release the outer operation,
   finalize resources and publish the composite result through the job snapshot.

Nested operations share the captured adapter's ContextVar lifetime. Use absolute
paths, with no worker/thread/context switch between the nested helpers. One
successful execution uses one FTP connection, one USER and one FEAT across
validation, MKD and upload. Core connection browsing and prepare review are
separate earlier lifetimes and must be counted separately. No failed/poisoned
lease can reopen, reconnect, reset through read fallback or continue mutation.
The Core epoch remains stable during the composite; every exit releases leases.

## Source policy and accepted limits

Reject initially empty files and non-files before consequential remote work.
Revalidate at execution before MKD; reject unsupported special files without
blocking on a FIFO/device open. Retain legacy regular-file interpretation
(including a symlink resolving to a regular file); do not introduce folder-copy
symlink policy as an unrelated CLI change. Never claim a source snapshot.

A pre-MKD stat alone cannot enforce nonempty upload if the file changes later.
R2 therefore needs a narrowly scoped, opt-in nonempty regular-descriptor guard
inside the managed upload source-open boundary, before write_from/STOR, using
fstat on the same descriptor that 3C sizes and transfers. Existing callers keep
3C's default zero-byte behavior and one-open exact-length semantics. Do not add
a second transfer engine, spool, source lock or second transfer-source open.
If this additive policy cannot preserve accepted 3C behavior, stop for review.

A source that becomes empty/nonregular/unreadable after MKD stops upload and
retains directory-created evidence. Preparation size is an observation; the
opened descriptor's expected length governs transfer. Preserve short/overlong
protections and hashes of bytes actually sent. Same-length rewrites remain
outside the guarantee. No precomputed hash substitutes for independent readback.
Destination recheck plus rename is not atomic exclusion of external writers.

## Composite evidence and outcome precedence

Use an immutable R2-specific result/evidence record, not a bare path or error
string. Reuse MutationResult and UploadEvidence without redefining their values.
It must survive preparation/execution failures, FileJobFailure.result or
JobCancelled.result, job snapshot serialization, CLI JSON and human diagnostics.
Never fabricate primitive observations for phases that did not execute.

Required fields/associations:

- Phase and source validation: unperformed/passed/failed for preparation and
  execution, with sanitized reason; expected length and sent count/SHA-256
  only where established. No invented hash or partial-prefix hash.
- Profile ID, verified device identity and captured session ID sufficient to
  explain stale-session refusal; no credentials or raw client objects.
- Intended parent, generated child and final file path; null if not yet known.
- MKD state: not-submitted, refused, completed (acknowledged), or unknown;
  original completed/stopped mutation records, actual reply codes, submission
  evidence and uncertain path. A collision before MKD is not a wire refusal.
- Directory disposition: not-established, created, or outcome-unknown. Retain
  created independently of all later failures; refusal does not prove absence.
- Nested UploadEvidence or null with explicit upload not-started state;
  preserve not-started, no-candidate, staging-candidate, published and
  location-unknown exactly. Preserve staging/final paths, STOR expected/sent
  bytes, length status, replies and hash where established.
- Independent readback and SIZE states, destination-recheck state
  (unperformed/passed/failed), publication mutation/submission/acknowledgement
  evidence. R2 may track recheck observation additively without changing 3C.
- Observed cancellation phase/boundary, sanitized primary category/code and
  structured transport evidence. Pending cancellation never replaces a real
  binding, transport, mutation or verification failure.
- Local cleanup status (not-required/attempted/passed/failed as applicable),
  sanitized secondary failures; never leak private temporary paths or raw
  exception/peer prose. R2 ordinarily needs no local temporary directory.
- Final composite disposition, workflow state and explicit inspection guidance.

| Established outcome | Final disposition / required interpretation |
|---|---|
| Validation/session refusal or cancellation before MKD | no-creation-established; no upload attempted; failed or cancelled according to primary cause |
| MKD refused | directory-refused; no STOR, no adoption, no assertion of absence |
| MKD reply lost/unknown | directory-outcome-unknown; stop, no STOR or reuse; inspect intended child in a new operation |
| MKD acknowledged; cancellation before STOR | directory-created-upload-not-started; cancelled, created empty directory left by this operation, no automatic removal |
| MKD acknowledged; upload setup/preliminary refusal | directory-created-upload-failed; preserve not-started/no-candidate, no claim that a staging file exists |
| MKD acknowledged; interrupted STOR/verification/conflict | directory-created-upload-incomplete; preserve staging-candidate and primary failure/cancellation |
| Publication reply uncertain | directory-created-file-location-unknown; preserve both staging/final alternatives, no staging-only cleanup shortcut |
| Publication acknowledged | published; verified upload success survives late cancellation |
| Acknowledged publication plus local cleanup failure | published-local-cleanup-failed; workflow failure, but remote publication stays completed and must not be replayed |

"Empty directory" after cancellation before STOR describes Argonaut's actions,
not a fresh listing or exclusion of external writers. A created directory is
consequential state even when no file was published. Do not erase it by reporting
only a file upload failure. Normalize primary evidence before cleanup; cleanup
failure is secondary and cannot erase remote certainty or cancellation.

No automatic replay/retry of consequential MKD, STOR or publication; no automatic
rollback or remote deletion. Unknown MKD does not permit probe-and-continue of
the old plan. A new inspection/review is required for any later action.
A staging candidate may use existing session-bound PartialUpload and fresh
reviewed deletion, only when 3C supports that disposition. It is neither proof
of existence nor exclusive ownership. Directory uncertainty is not PartialUpload.
Location-unknown preserves both alternatives without selecting either for cleanup.
The CLI performs no cleanup command implicitly and exposes no destructive token
as authorization. A later CLI process must inspect/review under a fresh session.

## JSON, errors, exits and cancellation

Put-new writes exactly one terminal JSON object to stdout on success, failure or
cancellation; progress, private prompts and concise sanitized explanations go
to stderr. Define schema_version=1, operation='file.fresh-folder-upload', state,
result, error and optional job snapshot/ID. Result carries the evidence above;
unavailable values are null/unperformed, not success-shaped defaults. Successful
result retains path, bytes, sha256 and verified=true plus the composite evidence.
Error contains stable code, sanitized message and retryable=false. Failed or
cancelled results retain all accumulated evidence; never serialize arbitrary
exceptions, credentials, credential-store contents or entire profiles.

Exit 0: acknowledged verified publication with successful required finalization.
Exit 1: validation/profile/identity/session/transport/verification/cleanup failure,
including uncertainty. Exit 2: CLI syntax or unsupported-option error. Exit 130:
cooperative cancellation/EOF at a defined boundary before acknowledged publication.
Recognized put-new usage errors also use the structured envelope; general help
and legacy commands retain their current behavior. Parser tests must cover this.

Ctrl-C requests Core job cancellation and drains the job to its terminal snapshot
before closing Core or printing final JSON. Repeated Ctrl-C must not tear down
an active consequence or overwrite its evidence. Blocking I/O remains bounded
by existing transport timeouts; do not promise instantaneous cancellation.
Use 3B deferral through submitted MKD and serialized RNFR/RNTO, not a deferral
across the entire composite. There is no new cancellation check after published
success or outer context exit. Acknowledged publication followed by a pending
cancel therefore returns success/0, not cancelled/130. Abrupt process death or
power loss cannot promise a final JSON record; it never authorizes automatic replay.

CoreJob can cancel or refuse stale queued work before invoking the task. The
FileService/CLI boundary must preserve or synthesize only truthful unperformed
R2 evidence from the retained intent in that case, without claiming validation,
MKD or upload occurred. This must not change generic CoreJob behavior merely to
make an R2 result appear complete.

## Deterministic implementation acceptance

The implementation establishes deterministic coverage for the following
requirements; exact commands and results are recorded below:

- Selected bound profile; explicit exact profile ID; missing, invalid, repeated,
  ambiguous or corrupt selection; unbound refusal before mutation; identity
  mismatch and stale Core session/binding, including queued-job refusal.
- Nonempty regular success; empty and non-file refusal before MKD; source changes
  before execution and between MKD/source open; descriptor nonempty enforcement;
  managed short/overlong/change protections and accepted same-length limitation.
- Reviewed parent/path/ancestor validation; unique child validation, collision,
  refusal and no adoption; MKD refusal and lost reply, with proof STOR never runs.
- Cancellation before MKD and after acknowledged MKD before STOR, preserving
  directory-created evidence; pre-task cancellation with unperformed evidence.
- STOR preliminary refusal; partial/interrupted STOR; corrupt readback; SIZE
  mismatch; destination appearing during upload; acknowledged publication;
  lost publication reply/location uncertainty; late cancellation after success.
- Local cleanup failure preserving primary failure, uncertainty, cancellation
  and publication evidence; no invented cleanup activity when none is required.
- One connection/USER/FEAT for successful composite and relevant failure paths,
  nested reuse and absolute-path safety; no self-contention, failed-lease reopen,
  mutation replay or read fallback after consequence; zero leaked leases and
  stable Core epoch on every completed/failed/cancelled execution.
- JSON success/error/evidence and deterministic exits, including unsupported
  flags, prompt EOF/private-input failure, Ctrl-C draining and late success;
  credential secrecy in stdout/stderr, snapshots, events and diagnostics;
  remembered/session credential resolution with no profile/credential writes.
- Unchanged legacy info/ls/browse/get; upload_new_folder compatibility unchanged
  except additive observation if tests require it; unchanged Flash and AI
  installation/upgrade/provisioning; unchanged accepted 3C/3D/R1 contracts and
  routing, including existing zero-byte support outside R2.

Use socket fixtures where wire behavior, uncertain replies, transport or session
ownership matters. Core/client mocks alone do not establish one FTP lifetime.
Count connect/prepare separately from execute. Include headless Core tests without
GTK/display imports. Run focused tests, relevant regression suites and required
normal/optimized full checks against the then-verified baseline. Stop at the
implementation review gate before separately authorized physical qualification.

## Later physical acceptance — separate authorization required

Do not perform physical acceptance during this pass. Later, independently qualify
Beige physical ID `25EA78` under `/USB2` and Founder's physical ID `25BE71` under
`/SD`. Use saved identity-bound profiles and reverify identity before mutation.
For each device:

1. Review a unique disposable parent/data set and known nonempty local file.
2. Execute the actual CLI put-new path, not a helper-only replacement.
3. Independently inspect the unique generated directory and exactly the intended
   file; verify destination size and SHA-256 by independent readback.
4. Confirm no unexpected staging artifacts, appropriate session behavior,
   stable Core epoch and zero leases using available diagnostics. Distinguish
   connection setup/review from the one execution lifetime.
5. Perform fresh reviewed cleanup, then independently verify absence.
6. Record exact invocation (without secrets), profile/physical identity, firmware,
   paths, byte counts, hashes, JSON/evidence, diagnostic counts, cleanup and
   limitations. Do not claim unobservable internal state as physically measured.

Do not physically inject lost replies, network interruption, active-transfer
disconnect, cleanup failure or external-writer races. Deterministic fixtures own
those cases. Both devices need their own evidence and acceptance decision.

## Completion and implementation stop conditions

R2 completes only after design approval, implementation review, deterministic
tests, separately authorized physical qualification on both devices, exact
physical evidence documentation, final review, normal fast-forward commit/push,
a clean worktree and no R3 begun. This implementation pass stops for pre-physical review. No physical
qualification, branch/worktree creation, commit, push, merge, tag, package
or release is authorized in this pass.

During implementation, stop and report if the solution requires changing
accepted 3C/3D/R1 contracts, migrating Flash/AI/unrelated CLI commands,
cross-device behavior, weakening identity binding, replaying an uncertain
consequential mutation, losing primary evidence to cleanup failure, or creating
a second independent raw-FTP ownership model for CLI. Report concrete profile
selection or Core integration incompatibilities rather than falling back to host
mutation. Current inspection establishes no incompatibility with selected-profile
and explicit --profile-id resolution.

## Deferred / out of scope

Legacy read CLI migration; general compatibility/raw-FTP retirement and final
ownership audit; Flash; AI installation/upgrade/provisioning; cross-device work;
new username handling; zero-byte put-new; new transport overrides, password-stdin,
profile editing and server hosting remain outside R2.

Physical cartridge in the C64 Ultimate cartridge port to cartridge image/file
dump, and physical Commodore cassette to .TAP imaging, are future requirements
requiring hardware/firmware/API investigation. Neither is ordinary file copying
or part of R2.


## Implemented boundary and deterministic review package — 3 October 2026

Authority was verified before edits: HEAD and local origin/development both
`3f7dace0b2c5b80316919db832dc583d4a19392a`, parent
`d0e605ebdc29cca15558d7fb6c5bf2dcfc6690bc`. Only the approved modification to
CURRENT-STATE.md and this untracked design document were present. Initial
`git diff --check` passed. No fetch, branch or worktree creation was needed.

Production changes:

- `__main__.py` dispatches only put-new into `fresh_folder_cli.py`; required-host
  read commands retain their defaults, private prompt, output and raw read routes.
  Recognized put-new syntax errors produce the R2 envelope and exit 2.
- `fresh_folder_cli.py` resolves the selected/exact bound saved profile, refuses
  corrupt selection, obtains at most one privately entered credential bounded
  to 1024 characters, and calls Core with require_bound=True, bind_identity=False,
  persist=False and remember=False. Getpass's echo fallback is refused. SIGINT
  cancels/drains the current job; repeated interrupts cannot discard consequences.
  Core close failures are secondary and do not erase acknowledged publication.
- `fresh_folder.py` owns frozen preview/result records and private consumed,
  expiring plans held in FileService's existing bounded registry. Preparation
  reviews exact ancestor kinds/spelling and child absence. Execution rechecks
  source, binding, session and reviewed paths, then performs MKD and nested
  managed upload in one synchronous outer operation. Completed MKD evidence is
  retained before post-MKD cancellation. No remote cleanup, retry or replay occurs.
- The R2-specific CoreJob subclass normalizes terminal snapshots that lack a
  task result after pre-task cancellation/stale refusal. It uses retained intent
  with unperformed validation; job lookups, wait results and events agree.
  Generic CoreJob and scheduler behavior are unchanged.
- `transfers.py` adds only the opt-in require_nonempty_regular descriptor policy
  and additive destination-recheck observation. R2 uses one nonblocking local
  source open, then fstat on that same descriptor for regular/nonempty checking
  and expected transfer length. The nonblocking flag prevents a raced FIFO from
  hanging before fstat on supported platforms. Source-close errors preserve the
  primary transfer/cancellation evidence. Default 3C callers keep their existing
  source-open path and zero-byte behavior. No spool or second transfer engine exists.

`MutationResult` and `UploadEvidence` retain their primitive meanings. Composite
records carry source/binding/path observations, MKD acknowledgement/uncertainty,
created-directory disposition, upload/STOR/readback/SIZE/recheck/publication
observations, cancellation, sanitized transport errors, secondary finalization
failures and inspection guidance. Unknown/unused observations remain null or
unperformed. Core/service exceptions retain their result. CLI stdout contains
exactly one terminal JSON object; explanations go to stderr. No profile or
credential writes occur.

### Test accounting and commands

Before edits, unittest discovery found **959 test methods**. This pass adds
**61 methods** in two new modules (36 composite + 25 CLI). No existing test was
removed, renamed or modified. Subtests are not counted as additional methods.

Commands ran from the existing argonaut-network-slice2 repository. The
PYTHONDONTWRITEBYTECODE setting avoids incidental bytecode writes. Socket tests
use only loopback fixtures; REST identity responses are fixtures. No physical
C64U was contacted for qualification.

```bash
# Focused R2
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests /usr/bin/python3 -m unittest test_fresh_folder test_fresh_folder_cli
# Directly affected regressions
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests /usr/bin/python3 -m unittest test_ftp_reads test_ftp_streaming test_ftp_mutations test_ftp_uploads test_ftp_replacements test_ftp_replacement_corrections test_ftp_folder_steps test_file_service test_core test_jobs test_scheduler test_transfers test_empty_upload test_upload_cleanup test_folder_copy test_file_copy test_usb_backup test_native_files test_c64_ai_install
# Documented normal and optimized full checks
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -O -m unittest discover -s tests -p 'test_*.py'
# Documented offline Test Lab
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m c64u_browser.test_lab --suite offline
# Final whitespace/error check
git diff --check
```

| Check | Methods/checks run | Passed | Skipped | Failures/errors |
|---|---:|---:|---:|---:|
| Focused R2 final | 61 | 61 | 0 | 0 |
| Directly affected regressions | 276 | 276 | 0 | 0 |
| Full normal | 1020 | 984 | 36 | 0 |
| Full optimized | 1020 | 984 | 36 | 0 |
| Offline Test Lab | 17 checks | 17 | 0 | 0 |

The 36 existing opt-in display skips are unchanged. Test Lab checks are separate
from unittest method counts. The initial sandboxed socket attempt ran 32 methods
and reported 48 setup/subtest errors because socket creation was denied. With
loopback access enabled, the next 32-method run exposed one new test's incorrect
snapshot accessor; correcting that test yielded 55/55, then the expanded 61/61
above. No production test failure was suppressed or removed. The direct regression
run preceded the six final additional edge-case tests. After final review also
closed the synchronous refusal-evidence gap, focused, regression and both full
suites were rerun successfully with all 61 R2 methods present. Final
`git diff --check` passed.

Coverage includes successful root/descendant uploads; exact selectors and MAC
fallback; corrupt/unbound/mismatched authority; source and ancestor races;
consumed/expired/discarded/bounded plans; MKD refusal/unknown without STOR;
queued cancellation/stale refusal; post-MKD cancellation; setup/STOR refusal;
partial cancellation, short/overlong/same-length source changes; corrupt
readback/SIZE/destination races; uncertain publication; late-success cancellation;
cleanup precedence; one connection/USER/FEAT per execution, stable epoch and
zero leases; no fallback after consequences; JSON/exits and repeated interrupt
draining; credential secrecy in output, snapshots, events and diagnostics;
unchanged read CLI and compatibility upload_new_folder; accepted 3C/3D/R1,
Flash and AI routing regressions.

### Remaining limits and review gate

No design deviation or repository incompatibility was required. Same-length
source rewrites are not a snapshot guarantee; a reviewed source size is only an
observation. Recheck plus FTP rename does not exclude an external writer
atomically. Acknowledged MKD describes Argonaut's action and does not assert
exclusive directory ownership. Unknown MKD/publication requires new inspection,
never automatic replay. Abrupt process death cannot promise final JSON. Blocking
transport I/O retains existing bounded timeouts. Ordinary R2 uses no local
temporary directory; only actual descriptor/Core/operation finalization failures
produce cleanup evidence.

The implementation is ready for review, **not physically qualified**. Both Beige
and Founder still require separately authorized actual CLI acceptance, independent
hash/size inspection, staging inspection, reviewed cleanup and independent absence
verification described above. No physical qualification, commit, push, merge, tag,
package, release, new branch or new worktree occurred. No R3 work began.


## Surgical pre-physical CLI recognition correction — 3 October 2026

Before editing, HEAD and local origin/development still matched
`3f7dace0b2c5b80316919db832dc583d4a19392a`. The entire tracked/untracked
R2 diff exactly matched the reviewed 2,116-line pre-physical artifact; no
unrelated changes were present. Initial `git diff --check` passed.

Only `c64u_browser/__main__.py`, `tests/test_fresh_folder_cli.py`, and this
append-only evidence section changed during this correction. The command scan
uses the existing parser's option recognition, consumes its single-value options,
respects attached values, abbreviations and `--`, and stops at the first
positional. Only that positional can establish put-new routing. The existing
parse_args call still owns validation and dispatch; no second parser was added.
The scan accepts both older tuple and newer candidate-list argparse results.

Five new test methods cover get source `put-new` with missing destination;
other legacy path/destination positions; option values (including attached and
abbreviated forms and no command); genuine malformed put-new JSON syntax/exit 2;
and valid put-new dispatch, including a profile ID literally named `put-new`.
Existing successful loopback CLI upload and legacy routing tests remain intact.
No test was removed or renamed. Subtests are not counted separately.

The exact focused, affected-regression, normal, optimized and offline commands
in “Test accounting and commands” above were rerun unchanged. The documented
normal/optimized checks and CI offline check were included; no packaging or
physical checks ran.

| Correction verification | Run | Passed | Skipped | Failures/errors |
|---|---:|---:|---:|---:|
| Focused R2 final | 66 | 66 | 0 | 0 |
| Affected regressions | 276 | 276 | 0 | 0 |
| Full normal | 1025 | 989 | 36 | 0 |
| Full optimized | 1025 | 989 | 36 | 0 |
| Offline Test Lab | 17 | 17 | 0 | 0 |

The first focused attempt ran 66 methods and reported 69 errors (including
subtests): the initial scanner expected the older argparse tuple shape, while
the installed Python 3.13.5 returns candidate lists. After correcting that
compatibility handling, all final runs above passed. Final `git diff --check`
passed. No outstanding issue or design deviation remains.

Stopped for correction review. No physical qualification, commit, push, merge,
tag, package, release, branch/worktree creation, R3 work or unrelated correction
occurred. The existing R2 implementation/design outside these three correction
files was preserved byte-for-byte.

## Physical qualification — PASS (3 October 2026)

The reviewed R2 implementation passed authorized physical qualification
independently on both C64 Ultimates through the actual production CLI `put-new`
path and saved identity-bound profiles.

| Device | Address / physical ID | Storage | Source | Bytes | SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| Beige | `192.168.68.70` / `25EA78` | `/USB2` | `/tmp/argonaut-r2-beige.txt` | 38 | `5ddaddfbb2b9878579fc6d1d8bf1a1239f704cc4a42a4d53f2f7d2d07b276344` |
| Founder's | `192.168.68.69` / `25BE71` | `/SD` | `/tmp/argonaut-r2-founder.txt` | 40 | `24dfd478836416eafc5bc7bbdb91c9ea1d02011d206919818267ebc6451d50a8` |

Beige used bound profile `979c7e4e-2c58-4dff-8536-f145c6a9155f` and exercised
the private `--password` prompt. Its disposable parent was
`/USB2/argonaut-r2-beige-8431c2b4baea449cba0522880c6da6fe`; R2 created
`c64u-transfer-9f8c7a96ca1f4c97b954a464401614e1` and published
`argonaut-r2-beige.txt`.

Founder's used bound profile `43f75f6d-87ed-4e2c-abe8-448679569a7d` and the
normal Core credential path. Its disposable parent was
`/SD/argonaut-r2-founder-d75717d680d843209847ff3823161ac6`; R2 created
`c64u-transfer-5b6f727d46dc4810a01c98bdc6abc9d7` and published
`argonaut-r2-founder.txt`.

On both devices the CLI reported acknowledged MKD, exact STOR transfer,
independent managed readback and SIZE verification, passed destination recheck,
acknowledged RNFR/RNTO publication, and final `published` success. Independent
fresh Core sessions then verified exactly one generated directory containing
exactly the intended file, the expected byte count and SHA-256, and no
`c64u-part-*` staging artifact. Core epochs remained stable and active lease
counts returned to zero.

Cleanup was separately prepared and reviewed on each device. Each deletion
contained exactly three disposable items: the published file, generated transfer
directory and acceptance parent. Reviewed deletion succeeded, followed by an
independent fresh-session parent listing that verified the complete acceptance
tree absent. Epochs remained stable and active lease counts were zero.

Lost replies, network interruption, active-transfer disconnect, cleanup failure
and external-writer races were intentionally not induced physically; deterministic
fixtures remain responsible for those cases. No R3 work was performed.

R2 is physically qualified on both devices and was subsequently committed and
pushed at `13bbc8a85d02cf75b1e58efde4e20b35d575e0df`. The statements above about
pending final review and publication record the state at the earlier acceptance
checkpoint.

## R3 current retirement status — 3 October 2026

[R3 — Compatibility Retirement](R3-COMPATIBILITY-RETIREMENT.md) is implemented
and awaiting final review. It removes the unused fresh-folder helper pair,
`ConnectionDialog.credential`, `file_copy.conflicts` and `CoreDeviceOperations.info`,
and makes Core credential resolution private as `_credential_for` without changing
its behavior. Earlier compatibility-retention requirements and resolver spelling
remain historical checkpoint evidence; R3 supersedes only those boundaries.
The accepted managed contracts and physical evidence are unchanged. Live CLI
reads, Test Lab storage, Flash and AI routes remain unchanged; deferred raw read
fallbacks and folder-copy alternatives remain. No physical qualification is
required or performed for R3, and no commit or publishing has occurred.
