# Issue #25 — LED mode-write containment review gate

## Issue #49 temporary LED Apply containment — offline candidate, 26 October 2026

This isolated, uncommitted candidate is based on published `development`
`d0925f2130daa213bf118f24dc064e9c35736ae9`. Under the maintainer's explicit
implementation authorization, shared Core admission now refuses every explicit
Apply write targeting `Keyboard Lighting` or `LED Strip Settings`, including
same-value and unknown fields, case variants and whole mixed batches, before
remote configuration/identity reads, history mutation or POST. All LED values
remain readable and visible; their editors are read-only. The narrower published
mode-write restriction and existing LED implementation/dependency rules are retained.
Unrelated writes retain metadata, dependency, staleness and session admission.

This candidate supersedes earlier parameter-write availability statements **only
for this isolated implementation**. It is not integrated or published. See
[the scope, evidence and acceptance gate](ISSUE49-LED-APPLY-CONTAINMENT.md).
The primary checkout and prior candidates are preserved. No physical C64U
operations, staging, committing, pushing, issue closure or Project updates occur.

The original intermittent lockup and its root cause remain unresolved. Firmware
runtime Auto SID transitions, other clients, device menus and firmware reset/load
are outside this Apply boundary. #49 remains open; #48 remains C1 tooling only.
RM-026/028/029 and all hardware, integration and publication gates remain in force.


## Qualified closure and accepted safety handoff — 26 October 2026

The [authorized #25 closure](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25#issuecomment-6402539547)
and [accepted #49 handoff](https://github.com/Mrbruceybruce/argonaut-c64u/issues/49#issuecomment-6402541994)
record **#25 Closed / Done** with **QUALIFIED ACCEPT** of the bounded investigation
and explicit LED mode-write containment. **#49 Open / P0 — Critical / In Progress**
now owns the defining safety investigation: the original intermittent LED lockup,
unknown triggering payload/prior state/request sequence/root cause, and indirect
or firmware-driven transitions including Auto SID. The lockup is unexplained and
unproven resolved; #49's acceptance criteria remain outstanding. **Bruce / Argonaut
maintainer retains accepted residual-risk ownership** and investigation/qualification
coordination, without a GitHub assignee change.

Containment refuses every explicit `LedStrip Mode` write in both LED categories,
including same-value writes and whole mixed batches, before configuration reads,
history mutation or POST. Parameter-only edits retain existing dependency,
firmware, metadata, staleness and session safeguards. Indirect/Auto SID transitions
are outside this guarantee; closure establishes neither general write safety nor
completed physical qualification. No dependency rule or firmware qualification changes.

[#48](https://github.com/Mrbruceybruce/argonaut-c64u/issues/48) remains open for C1
executor correctness, premature termination, truthful outcomes, scheduled readback/
observation accounting, offline regressions, independent review and durable evidence
retention only; it does not own device-lockup safety. C1 retains bounded intensity
**6→16** functional success, but its original 14-request protocol did not pass:
requests 9–14 and both scheduled readback/observation rounds remain incomplete.
The 33-event journal, consumed authorization, `protocol_complete=false`,
`physical_acceptance=false`, `evidence_complete=false` and
`write_outcome="write outcome uncertain"` remain unchanged. Supplemental readback
cannot complete that protocol; no original final manifest exists. Do not manufacture
one or resume the consumed attempt.

RM-027 retains its G2 / LED safety identity under RM-007, with #25 as the qualified
closure history and #49 as the accepted successor safety tracker. Coordinate with
#24 / RM-026; RM-028 redesign and RM-029 enhancements retain their capability and
applicable safety gates. Closing #25 does not release those dependencies.
Physical-header mapping, other hardware variants, firmware `1.1.0s2`, prolonged
stability, device-side atomicity and broader UI/package/cross-platform/release
qualification remain unproven.

### Stage 2 closeout reconciliation — 26 October 2026 (America/Chicago)

The independently reviewed Stage 2 documentation reconciliation is committed and
published to GitHub `development` at
`c300bf4292b5bd3e4e7037650d89b3b811d29389` (parent
`f955e96ace7db4f0caa2026422a2f4dec0418e4b`). Primary and live GitHub HEADs were
verified equal before this publication-status correction, with the intended GitHub
fetch/push remotes, clean tracked files/index and seven preserved untracked artifacts.
GitHub dependencies and Project tracking are synchronized as recorded below.
Containment remains published at `40da3846e88c6efe5395928394a6850c17e92f1c`.
Historical integration results remain 120/120 normal, 120/120 optimized and
35/35 GTK, with independent engineering/integration review PASS; no tests were
rerun for this documentation-only reconciliation.

GitHub dependency/reference reconciliation is complete and was verified read-only:
[#26](https://github.com/Mrbruceybruce/argonaut-c64u/issues/26) references #49 for
applicable RM-027 safety findings; its native blockers are exactly **#24 Open,
#25 Closed and #49 Open**, with the reciprocal **#49 blocks #26** link present.
#49's accepted-handoff notice supersedes its preserved creation-time description;
#48's provenance identifies #49 as the safety successor. In
[Argonaut Development](https://github.com/users/Mrbruceybruce/projects/1), #48 is
registered **Backlog / P1 — High / Test Lab / AI**. This completes tracking only,
not #48 tooling work, #49 safety acceptance or RM-026/028/029 dependency gates.

**Stage 1: Gate B journal not recovered.** Its documented original path is
`/tmp/argonaut-gate-b-20261025-schema-local-01.jsonl`; expected SHA-256:
`6d336c460366b78276d9d95c301c8648df557f7518f18e22d4e064193c6260b1`.
The completed Stage 1 search reported no exact-hash copy or plausible renamed
journal. It excluded Git internals, dependency/cache directories, content over
10 MB and inaccessible system-private temporary directories; this is not proof
that no copy exists elsewhere. Stage 2 confirmed the documented path is absent;
it did not repeat the recovery search or recreate evidence.

[Historical Gate B acceptance](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25#issuecomment-6393217684)
remains documented: five sequential validated GETs, all HTTP 200 with empty API
errors, device `25BE71`, firmware `1.1.0`, final `complete=true`, `stop=null`.
That record describes cumulative snapshots, not additional requests. Without the
original journal, its bytes, hash, row structure and captured responses cannot be
independently reverified. The `c64u_browser/led_capture_baseline.json` fixtures in
the preserved `issue25-get-capture` and `issue25-get-test` checkouts explicitly
identify themselves as transcriptions of that comment, not recovered originals.
**Historical bounded acceptance retained; original journal unavailable for
reinspection.** Earlier references to a retained journal describe historical
availability, not current possession or fresh verification.

This checkpoint supersedes older statements below that #25 is open, closure awaits
a decision, ownership is only proposed, C1 follow-up tracking is missing, or GitHub
reconciliation is pending. Earlier publication-pending and candidate statements
retain their dated historical scope. #25's qualified closure, #49's unresolved
lockup and indirect/Auto SID safety scope, #48's tooling-only boundary, incomplete
C1 physical acceptance and all dependency rules remain unchanged. Stage 2's
independent read-only review and manual publication gates are complete; its former
publication-pending statements are superseded by the verified commit above.
Stage 2 publication at `c300bf4292b5bd3e4e7037650d89b3b811d29389` and the
publication-status correction at `60a8907d9ae54c7e3038128fb62466fbb2db7d24`
were both verified on GitHub `development`. At that checkpoint, GitHub dependency
and Project reconciliation was complete, with no outstanding primary `development`
publication or administrative reconciliation. The original Gate B journal remained
unavailable, #49's lockup and indirect/Auto SID safety remained unresolved, and C1
physical acceptance remained incomplete. All evidence limitations and safety,
dependency, review and manual publication gates remain unchanged.

## Recorded ownership and linked tooling follow-up — 25 October 2026

[The accepted ownership record](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25#issuecomment-6402085824)
identifies **Bruce / Argonaut maintainer** as residual-risk owner for the intermittent
lockup and indirect/firmware-driven LED transitions, including Auto SID, and their
investigation/qualification coordination. GitHub assignees are unchanged.
[Issue #48](https://github.com/Mrbruceybruce/argonaut-c64u/issues/48) is the linked C1
executor follow-up for premature termination, truthful terminal outcomes, scheduled
readback/observation accounting, deterministic offline regressions, independent
review and durable evidence retention. Tracking exists; correction and retention
work are not complete or authorized by this reconciliation.

**QUALIFIED ACCEPT** covers the bounded investigation and explicit mode-write
containment, not a demonstrated lockup fix or general write/transition safety.
The original triggering payload/root cause and lockup remain unresolved. Indirect
transitions, including Auto SID, remain outside the containment guarantee.
**#25 remains Open / P0 — Critical / In Progress** and retains this defining safety
scope; completion of #48 cannot establish its resolution or authorize its closure.
#24 capability coordination and RM-026, RM-028 and RM-029 gates remain unchanged.

C1 intensity **6→16** retains bounded functional success only. Requests 9–14 and
both scheduled readback/observation rounds remain incomplete; supplemental GET
evidence cannot replace them. Preserve the original 33-event journal and consumed
authorization claim, with `protocol_complete=false`, `physical_acceptance=false`,
`evidence_complete=false` and `write_outcome="write outcome uncertain"` unchanged.
No original final manifest exists; #48 must distinguish later archival metadata
from original evidence and must not manufacture that manifest or resume the attempt.
Hardware/header mapping, other variants, firmware 1.1.0s2, prolonged stability,
device-side atomicity and broader release qualification remain unproven.

The prior four-document reconciliation is published at
`2dc8bdc09740ca1a0a2e69ff92ec2fa44be4f4c9`; primary/live `development` equality was
verified before this edit. Historical proposed-owner, missing-follow-up and pending-
publication statements below are preserved and superseded by this checkpoint.
This new documentation-only update requires independent review and the user's
manual staging, staged-diff review, commit, push and live-verification gates.
Any closure decision requires separate explicit maintainer review and authorization.
No Git publication, GitHub change, hardware contact or C1 implementation occurs here.

## Qualified-acceptance disposition — 25 October 2026

The user approved documentation and tracking reconciliation toward **QUALIFIED
ACCEPT** of the bounded investigation and explicit LED mode-write refusal policy.
This does not close #25 or claim the intermittent device-lockup defect is fixed.
The original implementation/review record below is preserved as a historical
checkpoint; its publication-pending statements no longer describe the containment.

The nine-file implementation is published at
`40da3846e88c6efe5395928394a6850c17e92f1c` on `development`, parent
`2cd5a60549e08cf734f192e0cfc38882f583c3db`. Primary/live HEAD equality, intended
GitHub fetch/push remotes, empty index and clean tracked files were verified before
this edit. All nine files match the reviewed manifest. Seven legacy untracked
artifacts and sixteen other snapshotted checkout contents are preserved.
This four-document reconciliation remains unstaged, uncommitted and unpublished.

### Acceptance criteria disposition

| Issue #25 criterion | Bounded assessment |
| --- | --- |
| Existing diagnostics and configuration behavior reviewed | Met within retained evidence; original triggering payload/root cause remain unknown. |
| Relevant request construction and ordering documented | Met: shared Core admission; mode-write batches refused whole before configuration reads/history/POST; admitted parameter batches record history before one configuration POST. |
| Hardware-specific dependencies identified where possible | Qualified: pinned official firmware 1.1.0 rules and Founder metadata; physical header mapping and other variants unverified. |
| Reviewed refusal policy | Met for every explicit mode write, including same-value writes, previews and mixed batches; indirect transitions are outside this guarantee. |
| Deterministic regression tests | Met for identified admission/dependency failure mechanisms; tests do not reproduce the unexplained physical lockup. |
| Independent engineering review | PASS for containment and its integration; retained reports remain source-bound. |
| Separate authorization for physical reproduction | Required; this reconciliation performs no hardware contact and grants no new authorization. |
| Remaining uncertainty documented | Explicit below; residual-risk ownership and final closure require a separate maintainer decision. |

Retained primary results: **120/120 normal**, **120/120 optimized**, **35/35 GTK**
(11 GTK, 22 Core, 2 LED), zero failures/errors/skips. Engineering and integration
reviews PASS. Local evidence is retained in `issue25-mode-integration-evidence/`
under the project workspace: `normal-primary.json`, `optimized-primary.json`,
`gtk-primary/summary.json`, `manifest.json`, `integration-report.txt` and
`independent-integration-review.txt`; it is not a published attachment. Results
were inspected, not rerun for this documentation-only change.
[Hosted Test Lab run 40223973630](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/40223973630)
is completed/success at `40da384`. The real-GTK Gate A module remains separate
from hosted suite qualification; no package/cross-platform/release acceptance follows.

### Physical evidence and unresolved risks

Gate A is bounded offline UI/Core coverage. Gate B accepted five validated
read-only requests on operator-identified Founder `25BE71`, firmware 1.1.0,
API 0.1; neither establishes general write or transition safety.
[C1 disposition](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25#issuecomment-6401134651)
supports keyboard intensity **6→16** functional success: seven validated GETs,
then the position-8 POST, operator observations and a separate authorized,
authenticated keyboard-category GET. That GET did not reverify identity/strip
settings or substitute for either timed readback/observation round.

The original 14-request protocol remains incomplete: premature terminal reply
prevented requests 9–14. Preserve `protocol_complete=false`,
`physical_acceptance=false`, `evidence_complete=false` and
`write_outcome="write outcome uncertain"`. Preserve the 33-event journal, permanent
consumed claim, reviewed source manifest and reports; no original final manifest
exists. Sanitized supplemental transcript retention and archival hash inventory
remain work, not completed evidence or permission to resume the attempt.

The original intermittent lockup remains unexplained and unproven resolved.
Explicit mode-write refusal does not control indirect/firmware-driven transitions,
including Auto SID behavior. Parameter-only edits retain safeguards but do not
establish universal hardware safety. Physical-header-to-REST-category mapping,
Beige/Starlight/other hardware variants, firmware 1.1.0s2, prolonged stability,
device-side atomicity and broader UI/package/cross-platform/release qualification
remain unproven.

### Tracking and decision gates

#25 remains the defining LED safety issue, **Open / P0 — Critical / In Progress**.
The live Project fields already match this approved scope; do not move it to Done
or lower its priority. #24 remains capability coordination (P1 / Backlog); #26
remains P2 / Backlog. RM-026, RM-028 and RM-029 retain their dependencies.

The repository issue inventory and existing #25 comments identify no dedicated
C1 executor premature-termination/evidence-retention follow-up issue. Record this
as a separate proposed follow-up, linked back to #25, requiring explicit creation
approval. Its scope should preserve the original failed protocol, diagnose early
termination and define durable evidence retention without inventing a missing
manifest or renewing hardware authorization. No new issue is created here.

Unresolved lockup and indirect/Auto SID transitions remain tracked by open #25;
coordinate hardware qualification with #24. #1 concerns a separate Undo/SuperCPU
freeze observation and is not a substitute for #25 or evidence of shared cause.
Proposed residual-risk owner: **Bruce / Argonaut maintainer, subject to explicit
acceptance**. #25 has no assignee; no assignment or ownership transfer is made.
Before any later closure, explicitly accept ownership and settle durable linked
follow-up tracking without dropping the defining LED safety scope.

Next: independent review and documentation checks, then the user's manual staging,
staged-diff review, commit, push and live publication verification gates. Final
closure requires separate authorization. This step authorizes no Git publication,
hardware contact, recovery, new issue, reassignment or issue-state change.

## Scope and implementation

Approved isolated implementation based on published development
`2cd5a60549e08cf734f192e0cfc38882f583c3db`, 25 October 2026.
The new checkout is `issue25-mode-containment` beside the retained prior candidates.
It has detached HEAD and a local primary-repository origin; it is not a publication
repository. No primary integration, Git staging/commit/push, GitHub mutation or
C64U contact is authorized or performed.

The shared headless `configuration_policy.py` rejects any explicit LED mode key
before dispatch/history, independent of value, firmware or supplied metadata.
`execute` applies it after detaching intent and checking the session; `validate`
also applies it to previews. Case-folded identity matching covers both exact LED
stores. `enabled` exposes modes as read-only with a specific containment reason.
No other source module changes. Parameter-only edits retain existing admission.

This is an Argonaut restriction, not a discovered firmware constraint or proof of
lockup resolution. Direct Core/public-client Apply, selected preview/Restore/Undo
and supported native-file staging share the refusal. A mixed requested batch is
refused whole without POST or history mutation. Snapshot values that are unchanged
are omitted by preview diff generation and are not write intent; an explicit
same-value request at the Core boundary is always refused.

## Validation

- Affected suite: **120/120 normal and 120/120 optimized**, zero failures,
  errors or skips, using a verified network namespace, no capabilities,
  no-new-privileges and Python socket/DNS guards.
- Real-GTK Gate A: **35/35**, comprising 11 GTK, 22 Core and 2 existing LED
  methods, zero failures/errors/skips. Private Xvfb/D-Bus, temporary HOME/XDG,
  network namespace and socket/DNS guards were verified by the existing runner.
- Source CI inventory audit and `git diff --check` passed.
- Initial namespace setup was blocked by the sandbox; approved escalation ran
  the same isolated protocol. An initial affected-suite run had one headless
  import failure because the evidence launcher used the parent directory.
  Correcting that launch directory produced the passing final results above;
  no product change was needed for that failure.

Retained local evidence (not published artifacts) is in sibling directories
`issue25-mode-containment-evidence/` (normal-reviewed.json/log,
optimized-reviewed.json/log, affected.py), `issue25-mode-containment-gate-a-reviewed/`
(summary.json, network.json, environment.json and per-class results/logs), and
`issue25-mode-containment-audit-reviewed/` (coverage.json). The affected launcher explicitly
loads configuration dependencies, configuration, dependencies, backups, settings
safety, native files, Core, API, C64 AI launch, scheduler, recovery and CI runner
modules. The exhaustive pair loops are subcases, not 85 separate test methods.

A review refinement keeps the containment predicate free of identity-validation
exceptions during unrelated UI rendering. Authoritative request identity checks
remain in `detach`/`validate`; an unrelated-metadata regression assertion covers
the presentation behavior. The final source was revalidated in all three runs.

Independent engineering review **PASS**, with no remaining actionable defects.
The reviewer inspected final source/call paths and refreshed evidence, independently
reran all 22 Core tests successfully, and confirmed the rendering correction.
The report is retained at `../issue25-mode-containment-evidence/independent-review.txt`.
This verdict covers the isolated implementation only; it grants no integration,
publication, hardware acceptance or closure authorization.
The 85 ordered mode pairs comprise 36 keyboard and 49 strip pairs, including all
13 same-value pairs. Parameter matrix checks still cover all active/inactive
fields and the mode-independent Auto SID/SID Select fields. Other coverage includes
case variants, missing metadata, mixed field/category orders, existing and absent
history, UI bypass, stale controller/session, unknown firmware/product, malformed
metadata, public-client POST interception, Restore, actual Undo and native preview.

## Changed-file inventory

- `c64u_browser/configuration_policy.py`: shared refusal and read-only mode state.
- `tests/test_configuration_dependencies.py`: exhaustive pair refusal, mixed/bypass
  and preserved parameter/safeguard coverage.
- `tests/test_ultimate_menu_gate_a.py`: real-GTK read-only mode, refusal and parameter checks.
- `tests/run_gate_a.py`: expected Core count increases from 20 to 22.
- `tests/ci_suites.json`: matching Core inventory count.
- `docs/CONFIGURATION-DEPENDENCIES.md`: policy and historical-scope reconciliation.
- `docs/CURRENT-STATE.md`: current isolated candidate checkpoint.
- `docs/ARGONAUT-ROADMAP.md`: RM-027 candidate checkpoint and unchanged dependencies.
- `docs/ISSUE25-MODE-CONTAINMENT.md`: this review/evidence record (new).

All nine files remain unstaged/uncommitted in the new isolated checkout. The
primary and prior candidates retain their original HEADs, branches, remotes and
working-tree inventories. Primary still has exactly seven untracked artifacts;
its tracked files and index are clean, with the historical stash retained.

## Limits and next decision

No hardware contact or new physical qualification. No claim of safe mode
transitions, prolonged stability, device-side atomicity, physical-header mapping,
firmware 1.1.0s2 support, hosted CI, package or cross-platform acceptance. C1's
incomplete protocol and executor termination remain unresolved. The original
intermittent lockup remains unexplained and unproven resolved.

Issue #25 remains Open / P0 / In Progress. Review completion permits the user to
decide whether to authorize verified integration into the primary checkout.
Staging, commit, push, publication verification and issue closure remain separate
user-controlled gates. Preserve this candidate and all prior unpublished work.
