# Final FTP ownership closure — 4 October 2026

Implementation and deterministic evidence; no new design or feature scope.

## Authority and scope

Repository: `/home/bruce/Documents/ChatGPT/Local Projects/argonaut-network-slice2`.
Initial HEAD = local `origin/development` =
`f9457acd3bcef4269d9d98e95ef3c6dc33f90ff1`; parent
`dab627979b9d3bb085c955c6e3bea8cdaff8b338`; subject
`Implement R6 managed Flash publication`; divergence `0 0`; worktree clean.
Starting RU: user-supplied 32%, no subsequent percentage inferred.
No fetch, staging, commit, push, branch/worktree creation, package or release.

Current callers were checked before deletion. No contrary supported raw owner
was found. Core installs the managed adapter; FileService and USB restore already
selected all managed folder branches, and remote deletion selected managed mode.
No supported workflow migration or local-only behavior removal was required.

## Removed and retained surfaces

- Removed `CoreDeviceOperations.open_ftp` and `transfers.connect`, without shims.
- Removed legacy `transfers.upload/_upload` and `files.operate`; shared mutation
  validation now requires the managed execution callback.
- Removed raw remote deletion and three folder-plan selection flags; supported
  remote additions/folders/replacements/deletion select accepted managed paths.
- Narrowed `copy_files` to local destinations and `replace_file` to local
  replacement. Remote destinations use existing managed folder/composite routes.
- Removed native/Game/SID read, disk image read, and USB hash raw fallbacks.
- Removed raw identity factory/listing and USB text identity compatibility.
  Managed MLSD/LIST byte fidelity, ordering, paths and fingerprint tests remain.
- Removed `api.parse_list`; parser checks use accepted `ListingParser`.
- Removed simulator `_TransferFTP`; explicit `MemoryFilesystem` exercises real
  managed adapters and staged upload/readback/SIZE/publication. USB policy tests
  share that fixture, with byte-preserving identity and cancellation/failure hooks.
- Retained Core facade, local operations, REST/DMA, and accepted managed transport.
  No `ftplib` import/constructor remains anywhere in application Python modules.
  Raw control/data sockets remain encapsulated in `c64u_ftp.py` by design.

The strengthened static boundary test recursively inspects all application Python
sources, normalizes absolute/relative/aliased imports and simple assignment
aliases, and rejects legacy factory/member references as well as definitions.
Client capability references (including constructor assignment) require exactly
`c64u_browser.c64u_ftp.C64UFtpLeaseManager.lease`. Three named offline import edges
permit `test_lab` → `simulated_c64u`, `simulated_c64u` → `simulated_ftp_reads`, and
`test_lab_probe` → `simulated_ftp_reads`; fixture modules are inspected too.
Local fixture definitions are not cross-module imports. No current internals
need ftplib constants/types, so the existing no-ftplib architecture is retained.
The conservative alias union does not let later shadowing erase a dependency;
wildcard imports are rejected. This is a static reference guard, not a proof
against dynamic import strings, reflection or arbitrary Python dataflow.
Existing runtime assertions also reject raw selection flags.
Runtime traps prohibit socket/raw FTP acquisition for missing-adapter calls and
all 17 offline checks. Identity-only test doubles explicitly provide byte methods.

## Deterministic commands and results

Run from the repository above. Loopback selections/full suites require local
socket permission; no hardware hosts are used.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python3 -m unittest test_ftp_ownership test_api test_transfers test_empty_upload test_cancel_copy test_upload_cleanup test_files test_deletion test_native_files test_disk_run test_next_pass test_replacement_source test_diagnostics test_test_lab test_usb_backup test_file_copy test_folder_copy
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python3 -m unittest test_c64u_ftp test_ftp_mutations test_ftp_uploads test_ftp_streaming test_ftp_reads test_ftp_folder_steps test_ftp_replacements test_ftp_replacement_corrections test_c64_ai_install test_c64_ai_preparation test_r5_headless_reads test_r6_flash test_flash_cleanup test_fresh_folder test_fresh_folder_cli test_file_service test_core
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 python3 -O -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m c64u_browser.test_lab --suite offline
git diff --check
```

Pre-correction accepted results: **125/125 focused**, **466/466 managed/R4/R5/R6**, normal and
optimized each **1,177 run = 1,141 passed + 36 existing display skips**, zero
failures/errors; **17/17 Offline Test Lab checks**. Normal elapsed 23.627 seconds;
optimized 23.145 seconds. No skips were added or used to hide a regression.

Published R6 baseline is 1,171 discovered methods, including the 18 cleanup tests
added after the historical 1,153-method R6 run. AST enumeration is 1,172 because
`test_core.FakeClient.test_connection` is a helper, not a discovered test.
The original closure added six boundary methods, yielding 1,177 discovered
methods / 1,178 AST definitions. This correction adds ten self-test methods:
final **1,187 discovered methods / 1,188 AST definitions**, sixteen total methods
added since R6. Discovery has zero loader errors. No methods deleted, no new
skips; the prior full runs retain 36 existing display skips. Four methods renamed:

- `test_ftp_mutations`: `test_deferred_composites_keep_explicit_legacy_routes`
  → `test_composites_have_no_legacy_routes`.
- `test_ftp_reads`: `test_fingerprint_exact_legacy_digest_with_one_connection`
  → `test_fingerprint_exact_byte_fixture_digest_with_one_connection`;
  `test_mutating_transport_factory_remains_legacy`
  → `test_raw_transport_factories_are_absent`.
- `test_ftp_uploads`: `test_deferred_routes_do_not_select_managed_upload`
  → `test_composite_routes_select_managed_owners`.

Other modified test methods were converted in place. Old raw-factory traps now
trap `ftplib.FTP` directly or assert symbol absence. Offline check IDs, schema,
privacy and outcomes remain; upload diagnostics now explicitly include the real
managed listing events (three before successful upload; one before collision).

Corrected iterations (temporary logs `/tmp/ftp-closure-*.log`):

| Run | Result and correction |
| --- | --- |
| focused1 | 84 tests, 2 failures + 1 error: fixture path validation and nested managed diagnostic expectations corrected. |
| focused2 | 119 tests, 1 failure: asserted cleanup's actual empty evidence tuple and verified staging directory removal directly. |
| focused3 | 125 tests, 2 failures + 2 errors: test-only allowlist, MLSD capability field and fingerprint argument corrections. |
| focused4 | 125 tests passed. |
| managed1 | 466 tests, 656 socket-permission subtest errors + 4 historical boundary failures; reran with authorized loopback and converted retention assertions. |
| managed2 | 466 tests, 2 historical boundary failures + 1 raw identity fixture error; corrected assertions and replaced raw peer with byte identity tree. |
| managed3 | 466 tests passed. |

## Tiny static-guard correction and final-review history

Final review blocked publication despite sound production closure: aliased
`ftplib` constructor assignment, module-qualified aliased client construction,
absolute simulator imports and aliased absolute `transfers.connect` imports all
escaped the original guard. It also accepted unrelated functions named `lease`
and scanned only top-level files. That failed review remains historical evidence;
the original guard was insufficient to support the ownership claim.

Correction authority reverified R6 HEAD, parent, subject, local origin equality,
`0 0` divergence and empty index. Initial preserved closure: 44 files,
+805/−823 (42 modified, two new). Correction RU baseline: user-supplied 25%;
no later percentage inferred. Only this report and `tests/test_ftp_ownership.py`
changed during this pass; content hashes verify every other repository file was
preserved, including all production/application files.

Ten self-test methods cover: ftplib import/constructor aliases; direct and
module-qualified client aliases; absolute/relative simulator imports; legacy
factory imports and references; false `lease` owners including nested functions,
lambdas and method defaults; recursive subpackage discovery; the legitimate
manager owner; the three explicit offline edges and fixture-local definitions;
legacy definitions/members and wildcard rejection; package-relative imports and
shadowed aliases. Positive controls accept the exact managed owner and offline
edges, while same-named subpackage impostors are rejected.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python3 -m unittest -v test_ftp_ownership test_c64u_ftp.ParserTests.test_only_core_read_adapter_imports_transport_and_headless_boundary test_ftp_reads.ReadMigrationTests.test_raw_transport_factories_are_absent test_ftp_mutations.MutationRoutingTests.test_composites_have_no_legacy_routes test_ftp_uploads.UploadTests.test_composite_routes_select_managed_owners
```

Final focused result: **20/20 passed**, zero skips, 1.657 seconds: 16 ownership
methods (ten new self-tests plus six retained) and four existing boundary methods.
The retained refusal tests and all 17 offline checks passed under network traps.
Each of the four exact review probes was also appended to real Core source in
memory only and independently rejected. Current recursive scan: **116 production
Python modules, zero violations**, with no module exclusions.

The first correction run had three assertion failures because fixture-local
references were misclassified as cross-module imports. The helper was corrected
and a positive control added; no production violation was found.

Full normal/optimized suites and the broad 125/466 selections were deliberately
not rerun: their accepted results above remain documentary evidence, not new
1,187-test execution claims. Final discovery only confirms 1,187 methods. Python
syntax compilation (without bytecode) and tracked plus both untracked whitespace
checks pass. No production changes or physical qualification were needed.
Verdict: READY for compact final re-review/publication; no staging/commit/push.

## Verification and qualification

`git diff --check` and untracked `git diff --no-index --check /dev/null <file>`
checks pass. All changed/new files are UTF-8, non-executable; Python compilation
and AST parsing pass without generating bytecode. Bounded scans found no private
key blocks or OpenAI/GitHub/AWS token patterns. Serialized offline evidence has no
private fixture names, fixture hostname, passwords, device paths or hardware IPs.
Command: `PYTHONDONTWRITEBYTECODE=1 python3 /tmp/ftp-closure-hygiene.py`; summary
saved to `/tmp/ftp-closure-hygiene.log`. The first hygiene wrapper incorrectly
required exit 0 for a nonempty no-index diff (Git returns 1); corrected to require
no whitespace diagnostics and exit 0/1, then passed. This was a wrapper error,
not a whitespace defect.

AST comparisons against HEAD confirm unchanged `upload_managed`,
`_managed_download`, `local_copy`, `run_image_bytes`, `validate_upload`, and
`_upload_flash`. Managed transport/types/adapter, folder steps, replacement,
fresh-folder, AI operation, headless reads and exact Flash cleanup modules have
no diff. Supported remote selectors are the same formerly-always-true branches.
Thus no supported managed wire sequencing or policy changed: **no physical
qualification required or performed**. R1–R6 physical evidence remains applicable.
Existing external-writer race limitations remain; no new atomicity is claimed.

No unresolved implementation issue or scope deviation is known. GUI display tests
remain the existing opt-in skips; deterministic service/CLI/Test Lab checks passed.
This closes FTP ownership only; Streams, Ultimate Menu and cartdumper remain later
product work. Stop for compact final review; implementation is not committed.

## Complete changed-file inventory

Including untracked new files after correction: **44 files, +1123/−823**
(42 modified, 2 new).
No files deleted. New files are this evidence record and `tests/test_ftp_ownership.py`.
All other listed files are modified:

- `c64u_browser/api.py`
- `c64u_browser/core.py`
- `c64u_browser/deletion.py`
- `c64u_browser/disk_run.py`
- `c64u_browser/file_copy.py`
- `c64u_browser/file_service.py`
- `c64u_browser/files.py`
- `c64u_browser/folder_copy.py`
- `c64u_browser/native_files.py`
- `c64u_browser/replacement.py`
- `c64u_browser/simulated_c64u.py`
- `c64u_browser/simulated_ftp_reads.py`
- `c64u_browser/test_lab.py`
- `c64u_browser/transfers.py`
- `c64u_browser/usb_backup.py`
- `docs/C64U-FTP.md`
- `docs/CURRENT-STATE.md`
- `docs/FTP-OWNERSHIP-CLOSURE.md`
- `tests/test_api.py`
- `tests/test_c64u_ftp.py`
- `tests/test_cancel_copy.py`
- `tests/test_deletion.py`
- `tests/test_diagnostics.py`
- `tests/test_disk_run.py`
- `tests/test_empty_upload.py`
- `tests/test_file_copy.py`
- `tests/test_files.py`
- `tests/test_folder_copy.py`
- `tests/test_fresh_folder_cli.py`
- `tests/test_ftp_folder_steps.py`
- `tests/test_ftp_mutations.py`
- `tests/test_ftp_ownership.py`
- `tests/test_ftp_reads.py`
- `tests/test_ftp_replacements.py`
- `tests/test_ftp_uploads.py`
- `tests/test_native_files.py`
- `tests/test_next_pass.py`
- `tests/test_r5_headless_reads.py`
- `tests/test_r6_flash.py`
- `tests/test_replacement_source.py`
- `tests/test_test_lab.py`
- `tests/test_transfers.py`
- `tests/test_upload_cleanup.py`
- `tests/test_usb_backup.py`
