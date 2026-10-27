# Configuration dependency validation — Issue #25 / RM-007 foundation

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

Primary and live GitHub `development` were verified at
`f955e96ace7db4f0caa2026422a2f4dec0418e4b` before this edit, with the intended
GitHub fetch/push remotes, clean tracked files/index and seven preserved untracked
artifacts. This is the published qualified-closure/safety-handoff checkpoint;
the present Stage 2 documentation update remains unstaged, uncommitted and unpublished.
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
C1 physical acceptance and all dependency rules remain unchanged. This update
requires independent read-only review and the user's manual publication gates;
closeout is not fully synchronized while publication remains outstanding.
No Git writes/publication, GitHub changes, hardware contact or new physical test
are part of Stage 2. The next gate is the user's separately controlled manual
publication review; #49 remains the P0 safety investigation.

## Ownership and follow-up reconciliation — 25 October 2026

[Recorded maintainer acceptance](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25#issuecomment-6402085824)
establishes **Bruce / Argonaut maintainer** as residual-risk owner, without changing
GitHub assignees. [C1 tooling #48](https://github.com/Mrbruceybruce/argonaut-c64u/issues/48)
tracks premature termination, truthful outcomes, scheduled readback/observation
accounting and evidence retention, with offline regressions and independent review.
The original lockup and indirect/firmware-driven transitions, including Auto SID,
remain unresolved under **#25, Open / P0 — Critical / In Progress**.
**QUALIFIED ACCEPT** remains explicit mode-write containment acceptance, not a fix,
general write safety or completed physical qualification. #24 coordination and
RM-026/028/029 gates remain. No dependency rule or firmware qualification changes.

The prior reconciliation is published at
`2dc8bdc09740ca1a0a2e69ff92ec2fa44be4f4c9`. Earlier proposed-owner, missing-follow-up
and publication-pending wording below is historical and superseded by this record.
See [current ownership, C1 evidence limits and decision gates](ISSUE25-MODE-CONTAINMENT.md#recorded-ownership-and-linked-tooling-follow-up--25-october-2026).
This new documentation update awaits independent review and manual publication;
#25 closure requires separate explicit maintainer review and authorization.

## Published containment and qualified-acceptance boundary — 25 October 2026

Explicit mode-write containment is published on `development` at
`40da3846e88c6efe5395928394a6850c17e92f1c`. Local/live HEAD equality and the nine-file
reviewed manifest were verified. The candidate checkpoint below is historical.
The approved reconciliation records **QUALIFIED ACCEPT** of the bounded investigation
and refusal policy, with #25 retained **Open / P0 / In Progress**.
See [criteria disposition and residual risks](ISSUE25-MODE-CONTAINMENT.md#qualified-acceptance-disposition--25-october-2026).

Core refuses all explicit mode writes, including same-value and mixed batches,
before configuration reads, history mutation or POST. Admitted parameter-only
batches retain fresh firmware/metadata, active-field, staleness and session checks;
history is recorded before the single admitted configuration POST. Refusal does
not establish control over indirect or firmware-driven transitions, including
Auto SID behavior. The intermittent lockup is unexplained and unproven resolved.

Retained integration tests passed 120/120 normal, 120/120 optimized and 35/35 GTK,
with engineering/integration review PASS; these tests were inspected, not rerun.
[Hosted CI at 40da384](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/40223973630)
succeeded for its configured suites. Gate A/B remain bounded offline/read-only
evidence. C1's validated intensity 6→16 POST and separate authenticated GET support
bounded functional success, not completion of its original 14-request protocol.
Requests 9–14 and both timed rounds remain incomplete; original flags stay false.

Hardware/header mapping, other variants and firmware 1.1.0s2 remain unqualified;
#24 coordination and RM-026/028/029 gates remain. Bruce / Argonaut maintainer is
only the proposed residual-risk owner, subject to explicit acceptance. Executor
termination/evidence retention need approved follow-up tracking while #25 remains
the defining lockup issue. This documentation edit awaits manual publication and
a separate final closure decision; it authorizes no hardware operation.

## LED mode-write containment candidate — 25 October 2026

This isolated, uncommitted candidate is based on published development
`2cd5a60549e08cf734f192e0cfc38882f583c3db`. The approved Argonaut policy refuses
**every explicit `LedStrip Mode` write** in **Keyboard Lighting** and
**LED Strip Settings**, including same-value writes, Off, Default, and all
otherwise advertised transitions. This is an Argonaut containment restriction,
not a firmware requirement or demonstrated lockup fix. It supersedes the earlier
controller-only transition admission described by the historical checkpoints.

Core's shared policy rejects the complete requested batch before configuration
reads, POST dispatch or history mutation; case variants cannot bypass it.
The detached intent and session gate remain in force. `validate` independently
refuses the same intent for Apply review and selected Restore, Undo and native
configuration previews. A selection containing a mode write is refused whole;
no valid companion edits are silently applied. Preview differences omit unchanged
stored values, which are not requested writes; direct explicit same-value writes
are refused. The mode row remains visible and read-only with the containment reason.

Parameter-only edits remain admitted exactly under the existing fresh firmware,
metadata, active-field, review-staleness and session checks. Dormant stored values
remain untouched. DHCP and unrelated configuration retain their existing behavior.
There is no new bypass, retry, rollback, hardware operation or firmware qualification.

Offline evidence and independent review are recorded in
[the containment review record](ISSUE25-MODE-CONTAINMENT.md).
Integration, physical acceptance, publication and issue closure remain separate.
Issue #25 remains **Open / P0 / In Progress**; the original lockup and C1 executor
termination remain unresolved. Earlier evidence below retains its historical scope.

## Gate C1 functional disposition — 25 October 2026 UTC

The approved [C1 disposition](CURRENT-STATE.md#gate-c1-functional-disposition--25-october-2026-utc)
records bounded keyboard intensity **6→16** success in Fixed Color / Red, supported
by the validated POST response, operator observations and a subsequent separately
authorized authenticated keyboard-category GET (HTTP 200, empty errors, intensity
16 and otherwise expected values/metadata). The attempt baseline had LED Strip
Settings mode Off; C1 sent no strip write or mode transition.

The original attempt stopped before requests 9–14; its two scheduled readback and
observation rounds did not complete. The later GET did not reverify identity or
the strip category. **The original 14-request protocol did not pass**, and its
terminal completion/acceptance/evidence flags remain false. The complete evidence
record and pending retention needs are linked above.

This changes no dependency rule or firmware qualification. It does not establish
safe mode transitions, prolonged stability, header mapping, device-side atomicity
or lockup resolution. The executor termination remains unresolved; Issue #25
remains **Open / P0 / In Progress**, with dependent work still gated. The isolated
executor is unpublished; independent documentation review found no actionable findings, and manual
publication remains pending. Earlier Gate A/B statements describe their historical checkpoints.

## Gate A/B evidence checkpoint — 25 October 2026 UTC

Gate A infrastructure is published at `89c8eea956dc66d52124da5969fc14ede9a5a27b`.
Its **33/33 isolated offline methods** passed; all eight jobs in
[hosted run 40154324070](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/40154324070)
passed separately. The real-GTK Gate A module remains deferred from hosted suites.
See [current publication and acceptance evidence](CURRENT-STATE.md#gate-a-publication-and-gate-b-read-only-acceptance--25-october-2026-utc).

[Accepted Gate B read-only evidence](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25#issuecomment-6393217684)
records **5/5 validated GETs** on operator-identified Founder `25BE71`, product
`C64 Ultimate`, firmware `1.1.0`, API `0.1`. Both Keyboard Lighting and LED Strip
Settings expose exactly seven expected fields. Enum arrays and defaults match
the full pinned source vocabularies in order; enum objects contain exactly
`current/values/default`. Intensity objects contain exactly
`current/min/max/format/default`, bounds 0–31 and format `%d`, with defaults
6 keyboard / 25 strip. Captured modes/intensities are Fixed Color / 6 for keyboard
and Rainbow / 25 for strip. Exact distinctions remain: standalone Sparkle is
strip-only; keyboard `Single Color` versus strip `SingleColor`; keyboard Circular
versus strip Serpentine. No metadata/source/published-rule discrepancy was found
within this capture. The linked acceptance record retains full values and the
sanitized local journal's path/hash.

The [pinned REST serializer](https://github.com/GideonZ/1541ultimate/blob/7b628eb166872965ea59d66f90ffd9bcf7d71d8a/software/api/route_configs.cc)
emits neither enabled/disabled nor hardware-presence flags. The captured keyboard
Outward pattern is dormant under Fixed Color; the strip Royal Blue fixed color
is dormant under Rainbow. These retained values are consistent with the unchanged
menu dependency matrix below, not permission to edit inactive fields.

The two RGB headers beneath the main board and keyboard are operator-reported;
physical-header-to-REST-category mapping remains unverified. This acceptance
establishes bounded identity/metadata reads only, not every physical mode, safe
writes, prolonged stability or other hardware qualification. **Gate C remains
unauthorized and unaccepted; the original lockup remains unexplained and unproven
resolved.** Firmware `1.1.0s2` remains unqualified. Issue #25 remains Open / P0 /
In Progress; capability, redesign and enhancement dependencies remain unchanged.
The earlier publication and original implementation checkpoints below retain
their historical scope, including inert-widget fixture limitations. This evidence
update changes no dependency rule and does not publish the isolated Gate B executor.

## Publication checkpoint — 24 October 2026

The reviewed slice is integrated and published on `development` at
`c3a4984a1a4754830cf2b02aa202e3d75b0b37a7`.
[Hosted Test Lab run 40150212361](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/40150212361)
passed all eight configured jobs, including GTK regression. The offline fixtures
and their limitations described below are unchanged. This hosted result does not
establish physical C64U, package, cross-platform or release acceptance, qualify
firmware `1.1.0s2`, or prove the device lockup resolved. Issue #25 is verified as
P0 / In Progress / Open in Argonaut Development; the Project status update is complete.
Physical acceptance and root-cause investigation remain pending.
Earlier candidate/integration-authorization statements below describe the
pre-publication checkpoint; they are not the current publication state or new
hardware authorization. See CURRENT-STATE for integration tests and review.

## Original implementation checkpoint

Offline implementation candidate, 24 October 2026, based on published
`development` commit `c6db7da2be7bc4f65d2bdad41491712e35b9718a`.
This is reusable Core infrastructure for the Ultimate Menu renovation
([#20](https://github.com/Mrbruceybruce/argonaut-c64u/issues/20)), scoped to
[#25](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25) and the bounded
capability evidence relevant to [#24](https://github.com/Mrbruceybruce/argonaut-c64u/issues/24).
It does not implement the tree/property-sheet redesign or LED enhancements.

## Official source qualification

Pinned official GideonZ/1541ultimate revision:
`7b628eb166872965ea59d66f90ffd9bcf7d71d8a`.
The [version commit](https://github.com/GideonZ/1541ultimate/commit/7b628eb166872965ea59d66f90ffd9bcf7d71d8a)
is titled “Set version to 1.1.0” and changes `software/application/versions.h`
`APPL_VERSION_NUMBER` to `1.1.0`. Qualification uses the commit, not a movable tag
or the current upstream branch.

- [Keyboard definitions and rules](https://github.com/GideonZ/1541ultimate/blob/7b628eb166872965ea59d66f90ffd9bcf7d71d8a/software/u64/bling_board.cc):
  mode/field definitions at lines 35–49; `update_menu` at 789–821.
- [Strip definitions and rules](https://github.com/GideonZ/1541ultimate/blob/7b628eb166872965ea59d66f90ffd9bcf7d71d8a/software/u64/led_strip.cc):
  enum/field definitions at 55–74; `update_menu` at 655–688.

Both categories use REST identity `LedStrip Mode`, despite the physical menu's
shortened label `Mode`. Keyboard modes are Off, Fixed Color, SID Music, Rainbow,
Rainbow Sparkle, and Default. The strip additionally supports Sparkle.

| Proposed mode | Pattern | Intensity | Fixed Color | Color tint |
| --- | --- | --- | --- | --- |
| Off | inactive | inactive | inactive | inactive |
| Default | inactive | active | inactive | inactive |
| Fixed Color | inactive | active | active | active |
| SID Music | active | active | inactive | inactive |
| Rainbow | active | active | inactive | active |
| Rainbow Sparkle | active | active | inactive | active |
| Sparkle (strip only) | inactive | active | inactive | inactive |

Auto SID Mode and SID Select have no mode-dependent disable rule in either
`update_menu`; advertised qualified choices remain available in every known mode.
The existing UI DHCP/static-IP dependency is also represented in the shared
registry and now enforced at the Core boundary.

Runtime LED admission requires a fresh `/v1/info` reporting exactly product
`C64 Ultimate` and firmware `1.1.0`, plus fresh category/field metadata: a known
current/controller choice, a nonempty subset of the qualified mode vocabulary,
known enum choices, and integer intensity bounds 0–31. Unknown versions,
including `1.1.0s2`, are not silently mapped to official `1.1.0`. They require
separate source qualification. This product/version scope follows the existing
[compatibility evidence](ULTIMATE-COMPATIBILITY.md); identity strings do not
attest the running image cryptographically.

Store exposure is configuration-contract evidence, not proof that LEDs are
physically installed. The firmware registers stores independently of installation,
and the strip physical-menu heading explicitly allows “if installed”. This slice
does not invent a hardware-presence probe or claim physical qualification across
Beige, Founder, Starlight, or other hardware.

## Shared ownership and admission

`configuration_policy.py` is headless Core policy. Its dependency registry,
`enabled`, and `validate` functions are shared by Ultimate Menu presentation,
Restore/Undo/native-file staging, direct Core calls, and the internal raw-client
public Apply entry point. `dependencies.py` retains compatibility imports for
existing UI callers. Future property sheets can use the same policy.

1. Detach and validate the full intent: plain dictionaries, unambiguous identities,
   finite scalar values. Reject case-colliding names and wildcard/path identities.
2. Read fresh settings for every touched category. For LED edits, read fresh
   firmware/product identity. Validate all selected values and capabilities.
3. Overlay every proposed controller before checking dependent edits. Retained
   dormant values are not edits. Controller-only LED changes are refused; other
   qualified controllers retain their dependency behavior.
   Same-value explicit edits to inactive fields still fail admission. Explicit LED
   mode edits are now refused before this step by the containment policy above.
4. For reviewed Apply, compare changed values and controlling settings against
   the review snapshot, including a mode the user did not edit. A stale controller
   refuses even if the requested dependent is active in both old and new modes.
5. Reject the entire invalid mixed batch before any REST write or history write.
   Never partially filter/apply a refused batch.
6. For an admitted batch, place enabling controllers before dependent fields,
   save the prior changed values for Undo if requested, then make one REST POST.
   Transport failure is uncertain and is not retried or automatically rolled back.

Core holds its session-admission gate through fresh reads, validation, history,
and dispatch. Reviewed UI work captures a session identity; reconnect invalidates
it. The raw public `UltimateClient.apply_configuration` uses the same admission;
`_apply_configuration_validated` is only the internal transport sink after Core
admission, not a public client capability. Core does not expose raw transports.

The UI uses the same final-state validator before review and before staging a
Restore/Undo/native-file selection. Invalid selections preserve existing state.
A preview cannot clear an existing reload gate. LED mode rows are read-only. Other interactive controller
changes retain the established behavior of discarding newly inactive local
field edits; selection previews validate the complete set before any staging.
Core rechecks independently, so bypassing UI admission cannot permit a bad write.
Definite refusal reports `Configuration not sent`; post-dispatch failures retain
uncertainty feedback and the prior-value recovery point.

## Limits and acceptance gates

- This enforces the evidenced menu contract. It neither reproduces nor explains
  the hardware lockup, and does not establish that valid requests cannot trigger
  a firmware defect. Issue #25 remains open.
- REST is not a device-side atomic compare-and-set transaction. Another client,
  the physical menu, or firmware may change values after the read. Core's local
  session gate cannot exclude those actors or make a POST atomically reversible.
- Unknown fields in a known LED store fail closed. Future renamed categories,
  cross-category dependencies, and indirect power selectors are not inferred to
  be LED modes. Broader hardware capability mapping remains Issue #24.
- Existing unrelated configuration writes remain available when fresh metadata
  validates them. Save to Flash remains its separate existing operation, persisting
  the running configuration including external changes; it does not use this
  per-edit dependency validator.
- Controller tests use inert GTK widgets. No real GTK rendering, physical C64U,
  package, hosted CI, or cross-platform acceptance is claimed.
- The earlier `issue25-led-safeguard` blanket-refusal checkout and its evidence
  remain untouched. This candidate is an independent checkout from the published
  baseline, not an integration or replacement of that workspace.

## Offline reproduction

From this checkout, run the focused suite:

```sh
PYTHONPATH=tests python3 -m unittest test_configuration_dependencies
```

Its fixtures reject Python socket connect/connect_ex/sendto/create_connection,
use injected synthetic transports, temporary preferences/history and inert GTK
widgets. The headless subprocess only imports Core/policy and checks that GI is
absent. The affected regression run also includes `test_configuration`,
`test_dependencies`, `test_backups`, `test_settings_safety`, `test_native_files`,
`test_core`, `test_api`, `test_c64_ai_launch`, `test_scheduler`, `test_recovery`,
and `test_ci_runner`, with the same socket guard installed around the full run.

CI registers the two classes (22 Core tests, 10 UI tests); the source audit
checks inventory, not execution of all CI selections. Tests cover all category
modes and transitions, active/inactive field rules, both field/category orders,
whole mixed-batch mode refusal, stale unedited controllers, malformed/unknown metadata,
case bypass, direct Core and public raw API, zero REST/history writes on refusal,
history on admitted dispatch, Restore/actual Undo/native previews, and existing
DHCP dependency semantics. See CURRENT-STATE for final test/review results.

Integration requires separate user approval after reviewing the exact diff,
source/target identities, ancestry, primary dirty files, and independent review
result. No staging, committing, pushing, publication, issue-state changes, or
physical acceptance are authorized by this implementation checkpoint.
