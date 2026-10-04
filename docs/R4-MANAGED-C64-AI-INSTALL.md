# R4 — Managed C64 AI Installation

## Status and authority

**Physically qualified on Beige and Founder; uncommitted; stop for final R4 review.**
See the controlled physical qualification record below. The following authority
statements describe earlier historical passes.
The design was subsequently approved and implementation explicitly authorized.
The design-only markers below are retained historical status, as confirmed by
the user. No physical, commit/push, branch/worktree, package or release authority
was granted. Implementation starting weekly baseline supplied by user: 80% remaining.

### Original design-pass status and authority (historical)

**Design only; awaiting approval. No implementation or physical authorization.**
This is the next bounded checkpoint after completed R3, not a general ownership
closure or a renaming of AI identifiers. Authority checked on 4 October 2026 in
`/home/bruce/Documents/ChatGPT/Local Projects/argonaut-network-slice2`:
`git status --short --untracked-files=all` was empty; HEAD and local
`origin/development` both were `a081b01c4a62198b35b88199c4c8e48f9c535f90`
(`Retire R3 compatibility surfaces`); divergence was `0 0`. No fetch or ref
mutation was performed. The supplied completed post-R3 AI inspection is the
factual starting point, cross-checked against this source tip. The referenced
conversation could not be retrieved; no additional claims are inferred from it.
Starting weekly usage baseline supplied for this pass: 81% remaining.

Accepted contracts remain authoritative: [C64U-FTP](C64U-FTP.md),
[SERVER-FIRST](SERVER-FIRST.md), [R1](R1-MANAGED-FOLDER-COMPOSITES.md),
[R2](R2-MANAGED-CLI-FRESH-FOLDER.md), and [R3](R3-COMPATIBILITY-RETIREMENT.md).
This document governs the proposed R4 scope; it does not report completed work.

## Confirmed problem and scope

`test_lab_tab.TestLabTab.pair_connected_c64` captures `app.client`, a mutable
Core facade, and invokes `setup_bridge` when configuration is absent, before
`install_and_pair_c64_ai`. Setup saves paired configuration, enables/starts the
bridge and enables health monitoring before file installation. The install helper
uses managed reads through the adapter, but general `upload` and `replace_file`
retain raw writes. Its preliminary full-byte ai.1 recognition does not constrain
the original bytes subsequently observed by generic managed replacement.

Move only AI classification/install/upgrade into a Core-owned scheduled,
session-bound file operation. Reuse managed 3C additions and 3D replacements.
Separate private configuration preparation from consequential bridge work and
retain file consequence independently. Keep generation, tokenizer, launch,
runtime, model selection, chat behavior and existing `c64_ai_*` names unchanged.

No Flash migration; CLI info/ls/browse/get migration/removal; headless Test Lab
hardware migration or roster redesign; raw-read fallback closure; general
folder-copy/deletion closure; credential-store/keyring redesign; background
service/timer redesign; cartridge/TAP/Streams/Ultimate Menu work. General
`upload`/`_upload`, remote `replace_file`, `copy_files` remote branches,
`files.operate` raw branch and `transfers.connect` remain deferred.

## Immutable content and path policy

- Default remains `/USB2/argonaut-ai.prg`, without automatic `/SD` fallback.
  An explicit controlled destination below `/USB[0-9]+` or `/SD` is supported
  for qualification. Apply existing `remote_file`/storage-root validation;
  reject root-only paths, dot/traversal components and protocol delimiters.
  Require an accessible existing parent; do not invent storage or create parents.
- Generate current bytes privately with
  `tokenize_basic_v2(render_chat_client(config.host, config.port, config.token))`.
  Recognized ai.1 is the same private host/port/token generation with
  `clear_question=False` via the existing legacy renderer. No other historical
  client, different pairing, name/size match or hash alone grants eligibility.
- Missing means absence in a successful managed parent observation, not a 550,
  inaccessible path or failed listing. Missing permits only 3C addition.
- Full-byte equality with current bytes permits a verified no-op, with no write.
  Full-byte equality with same-configuration ai.1 permits only protected 3D
  replacement with the additional execution predicate below.
- Every other existing file, including empty, is foreign and refused. Directory
  and unsupported non-file entries are refused. Ambiguous/case-fold collisions
  retain accepted primitive protections. Nothing unknown is overwritten.
- The public result size/hash always describe the generated **current** program,
  even when the existing file is legacy, foreign or no write occurred.

## Decision A — bind full-byte ai.1 eligibility to both 3D observations

Add one optional, Core-private original-content validator factory to
`managed_replacement.replace_managed`, default `None`. This is a sink-side
validation extension, not a new source API or replacement engine. The current
`validate` callback runs before the reads and is insufficient for this purpose.

For each existing original observation (`original-before`, `original-after`),
create a fresh validator sink instead of `_Discard` **only when opted in**.
The AI sink compares each received block at its byte offset against the private
expected ai.1 byte string, remembers mismatch/overflow without storing remote
bytes, consumes the whole bounded observation and checks exact total length.
It returns the accepted block length. Successful completion requires both:

1. The existing independent `adapter.read_into` SIZE → RETR/hash → SIZE sequence
   returns successfully with accepted exact length/transport completion.
2. That observation's fresh sink confirms every byte and total length equal
   the expected legacy generation. Finalize the validator only after the entire
   observation succeeds, never at RETR completion before the final SIZE.

Bind safe eligibility evidence to the precise observation slot, path, device,
session and private preparation ID, with observed byte count/hash and
`full-byte-match`/`mismatch`/`unverified`. No sink, expected bytes or callback
is serialized. Record a slot as passed only after both conditions above.
Require **both** full-byte matches, and keep 3D's existing independent hashes,
signatures, backup inspection and protected exchange checks unchanged. A hash
comparison can corroborate evidence but can never replace the byte predicate.

A preflight classification read remains useful for refusing known foreign content
before any mutation. It is never substituted for either authoritative 3D read.
If ai.1 changes to same-sized foreign bytes after classification, the first
validator refuses before staged upload or original rename. Current 3D has already
created its staging directory at that point: report that acknowledged MKD and
its inspection candidate, without automatic cleanup. Do not promise zero remote
mutation for this race. If change occurs before the second read, that validator
and the existing comparison prevent exchange. A change to exact current during
an attempted legacy replacement also refuses; only a new operation can classify
it as a no-op. No dynamic fallback/reclassification inside replacement.

Defaults are demonstrably unchanged: `None` uses `_Discard` at both original
read sites; no extra read, command, callback, new failure, timing check or
cancellation boundary is introduced for FileService/USB callers. Keep their
signatures, hashes, ordering, 3C nesting, protected rename/cleanup and evidence
semantics. Any new evidence field defaults to absent. Validator errors stop
before exchange and are normalized without exception text or private values.
Use a narrow private validator protocol, not a public arbitrary-byte event hook.

A completed mismatch is a **policy refusal**, not evidence of uncertain mutation.
Incomplete read/transport failure cannot certify foreign or legacy content:
retain unverified eligibility plus failed/cancelled read evidence. Mutation
certainty comes exclusively from 3B/3C/3D evidence; an unknown MKD/publication
reply remains unknown even if a separate policy/read check fails. Candidates
are inspection hints, never existence, cleanup or replay authority.

This closes the classification-to-authoritative-observation gap. It does not
claim server-side compare-and-swap: accepted FTP 3D cannot prevent an external
writer changing a file after the final observation and before rename. Preserve
that documented concurrency limit; do not claim absolute exclusion of external
writers or silently redesign 3D to promise atomic conditional replacement.

## Decision B — private preparation, then gated bridge consequence

The pairing entry point must stop calling consequential `setup_bridge` before
file work. Split out/reuse its pure configuration preparation and its existing
bridge commit/activation behavior, without changing service policy.

1. Under a narrow per-configuration orchestration guard, capture the existing
   validated configuration and revision, or prepare a new private pending
   configuration. Determine local host and validate fixed C64U IPv4 context;
   retain model, port, token and intended address privately. Validate address
   capacity before FTP. The present schema requires 1–4 allowed addresses:
   pending configuration can contain the intended address because it is stored
   separately, never at the service's active configuration path. No schema or
   credential backend redesign is needed.
2. New pending configuration is stored with private directory/file permissions
   (0700/0600), outside any service-consumed path, with an opaque preparation ID.
   Preparation performs no enable/start/restart/pair, health-timer activation,
   service launch or C64 launch. Existing active configuration is not rewritten.
   Privately prepared address membership is intent, not completed pairing.
3. Execute the Core file operation below against that immutable configuration.
   Release the FTP lifetime before bridge work. Evaluate its explicit result,
   not a truthy `installed` field or a generic job-success flag.
4. At the gate, revalidate device/session/address and private configuration
   revision/content against the preparation. Serialize app-supported configuration
   writers with the same narrow guard through commit/pair/activation; use expected
   revision checks at each configuration write. An existing config must still
   match all fields, including token, endpoint, model and address membership.
   For new setup the active path must still be absent. Reload/compare privately
   before consequence and verify the committed configuration afterward. Detect
   unexpected external edits and stop; do not promise locking against arbitrary
   out-of-process writers. Failure to implement bounded config revalidation is a
   stop condition, not permission for general service redesign.
5. Only a permitting file result and matching configuration authorize publishing
   the pending config into the active location, pairing, and the existing
   enable/activation/health behavior. Existing-config pairing uses the current
   bridge helper's rollback behavior. First-time finalization reuses the prepared
   token/endpoint; it must not regenerate them by calling unmodified setup.
   Keep bridge work outside FTP ownership. No remote-file rollback.

If file work fails/refuses/cancels/is uncertain, do not commit active configuration
or invoke bridge side effects. Retain the pending private configuration and safe
operation evidence for explicit review, especially after uncertain or acknowledged
publication; never silently rotate/discard the pairing token and orphan the file.
Existing configuration stays untouched. Retention is not permission to resume:
a new explicit request revalidates context and file state. Pending configuration
may later be explicitly discarded; do not delete remote evidence/artifacts with it.

If bridge work fails/cancels, retain the completed file result and report bridge
failure separately. Preserve bridge-internal rollback and retain the pending
configuration privately even if rollback removes a newly active configuration.
No upload/replacement replay in a bridge retry. A later explicit attempt may use
a new managed exact-current verification; its bridge phase cannot replay the
previous acknowledged mutation. Config changes require stop/reprepare and fresh
policy classification; a differently paired existing program may then be foreign.

## Decision C — Core boundary and lifetime

Expose a dedicated AI file preparation/execution capability through Core, using
its existing scheduler. API names are implementation details; the contract is:

- Preparation captures bound physical identity, `DeviceSession(device_id,
  session_id)`, matching FTP `ConnectionBinding` epoch, concrete private
  `UltimateClient`/managed adapter, endpoint/address and immutable private config.
  Validate the session before and after resolving the concrete client, following
  FileService's capture/check pattern. Reject unbound identity. Never retain or
  resolve `CoreDeviceOperations`/`app.client` as execution authority.
- Return only an opaque, bounded-lifetime, single-use preparation handle and safe
  metadata. Core retains secret configuration and current/legacy generation;
  expiry, discard or terminal completion releases in-memory private state.
  Pending private configuration retention is separate from job/plan retention.
  Preview classification, if offered, is advisory and uses a separate read lifetime.
- Execute one `CoreJob` on `JobBinding.device(captured_session)` in the existing
  `c64u:<physical-id>` FIFO lane. Validate queued session and binding again at
  execution. A same-device reconnect changes session/epoch and refuses, even if
  host and identity are identical. Do not recapture a new client to continue.
- One outer adapter operation owns execution classification, nested read helpers,
  3C or 3D and their accepted nested leases. Acquisition is lazy; release on all
  exits. Do not retain a lease over user review, config review or bridge calls.
  No nested scheduler job that waits on the same lane; invoke managed composites
  inside the owning job. Failure cannot reset/reconnect as a read fallback.
- Execution repeats managed inspection and full-byte current/legacy comparison.
  Compare streaming bytes privately using bounded sinks; do not retain arbitrary
  remote content. Exact-current no-op uses successful execution-time exact
  SIZE/RETR/SIZE plus full-byte equality, not a preview hash. Missing uses 3C's
  no-overwrite revalidation, so a destination occupied during execution refuses.
- 3C/3D take filesystem sources. Create a private 0700 temporary directory and
  0600 current-program file with the intended remote basename, close it before
  use, and never expose its path. Keep it immutable and alive through the entire
  primitive call; no general byte-source API. Do not use generated bytes in
  progress, exception repr, dataclass repr, tracebacks or diagnostic payloads.
- Normalize remote evidence before local cleanup on every exit. Cleanup errors
  are safe secondary categories, never raw OSError/path strings and never a
  replacement for acknowledged publication or uncertainty. Attempt local cleanup
  on success/failure/cancellation; do not add automatic remote cleanup.
- Cancellation before/during read/staging follows accepted primitive behavior.
  Preserve 3C publication and 3D protected-sequence deferral: no post-publication
  cancellation check may turn completed file consequence into cancelled work.
  Use committed-result reporting where appropriate. A pending cancellation may
  stop the subsequent bridge phase without changing the file result.

No raw factory, `open_ftp`, mutable facade, automatic reconnect, retry, rollback
or replay is allowed in this file operation. Preparation handles are one-shot,
including failures. Inspection/review is a new operation, not recovery continuation.

## Decision D — additive typed result and evidence

Extend/adapt `ClientInstallResult` rather than losing its path/installed/size/hash
compatibility; `installed` remains true for acknowledged install or upgrade and
false for no-op/refusal, but is **never** the provisioning gate. Preserve
`ClientProvisionResult` as a composition of file and bridge outcomes, including
failure/cancellation paths. Ensure Core job snapshots retain the safe result on
failed/cancelled jobs, rather than losing it through a raised generic exception.

| Field group | Required meaning |
|---|---|
| Classification | `missing`, `current`, `recognized-legacy`, `foreign`, `non-file`, or `unverified` if observation failed; empty is foreign. Record initial classification separately from authoritative legacy eligibility. |
| Action | `installed`, `upgraded`, `no-op`, `refused`, or `not-completed`; do not invent a successful action for uncertainty. Record attempted action separately if needed. |
| Target/generation | Validated intended remote path; generated current byte count and SHA-256, never remote-foreign digest presented as generated digest. |
| Authority | Captured device ID, session/epoch, safe address context, opaque preparation/config revision ID; mismatch reason. Public config identity is a random opaque ID backed by private exact comparison, not a token or reusable secret hash. |
| Addition/replacement | Accepted `UploadEvidence` or `ReplacementEvidence`, including ordered acknowledged prefix, nested staging upload, publication, cleanup, uncertain paths and transport evidence. Nested 3C publication inside staging is not final replacement publication. |
| Current verification | Execution observation identity, exact count/hash, successful SIZE/RETR/SIZE and full-byte equality; absent/unverified if interrupted. |
| Legacy eligibility | Separate first/second original observation references, counts/hashes, full-byte match status and opaque private generation identity. Never the expected/observed program itself. |
| Cancellation | Queued/classification/staging/original observation/exchange/cleanup/post-file/pre-bridge/bridge phase as applicable; requested, observed and deferred distinctions. |
| Remote disposition | Preserve 3C published/staging-candidate/location-unknown and 3D publication/cleanup/uncertain-path semantics verbatim; no flat boolean replacing them. |
| Secondary evidence | Local temp cleanup attempted/completed/failed with sanitized category; bridge and local cleanup errors separate from primary file consequence. |
| Final disposition | `verified-current`, `installed`, `upgraded`, `refused-unchanged`, `not-completed`, `published-cleanup-incomplete`, or `uncertain`; safe reason and inspection guidance. Refusal can leave staging artifacts: unchanged refers to the original, not the entire directory. |

All results/events/errors/diagnostics exclude password, token, generated or
observed program bytes and private temp/config paths. Sanitize nested primitive
errors before publication; exception chaining and automatic dataclass serialization
must not bypass the safe projection. Remote inspection paths are permitted.
Guidance names last acknowledged/possible locations and instructs fresh inspection
and explicit reviewed action; it grants no cleanup/retry/rollback authorization.

### Exact install/pair gate

| File result | Pair/activate? |
|---|---|
| `verified-current` with successful execution full-byte verification | Yes, only after config/session gate and no cancellation of bridge phase. |
| `installed` with 3C verified acknowledged final publication | Yes, subject to the same gate. |
| `upgraded` with both authoritative legacy matches, 3D publication completed and remote cleanup completed | Yes, subject to the same gate. |
| Any refusal, incomplete/failed read or mutation, cancelled file work, stale context, config mismatch, or uncertain consequence | No. |
| Replacement publication completed but cleanup incomplete/uncertain | No; retain upgraded remote consequence, inspect separately, never replay. |
| Local temp cleanup failure with otherwise trustworthy file success | Retain success; conservatively hold provisioning for review. Do not relabel the remote consequence. |
| Late cancellation after acknowledged file success | File success stands; bridge phase is skipped/cancelled if cancellation is pending. No replay. |

A later bridge failure cannot change these historical file facts. A live bridge
that pre-existed this request need not be stopped on file refusal; the gate forbids
new pairing/activation side effects from this orchestration, not unrelated service
policy. Standalone bridge controls remain outside this file migration.

## Bounded legacy retirement

**Include conditional removal of `CoreDeviceOperations.open_ftp` only.** At this
tip its indirect production caller is `transfers.connect` when
`credentials_encapsulated is True`; the inspected live facade route is AI.
Flash reaches `upload_flash` through FileService's concrete client; CLI get uses
its concrete client. Both continue to require `transfers.connect`. Managed routes
never need the facade factory. Reconfirm the complete static call graph after
migration, including dynamic/attribute dispatch and retained compatibility routes.

Known bounded test adaptations: remove the obsolete presence assertion in
`test_ftp_mutations`; change the `test_fresh_folder_cli` absent-method patch trap
to an absence/static assertion while retaining its raw-connect trap. The
`test_usb_backup` MemoryClient's homonymous method is a test double, not the Core
method. Preserve useful assertions and report test-count changes explicitly.
Add static proof that AI no longer imports/calls legacy upload/replacement or
obtains transport through a facade. Do not remove `transfers.connect` or its
broader compatibility branch merely because this one facade method becomes dead.
If any remaining production caller or material test expansion appears, exclude
this removal and report it for review; do not migrate the caller to force closure.

## Deterministic verification contract for implementation

Use real loopback/socket fixtures for transport and authoritative-observation
races, with synchronization barriers at named phases; mocks alone are inadequate.
Retain existing generation/tokenizer/policy tests. Required assertions include:

1. Missing install enters 3C with fixed ownership, one coherent lease and no raw
   factory/open_ftp. Independent current readback matches; default path and explicit
   storage paths obey policy. Occupy missing destination before 3C publication:
   refuse with accepted staging evidence and preserve occupant.
2. Exact current is verified at execution, causes no STOR/MKD/RNFR/RNTO/DELE/RMD,
   and may pair only after the config gate. Change current after advisory preview
   to foreign: refuse at execution, no mutation.
3. Exact same-config ai.1 enters 3D. Capture command ordering and both independent
   SIZE/RETR/SIZE observations. Both full-byte sinks pass; other-config ai.1,
   foreign, empty, directory/unsupported non-file refuse before any mutation.
4. Barrier after classification but before first original RETR: replace with
   same-length foreign bytes; first predicate fails, no upload/exchange, original
   preserved, only acknowledged staging MKD candidate retained. Repeat with both
   originals returning the same foreign bytes to prove generic hash equality
   cannot authorize AI replacement. Directly test equal count/hash metadata with
   unequal sink bytes to prove the predicate is not digest-only.
5. Barrier after first original observation/during staging: same-size change
   before second original read refuses, keeps accepted 3D artifacts/evidence and
   never renames original. Test short/overlong data, missing/changing SIZE and
   interrupted completion: eligibility remains unverified, not a successful match.
   Existing generic 3D callers without the hook retain exact command/evidence
   behavior and independent-observation mismatch protection.
6. Wrong/stale identity, changed endpoint, same-device reconnect while queued and
   running, queued cancellation with zero wire access, running cancellation in
   classification/staging, lost replies and uncertain exchange preserve contracts.
   No fallback/reopen/replay; leases return to zero and Core epoch never renews
   merely because FTP opens. No mutable facade lookup during execution.
7. Late cancellation after acknowledged publication/replacement keeps success;
   cancellation of subsequent bridge work does not replay file work. Completed
   replacement publication plus backup-delete/rmdir failure preserves consequence
   and blocks provisioning. Local temp cleanup failure is secondary and sanitized.
8. First-time setup with each refused/failed/cancelled/uncertain result performs
   no active-config publish, enable/start/restart/pair/health activation. Verify
   pending config retention and no live-config change. Exact-current/install/
   upgrade permit bridge work only with matching context; config edits at generation,
   queue, pre-pair and commit boundaries stop/reprepare. Concurrent supported config
   writers serialize. Later bridge failure/rollback retains successful file result
   and private pending config; bridge retry cannot invoke acknowledged mutation.
9. Scan public snapshots, progress, errors, exception chains and diagnostics for
   sentinel password/token/program bytes/private paths, including local I/O and
   callback failure. Assert size/hash still describe generated current program.
10. Launch/runtime/chat, Flash, CLI info/ls/browse/get, headless Test Lab roster and
    all deferred compatibility routes remain unchanged. Run accepted 3C/3D/R1/R2/R3,
    FTP and USB regressions, focused AI/Core/scheduler/bridge/GUI orchestration
    tests, full normal and optimized suites and offline Test Lab. No hardware
    sockets in deterministic tests; no skips added to hide regressions.

Historical accepted R3 baseline is 1032 methods (996 passed, 36 display skips)
in each full suite, 162 focused, 257 FTP/USB and 17/17 offline checks. These are
not R4 test results. Use repository-documented test commands and account for new,
adapted and retired methods. `git diff --check` is required throughout.

## Separately authorized physical acceptance

Physical qualification is required later on **both** Beige `25EA78` and Founder
`25BE71`, independently, after design/implementation review and deterministic
checks. It is forbidden in this design pass. Never touch deployed
`/USB2/argonaut-ai.prg`, invoke pairing/service activation, or launch a C64 client.
Use the Core file-only entry point with synthetic private bridge configuration;
no active/pending production bridge config or live token is used.

Reverify identity/session, storage availability and authorization first. Beige
uses a unique private disposable tree under `/USB2`; Founder uses one under
`/SD`. Do not assume advertised media exists and do not silently switch storage.
Qualification must stop if controlled destination/synthetic config cannot be
used safely; deployed AI is never a fallback.

- Missing disposable destination: install with 3C, then independent managed read
  in a new operation comparing complete current bytes/count/SHA-256.
- Repeat at that destination: exact-current no-op, independent byte/hash readback
  and transport command/counter evidence proving zero mutation commands, including
  no temporary staging creation or cleanup.
- At a separate disposable destination, seed exact synthetic same-config ai.1
  using accepted managed addition; verify seed independently. Upgrade through
  the actual Core operation/3D route, independently verify current bytes/hash.
- Seed a foreign file and create a directory at separate disposable destinations;
  both refuse, with independent preservation checks. No production destination.
- Inspect staging/backup state, acknowledged publication/cleanup, stable Core
  epochs/session behavior and zero active leases after every completed operation.
- Explicitly review cleanup of the disposable tree/artifacts using accepted
  reviewed deletion, then independently verify absence in a new operation.
  Unknown outcomes stop qualification for fresh inspection/review, never automatic
  cleanup. Fault injection and timed cancellation remain deterministic only.

Record exact device identities, firmware/API as observed, paths, synthetic byte
counts/hashes, independent observations, command/lease counts, cleanup evidence
and limitations. Do not publish synthetic secrets or generated bytes either.

## Completion, documentation and stop conditions

Later implementation updates current status in CURRENT-STATE, C64U-FTP,
C64-AI-BRIDGE and TEST-LAB, including the minimal setup sequencing and preserved
file/bridge consequences. Keep historical evidence; no broad roadmap rewrite.
This design pass edits only this document, bounded CURRENT-STATE status and a
concise R3 completion clarification, leaving earlier R3 evidence intact.

Checkpoint completion requires design approval; implementation review;
deterministic focused/regression/full/offline tests; static proof of no AI raw
write or facade escape; separately authorized disposable physical qualification
on both devices; exact physical evidence docs; final review and normal
fast-forward commit/push; clean worktree; no next checkpoint begun. None of those
later actions is authorized merely by this design.

Stop for weaker full-byte policy; changed default generic 3C/3D semantics;
inability to bind eligibility to both authoritative observations; premature
pair/activation; replay/rollback/automatic cleanup after uncertain mutation;
mutable facade or stale-session continuation; secret/generated-byte exposure;
deployed-client qualification; or expansion into excluded migrations/general
ownership/service redesign. The accepted final-read-to-rename external-writer
limit is explicit, not a claimed new guarantee. No unresolved policy decision
remains in this proposal; validator integration, config guard coverage and
conditional open_ftp reachability must be proven during implementation review.

### Historical design-pass stop marker

**Stop for design review. No implementation, physical contact, branch/worktree,
commit, push, merge, tag, package or release in this pass.**


## Historical pre-correction implementation evidence — 4 October 2026

The record below preserves the initial implementation claims and results. The
subsequent read-only review found three blocking defects; the correction record
below supersedes claims of complete bridge gating, pre-submission privacy and
ordinary retained-token retry verification. Initial counts are historical.

### Authority and scope

Before editing: working directory was the existing `argonaut-network-slice2`
checkout. HEAD and local `origin/development` both were
`a081b01c4a62198b35b88199c4c8e48f9c535f90`, divergence `0 0`, parent
`13bbc8a85d02cf75b1e58efde4e20b35d575e0df`, subject
`Retire R3 compatibility surfaces`. Initial dirt was exactly CURRENT-STATE,
R3-COMPATIBILITY-RETIREMENT and this untracked design, totaling 448 additions /
9 deletions. No unrelated edits were present. No fetch or Git mutation occurred.
The same authority remains after implementation; all R4 changes are uncommitted.

### Decisions A–D as implemented

- **A:** `replace_managed(..., original_validator_factory=None)` preserves the
  generic `_Discard` path, commands, independent signatures/hashes and protected
  exchange. Opted-in sinks consume every block without retaining remote bytes.
  `original_eligibility` is absent (`None`) for generic callers. R4 records each
  slot as unverified before reading, then finalizes full-byte equality/count
  only after `read_into` returns from final SIZE. Completed mismatch is policy
  refusal with existing MKD/staging evidence; neither mismatch nor uncertainty
  authorizes cleanup. The final-observation-to-rename window remains explicit.
- **B:** `c64_ai_preparation` captures private active content/revision or creates
  a private pending setting, then validates generation/submission, queue and
  pre-bridge gates. Supported saves/setup/pair/activation share a per-path guard;
  exact content plus an in-process revision detects supported edits, including
  same-content saves. First-time finalization reuses prepared values; rollback
  retains pending configuration and historical file outcome. It does not claim
  exclusion of arbitrary external writers. The GUI no longer calls setup first.
- **C:** `core.ai` owns expiring (five-minute), single-use plans, bound identity,
  DeviceSession, matching binding/session epoch and concrete UltimateClient.
  Execution uses one `JobBinding.device` job and outer managed lifetime. Plans
  are consumed on submission; queued terminal failures release private state.
  Temporary source directory/file modes are 0700/0600; the closed source remains
  alive through primitives. Remote evidence is normalized before local cleanup.
  No fallback, new session, facade authority, nested scheduler wait or replay.
- **D:** `ClientInstallResult` retains path/installed/size/hash and adds safe
  classification/action/disposition, authority/config identity, current/legacy
  predicates, accepted upload/replacement evidence, cancellation and local
  cleanup categories. `permits_provisioning` checks explicit evidence, never
  `installed`. CoreJob's optional failure-result projection retains R4 evidence
  for queued/running failed and cancelled jobs; other jobs keep existing behavior.
  `ClientProvisionResult` separates bridge disposition/reason/pending identity.
  Sentinel tests cover snapshots/events/diagnostics and normalized exception
  paths. No generated bytes, tokens or local private paths are public results.

### Conditional open_ftp retirement — retained for review

AI source has no legacy `upload`, `download`, `replace_file`, raw `connect` or
facade `open_ftp` execution route; AST guards and raw-factory traps enforce this.
Static search still finds the production dynamic call in `transfers.connect`,
the facade definition, and the known bounded tests (plus the unrelated
MemoryClient double). Automatic approval review rejected removing the facade
method on that basis, citing potential upload regressions and insufficient proof
of production-dead status. The safer authorized alternative was taken: retain
`open_ftp` and its tests unchanged, retain `transfers.connect`, and do not broaden
migration to force closure. Conditional retirement proof is a remaining review
item; removal is not claimed complete. No functional A–D design deviation is
intended, and no default generic 3C/3D contract changed.

### Deterministic commands and accounting

Commands were executed from the existing repository, with loopback fixture
sockets allowed and no physical device contact:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests /usr/bin/python3 -m unittest test_c64_ai_install test_c64_ai_preparation test_c64_ai_bridge test_c64_ai_bridge_alert test_c64_ai_bridge_background test_c64_ai_bridge_check test_c64_ai_bridge_cli test_c64_ai_bridge_control test_c64_ai_health_alert test_c64_ai_launch test_core test_jobs test_scheduler test_file_service test_test_lab test_test_lab_access test_test_lab_presentation test_compatibility_retirement
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests /usr/bin/python3 -m unittest test_c64u_ftp test_ftp_reads test_ftp_streaming test_ftp_mutations test_ftp_uploads test_ftp_replacements test_ftp_replacement_corrections test_ftp_folder_steps test_replacement_source test_usb_backup test_usb_backup_preferences
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -O -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m c64u_browser.test_lab --suite offline
git diff --check
```

Results: **143 focused passed; 257 FTP/USB passed; normal and optimized each
1076 methods, 1040 passed, 36 existing display skips, zero failures/errors;
offline 17/17 passed.** No skips added. Whitespace checks include untracked files.
The normal/optimized full suites include accepted 3C/3D/R1/R2/R3 and unchanged
Flash, CLI, launch/chat/runtime and headless tests.

Accounting against R3's 1032: **44 added, zero removed, zero renamed**.
`test_c64_ai_install` adds 28 to its existing six methods. Its tokenizer fixture
is retained; the other five methods replace mock-only legacy route assertions
with real managed loopback behavior. New `test_c64_ai_preparation` adds 16.
Parameterized subcases do not inflate method counts. The earlier 162-focused
R3 count is historical, not the differently selected 143-method R4 run.

R4 coverage includes both authoritative substitution barriers, mismatched bytes
with equal digest metadata, generic equal-foreign-hash acceptance without the
hook versus refusal with it, short/overlong/missing/changing SIZE/interrupted
observations, wrong identity/endpoint/reconnect, queued/running cancellation,
lost publication/exchange replies, deferred cancellation, remote/local cleanup
failure, private modes, zero leases, single-use/expiry and privacy projections.
Bridge tests cover all permitting paths, nonpermitting first setup, pending
retention, generation/queue/post-publication/commit edits, serialization,
rollback and a fresh exact-current verification instead of upload replay.

Initial iterations: the first 84-method bridge/job/replacement run encountered
74 socket PermissionErrors in the restricted sandbox (including subcases).
Rerunning with authorized local sockets passed all 84; no application correction
was involved. The first 27 R4 loopback methods passed. Expanded 154-method
selection had one obsolete mock signature (new gate keyword arguments), fixed
by adapting the test double; 161-method rerun passed. Strengthening pre-queue
cancellation exposed one scheduler-admission error in the 142-method selection;
R4 now sets the pending cancellation event before submission while preserving
PENDING admission. Final review added committed-revision checks before subsequent activation/health
steps and preservation of an intervening configuration edit. One additional
regression method raised the final focused selection to 143 and each full suite
to 1076. The final focused and both full runs pass. No test failure
was suppressed or converted into a skip.

### Review boundary

**Stop for pre-physical implementation review.** Physical qualification on both
devices remains pending and was not performed. No deployed file, physical C64U,
service or active bridge configuration was touched by this pass. No commit,
push, merge, tag, package, release, branch/worktree or next-checkpoint work.


### Complete changed/new file list and diff stat

Relative to the verified R3 HEAD, including the initial approved documentation:

- `c64u_browser/c64_ai_bridge_config.py` — guard/revision and private config repr.
- `c64u_browser/c64_ai_bridge_control.py` — prepared finalization and commit gates.
- `c64u_browser/c64_ai_install.py` — safe result models and provisioning gate.
- `c64u_browser/c64_ai_operation.py` (new) — captured managed Core operation.
- `c64u_browser/c64_ai_preparation.py` (new) — private pending configuration.
- `c64u_browser/core.py` — capability construction and shutdown cleanup.
- `c64u_browser/jobs.py` — optional terminal failure-result projection.
- `c64u_browser/managed_replacement.py` — default-preserving original validator.
- `c64u_browser/test_lab_tab.py` — Core-only setup/install entry and reporting.
- `tests/test_c64_ai_install.py` — loopback policy/race/evidence/privacy contracts.
- `tests/test_c64_ai_preparation.py` (new) — preparation/bridge/revision contracts.
- `docs/R4-MANAGED-C64-AI-INSTALL.md` (new) — preserved design and this evidence.
- `docs/CURRENT-STATE.md` — current R4 status.
- `docs/C64U-FTP.md` — managed AI route and remaining raw ownership.
- `docs/C64-AI-BRIDGE.md` — full-byte eligibility and file-before-bridge gate.
- `docs/TEST-LAB.md` — setup/install messaging and failure boundary.
- `docs/R3-COMPATIBILITY-RETIREMENT.md` — original concise completion correction.

Final diff stat, including untracked files: **17 files, 2044 insertions, 212 deletions**.

## Bounded pre-physical correction record — 4 October 2026

### Authority and historical review

Starting RU supplied by the user: **70% remaining**. Before and after this pass,
`pwd` is `/home/bruce/Documents/ChatGPT/Local Projects/argonaut-network-slice2`;
HEAD and local `origin/development` remain
`a081b01c4a62198b35b88199c4c8e48f9c535f90`, parent
`13bbc8a85d02cf75b1e58efde4e20b35d575e0df`, divergence `0 0`, latest subject
`Retire R3 compatibility surfaces`. No fetch or Git state mutation was performed.
The initial worktree exactly matched the reviewed 17-file list above: tracked
839 insertions / 212 deletions plus 1,205 lines in four untracked files, totaling
**2,044 insertions / 212 deletions**. No unrelated dirt was found. A read-only
snapshot outside the repository was used to distinguish this correction delta.

The preceding read-only review verdict was **CORRECT BEFORE PHYSICAL**:

- **P1:** A token edit during existing-config status observation still permitted
  restart; cancellation during health daemon-reload still permitted enable-now.
  Activation's restart/reload/restart sequence also lacked internal gates.
- **P2:** Path-bearing revision/validation exceptions escaped the public
  pre-submission boundary and could reach GUI exception presentation.
- **P2:** Retained pending config was ignored on ordinary re-entry; a newly
  generated token made the installed client foreign. The fixed-token test masked
  this defect.
- Test-strength findings: the old late-cancellation fixture paused after server
  mutation but before its reply; direct session-field mutation was described as
  reconnect; some runner assertions could be swallowed by bridge error handling.

Review A passed: authoritative full-byte validators and generic default behavior
were sound. Core file ownership and typed file evidence had no blocking defect.
Those findings and the original design/history remain authoritative and preserved.

### Corrections implemented

**P1 — consequential boundaries.** Optional R4 callbacks propagate prepared
revision/content, pending integrity and device/session/cancellation context into
activation and health helpers. Every new enable, restart, retry restart and
consequential daemon-reload is gated. Active-config writes also recheck after
temporary-file flush/chmod immediately before `os.replace`, including pairing.
Existing-config finalization carries the expected committed revision through
status observation, checks it before activation, and uses the same check inside
activation. Defaults for unrelated callers remain no-op checks; existing
standalone command-order tests pass. Existing authorized bridge rollback stays
intact, including stop/disable or pairing restoration/restart where already
specified. Rollback is not a new forward action and never invokes remote file
work. `ClientProvisionResult.bridge_commands` records only command/category and
completed/failed/unknown outcome, including rollback; later cancellation cannot
relabel an already completed command. Final-check-to-one-system-call windows
against arbitrary external writers remain; no atomicity claim is added.

**P2 — public privacy.** Context capture, private preparation, generation,
post-generation validation and submission are covered by one public sanitization
boundary. New exceptions report only a fixed phase and safe review guidance;
they are raised outside the original handler with `from None`, leaving neither
original `__cause__` nor `__context__`. Handles are discarded on validation or
submission setup failure; Core also discards a registered plan if timer setup
fails. Pending config is retained for review. Accepted remote inspection paths,
file results and primitive evidence remain intact.

**P2 — useful retained re-entry.** Before generating any new token, preparation
examines the private pending directory. Exactly one candidate is eligible only
with owned non-symlink 0700 directories and 0600 single-link regular files,
expected opaque preparation name, exact schema/fields and private provenance.
The private provenance records preparation ID, intended active path, physical
device/address and config identity (device/inode/size/mtime plus full content
hash). It is never a public config ID or diagnostic payload. Supported endpoint
and model validation is reused; retained address, selected model, standard port
and current local route host must match. Config/provenance edits, missing older
provenance, corrupt/insecure candidates, multiple candidates, wrong context or
conflicting active config safely refuse before token generation, Core file
submission or service commands. No candidate is arbitrarily selected or deleted.

Eligible re-entry preserves the token/config identity but captures a new
single-use Core handle and current session; a same-device reconnect can start
new work, while its old handle cannot continue. Execution performs fresh managed
full-byte classification. Exact-current performs no mutation; foreign content
still refuses. Verified ready commit checks active content/revision again, then
unlinks only the matching pending config, private provenance and empty candidate
directory. No historical secret copy is retained on success. Cleanup errors are
safe failures with completed file/command evidence preserved; remaining active/
pending conflicts require explicit local review. No general manager UI, token
rotation or remote cleanup/replay is introduced.

**Test strength.** A client-side barrier after managed addition/replacement
returns with acknowledged publication (and completed replacement cleanup)
requests actual Core-job cancellation. The job remains succeeded and preserves
installed/upgraded evidence while provisioning is held, with no second STOR.
The older mutation-before-reply fixture remains under an accurate name. Actual
Core reconnect coverage remains; direct running session-field mutation is named
accurately. Exact command lists cover existing and first-time activation,
health boundaries and pre-existing rollback. Public active/pending PermissionError
injections occur after generation through `install_and_pair_c64_ai`; token,
program, password and private-path sentinels are absent from public exceptions,
chains, snapshots/events and diagnostic records. Successful file size/hash and
remote inspection evidence are retained.

### Deterministic verification and accounting

Executed from the existing repository with `PYTHONDONTWRITEBYTECODE=1`; all
transport fixtures use local loopback. No physical devices or real systemd
service runners were invoked. Exact test commands (output redirection omitted):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests /usr/bin/python3 -m unittest test_c64_ai_preparation test_c64_ai_install test_c64_ai_bridge_control test_core
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests /usr/bin/python3 -m unittest test_c64_ai_install test_c64_ai_preparation test_c64_ai_bridge test_c64_ai_bridge_alert test_c64_ai_bridge_background test_c64_ai_bridge_check test_c64_ai_bridge_cli test_c64_ai_bridge_control test_c64_ai_health_alert test_c64_ai_launch test_core test_jobs test_scheduler test_file_service test_test_lab test_test_lab_access test_test_lab_presentation test_compatibility_retirement
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests /usr/bin/python3 -m unittest test_c64u_ftp test_ftp_reads test_ftp_streaming test_ftp_mutations test_ftp_uploads test_ftp_replacements test_ftp_replacement_corrections test_ftp_folder_steps test_replacement_source test_usb_backup test_usb_backup_preferences
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -O -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m c64u_browser.test_lab --suite offline
```

| Selection | Final result |
|---|---|
| Corrected preparation/install/bridge-control/Core | 94 passed |
| Full prior R4 focused selection plus corrections | 160 passed |
| FTP/USB regressions | 257 passed |
| Normal complete suite | 1093 methods: 1057 passed, 36 existing skips |
| Optimized complete suite | 1093 methods: 1057 passed, 36 existing skips |
| Offline Test Lab | 17/17 passed |

**Accounting:** this pass adds 17 preparation methods (16 → 33); install remains
34 methods. Two install methods are renamed, not retired:
`test_running_cancellation_and_reconnect` →
`test_running_cancellation_and_session_field_invalidation`, and
`test_late_cancellation_keeps_file_success` →
`test_cancellation_after_mutation_before_reply_keeps_file_success`.
Thus 1076 + 17 = 1093, 143 + 17 = 160; FTP/USB remains 257. Total additions
against R3 are 44 + 17 = 61. No methods retired and no skips added.

Iterations, including failures:

1. Initial restricted 90-method correction run: 94 socket PermissionErrors
   including subcases. No tests were weakened; authorized loopback rerun followed.
2. First loopback 90-method run: two failures and one error in test fixtures.
   A broad test edit removed one preparation assignment (NameError); a context
   injector fired during file work instead of the pairing boundary; an overstrict
   no-call assertion rejected the pre-existing authorized rollback stop. Restored
   setup, moved injection to the intended boundary, and asserted exact rollback
   calls. The corrected 90-method run passed.
3. Expanded 93-method correction run passed; 159 focused, 257 FTP/USB, both full
   suites at 1092 (1056 passed + 36 existing skips), and 17 offline checks passed.
4. Final source review added a check immediately before active-config publication
   after private temp-file flush and one test method covering first/existing config
   cancellation/revision races. The 94-method focused run passed, followed by the
   final selections/counts above. No production test failure was hidden or skipped.
5. The first audit wrapper interpreted `git diff --no-index --check` exit 1
   (differences present, with empty diagnostics) as failure. The wrapper was
   corrected to accept 0/1 only when both output streams are empty; actual
   whitespace diagnostics still fail. No repository whitespace fix was needed.

Static AI ownership checks and runtime sentinel scans pass. AI still calls only
the captured managed file route; no legacy upload/replacement, raw `operate`,
`open_ftp`, facade transport or mutable authority was introduced. Full-byte
validator production code and generic 3C/3D code match the reviewed snapshot.
`CoreDeviceOperations.open_ftp` and deferred callers remain untouched by this
pass. `git diff --check` plus `git diff --no-index --check /dev/null <file>` for
each untracked file pass. Test-name accounting was checked by AST comparison to
the initial reviewed files.

### Correction files and review stop

This correction edits only these 12 already-reviewed R4 files:

- `c64u_browser/c64_ai_bridge_config.py`
- `c64u_browser/c64_ai_bridge_control.py`
- `c64u_browser/c64_ai_install.py`
- `c64u_browser/c64_ai_operation.py` (already untracked)
- `c64u_browser/c64_ai_preparation.py` (already untracked)
- `tests/test_c64_ai_install.py`
- `tests/test_c64_ai_preparation.py` (already untracked)
- `docs/R4-MANAGED-C64-AI-INSTALL.md` (already untracked)
- `docs/C64-AI-BRIDGE.md`
- `docs/CURRENT-STATE.md`
- `docs/TEST-LAB.md`
- `docs/C64U-FTP.md`

The complete R4 status remains the same 17 files listed above; this pass does not
edit `core.py`, `jobs.py`, `managed_replacement.py`, `test_lab_tab.py` or
`docs/R3-COMPATIBILITY-RETIREMENT.md`. The historical initial combined stat above
is preserved; the final aggregate is recorded below after reconciliation.

No known design deviation or unresolved correction defect remains. Strict
refusal of older pending files lacking provenance is intentional safe review
policy, not token regeneration or automatic migration. Config/file external-writer
windows and the need for fresh context remain explicit limitations.

**STOP FOR PRE-PHYSICAL CORRECTION REVIEW.** Physical qualification remains
pending and was not performed. No commit, push, merge, tag, package, release,
branch/worktree creation, physical service/device contact or next-checkpoint work
was performed.


### Final reconciled worktree

Final combined R4 delta against R3, including all four untracked files:
**2922 insertions / 218 deletions across the same 17 files**.
This correction versus the reviewed starting snapshot:
**947 insertions / 75 deletions across 12 files**.

Final complete `git status --short --untracked-files=all`:

```text
 M c64u_browser/c64_ai_bridge_config.py
 M c64u_browser/c64_ai_bridge_control.py
 M c64u_browser/c64_ai_install.py
 M c64u_browser/core.py
 M c64u_browser/jobs.py
 M c64u_browser/managed_replacement.py
 M c64u_browser/test_lab_tab.py
 M docs/C64-AI-BRIDGE.md
 M docs/C64U-FTP.md
 M docs/CURRENT-STATE.md
 M docs/R3-COMPATIBILITY-RETIREMENT.md
 M docs/TEST-LAB.md
 M tests/test_c64_ai_install.py
?? c64u_browser/c64_ai_operation.py
?? c64u_browser/c64_ai_preparation.py
?? docs/R4-MANAGED-C64-AI-INSTALL.md
?? tests/test_c64_ai_preparation.py
```

Final audit command: `PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /tmp/r4-audit.py`.
It verifies authority/status, compares every initial R4 file, checks the five
untouched files byte-for-byte, runs AST ownership/exception-chain and production
sentinel scans, and checks tracked/untracked whitespace. Runtime secret scans
are included in the focused and full test suites above. All final audit checks
passed. No physical qualification or Git publication was performed.


## Controlled physical qualification — PASS, 4 October 2026

**R4 physically qualified on both devices; uncommitted; STOP FOR FINAL R4 REVIEW.**
The final correction verification verdict was **APPROVE PHYSICAL QUALIFICATION**:
all three blockers closed, no blocking defect. The user separately authorized this
bounded procedure. Starting user-supplied RU baseline: **65% remaining**.
Beige completed every scenario, reviewed cleanup and independent absence before
Founder was connected using its own saved bound Ethernet profile.

### Authority and execution boundary

Before device contact, `pwd`, `git status --short --untracked-files=all`, HEAD,
local `origin/development`, parent, divergence, latest subject and
`git diff --check` were checked. Repository:
`/home/bruce/Documents/ChatGPT/Local Projects/argonaut-network-slice2`.
HEAD and local `origin/development` both:
`a081b01c4a62198b35b88199c4c8e48f9c535f90`; parent:
`13bbc8a85d02cf75b1e58efde4e20b35d575e0df`; divergence `0 0`; latest subject
`Retire R3 compatibility surfaces`. Exactly the reviewed 17 files were present:
13 tracked modifications plus four untracked files, **+2922/-218** combined.
Tracked and untracked whitespace checks passed. No unrelated dirt was present.
The approved sequence and complete final correction verification record were read.

An external qualification driver invoked actual `ArgonautCore.connect` with
`require_bound=True`, `persist=False`, then `core.ai.prepare/execute` for each
R4 scenario. Each execution received a fresh single-use preparation handle.
No GUI install-and-pair orchestration or bridge preparation/finalization ran.
Synthetic validated configurations existed only in process memory, with distinct
random tokens and opaque config IDs per device and a documentation-only endpoint.
No active or pending production bridge configuration was read or written.
Private local ai.1 sources used mode 0700 directories and 0600 files and were
removed after accepted managed publication. No secret, program bytes or private
source/configuration paths are included in this record.

Root/directory creation used `core.files.create_folder`. Seed additions used
accepted `upload_managed` (3C), in a Core device-lane job with a captured managed
adapter. Independent listings and full-file SIZE/RETR/SIZE reads used fresh Core
jobs and managed operation lifetimes. Readback sinks compared every byte and
length privately against the expected generation, in addition to SHA-256.
Deletion used `core.files.prepare_delete/execute_delete`, after explicit inspection
and review of the exact five-item set. No raw/legacy cleanup was used.

The exact intended storage root was discovered and freshly listed before mutation;
no alternate storage was selected. The listing API exposes no authoritative
read-only writability flag, so pre-mutation evidence establishes availability and
appropriateness, while acknowledged creation of only the unique disposable root
establishes writability. Each root was absent beforehand and empty immediately
after acknowledged creation. Initial and terminal active lease counts were zero.

### Beige — independently passed

- Saved profile ID: `979c7e4e-2c58-4dff-8536-f145c6a9155f`; reported physical ID: `25EA78`.
- Current host: `192.168.68.70`; firmware: `1.1.0s2`; API: `0.1`.
- Core session / binding epoch: `09f8e5d715f84798a768432284a7fd3c` (unchanged through absence verification).
- Approved storage: `/USB2`.
- Disposable root: `/USB2/argonaut-r4-accept-b108630f31ba490598cf67c358f9423e` (now independently verified absent).
- Opaque synthetic config ID: `0a9822103f3c492b9e0f34410b2b14e8`.

| Synthetic content | Expected and independently observed bytes | SHA-256 |
|---|---:|---|
| CURRENT | 1512 | `122d5ee0ce0b0cc2202fd74a86d3654a9faa7bbdd23d22fd8f9428d1f900e773` |
| same-config ai.1 | 1506 | `9c6f0884c29f9396df3addf056a12ab532569d32353d7ecfda75b2c50c7e897b` |
| foreign fixture | 30 | `e09ce9b215f067dbd9d3d73c5339e94c8771b0194aa10a0f81ab2b80fd32e1f3` |

| Scenario / target | Classification | Action / final disposition | Preparation ID |
|---|---|---|---|
| missing / `current.prg` | missing | installed / installed | `6669b29fdcf64ac691d57d320a103134` |
| current / `current.prg` | current | no-op / verified-current | `0c527086dc354d599c5e344fd1bf52b6` |
| upgrade / `upgrade.prg` | recognized-legacy | upgraded / upgraded | `b42a1a6211f147daa279f6a4614a408b` |
| foreign / `foreign.prg` | foreign | refused / refused-unchanged | `0bf862c76c0847148d10117bdc88b930` |
| directory / `directory-target.prg` | non-file | refused / refused-unchanged | `e397d316e9414c228f0dfe6ea5f12f6a` |

Missing installation completed 3C with exact STOR length, terminal reply 226,
passed readback/SIZE/destination recheck and RNFR 350 / RNTO 250 acknowledged
publication. Local cleanup completed. A new managed operation independently
verified all CURRENT bytes/count/hash. Fresh root inspection found only
`current.prg`, with no upload staging residue.

The fresh exact-current operation produced `full-byte-match`, `no-op` and
`verified-current`. Its command diagnostics recorded RETR=1, SIZE=2 and
**STOR=MKD=RNFR=RNTO=DELE=RMD=0**. A new independent full-file read confirmed
unchanged CURRENT bytes/count/hash; no staging artifact was created.

The separate ai.1 seed at `upgrade.prg` completed accepted 3C publication and
independent full-byte/count/hash verification. Actual R4 classified
`recognized-legacy`. Both authoritative `original-before` and `original-after`
observations passed `full-byte-match` after their complete SIZE/RETR/SIZE sequence,
with the ai.1 count/hash above and the same captured device/session/preparation.
3D protection passed. Acknowledged steps were mkdir, first rename, publication
rename, backup delete and directory remove (MKD 257; rename 350/250; DELE/RMD 250).
Final replacement publication and remote cleanup both completed; uncertainty,
error and candidate lists were empty; local cleanup completed. A fresh independent
read verified CURRENT bytes/count/hash and a fresh listing found no backup or
replacement staging residue.

The foreign fixture was separately published through 3C and independently verified
before R4. R4 refused it before any mutation; all six mutation-command counts
were zero, upload/replacement evidence absent, and no R4 artifact existed.
Independent readback confirmed unchanged foreign bytes/count/hash.
The directory target was created through managed folder creation and verified
empty. R4 classified `non-file`, refused without mutation, and independent
listing verified that it remained an empty directory. All terminal operations
preserved the captured session/epoch and released every active lease.

| Actual R4 operation only | STOR | MKD | RNFR | RNTO | DELE | RMD | RETR | SIZE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| missing | 1 | 0 | 1 | 1 | 0 | 0 | 1 | 1 |
| current | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 2 |
| upgrade | 1 | 1 | 3 | 3 | 1 | 1 | 4 | 7 |
| foreign | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 2 |
| directory | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Reviewed deletion plan: `656b395ea9bc42c78222eeaedd64f6d0`. Exact target: `/USB2/argonaut-r4-accept-b108630f31ba490598cf67c358f9423e`.
Final recursive inspection and fresh readbacks confirmed exactly this complete
reviewed item set, printed and reviewed before execution:

| Exact reviewed and removed path | Type | Final pre-delete verification |
|---|---|---|
| `/USB2/argonaut-r4-accept-b108630f31ba490598cf67c358f9423e/current.prg` | file | CURRENT bytes/count/hash matched |
| `/USB2/argonaut-r4-accept-b108630f31ba490598cf67c358f9423e/directory-target.prg` | dir | empty |
| `/USB2/argonaut-r4-accept-b108630f31ba490598cf67c358f9423e/foreign.prg` | file | foreign bytes/count/hash unchanged |
| `/USB2/argonaut-r4-accept-b108630f31ba490598cf67c358f9423e/upgrade.prg` | file | CURRENT bytes/count/hash matched |
| `/USB2/argonaut-r4-accept-b108630f31ba490598cf67c358f9423e` | dir | only these four children |

Reviewed deletion removed **5/5**, exactly the set above, with no failure,
stopped target, uncertain mutation or unattempted item. A fresh independent
managed listing of the parent storage root verified the unique acceptance root
absent. Session/epoch remained stable; active leases were zero. Core was then
closed without any device retry, rollback or extra remote cleanup.

### Founder — independently passed

- Saved profile ID: `43f75f6d-87ed-4e2c-abe8-448679569a7d`; reported physical ID: `25BE71`.
- Current host: `192.168.68.69`; firmware: `1.1.0`; API: `0.1`.
- Core session / binding epoch: `9be04326616447d0b7d0029cf6e790da` (unchanged through absence verification).
- Approved storage: `/SD`.
- Disposable root: `/SD/argonaut-r4-accept-cc8326785c944df48c7d9bf6959bba0a` (now independently verified absent).
- Opaque synthetic config ID: `c1a9797213a24c97a8f45ea5992ca215`.

| Synthetic content | Expected and independently observed bytes | SHA-256 |
|---|---:|---|
| CURRENT | 1512 | `9898334f40a0b243bb570a75ffc54c857c2c6f46a4843bfc48c86061cc4a6dfd` |
| same-config ai.1 | 1506 | `4ef3b2c90b8073342e749ce7768586fffb08ca9585a25282477a2732487d0b83` |
| foreign fixture | 30 | `e09ce9b215f067dbd9d3d73c5339e94c8771b0194aa10a0f81ab2b80fd32e1f3` |

| Scenario / target | Classification | Action / final disposition | Preparation ID |
|---|---|---|---|
| missing / `current.prg` | missing | installed / installed | `470fb0235f604ae6bcc925c07ab227c9` |
| current / `current.prg` | current | no-op / verified-current | `7287916694ad44028dbade35ba237ebe` |
| upgrade / `upgrade.prg` | recognized-legacy | upgraded / upgraded | `47f14316ebe146a9bd3f3e8c2a6ff279` |
| foreign / `foreign.prg` | foreign | refused / refused-unchanged | `d343452cdf7048719c810aae6b8963aa` |
| directory / `directory-target.prg` | non-file | refused / refused-unchanged | `649ac4a7f02a49ed8fb64c70031945ae` |

Missing installation completed 3C with exact STOR length, terminal reply 226,
passed readback/SIZE/destination recheck and RNFR 350 / RNTO 250 acknowledged
publication. Local cleanup completed. A new managed operation independently
verified all CURRENT bytes/count/hash. Fresh root inspection found only
`current.prg`, with no upload staging residue.

The fresh exact-current operation produced `full-byte-match`, `no-op` and
`verified-current`. Its command diagnostics recorded RETR=1, SIZE=2 and
**STOR=MKD=RNFR=RNTO=DELE=RMD=0**. A new independent full-file read confirmed
unchanged CURRENT bytes/count/hash; no staging artifact was created.

The separate ai.1 seed at `upgrade.prg` completed accepted 3C publication and
independent full-byte/count/hash verification. Actual R4 classified
`recognized-legacy`. Both authoritative `original-before` and `original-after`
observations passed `full-byte-match` after their complete SIZE/RETR/SIZE sequence,
with the ai.1 count/hash above and the same captured device/session/preparation.
3D protection passed. Acknowledged steps were mkdir, first rename, publication
rename, backup delete and directory remove (MKD 257; rename 350/250; DELE/RMD 250).
Final replacement publication and remote cleanup both completed; uncertainty,
error and candidate lists were empty; local cleanup completed. A fresh independent
read verified CURRENT bytes/count/hash and a fresh listing found no backup or
replacement staging residue.

The foreign fixture was separately published through 3C and independently verified
before R4. R4 refused it before any mutation; all six mutation-command counts
were zero, upload/replacement evidence absent, and no R4 artifact existed.
Independent readback confirmed unchanged foreign bytes/count/hash.
The directory target was created through managed folder creation and verified
empty. R4 classified `non-file`, refused without mutation, and independent
listing verified that it remained an empty directory. All terminal operations
preserved the captured session/epoch and released every active lease.

| Actual R4 operation only | STOR | MKD | RNFR | RNTO | DELE | RMD | RETR | SIZE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| missing | 1 | 0 | 1 | 1 | 0 | 0 | 1 | 1 |
| current | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 2 |
| upgrade | 1 | 1 | 3 | 3 | 1 | 1 | 4 | 7 |
| foreign | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 2 |
| directory | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Reviewed deletion plan: `d4bef4d890b04b9c880229d41955ed9c`. Exact target: `/SD/argonaut-r4-accept-cc8326785c944df48c7d9bf6959bba0a`.
Final recursive inspection and fresh readbacks confirmed exactly this complete
reviewed item set, printed and reviewed before execution:

| Exact reviewed and removed path | Type | Final pre-delete verification |
|---|---|---|
| `/SD/argonaut-r4-accept-cc8326785c944df48c7d9bf6959bba0a/current.prg` | file | CURRENT bytes/count/hash matched |
| `/SD/argonaut-r4-accept-cc8326785c944df48c7d9bf6959bba0a/directory-target.prg` | dir | empty |
| `/SD/argonaut-r4-accept-cc8326785c944df48c7d9bf6959bba0a/foreign.prg` | file | foreign bytes/count/hash unchanged |
| `/SD/argonaut-r4-accept-cc8326785c944df48c7d9bf6959bba0a/upgrade.prg` | file | CURRENT bytes/count/hash matched |
| `/SD/argonaut-r4-accept-cc8326785c944df48c7d9bf6959bba0a` | dir | only these four children |

Reviewed deletion removed **5/5**, exactly the set above, with no failure,
stopped target, uncertain mutation or unattempted item. A fresh independent
managed listing of the parent storage root verified the unique acceptance root
absent. Session/epoch remained stable; active leases were zero. Core was then
closed without any device retry, rollback or extra remote cleanup.

### Evidence strength, limitations and final stop

Command counts came from the existing managed FTP diagnostic callback at `_send`,
which reports command verbs without arguments; the observer preserved the original
diagnostic callback and did not alter protocol behavior. Counting was scoped to
one actual R4 preparation/execution, excluding seeding, independent observations
and deletion. Each R4 operation used one USER and one FEAT, consistent with one
outer operation lease; initial and every terminal lease count were zero. Counts
are client send-boundary diagnostics, not an independent packet capture or
server-wide audit. No mutation command was attempted in either exact-current
operation or either refusal scenario on either device.

Normal acknowledged device behavior is physically established. Fault injection,
uncertain replies, cancellations, concurrent external writers and cleanup failures
were not physically induced. The documented final-observation-to-rename external
writer window remains. GUI, pairing, bridge services/health and C64 launch were
not exercised. The deployed `/USB2/argonaut-ai.prg` was never a read/write target;
only ordinary storage parent listings could include its directory entry.
No production bridge token/configuration was used or modified.

No implementation or test file changed in this pass. Documentation changes are
limited to this physical record and current R4 status in CURRENT-STATE,
C64-AI-BRIDGE, C64U-FTP and TEST-LAB. Historical design/implementation/correction
records remain historical. Deterministic suites were not rerun for this
physical/documentation-only pass; their accepted results remain recorded above.
Final tracked and untracked whitespace checks passed after the documentation
updates. HEAD, local origin/development, parent, divergence and subject still
match the pre-contact authority above; the same 17 files remain, with no
unrelated dirt. Implementation/test content was verified unchanged by the
documentation update. The final aggregate delta is reported in the task result.

**STOP FOR FINAL R4 REVIEW.** No commit, push, merge, tag, branch/worktree,
package, release or next checkpoint was performed.
