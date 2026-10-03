# R3 — Compatibility Retirement

## Status, authority and decision

Approved contract implemented, 3 October 2026. **Implemented; final review pending.**
This implementation pass stops for review with uncommitted source, tests and
bounded documentation changes. No physical qualification, live-consumer migration,
R4 work, branch/worktree creation, commit, push, merge, tag, package or release
occurred. Historical design observations below describe the authority tip;
implementation evidence and test accounting are recorded at the end.

Authority was checked in the existing repository
`/home/bruce/Documents/ChatGPT/Local Projects/argonaut-network-slice2`:

- The design pass began clean. Before implementation, both status checks showed
  exactly the approved `M docs/CURRENT-STATE.md` and
  `?? docs/R3-COMPATIBILITY-RETIREMENT.md`; no other dirt. Pre-edit
  `git diff --check` passed.
- HEAD and local `origin/development` both resolve to
  `13bbc8a85d02cf75b1e58efde4e20b35d575e0df`,
  `Implement R2 managed CLI fresh-folder upload`.
- `git rev-list --left-right --count HEAD...origin/development`: `0 0`.
- Checkout is detached at that commit. No ref was changed or fetched;
  `origin/development` here is the existing local remote-tracking ref.

The completed **Post-R2 Ownership & Retirement Assessment**, supplied with
“Plan Slice 3 Inspection,” is the factual starting point. Its smallest-checkpoint
recommendation is reconfirmed below against this tip. R1/R2 are complete and
are not reopened. Repository docs contain historical R2–R6 sequencing, but no
existing R3 design. This document assigns R3 only to compatibility retirement;
older sequence labels do not assign its scope.

**Decision:** remove the two superseded fresh-folder functions and three unused
public helpers; make the existing Core credential resolver private. Defer all
four candidate raw read fallbacks and the unmanaged remote alternatives in
`folder_copy.execute_plan()`. They are dead production alternatives, but their
fixture/API adaptation would materially widen this checkpoint. No live workflow
migration is necessary to obtain this smaller cleanup.

Preserve [SERVER-FIRST.md](SERVER-FIRST.md), accepted 3A/3B/3C/3D contracts in
[C64U-FTP.md](C64U-FTP.md), [R1](R1-MANAGED-FOLDER-COMPOSITES.md) and
[R2](R2-MANAGED-CLI-FRESH-FOLDER.md). R2's requirements to retain compatibility
were boundaries of that completed checkpoint, not permanent API promises.

## Exact included surface and static reachability

Paths below are repository-relative and observations apply to the authority tip.
The audit searched tracked source, tests, documentation and packaging for symbol
names, imports, attribute calls and dynamic access, then traced clients and
routing. Homonymous fields, log methods, tests and diagnostic strings are not
production calls. No repository alias/export/dynamic dispatch to the proposed
unused helpers was found. This is repository reachability evidence, not proof
about arbitrary external Python programs.

| Surface | Production reachability at R2 tip | R3 change |
|---|---|---|
| `c64u_browser/transfers.py:upload_new_folder()` | No production caller. Only its definition, test import/calls, a test patch target and diagnostic-name string remain. `__main__.main()` recognizes put-new before legacy client construction and dispatches `fresh_folder_cli.run`; that calls Core prepare/execute, FileService and the managed fresh-folder composite. | Delete the public wrapper and its obsolete event emitter; preserve R2 dispatch and the managed composite unchanged. |
| `transfers.py:_upload_new_folder()` | Called only by the obsolete wrapper; independently owns raw connect/CWD/MKD/STOR/RETR/SIZE/close. | Delete its complete implementation. Do not redirect it, alias it or provide a compatibility fallback. Do not delete shared imports/helpers still used by general upload or download. |
| `connection_dialog.py:ConnectionDialog.credential()` | No caller. Its body alone exposes `core.credential_for()`. Dialog test/connect/read-model/save paths already delegate operations to Core and pass entered credentials inward. | Delete the method; keep dialog operations and entered-password handling unchanged. |
| `file_copy.py:conflicts()` | No production import/caller. Only `tests/test_file_copy.py` invokes it. Current GUI copy review uses FileService → `folder_copy.build_plan()`; `plan.conflicts`, preview/report fields and local variables with that name are distinct. | Delete only this helper. Preserve `local_copy`, `copy_files`, planning, conflict/replacement policy and accounting. |
| `core.py:CoreDeviceOperations.info()` | No facade caller. CLI `info` calls **UltimateClient.info()**, also used by `UltimateClient.test_connection()`. Logging `.info()` calls are unrelated. | Delete only the facade forwarding method. Preserve UltimateClient.info(), test_connection(), Core connection information and CLI output. |
| `core.py:ArgonautCore.credential_for()` | Four necessary internal callers: `test_profile`, `read_model`, `connect`, `reconnect`. The only other source call is the unused dialog helper above. Package credential-channel tests also invoke it, including embedded subprocess source. | Rename to private `_credential_for()` with the same signature/body; update exactly those four internal callers. Remove the public name, without alias, wrapper or replacement presentation API. |

No proposed dead-helper deletion has a live production caller. The resolver's
four internal uses are expected, not a contradiction: only its public surface
is retired. No new fallback becomes reachable when an uncalled definition is
removed. Internalization changes name resolution only; do not add `getattr`
fallbacks, exception-driven raw routing or alternate credential sources.

## Credential internalization contract

Use `ArgonautCore._credential_for(self, profile, entered='')` as the smallest
private replacement. Keep the current algorithm exactly:

1. A truthy explicitly entered value wins without consulting saved credentials.
2. Otherwise find a saved profile by ID. Its host, HTTP port and FTP port must
   equal the supplied profile's endpoint before reusing credentials.
3. Resolve truthy session password, then truthy remembered password, then `''`.
4. Missing ID or changed endpoint resolves `''`; empty entered input retains the
   existing fallback semantics. It does not mean erase a remembered password.

Do not change `save_profile`, `forget_credential`, profile removal, backend
selection, `_session_passwords`, `_ftp_password`, pending FTP binding, client
construction or reconnect behavior. `connect_selected` continues through
`connect`; package/session handling keeps its current lifetime and isolation.
No keyring, portability, credential-store or authentication retry redesign.

The private method is an implementation boundary, not a Python security sandbox.
No public presentation method should return stored secrets. GUI/CLI clients must
not replace calls with `_credential_for()`; they continue submitting operations.
No secret goes into results, events, logs, exception messages or new diagnostics.
Tests use synthetic credentials and injected client factories/backends only.

## Exact adaptation and behavioral evidence

The following approved adaptation inventory was implemented. The final evidence
and exact method accounting appear below; obsolete APIs were not recreated.

| File / exact existing dependency | Required adaptation and behavior retained |
|---|---|
| `tests/test_transfers.py` import and `Transfers.test_upload_verification_and_mkdir_failure` | Remove old-helper import and this helper-only test. Its successful verified upload assertion maps to `tests/test_fresh_folder.py:test_success_one_execution_lifetime`; MKD failure before STOR maps to `test_mkd_refusal_and_lost_reply_stop_stor`. Keep all raw download and general-upload tests because their consumers remain live. |
| `tests/test_transfers.py:Transfers.test_corrupt_upload` | Remove helper-only test. Map integrity failure to `test_fresh_folder.py:test_corrupt_readback_and_size_mismatch`. Explicitly retain/add a command-log assertion there that corrupt readback causes no publication, automatic DELE/RMD, retry or replay; retain inspection evidence. Existing failure tests must not merely assert an exception. |
| `tests/test_fresh_folder_cli.py:test_selected_profile_success_and_no_writes` | Replace the patch of nonexistent `transfers.upload_new_folder` with guards on retained raw factories, e.g. `transfers.connect` and `CoreDeviceOperations.open_ftp`, which raise if invoked. Keep the actual Core/loopback managed success, saved bound profile, no writes, lease and JSON assertions. Do not use `patch(..., create=True)` to recreate the retired symbol. |
| `tests/test_file_copy.py` import and `test_conflicts_include_directories_and_broken_links` | Remove the unused-helper dependency. Preserve its useful safety assertions through current planning: extend `tests/test_folder_copy.py` to prove file destinations that are directories or broken symlinks are conflicts and not overwritten, and case-insensitive remote name collisions are refused/skipped without mutation. Use the planner's current policy: directory-to-directory merging remains supported; do not transplant the old helper's blanket directory-conflict policy. Retain `test_file_service.py:test_conflict_preview_skip_replace_and_revalidation` and local-copy no-overwrite tests. |
| `tests/test_package_credential_channel.py:test_development_never_accesses_store_and_core_secret_does_not_persist` | Replace its two public resolver calls with injected fake-client observations through `test_profile`, verifying current-instance use and fresh-instance absence. Preserve Stable-store access traps, unchanged Stable preferences and absence of secret bytes on disk. |
| `tests/test_package_credential_channel.py:test_development_secret_is_absent_after_process_termination` | Update the embedded second-process source, which also calls the removed public method. Observe the credential passed to a fake client through `test_profile`; assert empty without printing it or connecting anywhere. Keep process termination, filesystem scan and channel isolation assertions. |
| `tests/test_core.py` | No existing public resolver call requires renaming. Extend injected-factory tests to cover all four internal callers and the resolution matrix above, including independent host/HTTP/FTP changes, missing profile, empty entered/session/backend cases, entered precedence and no backend access when short-circuited. Keep connection/reconnect identity, public-data and event behavior. Supply fake configuration data for read_model. |
| `ConnectionDialog.credential` and `CoreDeviceOperations.info` | No direct test/simulator invocation found. Add headless source/AST absence checks for the dialog method (no GTK requirement), and facade public-surface absence coverage alongside existing Core boundary tests. Do not remove tests for UltimateClient.info(), CLI info, model reading or dialog delegation. |
| `c64u_browser/ai_analysis.py:SAFE_OPERATIONS['ftp']` | **Retain** the literal `upload_new_folder` as a deliberately documented historical-event label for saved-report interpretation. Add a short comment identifying it as history-only; no callable lookup or emitter may survive. |
| `tests/test_ai_analysis.py` | Add a saved failed-report fixture using that historical label; prove it retains sanitized generic operation/target evidence while unknown labels remain rejected/normalized and private fields stay excluded. Retain `test_only_failed_checks_and_whitelisted_operation_fields` and `test_unexpected_operation_labels_cannot_reach_ai_evidence`. No history schema change. |

`c64u_browser/package_self_test.py` inspects backend/channel metadata directly;
it does not invoke the public resolver and needs no implementation change.
Other credential-channel tests, including Stable persistence and portable
session-only behavior, remain unchanged.

No shipped simulator invokes an included retired helper. `simulated_c64u.py`
uses ordinary raw listing/download/general upload; `test_lab_probe.py` exercises
raw listing/authentication refusal. Keep these offline diagnostics and their
17-check baseline intact. They justify their diagnostic assertions, not permanent
raw production compatibility. No simulator migration belongs in R3.

Documentation references requiring deliberate treatment are exactly:

- `docs/CURRENT-STATE.md`: correct post-R2 authority/status now; mark R3 as a
  design proposal. At implementation completion, state the actual retired set
  and new deterministic counts, without calling excluded workflows migrated.
- `docs/R2-MANAGED-CLI-FRESH-FOLDER.md`: original scope/inspection, credential
  table, required checks and implemented coverage name the old helpers. These
  remain historical R2 evidence; R3 supersedes their compatibility-retention
  constraint and resolver spelling, not their behavior. At R3 completion add a
  concise cross-reference/status note rather than rewriting accepted evidence.
- `docs/C64U-FTP.md`: historical remaining-path lists and the R2 consumer section
  mention the helper; add a bounded current R3 retirement note on completion.
  Preserve historical 3A–R2 wire/physical acceptance records.
- This document records the retirement decision. No direct documentation promise
  for `ConnectionDialog.credential`, `file_copy.conflicts` or facade `info` was
  found. No broad README, NEXT-PASS or roadmap rewrite is required.

## Deferred dead fallbacks: explicit decisions

All four are **excluded from R3**. Reconfirmed call chains below explain why
“raw branch unreachable in production” does not mean “delete the capability.”
Real Core clients receive `FtpReadAdapter` in `_prepare_read_session`; facade
`_ftp_reads` delegates to that client. Deliberately non-UltimateClient test doubles
bypass adapter installation. Those doubles are not production owners.

| Candidate | Reconfirmed production path and fixture coupling | Decision |
|---|---|---|
| Raw `native_files._read_remote()` branch | Core Game/SID reads use `_require_client`; FileService native/Flash preparation reads use Core clients; FlashDialog and GUI disk-image reads use the Core facade. Managed `adapter.read` is selected. `tests/test_native_files.py:test_game_library_has_scoped_64_mib_remote_read`, `tests/test_diagnostics.py:test_flash_or_storage_read_and_dma_run_do_not_log_paths_or_password`, and legacy comparison in `tests/benchmark_ftp_reads.py` use raw seams; `tests/test_ftp_reads.py` covers managed bounds and errors. | Defer fixture/benchmark conversion. Keep read_remote/read_remote_game, their distinct bounds, Flash validation and disk/Game/SID capabilities. |
| Raw `disk_run._mount_and_run()` FTP branch | `DrivesTab.mount_run` passes the Core facade into managed bounded D64 read, followed by existing DMA. `tests/test_disk_run.py` supplies raw FTP for wire/authentication/uncertain-launch tests; `test_ftp_reads.py` covers managed Mount & Run. | Defer: separate read fixture adaptation from DMA launch guarantees. Do not change Mount & Run or DMA. |
| Raw `UsbBackupService._remote_hash()` fallback | Core constructs UsbBackupService with `_require_client`; backup preview/execution/restore comparison use the managed client and `read_into`. `tests/test_usb_backup.py` has nonmanaged service doubles and raw transfer plumbing; managed streaming/replacement/restore tests cover real adapters. | Defer broader service-double conversion; retain hashing, independent rereads and per-file lifetime. |
| `UltimateClient._list_directory_identity()` raw implementation | Only production use of public identity listing is USB volume fingerprinting with a Core client; public `list_directory_identity` selects its adapter. Raw tests in `tests/test_api.py` cover octets, LIST fallback and path rejection; `test_ftp_reads.py` covers managed identity listing. | Defer API/fixture closure. Later removal must retain public managed identity capability and explicit rejection of missing ownership, not fall back to ordinary text listing. |

Later consideration must repeat reachability, specify missing-adapter refusal
and preserve the useful managed tests. No such changes are authorized by R3;
no separate live-consumer migration design is assigned here.

## Folder-copy alternatives: defer compatibility closure

The only production `execute_plan` calls are `FileService.execute_copy` and
`UsbBackupService.execute_restore`; both pass `managed_uploads=True`,
`managed_replacements=True`, `managed_folders=True`. Remote missing directories
and remote additions enter R1; remote replacements enter 3D; local-source remote
additions enter 3C. The old remote `operate` / `copy_files` / `replace_file`
alternatives remain reachable through direct callers/default or partial flags,
including tests, but are bypassed by these production callers.

**Exclude their removal.** Flag/API closure affects `tests/test_folder_copy.py`,
`test_empty_upload.py`, `test_replacement_source.py`, `test_next_pass.py`, partial
flag cases in `test_ftp_uploads.py` / `test_ftp_replacements.py`, and USB service
doubles. It is materially larger than removing an uncalled function. Preserve
all local branches, directory merge behavior, completed/skipped/remaining and
partial/cancellation/evidence accounting. The underlying remote replacement and
general upload also still serve AI; removing those is expressly forbidden.

## Live exclusions and public compatibility

The current four live raw-FTP groups remain exactly:

1. CLI `ls`/`browse` use raw ordinary listing; `get` uses raw download.
2. Headless Test Lab `hardware.storage` uses raw ordinary listing via its profile
   client. No check or hardware runner is removed or migrated.
3. Native Flash writes use `upload_flash` → `transfers.connect` and raw writes.
4. AI installation/upgrade uses general `upload` / remote `replace_file`,
   `copy_files` and raw FTP; the facade path still requires `open_ftp`.

CLI `info` is also unchanged, but uses REST rather than FTP. Do not retire browse
in this checkpoint. Keep `transfers.connect`, `CoreDeviceOperations.open_ftp`,
general `upload`/`_upload`, remote `replace_file`, raw ordinary listing and raw
download fallback. Do not change AI/Flash policy, 3A/3B/3C/3D/R1/R2 contracts,
credential backends/portability, cartridge or cassette/TAP work. No R4 or other
live-consumer migration design is included. Remaining direction is deletion of
proved dead compatibility and, only under future separately approved work,
closure of the four live groups; this is not a new numbered roadmap.

README and packaging describe an application and launch/build artifacts;
`c64u_browser/__init__.py` provides no re-export or `__all__` promise for these
helpers. No tracked setup.py/pyproject library declaration or documented stable
external Python API for them was found. SERVER-FIRST promises a Core application
boundary and explicitly forbids returning credentials to clients; it does not
promise these particular helpers indefinitely. External direct imports would
break, so record the removals in R3 completion documentation. Do not silently
claim external compatibility or add a deprecation shim that preserves the secret
surface/raw implementation. Discovery of an actual support promise or downstream
production consumer requires review and exclusion of the affected deletion.

## Approved implementation verification contract

Add narrowly scoped static/AST assertions, preferably in a dedicated
`tests/test_compatibility_retirement.py`, to establish:

- Neither fresh-folder helper has a definition, import or callable reference in
  application source. The only allowed source occurrence of its public name is
  the explicit history-label entry/comment in `ai_analysis.py`.
- The three deleted class/module helpers and public Core resolver are absent.
  Check the exact owner, not every occurrence of words such as info/conflicts.
- `_credential_for` calls occur only in the four Core methods named above;
  presentation modules cannot call it. AST inspection of ConnectionDialog avoids
  adding a GTK/display prerequisite to this boundary test.
- R2 dispatch still enters its existing runner/Core/FileService route; successful
  put-new with retained raw factories trapped cannot use compatibility transport.
  Keep refusal/missing-adapter and no-reopen-after-consequence tests. Removing
  symbols must never trigger dynamic compatibility fallback or create an alias.

Example repeatable audit searches (classify results; strings are not calls):

```sh
git grep -n -E 'upload_new_folder|credential_for' -- c64u_browser tests docs
git grep -n -E 'def credential\(|def conflicts\(|def info\(' -- c64u_browser
git grep -n -E 'execute_plan\(|managed_uploads|managed_replacements|managed_folders' -- c64u_browser
git grep -n -E 'open_ftp|transfers\.connect|replace_file|upload_flash' -- c64u_browser
```

Required deterministic evidence before implementation acceptance:

- All existing 66 focused R2 methods remain passing after named-patch adaptation;
  preserve profile/identity binding, parser ambiguity cases, credential secrecy,
  evidence, cancellation, publication and no fallback/replay assertions.
- Legacy CLI info/ls/browse/get dispatch, required host, output and parser behavior
  remain unchanged (`test_fresh_folder_cli.py` legacy and recognition cases).
- Resolution matrix and all four internal paths pass; session/remembered/empty
  behavior, no public stored-secret retrieval and package credential-channel
  isolation pass. No real keyring or device is needed.
- Copy-plan conflict protection survives removal of the unused helper.
- Flash and AI regressions remain on intentionally unchanged legacy routes;
  managed 3A/3B/3C/3D/R1/R2 regressions pass. Deferred fallback files/routes must
  not change. No unreachable fallback is included in this design; adding one
  requires a revised reviewed design and managed-capability proof.
- Historical diagnostic labels remain interpretable without a live emitter;
  offline Test Lab/simulator purpose, redaction and check roster remain intact.
- Full normal and optimized suites and offline Test Lab pass against the
  then-current baseline; `git diff --check` is clean. Account explicitly for
  removed helper-only tests and added/re-homed assertions, not a fabricated
  unchanged test count or new skips hiding regressions.

Minimum focused modules: `test_fresh_folder`, `test_fresh_folder_cli`,
`test_transfers`, `test_file_copy`, `test_folder_copy`, `test_file_service`,
`test_core`, `test_package_credential_channel`, `test_ai_analysis`,
`test_diagnostics`, `test_native_files`, `test_c64_ai_install`, and the new static
boundary module. Include the accepted FTP reads/streaming/mutations/uploads/
replacements/replacement-corrections/folder-steps and USB regression families.
Use the repository's documented commands, including:

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -O -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m c64u_browser.test_lab --suite offline
git diff --check
```

Historical completed R2 baseline: 1025 methods, 989 passed and 36 opt-in display
skips in each full suite; 66 focused R2, 276 affected regressions and 17/17 offline
checks. These are prior acceptance results, not tests run in this design pass.

## Physical qualification, completion and stop conditions

**Physical qualification is not required for this exact R3 scope.** No live
transfer workflow changes. Deletions are unreachable helpers and public-surface
narrowing; internal credential behavior is preserved by deterministic injected
clients. Existing R2/3C/3D/R1 physical acceptance remains valid. Contacting a C64U
adds no necessary evidence for symbol absence. A discovered live behavior change
is a stop condition, not a reason to add hardware testing by habit.

Final R3 completion still requires reviewed implementation;
deterministic tests/regressions; a final static ownership/reachability audit
showing intended symbols gone, only deliberate history strings retained and
excluded live consumers unchanged; truthful docs/test accounting; final review
and normal fast-forward commit/push under the established repository workflow;
a clean worktree; and no next live-consumer checkpoint begun. The current detached
checkout is recorded, not permission to create a branch/worktree or mutate refs
in this pass. Publishing remains a later completion step.

Stop implementation and report if:

- A proposed deletion has a live production caller or an actual public support
  promise that invalidates the current evidence; exclude it rather than guess.
- Accepted R2/3C/3D/R1 (or 3A/3B) behavior would need to change.
- A live CLI, Test Lab, AI or Flash workflow must migrate or be removed.
- Credential semantics must change instead of only internalizing the API.
- Removal would force deletion of a useful managed capability.
- A removed name would need an alias, recreated test symbol or raw fallback to
  keep production working; reassess reachability instead.
- Scope expands into general raw-factory retirement before last consumers move.

No unresolved repository reachability contradiction was found. Scope was approved;
implementation is complete and final review is pending. External Python consumers are not discoverable from this repository
alone; the audit found no support promise and does not claim to have surveyed
external installations. Deferred compatibility work remains explicitly deferred.

## Implementation evidence — final review pending

Authority was reconfirmed before editing at the exact expected HEAD and local
`origin/development`, `13bbc8a85d02cf75b1e58efde4e20b35d575e0df`, divergence
`0 0`, detached checkout. Only the two approved design documents were initially
dirty. No fetch, ref change, branch or worktree creation occurred.

### Retired set and static audit

Deleted `transfers.upload_new_folder`, `transfers._upload_new_folder`,
`ConnectionDialog.credential`, `file_copy.conflicts`, and
`CoreDeviceOperations.info`. Only the now-unused `posixpath` import and the
obsolete wrapper's event emitter were removed with the fresh-folder pair.
Shared transfer imports/helpers and retained raw factories remain.
`ArgonautCore.credential_for` became `_credential_for`; an AST comparison to
HEAD confirms an identical signature/body after normalizing only the name.
Exactly `test_profile`, `read_model`, `connect`, and `reconnect` call it.

The production symbol search now finds only the private definition/four calls
and one explicitly commented history-only `ai_analysis.py` literal. No public
resolver, deleted callable, alias, shim, dynamic lookup or presentation resolver
caller remains. The three boundary methods inspect application AST/source and
exact owners without importing GTK. The existing real loopback R2 CLI success
case now traps both `transfers.connect` and `CoreDeviceOperations.open_ftp`.
All 36 composite and 30 CLI R2 methods remain present and pass.

Pre-deletion reachability confirmed the contract: no live caller for a deleted
surface, and no supported external Python API promise found in repository
exports, documentation or packaging. Other `info` calls belong to UltimateClient
or logging; `conflicts` fields belong to current plans/reports. Historical docs
and diagnostic strings are not callable references. External arbitrary Python
imports were not surveyed and are not promised compatible.

Byte comparisons against HEAD confirm unchanged `native_files.py`, `disk_run.py`,
`usb_backup.py`, `api.py`, `folder_copy.py`, `simulated_c64u.py`,
`test_lab_probe.py`, `__main__.py`, `fresh_folder_cli.py`, `file_service.py`,
`c64_ai_install.py`, and `test_lab.py`. All other tracked application files
outside the five explicitly changed files remain unchanged. SERVER-FIRST.md,
README and NEXT-PASS remain unchanged. Both production folder-plan consumers
still pass all three managed flags. No deferred branch or live route was edited.

### Commands and exact results

Run from the existing repository, in the required sequence (output logs were
written outside the repository under `/tmp/r3-*.log`):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests /usr/bin/python3 -m unittest test_fresh_folder test_fresh_folder_cli test_transfers test_file_copy test_folder_copy test_file_service test_core test_package_credential_channel test_ai_analysis test_diagnostics test_native_files test_c64_ai_install test_compatibility_retirement
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests /usr/bin/python3 -m unittest test_c64u_ftp test_ftp_reads test_ftp_streaming test_ftp_mutations test_ftp_uploads test_ftp_replacements test_ftp_replacement_corrections test_ftp_folder_steps test_replacement_source test_usb_backup test_usb_backup_preferences
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -O -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m c64u_browser.test_lab --suite offline
git diff --check
```

| Acceptance run | Methods/checks | Passed | Skipped | Failures/errors |
|---|---:|---:|---:|---:|
| Focused R3, including all 66 existing R2 methods | 162 | 162 | 0 | 0 |
| FTP and USB regression families | 257 | 257 | 0 | 0 |
| Full normal | 1032 | 996 | 36 | 0 |
| Full optimized | 1032 | 996 | 36 | 0 |
| Offline Test Lab | 17 | 17 | 0 | 0 |

The initial sandboxed focused attempt reported 84 errors/subtest errors because
local fake-server socket creation was denied. The same command passed after
allowing loopback sockets. No assertion was weakened and no skip was added to
work around the restriction. The 36 full-suite skips are the existing opt-in
display cases. Pre-edit and final `git diff --check` passed, including a separate
whitespace check for the untracked R3 document and new boundary module.

### Method accounting and retained evidence

Historical R2 full baseline: 1025 = 989 passed + 36 skipped.
Removed three helper-only methods:

- `Transfers.test_upload_verification_and_mkdir_failure`.
- `Transfers.test_corrupt_upload`.
- `CopyTests.test_conflicts_include_directories_and_broken_links`.

Added ten methods:

- Four Core operation matrix methods, one each for test_profile, read_model,
  connect and reconnect. Together these exercise 45 applicable synthetic matrix
  rows, including independent endpoint changes, missing IDs, entered/session/
  remembered precedence, empty/None backend values and short-circuit lookup traps.
  Reconnect has no entered-password argument, so only its nine applicable rows run.
- Two current folder-planner methods for file-vs-directory/broken-link conflicts
  and case-insensitive existing remote collisions, with no-overwrite/no-mutation
  assertions. Existing directory merge coverage is retained.
- One saved historical-report sanitization method in test_ai_analysis.
- Three source/AST/owner boundary methods in test_compatibility_retirement.

Thus 1025 - 3 + 10 = 1032 methods; net +7. Success and MKD-refusal assertions
from the retired transfer tests remain in existing R2 methods. Existing R2
corrupt-readback/SIZE coverage now explicitly proves no RNFR/RNTO/DELE/RMD,
one MKD/STOR/RETR, no published destination, retained staging evidence, created
directory evidence and no retryability. Existing R2 helpers already prove one
connection/no reopen and no cleanup. These are strengthened existing methods,
not new methods. Both package credential-channel methods retain their identities
and now observe fake-client inputs via test_profile (including subprocess code);
store isolation, filesystem scans and process lifetime checks remain intact.

### Review boundary and limitations

Implemented only the approved retirement. No unresolved issue or design deviation
remains. Final human review is pending. Physical qualification is not required
because no live transfer workflow changed, and no physical C64U was contacted.
No live CLI/Test Lab/AI/Flash migration, deferred fallback retirement, R4 design,
commit, push, merge, tag, package or release occurred. The starting weekly usage
baseline supplied for this pass was 85% remaining; no new meter value is inferred.
