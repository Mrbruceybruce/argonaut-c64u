# Argonaut roadmap

## Live planning authority — GitHub Project

GitHub Project **Argonaut Development** is authoritative for live work status,
priority, ordering and scheduling. Consult and update the Project when selecting
or scheduling work and when its live status changes. This document defines stable
scope, dependencies, safety principles and evidence links; its order is not a queue.

RM-001 through RM-031 are permanent scope identities. Preserve their aliases when
linking issues, Project items and repository evidence. Do not renumber or reuse
an ID; retain retired IDs with successor references. R1–R6, PA-* and Managed Import
phase identifiers remain separate technical checkpoints, not replacement RM IDs.

Record planning changes in the Project and technical decisions and acceptance in
the relevant repository documents. A Project status change neither satisfies a
dependency or safety gate nor authorizes execution. Keep design approval,
implementation, review, physical acceptance and Git publication distinct.

## Stable scope register

The identity/alias mapping is recovered from the pre-migration audit preserved in
stash commit `1cd2cdad5f4e42c508d596f9e6181839c3a38934`; its old statuses and
authority claims are not adopted here. Parent relationships organize scope;
technical dependencies below do not prescribe Project scheduling.

| Stable ID | Historical alias / scope | Parent or technical dependency | Evidence / boundary |
| --- | --- | --- | --- |
| <a id="rm-001"></a>RM-001 | A / network foundation | Foundation for device work | Preserve managed FTP ownership and R1–R6 qualification boundaries. [History](ARGONAUT-ROADMAP-HISTORY.md#a-baseline--completed-foundation) |
| <a id="rm-002"></a>RM-002 ([#18](https://github.com/Mrbruceybruce/argonaut-c64u/issues/18)) | B / stabilization | Children RM-015–020 | Reliability, credentials, connection UX, header, cancellation and local packaging. [History](ARGONAUT-ROADMAP-HISTORY.md#b-stabilization--spit-shine--do-first) |
| <a id="rm-003"></a>RM-003 | C / Files storage UX | Children RM-021–025 | Selection, root visibility, backup UI retirement, storage policy and polish. [History](ARGONAUT-ROADMAP-HISTORY.md#c-files--storage-ux) |
| <a id="rm-004"></a>RM-004 ([#28](https://github.com/Mrbruceybruce/argonaut-c64u/issues/28)) | D / shared picker | Core file references and consumer-specific permissions | Local/C64U selection; audit each consumer before further migration. [History](ARGONAUT-ROADMAP-HISTORY.md#d-shared-argonaut-file-picker--reusable-component) |
| <a id="rm-005"></a>RM-005 ([#29](https://github.com/Mrbruceybruce/argonaut-c64u/issues/29)) | E / Drives redesign | RM-004; firmware mode/ROM investigation | Drive operation versus configuration; preserve three write modes; see UI-36 below. [History](ARGONAUT-ROADMAP-HISTORY.md#e-drives-redesign) |
| <a id="rm-006"></a>RM-006 ([#19](https://github.com/Mrbruceybruce/argonaut-c64u/issues/19)) | F / Streams | RM-015 diagnosis and independent verification | Replay removal, scaling, remote keyboard and interaction; OBS remains separate. [History](ARGONAUT-ROADMAP-HISTORY.md#f-streams--stability-then-interaction) |
| <a id="rm-007"></a>RM-007 ([#20](https://github.com/Mrbruceybruce/argonaut-c64u/issues/20)) | G / Ultimate Menu redesign | Children RM-026–029 | Capability-aware tree/property sheets with physical-menu parity. [History](ARGONAUT-ROADMAP-HISTORY.md#g-ultimate-menu-redesign--major-category-not-spit-shine) |
| <a id="rm-008"></a>RM-008 ([#30](https://github.com/Mrbruceybruce/argonaut-c64u/issues/30)) | H / broader power controls | Per-action API and safety review | Global Ultimate Power; B4 Reset/Reboot acceptance does not qualify additional actions. [History](ARGONAUT-ROADMAP-HISTORY.md#h-machine--global-power-controls) |
| <a id="rm-009"></a>RM-009 ([#31](https://github.com/Mrbruceybruce/argonaut-c64u/issues/31)) | I / Test Lab placement | Channel gating and lifecycle preservation | Settings → Developer → Open Test Lab; see later UI decision below. [History](ARGONAUT-ROADMAP-HISTORY.md#i-test-lab--developer-mode) |
| <a id="rm-010"></a>RM-010 ([#32](https://github.com/Mrbruceybruce/argonaut-c64u/issues/32)) | J / SIDJuke follow-ups | RM-004; trustworthy duration evidence | Preserve playlists, playback and manual navigation; multi-select/directory add needs review. [History](ARGONAUT-ROADMAP-HISTORY.md#j-sidjuke) |
| <a id="rm-011"></a>RM-011 ([#21](https://github.com/Mrbruceybruce/argonaut-c64u/issues/21)) | K / Game Library and managed import | Children RM-030–031 | Separate referenced-file catalog, managed import/publication and launch evidence. [History](ARGONAUT-ROADMAP-HISTORY.md#k-game-library) |
| <a id="rm-012"></a>RM-012 ([#33](https://github.com/Mrbruceybruce/argonaut-c64u/issues/33)) | L / Cartridge Tools | Clean reboot without cartridge saved to Flash; RM-011 handoff | Review cartdumper integration and machine-state guard; optional dumped CRT catalog handoff. [History](ARGONAUT-ROADMAP-HISTORY.md#l-cartridge-tools--separate-feature-category) |
| <a id="rm-013"></a>RM-013 | M / later tracks | Track-specific qualification | Core/API, PWA, OBS/YouTube, release, themes, recovery UX and media extensions. [History](ARGONAUT-ROADMAP-HISTORY.md#m-later--deferred--including-recovered-existing-roadmap-items) |
| <a id="rm-014"></a>RM-014 ([#22](https://github.com/Mrbruceybruce/argonaut-c64u/issues/22)) | N / offline libraries and playback | Six-step design sequence below | Multiple libraries, local preparation, discovery/adoption, VICE and VSID. [History](ARGONAUT-ROADMAP-HISTORY.md#n-argonaut-offline-libraries-and-playback--planned-future-track) |
| <a id="rm-015"></a>RM-015 ([#23](https://github.com/Mrbruceybruce/argonaut-c64u/issues/23)) | B1 / streaming hang | Parent RM-002; prerequisite to RM-006 expansion | Capture hung process/thread evidence; replay causality is unproven. [History](ARGONAUT-ROADMAP-HISTORY.md#1-p0--streamingnavigation-permanent-hang) |
| <a id="rm-016"></a>RM-016 | B2 / credential UX | Parent RM-002 | Preserve bounded credential acceptance; native-store platform qualification is separate. [History](ARGONAUT-ROADMAP-HISTORY.md#2-credential--saved-network-connection-ux) |
| <a id="rm-017"></a>RM-017 | B3 / Device Details | Parent RM-002 | Network connections, discovery and layout; retain subnet and credential limitations. [History](ARGONAUT-ROADMAP-HISTORY.md#3-device-details--connection-profile-ux) |
| <a id="rm-018"></a>RM-018 | B4 / header cleanup | Parent RM-002; distinct from RM-008 | Preserve identity/session, stale-settings and Reset/Reboot safety; later UI direction below. [History](ARGONAUT-ROADMAP-HISTORY.md#4-global-headernavigation-cleanup) |
| <a id="rm-019"></a>RM-019 | B5 / contextual cancellation | Parent RM-002 | Scoped foreground admission and sticky cancellation; not all-worker cancellation. [History](ARGONAUT-ROADMAP-HISTORY.md#5-contextual-operation-statuscancellation) |
| <a id="rm-020"></a>RM-020 | B6 / local packaging | Parent RM-002; separate public release gates | Local dev2 acceptance does not qualify public 1.10 or other platforms. [History](ARGONAUT-ROADMAP-HISTORY.md#6-packaging-spit-shine) |
| <a id="rm-021"></a>RM-021 | C0 / selection | Parent RM-003 | Native selection/activation and focus; retain later chooser/lifecycle acceptance gaps. [History](ARGONAUT-ROADMAP-HISTORY.md#c-files--storage-ux) |
| <a id="rm-022"></a>RM-022 | C1 / storage roots | Parent RM-003; Core permissions | USB/SD/Flash/Temp visibility; Flash/Temp generic operations remain restricted. [History](ARGONAUT-ROADMAP-HISTORY.md#c-files--storage-ux) |
| <a id="rm-023"></a>RM-023 | C2 / remove backup UI | Parent RM-003 | Retain ordinary copying and reviewed recovery; retained Core backup code is not a UI mandate. [History](ARGONAUT-ROADMAP-HISTORY.md#c-files--storage-ux) |
| <a id="rm-024"></a>RM-024 | C3 / storage policy review | Parent RM-003; preserve C1 policy | No generic Flash/Temp mutation; new export/recovery needs separate review; restore unapproved. [History](ARGONAUT-ROADMAP-HISTORY.md#c-files--storage-ux) |
| <a id="rm-025"></a>RM-025 | C4 / Files polish | Parent RM-003; C0–C3 and RM-019 contracts | Accessibility, labels, menus/focus and recovery visibility; bounded acceptance only. [History](ARGONAUT-ROADMAP-HISTORY.md#c-files--storage-ux) |
| <a id="rm-026"></a>RM-026 ([#24](https://github.com/Mrbruceybruce/argonaut-c64u/issues/24)) | G1 / capabilities | Parent RM-007; before dependent filtering | Firmware detection → configuration → visibility/dependencies → REST evidence. [History](ARGONAUT-ROADMAP-HISTORY.md#1-firmwarehardware-capability-investigation--first-engineering-phase) |
| <a id="rm-027"></a>RM-027 ([#25](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25) qualified closure; [#49](https://github.com/Mrbruceybruce/argonaut-c64u/issues/49) successor safety scope) | G2 / LED safety | Parent RM-007; prerequisite to dependent LED changes | Investigate payload/order and valid transitions; no casual lockup reproduction. [History](ARGONAUT-ROADMAP-HISTORY.md#2-led-safety-investigation--p0-device-safety-gate) |
| <a id="rm-028"></a>RM-028 ([#26](https://github.com/Mrbruceybruce/argonaut-c64u/issues/26)) | G3 / property-sheet redesign | Parent RM-007; RM-026 and applicable RM-027 findings | Hierarchical navigation, persistent properties, Advanced/F2 parity; remove Favorites. [History](ARGONAUT-ROADMAP-HISTORY.md#3-treeproperty-sheet-redesign--settled-direction) |
| <a id="rm-029"></a>RM-029 | G4 / LED enhancements | Parent RM-007; RM-026 and RM-027 | Profiles, random generation and color controls after capability and safety qualification. [History](ARGONAUT-ROADMAP-HISTORY.md#4-led-enhancements--later-within-redesign) |
| <a id="rm-030"></a>RM-030 ([#27](https://github.com/Mrbruceybruce/argonaut-c64u/issues/27)) | Managed Import / general workflow and recovery | Parent RM-011; staged phase gates | 3A/3B foundations; 3B-2C workflow, 3B-3 recovery and general 3C are not closed by pinned PA results. [History](ARGONAUT-ROADMAP-HISTORY.md#managed-import-phase-3b-2b3e2f--exclusive-writer-correction-pending-inspection) |
| <a id="rm-031"></a>RM-031 | PA / pinned publisher and managed display | Parent RM-011; exact reviewed publication/launch scope | Read PA-5.10–13 reconciliation in CURRENT-STATE; preserve attempt-specific limitations. [History](ARGONAUT-ROADMAP-HISTORY.md#pa-51c-offline-implementation-checkpoint) |

Historical migration decision: RM-031's original pinned publisher/managed-display
scope was approved **COMPLETE** during migration. Managed CRT launch, Founder
qualification and general import/recovery remain separate RM-011/RM-030 work.
GitHub Project **Argonaut Development** owns live status.

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

Historical pre-reconciliation snapshot (superseded by Stage 2 above): native
GitHub dependencies listed #26 as blocked by #24 and closed #25; #49 had no native
blocking links. #26's text and #48's body retained older #25 references, and #49's
creation-time text described a proposed handoff. These discrepancies required
separate authorization and have since been reconciled; their correction does not
clear safety gates. RM-029 remains under #20 / RM-007 and this roadmap; no dedicated
issue was identified at that checkpoint.

## RM-027 dependency-validation implementation candidate

### Recorded residual-risk ownership and C1 follow-up — 25 October 2026

The [maintainer ownership record](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25#issuecomment-6402085824)
confirms **Bruce / Argonaut maintainer** accepts residual intermittent-lockup and
indirect/firmware-driven LED-transition risk ownership, including Auto SID, and
coordination of investigation and qualification. This is recorded responsibility,
not a GitHub assignee change. [C1 tooling issue #48](https://github.com/Mrbruceybruce/argonaut-c64u/issues/48)
now tracks premature termination, truthful outcomes, scheduled readback/observation
accounting, deterministic offline regressions, independent review and durable
evidence retention. Its creation does not authorize implementation or hardware work.

**QUALIFIED ACCEPT** remains bounded acceptance of explicit mode-write containment,
not a lockup fix, general write safety, completed physical qualification or closure.
The original lockup/root cause and indirect transitions remain unresolved under
**#25, Open / P0 — Critical / In Progress**; no safety scope transfers to #48.
#24 capability coordination and RM-026, RM-028 and RM-029 gates remain unchanged.
See the [current evidence boundaries](ISSUE25-MODE-CONTAINMENT.md#recorded-ownership-and-linked-tooling-follow-up--25-october-2026).

The preceding four-document reconciliation is published on `development` at
`2dc8bdc09740ca1a0a2e69ff92ec2fa44be4f4c9`, verified against primary and live GitHub
HEADs before this edit. Earlier proposed-owner, missing-follow-up and publication-
pending statements below retain their historical checkpoint scope and are superseded
by this record. This new documentation-only reconciliation awaits independent review
and the user's manual publication gates. Any #25 closure still requires separate
explicit maintainer review and authorization preserving the unresolved safety scope.

### Publication and qualified-acceptance reconciliation — 25 October 2026

The reviewed explicit LED mode-write containment is integrated and published on
`development` at `40da3846e88c6efe5395928394a6850c17e92f1c` (parent `2cd5a60549e08cf734f192e0cfc38882f583c3db`).
Primary and live GitHub HEADs were verified equal before this documentation edit;
tracked files/index were clean, with seven preserved legacy untracked artifacts.
All nine published files match the reviewed integration manifest. The sixteen
other snapshotted checkouts retain their recorded file contents and unpublished work.

**QUALIFIED ACCEPT** is the bounded investigation/refusal-policy disposition being
reconciled with the user's approval. It accepts explicit mode-write containment,
not resolution of the intermittent device lockup, general write safety, completed
physical qualification or issue closure. The original triggering payload and root
cause remain unknown. The historical candidate checkpoints below are preserved;
their unintegrated/unpublished wording does not describe the published containment.
This four-document reconciliation itself remains unstaged, uncommitted and unpublished.

Retained primary integration evidence passes **120/120 normal**, **120/120 optimized**
and **35/35 GTK Gate A** (11 GTK, 22 Core, 2 LED), zero failures/errors/skips.
Engineering and integration independent reviews report PASS. These results were
inspected, not rerun for this documentation-only change.
[Hosted Test Lab run 40223973630](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/40223973630)
completed successfully at `40da384`; it qualifies the configured hosted suites,
not the separately executed real-GTK Gate A module or physical/package/release acceptance.
See the [acceptance criteria and residual-risk record](ISSUE25-MODE-CONTAINMENT.md#qualified-acceptance-disposition--25-october-2026).

Gate A remains bounded offline UI/Core evidence; Gate B accepted five read-only
requests on operator-identified Founder hardware with firmware 1.1.0.
C1 supports bounded intensity **6→16** functional success through the validated
POST, operator observations and a separate authenticated GET. Requests 9–14 and
both timed readback/observation rounds remain incomplete; the original 14-request
protocol did not pass. Original terminal flags and evidence are unchanged.

Explicit mode refusal does not control indirect/firmware-driven transitions,
including behavior associated with Auto SID. Intermittent lockup, transition safety,
physical-header-to-category mapping, Beige/Starlight/other variant qualification,
firmware `1.1.0s2`, device-side atomicity and broader release acceptance remain open.
Proposed residual-risk owner: **Bruce / Argonaut maintainer, subject to explicit
maintainer acceptance**; no ownership assignment is made by this reconciliation.

Issue #25 remains **Open / P0 — Critical / In Progress** and the defining LED safety
issue. Its existing Project fields already match the approved disposition; no field
change is needed. Capability coordination remains with #24; RM-026, RM-028 and
RM-029 retain their gates. C1 executor premature termination and evidence retention
need separately approved follow-up tracking; no dedicated issue was identified in
the repository issue inventory. No new issue, reassignment, closure, hardware
operation or Git publication is authorized by this checkpoint. Next gates are
independent documentation review, the user's manual publication sequence, and a
separate final acceptance/closure decision with explicit residual-risk ownership.

### LED mode-write containment candidate — 25 October 2026

A new isolated candidate based on published `development` at
`2cd5a60549e08cf734f192e0cfc38882f583c3db` implements the user-approved Argonaut
restriction: refuse every explicit `LedStrip Mode` write in Keyboard Lighting
and LED Strip Settings, including same-value writes and whole mixed batches.
Active parameter-only edits retain existing dependency, firmware, metadata,
staleness and session safeguards. See the [updated contract](CONFIGURATION-DEPENDENCIES.md#led-mode-write-containment-candidate--25-october-2026)
and [offline tests/review record](ISSUE25-MODE-CONTAINMENT.md).

This candidate is uncommitted, unpublished and not integrated into primary.
Primary/live HEAD match the baseline; tracked primary files/index are clean,
seven pre-existing untracked artifacts and the historical stash remain preserved.
Prior isolated candidates remain untouched. Live tracking is **Open / P0 /
In Progress** for #25; #24 is P1 / Backlog and #26 is P2 / Backlog.
No tracking change is made. Integration requires a separate authorization decision.

Containment is not a firmware requirement, demonstrated lockup fix or physical
acceptance. The original lockup and C1 executor termination remain unresolved;
safe mode transitions, hardware mapping, firmware 1.1.0s2 and broader release
qualification remain unproven. RM-026, RM-028 and RM-029 retain their gates.
The historical checkpoints below are not fresh authorization or current candidate
publication claims.

### Gate C1 functional disposition — 25 October 2026 UTC

The user approved recording **bounded keyboard-intensity functional success
(6→16, Fixed Color / Red), with the original C1 protocol incomplete**. Seven
validated GETs and one validated POST response were retained; the operator
reported brighter LEDs and a responsive keyboard. A separately authorized
authenticated keyboard-category GET returned HTTP 200, empty errors and intensity
16 with the other expected values/metadata retained.

The executor stopped with `premature terminal reply` before requests 9–14;
neither scheduled readback/observation round completed. The supplemental GET did
not reverify identity or LED Strip Settings. It does not make the original
14-request protocol pass or change its false completion/acceptance flags.
See [full disposition and evidence retention needs](CURRENT-STATE.md#gate-c1-functional-disposition--25-october-2026-utc).

Primary/live `development` were verified at `873fa34ecacaba56dc04db7694a2483e3e2c922e`.
Issue #25 remains **Open / P0 / In Progress**. Executor termination, the original
lockup, safe mode-transition qualification and hardware mapping remain unresolved;
firmware `1.1.0s2` remains unqualified. RM-026, RM-028 and RM-029 retain their gates.
The isolated executor remains uncommitted/unpublished. Independent documentation review
found no actionable findings; manual Git publication remains pending; no new hardware action or issue
closure is authorized. Earlier Gate A/B statements retain their historical scope.

### Gate A publication and Gate B read-only acceptance — 25 October 2026 UTC

Gate A is published on verified primary/live GitHub `development` at
`89c8eea956dc66d52124da5969fc14ede9a5a27b`: **33/33 isolated offline methods**
passed (11 real GTK, 20 Core, 2 LED), with zero failures/errors/skips and independent
integration review without actionable findings.
[Hosted Test Lab run 40154324070](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/40154324070)
passed all eight jobs; the new Gate A module remains deferred from hosted suites,
so its offline result is separate evidence.

[Gate B READ-ONLY acceptance](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25#issuecomment-6393217684)
records **5/5 validated GETs** on operator-identified Founder `25BE71`, REST product
`C64 Ultimate`, firmware `1.1.0`, API `0.1`. Both LED categories' seven-field
metadata matched qualified source. See [current evidence and limitations](CURRENT-STATE.md#gate-a-publication-and-gate-b-read-only-acceptance--25-october-2026-utc)
and [dependency evidence](CONFIGURATION-DEPENDENCIES.md#gate-ab-evidence-checkpoint--25-october-2026-utc).
The isolated Gate B executor remains uncommitted/unpublished.

Live Issue #25 remains **Open / P0 / In Progress**. RGB header-to-REST mapping is
unverified; firmware `1.1.0s2` remains unqualified. **Gate C remains unauthorized
and unaccepted**, and the original lockup remains unexplained and unproven resolved.
Read-only metadata acceptance does not qualify writes, prolonged stability, other
hardware, device-side atomicity, broader UI/package/cross-platform or release
acceptance. RM-026, RM-028 and RM-029 dependencies remain in force.
The checkpoints below preserve their historical scope, including the former
Gate A publication-pending and Gate B outstanding statements. This documentation
reconciliation awaits the user's manual publication gates; it changes no tracking
state and grants no hardware or issue-closure authorization.

### Gate A integration checkpoint — 25 October 2026 UTC / 24 October America/Chicago

The dependency validator is published on `development` at verified local/live
HEAD `6ff217c9aaaec834875e51e8cbe55d37585b998d` (implementation at `c3a4984`,
followed by publication-status documentation). The separate five-file GTK Gate A
infrastructure is integrated in the primary checkout but remains **unstaged,
uncommitted and unpublished**. Its 512 additions / 1 deletion and five hashes
match the independently reviewed candidate; no production behavior changed.

Primary isolated offline validation passed **33/33 methods** (11 real GTK,
20 Core, 2 existing LED), with zero failures/errors/skips and verified network
isolation. Independent final candidate execution also passed 33/33; independent
integration review found no actionable blocker within that offline scope.
See [current integration state and retained evidence](CURRENT-STATE.md#gate-a-integration-checkpoint--25-october-2026-utc--24-october-americachicago)
and [bounded Gate A coverage](ISSUE25-GATE-A.md). The latter remains the unchanged
pre-integration evidence record; CURRENT-STATE records its later integration.
The new GTK module is deferred from hosted suites; prior hosted CI success does
not qualify this candidate.

Issue #25 remains Open / P0 / In Progress on fresh read-only verification.
The intermittent lockup remains unexplained and unproven resolved. Physical
Gates B/C, native Restore chooser/real remote transport, exhaustive keyboard and
exact focus preservation, firmware `1.1.0s2`, broader hardware capabilities,
device-side atomicity and hosted/package/cross-platform/release qualification
remain outstanding. RM-026, RM-028 and RM-029 retain their separate dependencies.
Publication of Gate A still requires documentation review and the user's manual
staging, staged-diff review, commit, push and publication-verification gates.
This documentation-only reconciliation changes no issue/Project state and
authorizes no hardware operations or issue closure.

### Earlier dependency-validator publication checkpoint

Publication checkpoint — 24 October 2026: the reviewed bounded slice is published
on `development` at `c3a4984a1a4754830cf2b02aa202e3d75b0b37a7`.
[Hosted Test Lab run 40150212361](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/40150212361)
passed all eight jobs. Issue #25 is verified as P0 / In Progress / Open
in Argonaut Development; the approved Project status update is complete. Physical acceptance and
lockup root-cause investigation remain pending. This supersedes
publication-pending wording in the candidate checkpoint below, without completing
RM-027 or its broader parent/dependent work.

The offline Issue #25 slice provides shared Core dependency admission for RM-007's
ongoing Ultimate Menu renovation. It validates whole proposed batches against
fresh controlling settings, with LED menu rules pinned to official 1.1.0 source.
See [contract and qualification boundaries](CONFIGURATION-DEPENDENCIES.md) and
[implementation evidence](CURRENT-STATE.md#issue-25--rm-007--offline-configuration-dependency-candidate).
This is neither the former blanket LED refusal nor a proven lockup correction.
RM-026 capability investigation, RM-028 structural redesign, RM-029 enhancements,
physical acceptance and publication remain separate gates. Live priority/status
remain with the Project; no issue or Project field was changed for this candidate.

## Strategic outcomes and boundaries

- **A–C:** preserve Network Foundation and bounded stabilization/Files acceptance.
  Diagnose streaming independently; maintain truthful credential/discovery outcomes,
  session-only modes, contextual cancellation, native selection and root permissions.
  Read [Device Details evidence](DEVICE-DETAILS-STABILIZATION.md) and
  [current acceptance records](CURRENT-STATE.md) before changing behavior.
- **D–F:** unify selection through Core-owned local/C64U references with per-consumer
  types and actions. Drives operate hardware; Ultimate Menu configures it. Retain
  enabled-switch and Run direction, and investigate D64/D71/D81, ROMs and JiffyDOS
  before removing mode/ROM controls. Streams includes aspect-preserving Fit to
  Window, scale expansion, obvious/escapable keyboard capture, C64 key mapping and
  UI/audio polish. Stream VIC/Stream Audio grouping is a deliberate exception to
  menu parity. Replay removal requires dependency review and does not prove a hang fix.
- **G–I:** investigate firmware capabilities across device variants before menu
  filtering and structural changes. Preserve physical-menu organization, Advanced/F2,
  Command Interface and Ultimate Audio placement. LED safety precedes enhancements.
  Qualify each additional power/memory action independently. Preserve deterministic
  Test Lab verdicts, diagnostics, reports, service isolation and channel access.
- **J–L:** retain SIDJuke playback and [duration policy](SID-JUKEBOX.md#duration-policy-and-deferred-work).
  Game Library distinguishes CRT/disk media and verified launch from catalog metadata;
  preserve [catalog and managed launch safety](GAME-LIBRARY.md). Cartridge dumping is
  separate from launching/copying CRTs: review the MIT-licensed
  `darkuni/c64-ultimate-cartdumper` integration and reboot/configuration guard before
  use; a successful dump can offer adding the CRT to Game Library.
- **M:** retain OBS/media qualification before a direct-YouTube go/no-go; audit the
  historical feature branch before reuse. Public 1.10 packaging/tag/release follows
  stabilization and release acceptance. Retain System/Light/Dark themes, Reset/Reboot
  recovery UX, song-length database/silence/advance investigations, SID reconfiguration,
  ZIP/7z/additional media, Tested/Playable user state and launch fingerprint performance.
  Tape/Datasette and cassette-to-TAP imaging require separate hardware/API investigation.
  Persistent Core/versioned API and CLI proof precede remote-client artifact ownership,
  limits/cleanup and then PWA work; preserve [server-first contracts](SERVER-FIRST.md).
- **N:** extend library management to offline local/removable storage and external
  VICE/VSID through separately reviewed contracts. Existing catalogs and C64U playback
  do not establish offline preparation or emulator integration. Do not reuse FTP
  staging unchanged for local filesystems or extend current game import formats implicitly.

### RM-006 replay-removal implementation checkpoint

The bounded Instant Replay removal is implemented locally and remains uncommitted;
see [inspection, preservation boundary and safety gates](CURRENT-STATE.md#issue-19--rm-006--instant-replay-removal-uncommitted).
Acceptance for this slice is **complete; Git publication remains pending**.
Independent code review passed with **no P0–P2 findings**; **95 regression tests
passed**. Operator-confirmed physical acceptance on the beige C64U passed for
streaming/tab navigation, clean shutdown, audio on/off, PNG capture, playable WebM
recording, stop/restart and disconnect/reconnect. RM-015 / Issue #23 stays open,
with causality unproven and independent hang retesting still required; no hang
root cause or fix is claimed.
This checkpoint does not complete RM-006 or change Project scheduling/status.

## Dependencies and safety gates

Technical prerequisites remain binding regardless of Project ordering:

- RM-027's qualified #25 closure does not satisfy the unresolved safety scope now
  retained by #49. RM-026 / #24 capability qualification remains required;
  RM-028 / #26 must incorporate applicable capability and safety findings, and
  RM-029 LED enhancements remain gated on capability and safety qualification.

- Core owns credentials, device rules, scheduling, identity, permissions and execution.
  UI changes must preserve managed ownership and accepted Network Foundation behavior.
- Keep approval, one-use authorization, durable intent/outcome, bounded capacity,
  independent readback and lifecycle evidence scoped to the exact operation and device.
  Loaded journals are inspection evidence, not migration/resume permission. Unknown
  effects or persistence failures block successors; no inferred retry, reconnect,
  cleanup, rollback, adoption or recovery authority comes from planning or receipts.
- Exclusive-writer acknowledgment is an operating contract, not an atomic FTP lock.
  External writers can race checks. Staged receipts are point-in-time evidence;
  publication must revalidate identity, content, collisions and manifest bindings.
- Preserve historical formats, hashes, test counts and acceptance limitations in the
  archive and [Managed Library contract](MANAGED-LIBRARY.md). Historical
  **PA-4.13 instruction-compliance FAIL** and **PA-4.2 UNCERTAIN** remain unchanged.
  Pinned physical publication does not close general import/recovery or qualify Founder.
- Read [current PA-5.10–13 evidence](CURRENT-STATE.md#current-game-library-state--pa-513-published)
  for publication, GUI, discovery/restoration and managed D64 launch. The archive's
  earlier “publisher/GUI unimplemented” statements are historical. Managed CRT launch,
  Founder qualification, specified GTK lifecycle regressions and post-launch remote
  integrity verification retain their recorded limitations; referenced-catalog CRT
  support is distinct. Protocol acceptance is not automatically gameplay acceptance.
- Physical testing requires its own reviewed scope and authorization. Do not casually
  reproduce the LED lockup or expand R6 exact-path qualification into generic Flash
  operations. Preserve sources and decline unsupported storage actions.
- Local Debian acceptance does not qualify Windows/macOS or public release. Retain
  portable implementation/automated checks, Linux-first hardware development and
  major-release cross-platform acceptance; old Stable 1.9 closure is historical.

### N: six-step design sequence

This is a technical design progression, not the live queue. Each slice requires
separate review/approval; this roadmap grants no implementation or device authority.

1. **Identity and compatibility:** define library/volume/catalog/content/location
   identities, versioning, explicit adoption/migration, non-overlap and rollback rules.
2. **Read-only locations/discovery:** bound roots, depth and scan budgets; retain
   detected/adopted/unavailable distinctions with no manifest writes or silent switching.
3. **Local preparation:** qualify permissions, names/case/links, shared capacity,
   rename/flush durability, source preservation, independent verification, interruptions,
   media removal and safe completion/ejection. No formatting or automatic cleanup.
4. **Offline game catalog and VICE:** multiple versions/locations, configured external
   executables (including investigation of x64sc), guarded process launch and CRT/D64/PRG
   compatibility/user-file protection per OS/player. Emulator writes must be addressed.
5. **SID Music Library and VSID:** bounded PSID/RSID metadata, original release text,
   subtunes, chip models/addresses and compatibility warnings; then reviewed playlists
   and future C64U media preparation. Share infrastructure, not game/music execution rules.
6. **Integrated workflow/platform acceptance:** selected library and playback target,
   unavailable media/reinsertion, multiple libraries and cross-platform behavior; explore
   Library Locations, Prepare USB/SD, Discover/Adopt, Emulator Settings, Play Locally and
   Launch on C64U without implicitly enabling or redesigning existing actions.

One physical device may contain multiple independent libraries, each with its own
UUID, manifest, managed root and catalog identity. Prevent overlapping roots and
path aliases; share capacity accounting and invalidate availability on media removal.
A mount path alone is not identity. Define duplicate/copied UUID handling without
silent merging, reidentification or manifest rewriting. Preserve unavailable catalog
references; never substitute a look-alike drive or file. Separate logical catalog
identity, exact content/version digest and storage location; cross-library relationships
and merges require explicit consent. Core-host storage differs from a remote client's
filesystem. Mounted/writable media is not proof of C64U compatibility.

Unresolved N decisions include shared versus separate game/music schemas, migration,
scan/network filesystem exclusions, metadata limits/provenance, local exclusive-writer
and recovery policy, filesystem durability, media identity/ejection, emulator discovery/
versions/arguments/lifecycle, SID compatibility and duplicate content/location handling.

## Design principles and later decisions

Preserve physical-menu familiarity; configuration belongs in Ultimate Menu, operations
in feature tabs and global machine actions in the header. Use intent labels such as
Run, switches for binary persistent state, checkboxes for properties and buttons for
actions, subject to the actual number of states. Do not hide storage merely because
mutations need stronger safeguards. Keep advanced capabilities discoverable without
burdening routine use; verify working credentials and firmware capabilities before change.

Later explicit decisions take precedence over superseded presentation proposals:

- [UI-36 three-mode drive writes](UI.md#revised-ui-36--approved-three-mode-drive-write-presentation)
  supersedes E's checkbox: preserve `readonly`, `readwrite` and `unlinked`, existing
  confirmations/session safety and Run's separate temporary-copy semantics.
- [Global controls and Test Lab direction](UI.md#global-controls-and-status): one
  contextual Connect/Disconnect, no manual Reconnect or relocation; preserve automatic
  recovery/internal reconnect and stale-settings protections. Test Lab moves to
  Settings → Developer → Open Test Lab, without a normal tab in either channel;
  preserve Stable restart/enablement gating and always-available Development access.
  These design decisions do not themselves establish implementation or acceptance.
- Follow [UI reconciliation and subsequent scoped records](UI.md) for later Files
  cancellation/recovery and presentation decisions; do not infer broader safety authority.
  Keep B4's earlier accepted technical behavior as evidence, not a mandate to restore
  superseded controls. C3 retains C1 Flash/Temp policy; C2 does not reopen backup UI.

## Evidence and history guide

[The immutable baseline archive](ARGONAUT-ROADMAP-HISTORY.md) retains the complete
1,706-line roadmap, including technical acceptance, both distinct 3B-2A records,
PA/3A/3B checkpoints, hashes and historical stop markers. Its provenance notice
identifies source commit and SHA-256. Historical status/priority/authority claims
are not live planning instructions and do not override the Project.

Use [CURRENT-STATE](CURRENT-STATE.md) for reconciled acceptance,
[MANAGED-LIBRARY](MANAGED-LIBRARY.md) for transaction contracts,
[UI](UI.md) for design decisions, [NEXT-PASS](NEXT-PASS.md) for older milestones,
and [RELEASING](RELEASING.md) for release gates. Preserve scoped foundation evidence:
[R1](R1-MANAGED-FOLDER-COMPOSITES.md), [R2](R2-MANAGED-CLI-FRESH-FOLDER.md),
[R3](R3-COMPATIBILITY-RETIREMENT.md), [R4](R4-MANAGED-C64-AI-INSTALL.md),
[R5](R5-CORE-OWNED-HEADLESS-READS.md), [R6](R6-MANAGED-FLASH-PUBLICATION.md) and
[FTP ownership closure](FTP-OWNERSHIP-CLOSURE.md). R5 was read-only; R6's physical
qualification used existing `/Flash/roms` and disposable one-byte fixtures, without
activation/reset; missing-directory MKD was deterministic-only.

### Legacy heading links

Existing heading fragments remain below as compact pointers. Their wording is
historical, including priority and pending labels; consult the linked record for
its original scope and the evidence guide above for later reconciliation.

| Historical section | Preserved record |
| --- | --- |
| <a id="pa-51a-publication-prerequisites--offline-foundation"></a>PA-5.1A publication prerequisites — offline foundation | [Archive](ARGONAUT-ROADMAP-HISTORY.md#pa-51a-publication-prerequisites--offline-foundation) |
| <a id="pa-46b-versioned-ftp-context-evidence--offline-implementation"></a>PA-4.6B versioned FTP context evidence — offline implementation | [Archive](ARGONAUT-ROADMAP-HISTORY.md#pa-46b-versioned-ftp-context-evidence--offline-implementation) |
| <a id="pa-4f3c-targeted-correction--pending-independent-reinspection"></a>PA-4F.3C targeted correction — pending independent reinspection | [Archive](ARGONAUT-ROADMAP-HISTORY.md#pa-4f3c-targeted-correction--pending-independent-reinspection) |
| <a id="pa-4f3-versioned-staging-mkd-evidence--pending-independent-inspection"></a>PA-4F.3 versioned staging MKD evidence — pending independent inspection | [Archive](ARGONAUT-ROADMAP-HISTORY.md#pa-4f3-versioned-staging-mkd-evidence--pending-independent-inspection) |
| <a id="pa-3e2-mkd-path-evidence-compatibility--pending-independent-inspection"></a>PA-3E.2 MKD path evidence compatibility — pending independent inspection | [Archive](ARGONAUT-ROADMAP-HISTORY.md#pa-3e2-mkd-path-evidence-compatibility--pending-independent-inspection) |
| <a id="pa-3f-library-creation-safety-correction--pending-independent-review"></a>PA-3F library creation safety correction — pending independent review | [Archive](ARGONAUT-ROADMAP-HISTORY.md#pa-3f-library-creation-safety-correction--pending-independent-review) |
| <a id="published-baseline-and-future-planning-status"></a>Published baseline and future planning status | [Archive](ARGONAUT-ROADMAP-HISTORY.md#published-baseline-and-future-planning-status) |
| <a id="managed-import-phase-3b-2b3e2f--exclusive-writer-correction-pending-inspection"></a>Managed Import Phase 3B-2B.3E2F — exclusive-writer correction; pending inspection | [Archive](ARGONAUT-ROADMAP-HISTORY.md#managed-import-phase-3b-2b3e2f--exclusive-writer-correction-pending-inspection) |
| <a id="managed-import-phase-3b-2b3e2--core-staging-executor-pending-inspection"></a>Managed Import Phase 3B-2B.3E2 — Core staging executor; pending inspection | [Archive](ARGONAUT-ROADMAP-HISTORY.md#managed-import-phase-3b-2b3e2--core-staging-executor-pending-inspection) |
| <a id="managed-import-phase-3b-2b3e1--transportevidence-prerequisites-pending-inspection"></a>Managed Import Phase 3B-2B.3E1 — transport/evidence prerequisites; pending inspection | [Archive](ARGONAUT-ROADMAP-HISTORY.md#managed-import-phase-3b-2b3e1--transportevidence-prerequisites-pending-inspection) |
| <a id="managed-import-phase-3b-2b3c1--policy-2-journal-foundation-pending-inspection"></a>Managed Import Phase 3B-2B.3C.1 — policy-2 journal foundation; pending inspection | [Archive](ARGONAUT-ROADMAP-HISTORY.md#managed-import-phase-3b-2b3c1--policy-2-journal-foundation-pending-inspection) |
| <a id="managed-import-phase-3b-2b2--read-only-admission-pending-independent-review"></a>Managed Import Phase 3B-2B.2 — read-only admission; pending independent review | [Archive](ARGONAUT-ROADMAP-HISTORY.md#managed-import-phase-3b-2b2--read-only-admission-pending-independent-review) |
| <a id="managed-import-phase-3b-2b1--journal-infrastructure-uncommitted-review-checkpoint"></a>Managed Import Phase 3B-2B.1 — journal infrastructure; uncommitted review checkpoint | [Archive](ARGONAUT-ROADMAP-HISTORY.md#managed-import-phase-3b-2b1--journal-infrastructure-uncommitted-review-checkpoint) |
| <a id="managed-import-phase-3b-2a--authorization-and-host-snapshots-approved-pending-manual-publication"></a>Managed Import Phase 3B-2A — authorization and host snapshots approved; pending manual publication | [Archive](ARGONAUT-ROADMAP-HISTORY.md#managed-import-phase-3b-2a--authorization-and-host-snapshots-approved-pending-manual-publication) |
| <a id="bounded-cleanupadmission-and-disk-accounting-correction--approved-in-final-review"></a>Bounded cleanup/admission and disk-accounting correction — approved in final review | [Archive](ARGONAUT-ROADMAP-HISTORY.md#bounded-cleanupadmission-and-disk-accounting-correction--approved-in-final-review) |
| <a id="managed-import-phase-3b-2a--approved-pending-manual-publication"></a>Managed Import Phase 3B-2A — approved; pending manual publication | [Archive](ARGONAUT-ROADMAP-HISTORY.md#managed-import-phase-3b-2a--approved-pending-manual-publication) |
| <a id="managed-import-phase-3b-1--approved-pending-manual-publication"></a>Managed Import Phase 3B-1 — approved; pending manual publication | [Archive](ARGONAUT-ROADMAP-HISTORY.md#managed-import-phase-3b-1--approved-pending-manual-publication) |
| <a id="managed-library-phase-3a--accepted-pending-manual-publication"></a>Managed Library Phase 3A — accepted; pending manual publication | [Archive](ARGONAUT-ROADMAP-HISTORY.md#managed-library-phase-3a--accepted-pending-manual-publication) |
| <a id="phase-3a-gnome-wayland-physical-acceptance--passed-pending-manual-publication"></a>Phase 3A GNOME Wayland physical acceptance — passed; pending manual publication | [Archive](ARGONAUT-ROADMAP-HISTORY.md#phase-3a-gnome-wayland-physical-acceptance--passed-pending-manual-publication) |
| <a id="game-library-settings-relocation--accepted-pending-manual-publication"></a>Game Library Settings relocation — accepted; pending manual publication | [Archive](ARGONAUT-ROADMAP-HISTORY.md#game-library-settings-relocation--accepted-pending-manual-publication) |
| <a id="user-confirmed-settings-physical-acceptance--passed"></a>User-confirmed Settings physical acceptance — passed | [Archive](ARGONAUT-ROADMAP-HISTORY.md#user-confirmed-settings-physical-acceptance--passed) |
| <a id="managed-library-forget-correction--historical-implementation-checkpoint"></a>Managed Library Forget correction — historical implementation checkpoint | [Archive](ARGONAUT-ROADMAP-HISTORY.md#managed-library-forget-correction--historical-implementation-checkpoint) |
| <a id="authority-sources-and-status-vocabulary"></a>Authority, sources, and status vocabulary | [Archive](ARGONAUT-ROADMAP-HISTORY.md#authority-sources-and-status-vocabulary) |
| <a id="a-baseline--completed-foundation"></a>A. Baseline / completed foundation | [Archive](ARGONAUT-ROADMAP-HISTORY.md#a-baseline--completed-foundation) |
| <a id="b-stabilization--spit-shine--do-first"></a>B. Stabilization / spit-shine — do first | [Archive](ARGONAUT-ROADMAP-HISTORY.md#b-stabilization--spit-shine--do-first) |
| <a id="1-p0--streamingnavigation-permanent-hang"></a>1. P0 — streaming/navigation permanent hang | [Archive](ARGONAUT-ROADMAP-HISTORY.md#1-p0--streamingnavigation-permanent-hang) |
| <a id="2-credential--saved-network-connection-ux"></a>2. Credential / saved-network-connection UX | [Archive](ARGONAUT-ROADMAP-HISTORY.md#2-credential--saved-network-connection-ux) |
| <a id="3-device-details--connection-profile-ux"></a>3. Device Details / connection-profile UX | [Archive](ARGONAUT-ROADMAP-HISTORY.md#3-device-details--connection-profile-ux) |
| <a id="4-global-headernavigation-cleanup"></a>4. Global header/navigation cleanup | [Archive](ARGONAUT-ROADMAP-HISTORY.md#4-global-headernavigation-cleanup) |
| <a id="5-contextual-operation-statuscancellation"></a>5. Contextual operation status/cancellation | [Archive](ARGONAUT-ROADMAP-HISTORY.md#5-contextual-operation-statuscancellation) |
| <a id="6-packaging-spit-shine"></a>6. Packaging spit-shine | [Archive](ARGONAUT-ROADMAP-HISTORY.md#6-packaging-spit-shine) |
| <a id="c-files--storage-ux"></a>C. Files / storage UX | [Archive](ARGONAUT-ROADMAP-HISTORY.md#c-files--storage-ux) |
| <a id="d-shared-argonaut-file-picker--reusable-component"></a>D. Shared Argonaut file picker — reusable component | [Archive](ARGONAUT-ROADMAP-HISTORY.md#d-shared-argonaut-file-picker--reusable-component) |
| <a id="e-drives-redesign"></a>E. Drives redesign | [Archive](ARGONAUT-ROADMAP-HISTORY.md#e-drives-redesign) |
| <a id="f-streams--stability-then-interaction"></a>F. Streams — stability then interaction | [Archive](ARGONAUT-ROADMAP-HISTORY.md#f-streams--stability-then-interaction) |
| <a id="g-ultimate-menu-redesign--major-category-not-spit-shine"></a>G. Ultimate Menu redesign — major category, not spit-shine | [Archive](ARGONAUT-ROADMAP-HISTORY.md#g-ultimate-menu-redesign--major-category-not-spit-shine) |
| <a id="1-firmwarehardware-capability-investigation--first-engineering-phase"></a>1. Firmware/hardware capability investigation — first engineering phase | [Archive](ARGONAUT-ROADMAP-HISTORY.md#1-firmwarehardware-capability-investigation--first-engineering-phase) |
| <a id="2-led-safety-investigation--p0-device-safety-gate"></a>2. LED safety investigation — P0 device-safety gate | [Archive](ARGONAUT-ROADMAP-HISTORY.md#2-led-safety-investigation--p0-device-safety-gate) |
| <a id="3-treeproperty-sheet-redesign--settled-direction"></a>3. Tree/property-sheet redesign — settled direction | [Archive](ARGONAUT-ROADMAP-HISTORY.md#3-treeproperty-sheet-redesign--settled-direction) |
| <a id="4-led-enhancements--later-within-redesign"></a>4. LED enhancements — later within redesign | [Archive](ARGONAUT-ROADMAP-HISTORY.md#4-led-enhancements--later-within-redesign) |
| <a id="h-machine--global-power-controls"></a>H. Machine / global power controls | [Archive](ARGONAUT-ROADMAP-HISTORY.md#h-machine--global-power-controls) |
| <a id="i-test-lab--developer-mode"></a>I. Test Lab / Developer Mode | [Archive](ARGONAUT-ROADMAP-HISTORY.md#i-test-lab--developer-mode) |
| <a id="j-sidjuke"></a>J. SIDJuke | [Archive](ARGONAUT-ROADMAP-HISTORY.md#j-sidjuke) |
| <a id="k-game-library"></a>K. Game Library | [Archive](ARGONAUT-ROADMAP-HISTORY.md#k-game-library) |
| <a id="l-cartridge-tools--separate-feature-category"></a>L. Cartridge Tools — separate feature category | [Archive](ARGONAUT-ROADMAP-HISTORY.md#l-cartridge-tools--separate-feature-category) |
| <a id="m-later--deferred--including-recovered-existing-roadmap-items"></a>M. Later / deferred — including recovered existing roadmap items | [Archive](ARGONAUT-ROADMAP-HISTORY.md#m-later--deferred--including-recovered-existing-roadmap-items) |
| <a id="n-argonaut-offline-libraries-and-playback--planned-future-track"></a>N. ARGONAUT OFFLINE LIBRARIES AND PLAYBACK — PLANNED future track | [Archive](ARGONAUT-ROADMAP-HISTORY.md#n-argonaut-offline-libraries-and-playback--planned-future-track) |
| <a id="existing-foundations-and-proposed-reuse"></a>Existing foundations and proposed reuse | [Archive](ARGONAUT-ROADMAP-HISTORY.md#existing-foundations-and-proposed-reuse) |
| <a id="planned--offline-preparation-and-multiple-libraries"></a>PLANNED — offline preparation and multiple libraries | [Archive](ARGONAUT-ROADMAP-HISTORY.md#planned--offline-preparation-and-multiple-libraries) |
| <a id="planned--discovery-explicit-adoption-and-availability"></a>PLANNED — discovery, explicit adoption and availability | [Archive](ARGONAUT-ROADMAP-HISTORY.md#planned--discovery-explicit-adoption-and-availability) |
| <a id="planned--offline-game-library-and-external-vice"></a>PLANNED — offline Game Library and external VICE | [Archive](ARGONAUT-ROADMAP-HISTORY.md#planned--offline-game-library-and-external-vice) |
| <a id="planned--sid-music-library-and-external-vsid"></a>PLANNED — SID Music Library and external VSID | [Archive](ARGONAUT-ROADMAP-HISTORY.md#planned--sid-music-library-and-external-vsid) |
| <a id="planned--catalog-content-and-location-identities"></a>PLANNED — catalog, content and location identities | [Archive](ARGONAUT-ROADMAP-HISTORY.md#planned--catalog-content-and-location-identities) |
| <a id="planned--ui-concepts-not-enabled-actions"></a>PLANNED — UI concepts, not enabled actions | [Archive](ARGONAUT-ROADMAP-HISTORY.md#planned--ui-concepts-not-enabled-actions) |
| <a id="proposed-development-sequence--all-planned-separate-approval-per-slice"></a>Proposed development sequence — all PLANNED, separate approval per slice | [Archive](ARGONAUT-ROADMAP-HISTORY.md#proposed-development-sequence--all-planned-separate-approval-per-slice) |
| <a id="unresolved-architecture-and-safety-decisions"></a>Unresolved architecture and safety decisions | [Archive](ARGONAUT-ROADMAP-HISTORY.md#unresolved-architecture-and-safety-decisions) |
| <a id="design-principles"></a>Design principles | [Archive](ARGONAUT-ROADMAP-HISTORY.md#design-principles) |
| <a id="open-investigations-and-review-reconciliation"></a>Open investigations and review reconciliation | [Archive](ARGONAUT-ROADMAP-HISTORY.md#open-investigations-and-review-reconciliation) |
| <a id="pa-51c-offline-implementation-checkpoint"></a>PA-5.1C offline implementation checkpoint | [Archive](ARGONAUT-ROADMAP-HISTORY.md#pa-51c-offline-implementation-checkpoint) |
