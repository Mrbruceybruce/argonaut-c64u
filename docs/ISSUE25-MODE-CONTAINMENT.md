# Issue #25 — LED mode-write containment review gate

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
