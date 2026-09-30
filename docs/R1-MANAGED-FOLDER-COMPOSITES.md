# R1 — Managed Folder Composites

## Status and authority

R1 is an approved implementation checkpoint within Argonaut 1.10 —
C64U Network Foundation / FTP Slice 3.

Accepted development baseline:

`8315985317086e52460c981a8135bffb359da958`

That commit contains the accepted and physically qualified FTP work through
Slice 3D.

This document is the implementation contract for R1.

The broader architecture and established FTP contracts remain documented in:

- `CURRENT-STATE.md`
- `C64U-FTP.md`
- `SERVER-FIRST.md`

If this document conflicts with an established safety or transport contract in
those documents, stop and report the conflict rather than silently changing
behavior.

## Purpose

R1 closes the two remaining raw-FTP ownership gaps in normal remote folder-plan
execution:

1. creation of missing remote directories;
2. same-device remote-source to remote-destination nonreplacement file
   additions.

R1 composes the managed FTP capabilities already accepted in Slices 3A–3D. It
must not create a second transport/session architecture.

## Scope

R1 migrates:

- missing remote directory creation in FileService folder plans;
- missing remote directory creation in USB restore plans;
- same-device remote-source to remote-destination nonreplacement file
  additions through FileService folder plans;
- structured evidence and reporting required by those routes;
- narrowly scoped managed-download cleanup evidence required to preserve
  primary failure certainty.

Production callers affected are:

- `FileService.execute_copy()` through `folder_copy.execute_plan()`;
- `UsbBackupService.execute_restore()` through the same folder-plan executor.

Remote-to-remote in the current Argonaut API means two paths on the same active
C64U. Cross-device copy is not represented or supported by this checkpoint.

## Explicit non-scope

R1 must not migrate or redesign:

- accepted local-source to remote additions from Slice 3C;
- accepted remote replacements from Slice 3D;
- local-destination operations;
- Flash workflows;
- CLI fresh-folder upload;
- C64 AI installation, upgrade or provisioning;
- general CLI or Test Lab networking;
- compatibility/raw-FTP retirement;
- cross-device copying.

Do not globally convert shared legacy helpers merely because managed
implementations now exist.

Legacy infrastructure required by later checkpoints must remain available until
its production consumers are migrated.

## Existing folder-plan behavior to preserve

Folder planning and execution currently preserve these rules:

- missing or unsupported sources are rejected;
- local symlinks are rejected;
- a directory cannot be copied into itself or a descendant;
- duplicate destination mappings are detected;
- remote duplicate/conflict matching is case-insensitive;
- existing directories are merged only when spelling and kind satisfy the
  existing contract;
- file conflicts remain distinct from additions;
- eligible replacements retain their reviewed signature;
- parent directories are planned before descendants;
- traversal remains bounded to the existing item and depth limits;
- execution revalidates source kind, checked ancestors and destination state;
- completed, skipped and remaining accounting is preserved.

R1 changes FTP ownership, not these planning semantics.

## Managed folder MKD contract

A planned missing remote directory must use the accepted managed MKD primitive
from Slice 3B.

Each directory step receives its own managed operation lifetime unless it is
already legitimately nested inside the same adapter operation.

The operation must include execution-time validation and the consequential MKD.

Do not hold one FTP lease across the complete folder plan.

Preserve:

- source and ancestor validation;
- remote storage-root/path restrictions;
- filename/path validation;
- case-insensitive conflict detection;
- distinction between a reviewed existing directory and a planned new
  directory.

A directory that appears after planning must not simply be adopted as though
Argonaut created it.

### MKD outcomes

Acknowledged MKD:

- record the mutation as completed;
- record the directory step in the completed prefix;
- do not add a trailing cancellation check that relabels the completed
  mutation.

Explicit refusal:

- stop the plan;
- retain mutation outcome and reply evidence;
- do not mark the directory completed.

Unknown completion:

- stop the plan;
- retain the uncertain directory path and mutation evidence;
- do not assume the directory exists or does not exist.

Cancellation before submission:

- submit no MKD;
- retain ordinary cancellation semantics.

Cancellation pending after acknowledged MKD:

- preserve the completed directory;
- honor cancellation before the next plan step.

Binding/session invalidation:

- stop through the established managed checks;
- retain all mutation evidence already established.

An uncertain MKD is an inspection target only. It is not authorization to:

- retry MKD automatically;
- probe the path and continue the old plan;
- reuse the directory as though its provenance were known;
- delete it automatically.

No additional post-MKD listing is required solely for R1.

## Same-device remote-to-remote addition contract

A remote-source to remote-destination nonreplacement file addition must use one
fixed-binding managed operation for that file.

The required sequence is:

1. require the captured managed adapter;
2. prepare private local temporary storage;
3. enter the per-file managed operation;
4. execute existing step validation and require an absent destination;
5. download the source through the accepted Slice 3A managed streaming path;
6. retain the source observation;
7. upload the locally published temporary file through the accepted Slice 3C
   managed staged-upload path;
8. retain the destination upload and publication evidence;
9. release the remote operation;
10. complete local temporary cleanup;
11. record whole-step completion only if all required work succeeded.

The next file receives a new operation lifetime.

Do not use a batch-wide FTP lease.

A missing managed context must fail closed. It must never fall back to raw FTP.

## Operation and lease ownership

For same-device remote-to-remote copy, one adapter/binding legitimately owns
both source and destination paths, including when they reside on different
volumes of the same C64U.

Within one file operation:

- lease acquisition remains lazy;
- nested source and destination operations reuse the same lease;
- commands use absolute remote paths;
- CWD-changing listings must not redirect later commands;
- nested acquisition must not self-contend;
- a poisoned or failed lease must not reopen;
- read fallback must not clear consequential mutation/write state;
- binding and recovery checks remain effective;
- the Core connection epoch must not change;
- outermost exit releases the lease.

Preview/review and execution remain separate lifetimes.

## Source verification

The source download retains the accepted Slice 3A contract:

`SIZE → RETR/hash → flush/fsync → SIZE → local publication`

Record the successful source byte count and SHA-256 observation.

The source is read-only.

R1 must never:

- STOR to the source;
- rename the source;
- delete the source;
- remove a source directory;
- convert cancellation into move semantics.

The source observation describes the bytes read during the download.

It does not guarantee:

- source locking;
- an atomic snapshot;
- immutability after the read;
- protection against external writers after the observation.

No final source reread is added by R1.

## Destination verification

The destination uses the accepted Slice 3C staged-upload contract:

`preflight → STOR staging → bounded RETR/hash → SIZE → destination recheck
→ RNFR/RNTO publication`

The local temporary file is opened and sized according to the accepted 3C
exact-length contract.

Preserve:

- zero-byte support;
- exact-length enforcement;
- case-insensitive destination conflict refusal;
- no intentional overwrite for an addition;
- sent-byte count/hash evidence;
- independent destination RETR/hash verification;
- SIZE verification;
- publication mutation evidence;
- staging-candidate semantics;
- location-unknown semantics;
- no automatic cleanup or publication replay.

The source and destination are independent observations.

Do not substitute the source digest for destination readback verification.

Record source and destination count/hash observations separately.

They should agree in normal successful execution, but R1 does not add a new
post-publication production verification merely to compare them.

## Local temporary storage

Remote-to-remote copy uses private local temporary storage.

Preserve the existing managed-download guarantees including local staging,
flush/fsync and no-replace publication.

Local temporary state must be cleaned on normal completion and attempted on
failure/cancellation.

### Failure precedence

A local cleanup failure must never overwrite more important remote or
cancellation evidence.

This applies to both:

1. managed download's staging-file cleanup;
2. outer composite temporary-directory cleanup.

Primary evidence must be normalized before cleanup can replace it.

### Source/download failure plus cleanup failure

Preserve:

- primary source/download failure;
- transfer evidence;
- count/hash evidence available to that point.

Record the local cleanup failure separately.

Do not start destination upload.

### Destination failure or uncertainty plus cleanup failure

Preserve the complete destination `UploadEvidence`, including:

- STOR evidence;
- verification state;
- publication state;
- staging/final alternatives where applicable.

Record local cleanup failure separately.

### Cancellation plus cleanup failure

Cancellation remains the primary workflow classification.

Retain all accumulated remote evidence.

Record local cleanup failure separately.

### Remote publication completed plus cleanup failure

Preserve destination publication as completed.

Do not create a remote partial-upload cleanup shortcut.

Retain the existing whole-step failure accounting, but reporting must clearly
state that destination publication completed and must not be replayed.

Record local cleanup failure as secondary local evidence.

A local cleanup failure must never cause:

- remote rollback;
- remote deletion;
- reconnect-and-continue;
- upload replay;
- mutation replay.

Cleanup evidence must be sanitized. Do not expose private temporary paths or
unrestricted local exception text.

## Partial state and destructive authorization

Preserve the accepted Slice 3C partial-state model.

A valid staging candidate may use the existing session-bound `PartialUpload`
workflow and fresh reviewed deletion.

Unknown publication:

- retains staging/final alternatives;
- must not become a staging-only cleanup shortcut;
- must not select either path automatically.

Successful destination publication followed by local cleanup failure has no
remote partial-upload shortcut.

MKD uncertainty must never become `PartialUpload`.

Source failure creates no destination partial state when destination work never
began.

All evidence is observational. It does not itself authorize deletion, replay or
rollback.

## Folder-step evidence

Add only the minimum immutable evidence needed to preserve R1 state through the
existing result layers.

A folder-step evidence record may contain:

- relative plan step;
- operation kind;
- source and destination;
- current/stopped phase;
- validation status;
- source count/hash observation;
- source transport failure evidence;
- directory mutation evidence;
- association with destination `UploadEvidence`;
- publication status;
- secondary local cleanup failure;
- sanitized primary error category.

Do not invent primitive outcomes for phases that did not run.

Preserve the existing upload collections:

- `Report.uploads`;
- `CopyResult.uploads`;
- `RestoreResult.uploads`.

Store an upload observation once. Folder-step evidence may reference/associate
with it but must not duplicate user-facing upload messages.

Evidence must survive:

`composite → Report → CopyResult/RestoreResult → job snapshot → details`

Uncertain mutation/write failures remain nonretryable.

## Accounting

Preserve current folder-plan accounting.

- Previously acknowledged steps remain completed.
- The stopped item remains first in `remaining`.
- Unattempted later items remain after it.
- Directory completion contributes no file bytes.
- USB restore byte accounting remains based on manifest sizes of completed file
  steps.
- Do not silently redefine existing progress behavior.

If destination publication completed but local cleanup subsequently failed, the
whole step may remain unfinished under existing accounting, but structured and
human-readable reporting must explicitly say publication completed and must not
suggest replay.

## Cancellation

### Directory step

Before validation/MKD:

- honor cancellation normally.

After MKD submission:

- use accepted 3B mutation/cancellation semantics.

After acknowledged MKD:

- preserve completed mutation;
- honor pending cancellation before the next plan item.

### Remote-to-remote file step

Before/during source read:

- honor cancellation;
- do not start destination upload after cancelled source acquisition.

After local source publication and before destination STOR:

- honor cancellation at the next established check.

During STOR/readback/SIZE:

- preserve accepted 3C cancellation and partial-state behavior.

Before destination publication:

- honor normal cooperative cancellation.

During RNFR/RNTO:

- preserve accepted 3B serialization and cancellation deferral.

After acknowledged destination publication:

- do not add a new cancellation check that relabels the completed publication;
- finish required local cleanup;
- preserve completion evidence.

Before the next plan item:

- honor pending cancellation while retaining the completed prefix.

A pending cancellation must not replace a real transport, mutation, binding or
verification failure.

No replacement-style cancellation scope spans the entire remote-to-remote
addition.

## USB restore

R1 affects USB restore through managed creation of missing destination
directories and folder-step evidence/reporting.

USB restore does not currently generate remote-to-remote additions.

Preserve:

- backup-storage identity;
- manifest verification;
- consumed/expiring review plans;
- device/session binding;
- volume fingerprint/reclassification;
- explicit replacement selection;
- accepted Slice 3C file additions;
- accepted Slice 3D replacements;
- skip/conflict/unchanged accounting;
- completed/remaining accounting;
- unrelated-file preservation.

Do not change accepted file routing.

## Reporting

Human-readable details must make relevant R1 state inspectable, including:

- uncertain MKD;
- source/download failure evidence where appropriate;
- destination publication uncertainty;
- publication-completed/local-cleanup-failed state;
- secondary local cleanup failure.

Inspection information does not authorize retry, rollback or cleanup.

Evidence-bearing cancelled copy jobs must remain inspectable through the
existing detailed-report mechanism.

Do not perform a general GUI redesign for R1.

## Legacy routing intentionally retained

After R1, FileService and USB restore folder plans must no longer use legacy
remote MKD.

FileService same-device remote-to-remote nonreplacement additions must no
longer use legacy destination upload.

Do not remove shared infrastructure still required by later checkpoints,
including as applicable:

- `transfers.connect()`;
- `CoreDeviceOperations.open_ftp()`;
- legacy upload;
- legacy remote replacement;
- Flash route;
- CLI route;
- AI route;
- offline simulation/test seams.

R1 is not the final escape-retirement checkpoint.

## Deterministic acceptance requirements

Start from the committed baseline:

**939 tests / 36 skips**

Focused deterministic coverage must establish at minimum:

### Managed MKD

- acknowledged creation;
- explicit refusal;
- lost reply / unknown completion;
- cancellation before submission;
- cancellation pending after acknowledgement;
- stale binding;
- source/ancestor/destination change;
- exact-case conflict;
- existing-directory merge;
- no retry/continuation after uncertainty;
- intended session/authentication/FEAT ownership;
- release on every exit.

### Remote-to-remote addition

- normal file;
- zero-byte file;
- source short/overlong/change failures;
- local source publication protection;
- destination conflict;
- destination STOR failure/uncertainty;
- destination readback/SIZE failure;
- destination publication uncertainty;
- source preservation;
- same-device single operation/lease;
- absolute-path safety;
- no self-contention;
- no failed-lease reopening.

### Cleanup precedence

Cover both managed-download staging cleanup and outer temporary-directory
cleanup.

At minimum:

- source failure + cleanup failure;
- destination uncertainty + cleanup failure;
- cancellation + cleanup failure;
- destination publication success + cleanup failure.

Primary evidence must survive every case.

### Cancellation/accounting

- cancellation at the defined boundaries;
- acknowledged late success;
- completed-prefix preservation;
- no cancellation leakage into later jobs.

### Result propagation

- directory evidence;
- source observation;
- destination UploadEvidence;
- publication uncertainty;
- secondary cleanup evidence;
- nonretryable uncertainty;
- detailed reporting for evidence-bearing cancellation.

### Routing regression

Verify unchanged routing for:

- accepted 3C local additions;
- accepted 3D replacements;
- local destinations;
- Flash;
- CLI;
- AI.

Use socket fixtures where wire behavior or session ownership matters.

Run focused tests first.

Do not proceed to physical qualification merely because focused tests pass.
Stop at the requested implementation review gate.

## Physical acceptance requirements

Physical acceptance, when separately authorized, must run independently on both
C64Us using uniquely named disposable data.

It should verify:

1. managed nested directory creation through a folder plan;
2. same-device remote-to-remote copy of known content;
3. zero-byte copy where practical;
4. source preservation;
5. independent destination count/hash verification;
6. absence of unexpected staging artifacts;
7. local temporary cleanup;
8. controlled USB restore missing-directory creation;
9. per-step session/authentication/FEAT behavior;
10. stable Core epoch and zero remaining leases;
11. final reviewed cleanup and independent absence verification.

Do not physically inject lost replies, uncertain publication, local cleanup
failure or active-transfer disconnects.

Those remain deterministic-fixture responsibilities.

## Completion criteria

R1 is complete only when:

- FileService/USB folder-plan missing-directory creation has no production raw
  FTP ownership;
- FileService same-device remote-to-remote nonreplacement additions have no
  production raw destination-upload ownership;
- source and destination verification remain independent;
- uncertain mutation/upload evidence survives to final result/report layers;
- local cleanup cannot erase primary remote certainty;
- accepted 3C/3D behavior remains unchanged;
- deferred R2–R6 consumers remain explicitly deferred;
- deterministic tests pass;
- physical qualification passes on both C64Us;
- the reviewed changes are committed and pushed by normal fast-forward.

## Stop conditions

During implementation, stop and report rather than expanding scope if:

- cross-device copy behavior is discovered;
- R1 requires changing accepted 3C or 3D contracts;
- a deferred Flash/CLI/AI route would need migration;
- an uncertain mutation cannot be represented by existing/additive evidence;
- a cleanup failure cannot be preserved as secondary evidence;
- implementation would require deleting a shared legacy escape route needed by
  later checkpoints.

Do not begin R2 as part of R1.

## Physical qualification — PASS (29 September 2026)

The reviewed R1 implementation passed authorized headless Core/service physical
qualification independently on both C64 Ultimates. Qualification used uniquely
named disposable trees and the normal identity-bound Argonaut profiles.

| Device | Address / physical ID | Firmware | Storage | Disposable tree (now removed) |
| --- | --- | --- | --- | --- |
| Beige | `192.168.68.70` / `25EA78` | `1.1.0s2` | `/USB2` | `/USB2/argonaut-r1-accept-166f51aa31974f2d8f5af0c60cc062cf` |
| Founder's | `192.168.68.69` / `25BE71` | `1.1.0` | `/SD` | `/SD/argonaut-r1-accept-8d8020abf4a84aebb105f66a7ef9c7f8` |

Identity was reverified through bound Core profiles before mutation. Previously
accepted managed mkdir and 3C local-source additions supplied disposable setup
data. Each R1 FileService folder plan copied a normal file, a zero-byte file and
a nested directory from one remote location to another on the same device. The
destination parent already existed; the nested destination directory did not.

On each device the folder plan completed exactly four items with no remaining
or skipped work:

- normal file: `remote-addition`;
- zero-byte file: `remote-addition`;
- nested directory: managed `mkdir`;
- nested file: `remote-addition`.

All four folder-step records completed with passed validation and no error
category. File publication evidence was completed for each remote addition.
Directory creation correctly had no file-publication completion.

Independent post-operation listings verified the zero-byte source and
destination as zero bytes. Independent bounded reads verified the non-empty
source and destination contents and matching SHA-256 values while preserving
the remote source and an unrelated sentinel.

| Device | Content | SHA-256 |
| --- | --- | --- |
| Beige | normal source/destination | `0abc18e15a0dbd17bfc0a0d2cd6b7df2d13e1899669acfa857404aea7e51bc5b` |
| Beige | nested source/destination | `6aa26c8fd197e1becf38fcc8f6e4abdc852d89c47483e7d68c4a0b717b943135` |
| Founder’s | normal source/destination | `8d5b50e8116b7ce2189cb754a84c9b8c859411915686675ab408b57e6a8c365a` |
| Founder’s | nested source/destination | `469b74ae4143db9f7662b7e8c028ff3ec28a01814c2d6c9322891206ac581478` |

A genuine Argonaut backup was then made from each device. Beige backed up the
600-byte nested destination from `/USB2`; Founder's backed up the 640-byte
nested destination from `/SD`. Each manifest reported `state: complete`, an
empty failure field, the expected bound device identity and volume, and a
payload SHA-256 matching the independently verified physical file.

Reviewed FileService deletion then removed only the disposable nested file and
its containing `nested` directory. USB restore preview/execution restored the
missing directory and file. On both devices the restore result reported the
directory and file as additions, with no replacements, skips, conflicts or
remaining work. R1 supplied one managed `mkdir` folder-step record with passed
validation; the restored file remained on the accepted 3C addition path.
Independent readback matched the genuine backup byte-for-byte and by SHA-256.

Every measured consequential operation preserved the Core epoch and ended with
zero active leases. Physical qualification did not inject lost replies,
uncertain publication, cleanup failure, cancellation or network interruption;
those remain deterministic-fixture responsibilities. Per-step authentication
and FEAT ownership are covered by deterministic socket tests; this physical pass
did not retain a complete diagnostic-event count suitable for an additional
physical count claim.

Final cleanup used fresh reviewed deletion plans. Beige removed 12 reviewed
items from its disposable tree; Founder's cleanup was likewise reviewed to
remain inside its unique disposable root. Independent parent listings verified
both acceptance trees absent afterward, with stable Core epochs and zero active
leases.

Immediately after physical qualification, the focused R1 suite passed **20/20**,
the USB backup/restore regression suite passed **19/19**, and the FTP regression
family passed **186/186**. `git diff --check` was clean. No R2 work was begun.
