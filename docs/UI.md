# Argonaut UI design and audit — 1.10 spit-shine

## 1. Purpose and scope

This permanent design and audit record supports visual consistency, usability,
and release readiness for Argonaut 1.10. UI-00 and UI-01 authorize documentation
only; UI-01 additionally authorizes read-only structural source inspection.
Implementation, device contact, publication, commits and pushes are not authorized.
The [roadmap](ARGONAUT-ROADMAP.md) retains its priorities, historical evidence and
release gates. Complete the interface audit before implementation, then deliver
small, independently testable slices.

Major Ultimate Menu redesign and new Game Library features are outside the
initial spit-shine scope. Existing functionality and keyboard access must survive.

Tracking statuses:

- **Proposed** — requires review; not an approved design or implementation.
- **Approved** — user-approved design direction; implementation remains pending.
- **Implemented** — change exists with recorded verification; acceptance pending.
- **Accepted** — reviewed acceptance evidence meets the applicable requirements.

Design approval alone never establishes implementation or acceptance. No new
spit-shine item is Implemented or Accepted in this document. Stable finding IDs
are UI-01 through UI-25; section 5 records their established meanings and all
53 provisional UI-26–UI-78 screenshot-review references.
Decision references below are stable descriptive anchors, not replacement finding IDs.
Section 9 preserves the UI-00 documentation reconciliation. Sections 10–12 add
the UI-01 first-pass consolidation, source inspection and implementation plan.
The task label UI-01 does not assign a new meaning to established finding UI-01.

## 2. Design principles

The following direction is **Approved**:

- Native GNOME/GTK appearance with subtle Argonaut branding.
- Consistent typography, spacing, buttons, icons and status presentation.
- Consistent disabled, loading, warning and error states without unnecessary decoration.
- Preserve existing functionality and keyboard accessibility.
- Prefer shared styling components over duplicated per-tab CSS.
- Avoid unnecessary gradients, shadows and decorative elements.
- Preserve the established dual-pane Files layout.
- Inspect the complete interface before implementation.
- Implement changes in small, independently testable slices.
- Keep major Ultimate Menu redesign and new Game Library features outside the
  initial spit-shine scope.

## 3. Screen audit inventory

UI-01 reports a completed first-pass visual audit of the twelve screen areas
below. The supplied UI-01 brief is the evidence source for coverage and design
direction. The original 78-entry screenshot-review mapping is now supplied and
reconciled in section 5; the underlying screenshot images were not supplied. This consolidation does not claim independent screenshot
inspection, new runtime verification or complete interaction/state coverage.

| Area | First-pass coverage reported by user | Remaining coverage |
| --- | --- | --- |
| Main application header | Covered | Connection/recovery transitions and keyboard routes. |
| Files | Connected and disconnected covered | Storage failures, menus, keyboard and operation states. |
| Settings → General | Covered | Autosave/Undo, chooser interactions, scale qualification. |
| Settings → Device Details | Covered | Credential state transitions, expansion and profile/discovery behavior. |
| Settings → About | Covered | Resize, links, selectable build identity and keyboard navigation. |
| Settings → Game Library | Covered | Partial discovery, unavailable states and selection/Forget interactions. |
| Ultimate Menu | Covered | Dialogs, staged edits, capability dependencies and safety investigations. |
| Drives | Covered | State transitions, write-mode preservation, image selection and confirmation. |
| SID Jukebox / SIDJuke | Covered | Playback review, subtunes, playlist interaction and duration uncertainty. |
| Streams | Covered | Hang diagnosis, resize/scale, stopped/running/error states and input. |
| Main Game Library | Covered | Selection, review/launch, Retry Load and import-planning state transitions. |
| Test Lab | Covered | Developer entry point, channel gating, diagnostics and lifecycle. |
| Confirmation/error dialogs, context menus, progress, tooltips and keyboard | Not comprehensively inspected | Targeted audit across changed surfaces before implementation/acceptance. |
| Loading, warning and error states across all screens | Not comprehensively inspected | Verify per-surface state matrix; Files connected/disconnected coverage is not universal coverage. |

Do not infer additional screenshot details, screenshot dates or completed
interaction tests from the supplied summary. Section 10 records screen decisions
with brief-section provenance; section 5 retains the supplied original review IDs.

## 4. Approved design decisions

### Global controls and status

**Approved:** remove permanent blue active-file-pane outlines while retaining
keyboard focus indicators. Use consistent GTK button hierarchy and styling,
with Argonaut blue as a restrained accent. Improve disconnected and empty states.

**Approved UI-02B.1b:** Remove manual Reconnect from the global header. Preserve automatic recovery and internal reconnect mechanisms.

The header contains one contextual Connect/Disconnect control, Settings, and
Ultimate Power, in that order. Do not relocate manual Reconnect to another menu
or control. Preserve connection/session semantics, identity and credential
checks, keyboard access, foreground admission, and recovery protections.

**Superseded:** UI-00/UI-02B.1 retained Reconnect as a secondary menu action.
UI-02B.1b supersedes that presentation decision only; internal reconnect and
recovery contracts remain unchanged. Visual acceptance remains pending.

Retain the Commodore Chicken Lips icon as the compact Ultimate Power control.
Preserve existing Reset/Reboot actions, tooltip, keyboard access and confirmation
behavior. This work does not authorize changes to power-action safety contracts.

Restyle the existing B5 status presentation as a visually distinct status bar and
separate overall device connection state from operation-specific warnings.
Preserve existing B5 cancellation, progress, error, uncertain-outcome and
foreground-job behavior. Visual redesign must not weaken lifecycle or
device-operation safety; detailed contracts remain in the sources linked in section 9.

**Approved Test Lab navigation:** relocate its entry point to
**Settings → Developer → Open Test Lab** and remove the normal top-level Test Lab
tab in both Stable and Development. Development retains always-available Test Lab
with no additional restrictions. Stable retains existing restart/enablement gating;
the new entry point must not bypass it. Preserve all Test Lab functionality,
diagnostics and regression capabilities, including existing channel isolation.
Treat relocation as a separately tested functional change when implementation is
authorized. This approval is documentation-only; no navigation change is implemented.

### Files

**Approved:** preserve the dual-pane layout and selected-file highlighting;
remove permanent blue pane outlines while preserving keyboard focus. Improve
pane headings and active-state presentation. Visually group navigation and
file-operation toolbar controls, standardize storage shortcut styling, and
improve folder/file icon alignment. Preserve filename tooltips and keyboard access.
Improve inaccessible-storage status reporting.

Supplied physical observation: Beige connected successfully and `/USB2` was
browsable. Clicking an unpopulated SD storage shortcut produced:

> The C64U path is missing or inaccessible. Refresh and check the path.

This was a legitimate path-accessibility response, not evidence of a disconnected
C64U. Proposed presentation must identify the affected storage root without
misrepresenting overall connection state. Exact wording remains **Proposed**;
the observed SD root was not specified and must not be invented.

### Settings — General

**Approved:** organize preferences into clear groups; standardize persistent
preference switches and action-specific checkboxes; improve typography, spacing
and dialog sizing. Improve media folder selection controls and reorganize Undo
and Restore Defaults. Keep existing automatic-save and Undo semantics.

Review Instant Replay dependencies before implementing its previously planned
removal. This document does not establish that replay caused the streaming hang
or that removal resolves it; preserve the roadmap's diagnosis and release gates.

### Preview scaling

**Approved:** replace the existing plus/minus control with a graduated slider,
clearly label major scale intervals and preserve preference persistence.
The range **100%–600%** and **25% increments** are **Proposed**, subject to renderer
verification. The exact maximum and GTK logical-pixel behavior remain unresolved.
Validate on a 4K monitor with 150% desktop scaling. Preserve aspect ratio and
avoid unintended cropping. Add Fit to Window as a separate Streams improvement;
its detailed design and implementation boundary require review after inspection.

### Settings — Device Details

**Accepted UI-DD.1/UI-DD.1a layout:** keep Saved Connections at the top, followed
by the selected profile and accessible connection controls. Always visible:

- Selected profile and Hostname/IP.
- Password field and visibility control.
- Test and Connect actions.
- Profile management actions.

Provide three independently expandable sections (superseding the original two-section direction):

| Section | Default | Contents |
| --- | --- | --- |
| Advanced Connection Settings | Collapsed | Existing REST and FTP ports, defaults 80 and 21, with custom overrides. |
| Hardware & REST Information | Collapsed | Serial number, saved device ID, box model, firmware-reported C64U model, notes and relevant hardware details. |
| Network Discovery | Collapsed | Discover, subnet input, Scan Subnet and associated feedback. |

All three sections start collapsed. Any combination can expand independently;
Settings reuse, tab changes and Keep editing retain expansion. Actual destruction
and recreation restore collapsed defaults. Reduce unnecessary window height and provide scrolling when expanded
content exceeds available space.

Preserve the distinction between editable box label and firmware-reported model.
Preserve saved Ethernet/Wi-Fi profile distinctions, device identity and credential
contracts, Development-mode session-only passwords, and Test versus Connect
semantics. Do not introduce implicit password persistence. Existing discovery
behavior and saved-connection semantics remain contractual constraints; see
[Device Details stabilization](DEVICE-DETAILS-STABILIZATION.md).

## 5. UI punch list and original-to-consolidated mapping

Historical source: user-supplied **“Argonaut UI-01 — Original Screenshot Audit
Mapping”**, attached with **“Resolve Final Audit HOLD”**. Its seven original
sections identify Initial Audit (01–25), Settings/About and Game Library (26–34),
Drives (35–43), SIDJuke (44–51), Streams (52–61), Main Game Library (62–70), and
Test Lab (71–78). The original finding text is reproduced below for all 78 IDs.
The source supplies no individual screenshot filenames, dates or coordinates;
none are invented. It is historical review evidence, not automatic approval.

UI-01–UI-25 now replace the former empty reservations with their supplied established
meanings, verbatim. UI-26–UI-78 remain provisional screenshot-review references,
not newly ratified final finding numbers. The “Work reference” column maps each
source ID to consolidated scope: four exact overlaps point to an established ID;
all other IDs retain distinct scope. No number is reassigned or erased. There are
**78 source entries and 74 distinct work references**, including provisional ones.
The seven documentation candidates in section 9 remain separately unnumbered.

**Status basis:** Approved means the current direction is explicitly supported by
UI-00, the UI-01 screen decisions/retained roadmap direction, or the final HOLD
resolution. Proposed means the screenshot recommendation lacks explicit approval
at that specificity. Approval of a broader goal is not approval of a collapsible
mechanism, precise copy or extra restructuring. No new task is Implemented or
Accepted. UI-36 retains its original title as superseded evidence; only its revised
three-state direction is Approved. Exact slider maximum, layout and copy remain
Proposed where noted. UI-59/60 are approved future direction, not release scope.

Priority and slice assignments are **Proposed planning**, independent of approval:
P0 = existing streaming release gate; P1 = safety/preservation review; P2 = polish;
P3 = deferred/future work. See section 12 for release classifications and dependencies.
Acceptance notes preserve detailed contracts by reference to sections 7, 9 and 11.

| Original ID | Original finding (verbatim) | Area | Work reference | Status of current direction | Priority | Proposed slice | Current change / acceptance notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| UI-01 | Remove permanent blue file-pane outline | Shared / Files / header | UI-01 | Approved | P2 | UI-C1 | Remove permanent border only; preserve focus and native selection. |
| UI-02 | Redesign header connection controls | Shared / Files / header | UI-02 | Approved | P2 | UI-B1 | One primary Connect/Disconnect; no manual Reconnect; preserve automatic recovery and session rules. |
| UI-03 | Introduce consistent status bar | Shared / Files / header | UI-03 | Approved | P1 | UI-B2 | Restyle B5; preserve cancellation, progress, errors, uncertainty and foreground ownership. |
| UI-04 | Standardize buttons, typography, spacing | Shared / Files / header | UI-04 | Approved | P2 | UI-A1 | Shared visual roles only; do not unify operation logic. |
| UI-05 | Improve active/inactive file-pane styling | Shared / Files / header | UI-05 | Approved | P2 | UI-C1 | Related to UI-01 but retain independent active-pane clarity requirement. |
| UI-06 | Refine disconnected empty state | Shared / Files / header | UI-06 | Approved | P2 | UI-C1 | Files disconnected state; not universal error-state coverage. |
| UI-07 | Move Test Lab into Developer Mode | Shared / Files / header | UI-07 | Approved | P2 | UI-F Test Lab-1 | Settings → Developer → Open Test Lab; both channels lose normal tab, availability unchanged. |
| UI-08 | Standardize icon appearance | Shared / Files / header | UI-08 | Approved | P2 | UI-A1 | Shared icon language; retain accessible names and meanings. |
| UI-09 | Ultimate Power / Chicken Lips button styling and placement | Shared / Files / header | UI-09 | Approved | P2 | UI-B1 | Keep artwork, tooltip, keyboard access and qualified Reset/Reboot. |
| UI-10 | Group General Settings into clear sections | Settings General | UI-10 | Approved | P2 | UI-D1 | Retain autosave and hidden preferences. |
| UI-11 | Standardize switches and checkboxes | Settings General | UI-11 | Approved | P2 | UI-D1 | Persistent preferences versus action choices; credential UNKNOWN state is an exception. |
| UI-12 | Remove Instant Replay after dependency review | Settings General | UI-12 | Approved | P1 | UI-F Streams-2 | Dependency/stability review first; preserve capture/recording and independently verify hang. |
| UI-13 | Improve Preview Scale control | Settings General | UI-13 | Approved | P2 | UI-F Streams-3 | Shared General/Streams control; 100–600% and 25% steps remain Proposed pending qualification. |
| UI-14 | Refine media folder selection rows | Settings General | UI-14 | Approved | P2 | UI-D1 | Preserve chooser, persistence and focus behavior. |
| UI-15 | Reorganize Undo / Restore Defaults | Settings General | UI-15 | Approved | P2 | UI-D1 | Retain Undo/defaults and hidden saved values. |
| UI-16 | Improve Settings dialog sizing and whitespace | Settings General | UI-16 | Approved | P2 | UI-D1/D2 | Cross-tab sizing/whitespace; keep UI-23 Device Details height concern separate. |
| UI-17 | Standardize Settings tab styling | Settings General | UI-17 | Approved | P2 | UI-D2 | Native tabs and page routes; not a new navigation contract. |
| UI-18 | Move Saved Connections to top | Device Details | UI-18 | Approved | P2 | UI-E1 | Presentation supersession only; saved profiles remain distinct. |
| UI-19 | Compact connection fields and actions | Device Details | UI-19 | Approved | P2 | UI-E1 | Preserve Test/Connect and endpoint/profile identity rules. |
| UI-20 | Collapsible Hardware Information | Device Details | UI-20 | Accepted | P2 | UI-E1 | Original finding retained verbatim; accepted UI-DD.1a title is Hardware & REST Information, one of three independent, initially collapsed sections. |
| UI-21 | Collapsible Network Discovery | Device Details | UI-21 | Approved | P2 | UI-E1 | Initially collapsed; preserve bounded discovery and feedback. |
| UI-22 | Improve credential presentation | Device Details | UI-22 | Proposed | P1 | UI-E1 | Specific presentation proposal; preserve credential matrix/UNKNOWN; no new persistence behavior. |
| UI-23 | Reduce unnecessary Device Details window height | Device Details | UI-23 | Approved | P2 | UI-E1 | Device Details height/scrolling; related to shared sizing without collapsing scope. |
| UI-24 | Standardize profile management buttons | Device Details | UI-24 | Approved | P2 | UI-E1 | Group New/Save/Delete; preserve explicit profile-save semantics. |
| UI-25 | Reduce inline instructional clutter | Device Details | UI-25 | Proposed | P2 | UI-E1 | Review which instructions may move; never remove safety or credential guidance. |
| UI-26 | Move About to final Settings tab | Settings About | UI-26 (provisional) | Approved | P2 | UI-D2 | About last; update named/positional navigation routes together. |
| UI-27 | Refine About typography, alignment, metadata | Settings About | UI-27 (provisional) | Approved | P2 | UI-D2 | Retain artwork ratio and accurate selectable version/build/platform; style links/copyright. |
| UI-28 | Standardize Settings dialog sizing across tabs | Settings About | UI-16 (alias; original retained) | Approved | P2 | UI-D1/D2 | Exact shared-sizing overlap with UI-16; preserve all Settings-tab coverage. |
| UI-29 | Compact current-library summary | Settings Game Library | UI-29 (provisional) | Approved | P2 | UI-D3 | Settings summary; related to UI-62 main summary, separate interactions. |
| UI-30 | Collapsible technical identifiers | Settings Game Library | UI-30 (provisional) | Proposed | P2 | UI-D3 | Secondary details approved; collapsible mechanism remains Proposed. |
| UI-31 | Group library-management buttons | Settings Game Library | UI-31 (provisional) | Approved | P2 | UI-D3 | Group discovery/selection/Forget; preserve Create and host-only Forget contracts. |
| UI-32 | Distinct discovery empty/warning states | Settings Game Library | UI-32 (provisional) | Approved | P2 | UI-D3 | Retain partial-discovery warnings; absence is not inaccessible storage. |
| UI-33 | Reduce redundant explanatory text | Settings Game Library | UI-33 (provisional) | Proposed | P2 | UI-D3 | Specific text reduction remains Proposed; retain safety/discovery explanations. |
| UI-34 | Improve library status and metadata hierarchy | Settings Game Library | UI-34 (provisional) | Approved | P2 | UI-D3 | Settings metadata hierarchy; relates to UI-29/30 without removing distinctions. |
| UI-35 | Replace Turn On/Off buttons with switch | Drives | UI-35 (provisional) | Approved | P2 | UI-F Drives-2 | Preserve reviewed action and actual drive state; do not bypass safety on toggle. |
| UI-36 | Replace write-protect dropdown with checkbox | Drives | UI-36 (provisional) | Approved | P1 | UI-F Drives-2 | Original checkbox proposal superseded. Approved compact three-state selector; see source terminology below. |
| UI-37 | Rename Mount & Run to Run | Drives | UI-37 (provisional) | Approved | P2 | UI-F Drives-2 | Label only; Run retains temporary-copy/reset/interruption semantics. |
| UI-38 | Restructure Drive A/B into consistent cards | Drives | UI-38 (provisional) | Approved | P2 | UI-F Drives-1 | A/B share presentation; preserve drive-specific capabilities. |
| UI-39 | Improve mounted-image and drive-status hierarchy | Drives | UI-39 (provisional) | Proposed | P2 | UI-F Drives-1 | Specific hierarchy proposal within approved card direction; no invented status. |
| UI-40 | Group secondary drive operations | Drives | UI-40 (provisional) | Proposed | P2 | UI-F Drives-1 | Grouping proposal; keep Reset/Eject/type operations and confirmations reachable. |
| UI-41 | Simplify image selection and explanatory text | Drives | UI-41 (provisional) | Proposed | P2 | UI-F Drives-1 | Retain shared C64U-only picker; text simplification proposed, no local upload implied. |
| UI-42 | Investigate ROM/drive-type control placement | Drives | UI-42 (provisional) | Approved | P1 | UI-F Drives-2 investigation | Investigation approved, not removal/relocation of ROM/type functions. |
| UI-43 | Improve operation-specific status feedback | Drives | UI-43 (provisional) | Proposed | P2 | UI-F Drives-1 + UI-B2 | Screen-specific feedback proposal; B5 remains sole foreground presenter. |
| UI-44 | Rename user-facing tab to SIDJuke | SIDJuke | UI-44 (provisional) | Approved | P2 | UI-F SID-1 | User-facing rename only; no internal rename requirement. |
| UI-45 | Simplify SID library entries | SIDJuke | UI-45 (provisional) | Proposed | P2 | UI-F SID-1 | Entry-level changes Proposed; approved metadata simplification does not authorize arbitrary row changes. |
| UI-46 | Group playlist management actions | SIDJuke | UI-46 (provisional) | Approved | P2 | UI-F SID-1 | Keep selection distinct from playback cursor and preserve playlist actions. |
| UI-47 | Give Now Playing a dedicated panel | SIDJuke | UI-47 (provisional) | Approved | P2 | UI-F SID-1 | Style existing Now Playing section; no second playback owner. |
| UI-48 | Relocate subtune controls | SIDJuke | UI-48 (provisional) | Approved | P2 | UI-F SID-1 | Relocation approved; exact placement and subtune targeting require design review. |
| UI-49 | Refine search/filter toolbar | SIDJuke | UI-49 (provisional) | Proposed | P2 | UI-F SID-1 | Specific toolbar proposal; retain filters/search behavior. |
| UI-50 | Improve disabled-state guidance | SIDJuke | UI-50 (provisional) | Proposed | P2 | UI-F SID-1 | Specific guidance copy Proposed; preserve enabled-state semantics and review requirements. |
| UI-51 | Preserve explicit playback review and status semantics | SIDJuke | UI-51 (provisional) | Approved | P1 | UI-F SID-1 + UI-G1 | Command accepted is not audible verification; preserve duration uncertainty. |
| UI-52 | Responsive preview viewport | Streams | UI-52 (provisional) | Approved | P2 | UI-F Streams-3 | Responsive viewport without changing media lifecycle. |
| UI-53 | Fit to Window mode | Streams | UI-53 (provisional) | Approved | P2 | UI-F Streams-3 | Fit to Window without cropping/aspect-ratio loss; separate from manual scale. |
| UI-54 | Graduated manual scale slider | Streams | UI-13 (alias; original retained) | Approved | P2 | UI-F Streams-3 | Alias of UI-13; retain Streams consumer as well as General. |
| UI-55 | Remove Instant Replay | Streams | UI-12 (alias; original retained) | Approved | P1 | UI-F Streams-2 | Alias of UI-12; inherits dependency/stability prerequisites. |
| UI-56 | Group preview/recording controls | Streams | UI-56 (provisional) | Approved | P2 | UI-F Streams-4 | Group preview/recording/audio; preserve session and action semantics. |
| UI-57 | Improve stopped-preview empty state | Streams | UI-57 (provisional) | Approved | P2 | UI-F Streams-3 | Intentional stopped state, distinct from disconnected/error. |
| UI-58 | Reorganize BASIC input | Streams | UI-58 (provisional) | Approved | P2 | UI-F Streams-4 | Group existing BASIC controls; preserve Return/send/focus, no new remote-input behavior. |
| UI-59 | Integrate remote-control interface | Streams | UI-59 (provisional) | Approved | P3 | Future Streams controls | Approved roadmap direction, separately scoped future feature; not polish authorization. |
| UI-60 | Add C64 keyboard overlay | Streams | UI-60 (provisional) | Approved | P3 | Future C64 overlay | Approved roadmap direction, separately scoped future feature; escapable keyboard capture. |
| UI-61 | Verify streaming status and stability | Streams | UI-61 (provisional) | Approved | P0 | UI-F Streams-1 + UI-G1 | P0 hang remains release gate; status is truthful and independent of replay assumptions. |
| UI-62 | Compact Game Library summary | Main Game Library | UI-62 (provisional) | Approved | P2 | UI-F Library-1 | Main-view summary; coordinate with UI-29, retain separate view scope. |
| UI-63 | Selectable, styled game rows | Main Game Library | UI-63 (provisional) | Approved | P2 | UI-F Library-1 | Style existing selection; do not change identity-bound launch eligibility. |
| UI-64 | Place launch action near selected game | Main Game Library | UI-64 (provisional) | Approved | P2 | UI-F Library-1 | Keep explicit Review & Launch then Launch and cancellation. |
| UI-65 | Contextual Retry Load | Main Game Library | UI-65 (provisional) | Approved | P2 | UI-F Library-1 | Contextual retry of loading only; never auto-retry a consequential launch. |
| UI-66 | Compact Library Settings action | Main Game Library | UI-66 (provisional) | Approved | P2 | UI-F Library-1 | Secondary Library Settings action; preserve explicit navigation. |
| UI-67 | Improve Add Games placement and wording | Main Game Library | UI-67 (provisional) | Approved | P2 | UI-F Library-1 | Clear planning versus actual import; exact placement remains design detail. |
| UI-68 | Collapsible technical library details | Main Game Library | UI-68 (provisional) | Proposed | P2 | UI-F Library-1 | Technical-detail collapse remains Proposed; distinct main-view counterpart of UI-30. |
| UI-69 | Improve empty/loading/error states | Main Game Library | UI-69 (provisional) | Approved | P2 | UI-F Library-1 | Main-view state coverage; distinct from Settings discovery UI-32. |
| UI-70 | Preserve verified launch and import safety | Main Game Library | UI-70 (provisional) | Approved | P1 | UI-F Library-1 + UI-G1 | Preserve managed D64 safety, no managed CRT expansion or fabricated import success. |
| UI-71 | Move Test Lab to Developer entry point | Test Lab | UI-07 (alias; original retained) | Approved | P2 | UI-F Test Lab-1 | Alias of UI-07, including Stable gating and always-available Development. |
| UI-72 | Separate Diagnostics, History, AI & Bridge, Automation | Test Lab | UI-72 (provisional) | Proposed | P3 | Deferred developer workspace | Four-section workspace remains a Proposed deferred redesign, not navigation work. |
| UI-73 | Improve diagnostic result presentation | Test Lab | UI-73 (provisional) | Proposed | P3 | Deferred developer workspace | Deferred presentation proposal; deterministic verdicts and evidence unchanged. |
| UI-74 | Group C64 AI bridge controls | Test Lab | UI-74 (provisional) | Proposed | P3 | Deferred developer workspace | Deferred grouping proposal; preserve AI bridge privacy and consequential action boundaries. |
| UI-75 | Consolidate automation controls | Test Lab | UI-75 (provisional) | Proposed | P3 | Deferred developer workspace | Deferred consolidation proposal; preserve opt-in/channel/service lifecycle distinctions. |
| UI-76 | Improve saved-run browsing | Test Lab | UI-76 (provisional) | Proposed | P3 | Deferred developer workspace | Deferred browsing proposal; retain reports/history and privacy. |
| UI-77 | Improve AI explanation/evidence association | Test Lab | UI-77 (provisional) | Proposed | P3 | Deferred developer workspace | Deferred association proposal; AI cannot alter verdicts or obscure source evidence. |
| UI-78 | Standardize Test Lab actions and spacing | Test Lab | UI-78 (provisional) | Approved | P2 | UI-A1 + UI-F Test Lab-1 | Shared styling approved; no approval for broad developer-workspace redesign. |

### Resolved overlaps and preserved distinct requirements

- **UI-28 → UI-16:** one cross-tab Settings sizing/whitespace task; retain the
  About/Game Library review provenance. UI-23 is still the Device Details-specific
  height/scrolling requirement, not an alias that loses its scope.
- **UI-54 → UI-13:** one shared graduated manual-scale task spanning General and
  Streams; UI-52 responsive viewport and UI-53 Fit to Window remain distinct.
- **UI-55 → UI-12:** one replay-removal task, including dependency/stability review
  and General/Streams surfaces; UI-61 P0 stability remains a separate gate.
- **UI-71 → UI-07:** one Test Lab navigation task, preserving both review references,
  channel gating and all capabilities. UI-72–77 are separate deferred proposals.
- Keep **UI-01 / UI-05** (border versus active/inactive presentation), **UI-29 / UI-62**
  (Settings versus main summary), **UI-30 / UI-68** (technical details on different
  screens), **UI-32 / UI-69** (discovery versus main loading states), and **UI-03 /
  UI-43 / UI-61** (global presenter versus feature feedback/stability) distinct.
  Shared styling is not permission to merge state ownership or safety boundaries.
- UI-04/UI-08 provide common roles across all screens; UI-78 applies those roles
  to Test Lab. Retain that screen-specific coverage rather than erase it as a duplicate.
- Mapping consolidation is complete for the supplied evidence; no additional final
  IDs are needed. Proposed items still require design approval, not identifier repair.

## 6. Proposed implementation slices

The UI-A–UI-G groups below are retained as the original planning taxonomy.
Section 12 refines them into bounded sub-slices without changing their meanings.

These are **Proposed** planning groups, not implementation authorization. Revise
boundaries after the full audit identifies shared components. Priorities and
finding-to-slice assignments are now recorded in section 5 and remain planning
recommendations for implementation-plan review.

| Slice | Planning scope |
| --- | --- |
| UI-A | Shared GTK styling foundation: shared typography, spacing, buttons, icons and restrained accents. |
| UI-B | Global header and status bar: contextual connection control, power control preservation and distinct connection/operation status. |
| UI-C | Files tab polish: panes, grouped toolbars, shortcuts, alignment and storage feedback. |
| UI-D | Settings / General: grouping, controls, media folders, Undo/Defaults and verified preview scaling. |
| UI-E | Device Details restructuring: always-visible connection controls and independent collapsible sections. |
| UI-F | Remaining tab-specific improvements after inspection; separate Streams Fit to Window and separately tested Test Lab relocation. |
| UI-G | Accessibility, regression and release acceptance. |

Instant Replay dependency review must precede its previously planned removal;
its functional work must retain the roadmap's separate diagnosis and testing
requirements rather than being treated as a cosmetic change.

## 7. Acceptance requirements

Before implementation, complete the relevant remaining interaction/state audit,
use the reconciled finding inventory in section 5, review proposals and
shared-component boundaries, and obtain
separate implementation authorization. For each later slice record the baseline,
changed components, verification evidence, outstanding issues and reviewer decision.

- Verify native GTK presentation, consistent hierarchy/spacing and restrained branding.
- Verify pointer and keyboard workflows, visible focus, selected-file highlighting,
  tooltips, context menus and accessible controls across applicable states.
- Verify dual-pane navigation, file operations and shortcut behavior remain intact.
- Verify inaccessible storage identifies the affected root without a false
  disconnected-device state; keep operation warnings distinct from connection state.
- Verify contextual Connect/Disconnect and internal reconnect and automatic recovery routes,
  identity binding and stale-settings protections. Preserve power actions,
  tooltip, keyboard access and confirmations.
- Verify General automatic-save, preference persistence, Undo and Restore Defaults
  semantics; review replay dependencies and the unresolved streaming diagnosis.
- Verify slider support/range/increments and major labels, 4K at 150% desktop
  scaling, GTK logical-pixel behavior, aspect ratio and absence of unwanted cropping.
  Verify Streams Fit to Window separately.
- Verify Device Details always-visible controls, independent expansion, persistence
  while open, collapsed defaults on reopening and scrolling on smaller windows.
  Verify Ethernet/Wi-Fi distinctions, editable box versus firmware model, identity,
  credential and discovery contracts, Test/Connect semantics and session-only
  Development passwords. No implicit password persistence.
- Test Test Lab relocation separately as a functional change, including access
  through Settings → Developer → Open Test Lab and removal of the normal top-level
  tab in both channels. Verify Development remains always available without new
  restrictions, Stable restart/enablement gating is not bypassed, and all diagnostics,
  functionality and regression capabilities remain intact.
- Complete applicable connected, disconnected, empty, loading and error-state
  checks and the roadmap's existing regression and release gates.

No physical acceptance is asserted or authorized by UI-00. Future device-based
validation requires its own authorization. Design approval, documentation review
and successful implementation tests are distinct from release acceptance.

## 8. Audit history and outstanding decisions

| Record | Evidence / disposition |
| --- | --- |
| UI-00 — documentation establishment, 2026-10-17 | Supplied design direction transcribed; no fresh visual audit, UI implementation or device contact. |
| Baseline | HEAD and local `origin/development` both `c1f6e0db7c47702834856d3898a88f07560a3f31`; working tree clean before edits. Local reference verification only; no fetch. |
| Original UI-01–UI-25 inventory | Missing during UI-00, so reservations were retained rather than guessed. The final UI-01 HOLD resolution supplies all 78 original entries; section 5 now preserves the established 01–25 meanings, provisional 26–78 references and four explicit aliases. |
| Earlier header history | Roadmap B4 records separate Reconnect/Disconnect controls and prior acceptance. The new contextual control is Approved future direction; earlier behavior and acceptance remain historical evidence. Preserve recovery and stale-settings protections. |
| Earlier Device Details history | Roadmap B3 records Saved Network Connections near the bottom and prior layout acceptance. The original future direction is now superseded by accepted UI-DD.1/UI-DD.1a: Saved Connections first and three independent expanders. Earlier B3 acceptance remains historical evidence. |
| Scaling | 100%–600% and 25% steps remain Proposed; renderer range, maximum and GTK logical pixels require verification. |
| Presentation details | Storage-warning wording, exact preference groupings, status-bar layout remain design details. Primary Connect/Disconnect without manual Reconnect (UI-02B.1b) and preservation of B5 behavior are Approved. |
| Functional boundaries | Test Lab placement and channel behavior are Approved as resolved below. Streams Fit to Window details and Instant Replay dependency review remain outstanding. |
| UI-00 reconciliation resolution, 2026-10-17 | User resolved the Test Lab, connection-control and status-bar questions. Documentation-only approval; no implementation or acceptance claimed. Preserve UI-01–UI-25 and all seven unnumbered candidates, with final candidate IDs deferred until the remaining visual audit is complete. |
| Remaining audit | UI-01 reports first-pass coverage of twelve screen areas. Section 3 distinguishes remaining interaction/state coverage; original review IDs are reconciled in section 5; underlying screenshots and uninspected interactions are not claimed as independently verified. |

Maintain original finding IDs as evidence accumulates. Record status transitions
only with corresponding design approval, implementation evidence or acceptance.
Publication remains subject to approval after documentation validation.

## 9. Documentation Reconciliation

### Scope, authority and classification

UI-00 amendment, 2026-10-17: searched all **40 tracked Markdown files**, including
historical and packaging documents, for UI requirements, decisions, acceptance,
and unresolved interface work; read relevant sections in context. This is a
repository-document inspection, not a fresh visual audit or application-code
verification. The untracked UI.md draft was reviewed separately and is not part
of the 40-file count. All seven specifically named source documents exist.
HEAD and local origin/development remain the UI-00 baseline. The only initial
working changes were the two expected UI-00 documentation files.

Authority boundaries are complementary, not an automatic conflict-resolution rule:

- **UI.md:** current UI design decisions, visual standards, audit and implementation tracking.
- **ARGONAUT-ROADMAP.md:** development priorities and release sequencing.
- **CURRENT-STATE.md:** implemented and accepted project state, with checkpoint limitations.
- **Feature documentation:** detailed functional, safety and technical contracts.

Classifications below mean **Current approved UI requirement**, **Implemented and
accepted behavior**, **Planned or proposed improvement**, **Historical or superseded
requirement**, or **Unresolved conflict requiring a decision**. These classifications
are separate from punch-list statuses. Referenced acceptance is existing evidence
at its stated scope, not new UI-00 acceptance. A document containing historical
checkpoints is not obsolete as a whole.

### Source-document inventory

Each row records inspection coverage and the sections relevant to reconciliation.
No source file was edited by this amendment.

| Source | Relevant sections / disposition |
| --- | --- |
| [README.md](../README.md) | Screenshots; Debian installation; platform installation — release-facing descriptions and older screenshots, not fresh audit evidence. |
| [docs/ARGONAUT-ROADMAP.md](ARGONAUT-ROADMAP.md) | B–K, M–N, Design principles, Open investigations — priorities, accepted checkpoints, current direction and deferred scope. |
| [docs/C64-AI-BRIDGE.md](C64-AI-BRIDGE.md) | C64-side AI bridge: first interface — separate AI explanation/bridge roles, private pairing and bounded device consequences. |
| [docs/C64U-FTP.md](C64U-FTP.md) | Boundary and ownership; Client operations; Slices 3A–3D; current consumer/closure checkpoints — preserve managed operations and uncertainty. |
| [docs/CURRENT-STATE.md](CURRENT-STATE.md) | Current Game Library State — PA-5.13 Published; B4–B6; C0–C4; Device Details; Known observations — scoped current acceptance and outstanding limitations. |
| [docs/DEVELOPER-MODE.md](DEVELOPER-MODE.md) | Developer Mode and Test Lab — Stable gating, restart, Development availability and service isolation. |
| [docs/DEVELOPMENT-TEST.md](DEVELOPMENT-TEST.md) | Historical 1.8-replay.3 record; Test checklist — replay, modality and platform evidence; not current release guidance. |
| [docs/DEVELOPMENT.md](DEVELOPMENT.md) | Local development — separate profiles/settings and device-operation scope. |
| [docs/DEVICE-DETAILS-STABILIZATION.md](DEVICE-DETAILS-STABILIZATION.md) | Credential behavior matrix; Persistence failure boundary; UNKNOWN correction; Discovery trace; Publication gate — detailed credential/discovery contract. |
| [docs/FTP-OWNERSHIP-CLOSURE.md](FTP-OWNERSHIP-CLOSURE.md) | Removed and retained surfaces; Verification and qualification — managed ownership closure, no new UI scope. |
| [docs/GAME-LIBRARY.md](GAME-LIBRARY.md) | Current managed Game Library status; GTK client workflow; Reviewed launch; Bulk Import — managed versus referenced-catalog contracts. |
| [docs/MACOS-BUILD.md](MACOS-BUILD.md) | Run from source; Intel tester checklist — platform qualification, not a new visual design. |
| [docs/MANAGED-LIBRARY.md](MANAGED-LIBRARY.md) | Identity and discovery; Data and remaining work; Settings relocation; Phase 3A; PA checkpoints — preserve technical contracts with historical scope. |
| [docs/NEXT-PASS.md](NEXT-PASS.md) | Linux-complete milestones; historical Sections 4–5; Completed foundation; Stable 1.9 boundary — milestone evidence and older UI plans. |
| [docs/QUICK-START.md](QUICK-START.md) | Sections 2–8 — explicitly 1.8 guidance; historical connection, Files, library, settings and replay workflows. |
| [docs/R1-MANAGED-FOLDER-COMPOSITES.md](R1-MANAGED-FOLDER-COMPOSITES.md) | Partial state and destructive authorization; USB restore; Physical qualification — consequence/evidence preservation. |
| [docs/R2-MANAGED-CLI-FRESH-FOLDER.md](R2-MANAGED-CLI-FRESH-FOLDER.md) | CLI contract; JSON, errors, exits and cancellation; Physical qualification — headless safety; no new desktop design. |
| [docs/R3-COMPATIBILITY-RETIREMENT.md](R3-COMPATIBILITY-RETIREMENT.md) | Credential internalization contract; Exact adaptation — keep secrets and raw transport outside UI. |
| [docs/R4-MANAGED-C64-AI-INSTALL.md](R4-MANAGED-C64-AI-INSTALL.md) | Decisions B–D; Corrections implemented; physical evidence — file disposition separate from bridge success, no replay. |
| [docs/R5-CORE-OWNED-HEADLESS-READS.md](R5-CORE-OWNED-HEADLESS-READS.md) | Headless Test Lab integration; Implemented behavior — preserve read-only diagnostics and private credential handling. |
| [docs/R6-MANAGED-FLASH-PUBLICATION.md](R6-MANAGED-FLASH-PUBLICATION.md) | Preserved current Flash contract; Minimum additive result and UI evidence; Completed behavior — separate publication, cleanup and activation. |
| [docs/RELEASING.md](RELEASING.md) | Local Debian Development build; Unsigned qualification boundaries; Other retained workflows — current packaging identity and platform gates. |
| [docs/SERVER-FIRST.md](SERVER-FIRST.md) | Core and client boundary; Filesystem ownership; Device scheduling and job lifecycle — technical authority boundaries. |
| [docs/SID-JUKEBOX.md](SID-JUKEBOX.md) | Result semantics; Linux physical acceptance; Duration policy and deferred work — playback claims, playlist semantics and duration constraints. |
| [docs/TEST-LAB.md](TEST-LAB.md) | Argonaut Test Lab foundation; R4 C64 AI setup/install boundary — opt-in diagnostics, sanitized reports, session switches and consequential setup. |
| [docs/ULTIMATE-COMPATIBILITY.md](ULTIMATE-COMPATIBILITY.md) | Purpose; Evidence levels; Known hardware — capability evidence, no inferred hardware support. |
| [docs/USB-BACKUP.md](USB-BACKUP.md) | Restore safety; Physical acceptance — retained Core capability; old GTK entry-point claim reconciled with C2. |
| [docs/testing/0.1.4-dev.2-CHECKLIST.md](testing/0.1.4-dev.2-CHECKLIST.md) | Testing checklist — historical control hit areas, scale persistence, overflow and close checks. |
| [docs/testing/0.1.4-dev.3-NOTES.md](testing/0.1.4-dev.3-NOTES.md) | Debian development pass 3 — historical explicit-save/close and plus/minus behavior. |
| [packaging/RELEASE-0.1.4.md](../packaging/RELEASE-0.1.4.md) | Changes — historical About/build identity and platform acceptance. |
| [packaging/RELEASE-1.5.md](../packaging/RELEASE-1.5.md) | Argonaut 1.5 — historical 100–300% scale and hardware metadata distinctions. |
| [packaging/RELEASE-1.6.md](../packaging/RELEASE-1.6.md) | Argonaut 1.6 (historical candidate) — autosave/Undo, old Quick Connect and Developer Mode. |
| [packaging/RELEASE-1.8.md](../packaging/RELEASE-1.8.md) | Files and preferences; Streams and replay — historical active-pane/replay presentation. |
| [packaging/RELEASE-1.9.md](../packaging/RELEASE-1.9.md) | Highlights; Known constraints — historical Linux acceptance and platform limits. |
| [packaging/RELEASE-DEVELOPMENT.md](../packaging/RELEASE-DEVELOPMENT.md) | Argonaut Development — 1.10 — packaged version/build identity and historical-workflow boundary. |
| [packaging/RELEASE-NOTES.md](../packaging/RELEASE-NOTES.md) | Argonaut 0.1.0 — Debian 13 — early validation and unchanged firewall/device setup boundary. |
| [packaging/icons/README.md](../packaging/icons/README.md) | Argonaut application icon — preserve supplied artwork/design and license; distinct from the compact Ultimate Power control. |
| [packaging/macos/INTEL-TEST.md](../packaging/macos/INTEL-TEST.md) | Intel Mac tester instructions — requested build identity and platform verification, not completed acceptance. |
| [packaging/macos/RELEASE.md](../packaging/macos/RELEASE.md) | Mac release instructions — saved-profile/keychain and limited platform acceptance; historical unresolved freeze. |
| [packaging/windows/RELEASE.md](../packaging/windows/RELEASE.md) | Windows release instructions — installed versus Portable credential behavior and qualification limits. |

### Recovered current requirements and accepted behavior

| Topic | Classification | Required preservation / reconciliation | Source document and section |
| --- | --- | --- | --- |
| Native controls and domain placement | Current approved UI requirement | Persistent binary preference → switch; action option/property → checkbox; action → button. Configuration in Ultimate Menu, feature operation in its tab, global power in the header. Credential controls retain their specific contract. | [Roadmap](ARGONAUT-ROADMAP.md), Design principles; [Server-first](SERVER-FIRST.md), Core and client boundary. |
| Files selection and activation | Implemented and accepted behavior | Preserve independent native multiple selection, Ctrl/Shift/arrow/Enter behavior, desktop click policy, qualified-release activation and COPY-only cross-pane dragging. Removing the permanent border supersedes presentation only; retain active-pane identification and focus. | [Current state](CURRENT-STATE.md), C0 and Combined C0/C1 physical acceptance. |
| Files labels, tooltips and menus | Implemented and accepted behavior | C4 already provides bounded filenames, right-aligned sizes, full-name tooltips/accessibility labels, This Computer/C64 Ultimate naming, Menu/Shift+F10 and focus return. Audit residual defects rather than re-create these tasks. | [Current state](CURRENT-STATE.md), C4 and C4 physical acceptance. |
| Storage visibility and errors | Implemented and accepted behavior | Advertised Flash/Temp are browsable, not generic mutation destinations; roots cannot be renamed/deleted. Unavailable roots are errors, not empty success. Temp wording promises neither persistence nor reboot erasure. Keep accessible root names and existing storage symbols. | [Current state](CURRENT-STATE.md), C1 and C3; [Roadmap](ARGONAUT-ROADMAP.md), C. Files / storage UX. |
| Backup entry points and hidden preferences | Implemented and accepted behavior | C2 removed Files Backup/Restore without a replacement UI; Core services remain. General edits, Undo and Restore Defaults preserve the hidden backup-root value. Separately saved managed-library location also survives General Undo/defaults. | [Current state](CURRENT-STATE.md), C2; [Managed Library](MANAGED-LIBRARY.md), Data and remaining work. |
| Connection and power | Implemented and accepted behavior | Existing B4 reconnect binds to active or selected saved identity, never implicitly saves credentials, and preserves stale-settings gates across restoration. Reset/Reboot use one-shot captured-session confirmation. Cosmetic changes must preserve these paths. | [Current state](CURRENT-STATE.md), B4 and B4 prerequisite; [Roadmap](ARGONAUT-ROADMAP.md), B4. |
| Status and cancellation | Implemented and accepted behavior | B5 already has a bottom status presenter and one contextual Cancel. Preserve sticky Cancelling, one-shot requests, hidden unavailable Cancel, job identity, truthful phase/counts and nuanced terminal results. Bulk Import shares cancellation authority. No invented percentages or automatic retries. | [Current state](CURRENT-STATE.md), B5 — contextual operation status/cancellation; [Roadmap](ARGONAUT-ROADMAP.md), B5. |
| Credentials | Implemented and accepted behavior | Test and Connect never persist passwords. Save Profile alone applies explicit Remember choices; Forget has separate semantics. Preserve fixed saved indication, UNKNOWN blocking/retry, retained edits on failure, safe HTTP errors and distinct session-only modes. Bounded Development acceptance does not qualify live native stores on every OS. | [Device Details](DEVICE-DETAILS-STABILIZATION.md), Credential behavior matrix; UNKNOWN correction; Persistence failure boundary; Publication gate. |
| Profiles and discovery | Implemented and accepted behavior | Saved selector contains profiles only; discovery candidates remain unsaved until explicit action. Keep host/port new-ID rules, Ethernet/Wi-Fi separation, Test/Connect distinction, Discover versus bounded Scan Subnet, truthful connection counts and password-required discovery limits. | [Current state](CURRENT-STATE.md), Device Details / connection-profile layout; [Device Details](DEVICE-DETAILS-STABILIZATION.md), Discovery trace and implemented UI. |
| General preferences | Current approved UI requirement | Keep autosave/Undo and explicit device-profile save semantics; slider replaces the old plus/minus presentation only. Do not revive old General Save/Discard prompts or alter hidden values. | UI-00 section 4; [Release 1.6](../packaging/RELEASE-1.6.md), General preferences paragraph (historical corroboration); [Current state](CURRENT-STATE.md), C2. |
| Managed Game Library | Implemented and accepted behavior | Current PA-5.11–13 GUI, partial-root warnings and matching-device restoration remain. Preserve explicit Review & Launch then Launch, expiring single-use plans and Accepted/Rejected/Uncertain outcomes. Accepted is protocol acceptance, not proof of gameplay. Managed CRT remains unimplemented; legacy referenced CRT is distinct. | [Current state](CURRENT-STATE.md), Current Game Library State — PA-5.13 Published; [Game Library](GAME-LIBRARY.md), Current managed Game Library status. |
| Legacy Game Library | Implemented and accepted behavior | Retained referenced catalog, reviewed launch, bulk-import accounting, unavailable entries and explicit different-content acceptance retain their existing scope; do not infer that all legacy workflows appear in the managed view. New features remain outside spit-shine. | [Game Library](GAME-LIBRARY.md), GTK client workflow; Reviewed launch; Stable 1.9 enhancement: Bulk Import Linux-complete. |
| SID playback | Implemented and accepted behavior | Preserve Library/Playlist/Now Playing separation, selection versus playback cursor, reviewed takeover, subtunes and manual navigation. Report Command accepted without claiming audible verification. No timer-based automatic advance or unreviewed SID reconfiguration. | [SID Jukebox](SID-JUKEBOX.md), Result semantics; Linux physical acceptance; Duration policy; [Next pass](NEXT-PASS.md), Linux-complete milestone: SID Jukebox. |
| Shared picker | Current approved UI requirement | Reuse context-constrained This Computer/C64 Ultimate selection and Core-owned file semantics. Foundation/SIDJuke migration is recorded published; remaining consumers need bounded review, not blanket migration during styling. | [Roadmap](ARGONAUT-ROADMAP.md), D. Shared Argonaut file picker — reusable component. |
| Drives | Current approved UI requirement | Recorded direction: Enabled switch, Run label preserving current behavior, shared Select Disk Image. The final UI-36 resolution supersedes the roadmap checkbox with a compact selector preserving all three write modes; see section 11. Removing model/ROM controls remains investigation, not approval. First-pass screen inspection is reported complete in UI-01; interaction/state qualification remains pending. | [Roadmap](ARGONAUT-ROADMAP.md), E. Drives redesign. |
| Streams and major redesign | Current approved UI requirement | Roadmap orders hang diagnosis before replay removal and independent verification, then scale/Fit to Window and interaction. Obvious escapable keyboard capture and no stolen app shortcuts are recorded direction. Major Ultimate Menu tree redesign, Favorites removal and LED enhancements stay outside initial spit-shine; retain safety investigation gates. | [Roadmap](ARGONAUT-ROADMAP.md), B1, F and G; UI-00 scope. |
| Theme, recovery and future clients | Planned or proposed improvement | System/Light/Dark, broader power/recovery UX, OBS/YouTube, persistent Core/PWA and offline libraries/emulators remain later work. Do not infer implementation or broaden UI-F to include them. | [Current state](CURRENT-STATE.md), Known observations and planned improvements; [Roadmap](ARGONAUT-ROADMAP.md), H, M and N. |
| Test Lab access and isolation | Current approved UI requirement | Settings → Developer → Open Test Lab replaces the normal top-level tab in both channels. Preserve Stable restart/enablement gating and always-available Development access without additional restrictions, all functionality, diagnostics and regression capabilities. Preserve opt-in checks, retained reports, channel isolation and deterministic verdicts. | [Developer Mode](DEVELOPER-MODE.md), Developer Mode and Test Lab; [Test Lab](TEST-LAB.md), foundation; [Roadmap](ARGONAUT-ROADMAP.md), I. |

### Authoritative technical cross-references

Use the following contracts during later UI implementation; do not copy or weaken
them for visual consistency:

- [Server-first](SERVER-FIRST.md), **Core and client boundary**, **Filesystem ownership**
  and **Device scheduling and job lifecycle**: Core owns safety, sessions, jobs,
  filesystem interpretation and secrets; a UI confirmation is not the safety boundary.
- [Device Details stabilization](DEVICE-DETAILS-STABILIZATION.md), **Credential behavior
  matrix**, **UNKNOWN correction** and **Discovery trace and implemented UI**:
  authoritative details for profile actions, privacy, state and subnet feedback.
- [C64U FTP](C64U-FTP.md), **Boundary and ownership**, **Client operations** and
  **Slices 3A–3D**, with [ownership closure](FTP-OWNERSHIP-CLOSURE.md), **Removed and
  retained surfaces**: no raw fallback, automatic mutation retry or invented success.
  [R1](R1-MANAGED-FOLDER-COMPOSITES.md), **Partial state and destructive authorization**,
  and [R6](R6-MANAGED-FLASH-PUBLICATION.md), **Minimum additive result and UI evidence**,
  preserve publication/cleanup/uncertainty distinctions. Flash upload does not activate
  a ROM/config or grant generic Files mutation permission.
- [Game Library](GAME-LIBRARY.md), **Current managed Game Library status** and
  **Reviewed launch**, plus [current PA-5.13 state](CURRENT-STATE.md#current-game-library-state--pa-513-published):
  keep managed and referenced-file capabilities distinct. [Managed Library](MANAGED-LIBRARY.md),
  **Settings relocation and later acceptance evidence**, **Identity and discovery**
  and **Data and remaining work** retain their checkpoint scope; later explicitly
  recorded restoration/launch behavior supersedes those presentation limitations.
- [SID Jukebox](SID-JUKEBOX.md), **C64U-resident SID safety**, **Result semantics**
  and **Duration policy and deferred work**: authorized-content playback and truthful
  result claims, without exporting SID-specific safeguards to destructive operations.
- [Developer Mode](DEVELOPER-MODE.md), [Test Lab](TEST-LAB.md), **foundation** and
  **R4 C64 AI setup/install boundary**, and [R4](R4-MANAGED-C64-AI-INSTALL.md),
  **Decision B** and **Decision D**: no background checks on simple enablement,
  deterministic results, sanitized evidence and separate file/bridge consequences.
- [USB backup](USB-BACKUP.md), **Restore safety**: retained Core functionality does
  not revive retired desktop entry points. [Releasing](RELEASING.md), **Local Debian
  Development build** and **Unsigned qualification boundaries** preserve build identity
  and platform gates. [Compatibility](ULTIMATE-COMPATIBILITY.md), **Evidence levels**,
  prohibits treating a hardware report as established support.

### Duplicate and superseded plans

| Topic | Classification and reconciliation | Both source references |
| --- | --- | --- |
| Quick Connect / Machine tab | Historical or superseded requirement: do not restore either. New contextual connection control supersedes the accepted separate-button presentation only; the earlier secondary Reconnect proposal is superseded by UI-02B.1b; automatic recovery and internal reconnect retain unchanged session semantics. | [Release 1.6](../packaging/RELEASE-1.6.md), Quick Connect paragraph; [Current state](CURRENT-STATE.md), B4; UI-00 Global controls. |
| Saved Connections placement | Historical or superseded requirement: earlier accepted bottom placement remains evidence. UI-00 explicitly approves top placement and collapsible details; profile/credential semantics survive. No new approval needed for this stated presentation supersession. | [Current state](CURRENT-STATE.md), Device Details / connection-profile layout; UI-00 Device Details. |
| Permanent pane border | Historical or superseded requirement: remove persistent blue outline as explicitly approved, while preserving native selection, keyboard focus and a clear active pane. C4 tooltip/menu/alignment work is already accepted and should not be duplicated. | [Development test](DEVELOPMENT-TEST.md), Test checklist; [Current state](CURRENT-STATE.md), C0/C4; UI-00 Files. |
| General save prompts / scale buttons | Historical or superseded requirement: old explicit General Save/Discard and plus/minus presentation do not override UI-00 autosave/Undo and slider. Historical 100–300% support is evidence to check, not proof that proposed 600% works. | [Dev.3 notes](testing/0.1.4-dev.3-NOTES.md); [Release 1.5](../packaging/RELEASE-1.5.md); [Release 1.6](../packaging/RELEASE-1.6.md); UI-00 General/Preview scaling. |
| Replay acceptance versus removal | Historical or superseded requirement: retain successful historical replay evidence, but do not use it to cancel the approved future removal. Preserve dependency review and independent hang verification. | [Next pass](NEXT-PASS.md), Completed historical Section 5; [Roadmap](ARGONAUT-ROADMAP.md), B1/F; UI-00 General. |
| Backup UI | Historical or superseded requirement: old Files Backup/Restore exposure is superseded by C2 retirement; technical backup/restore services remain valid. | [USB backup](USB-BACKUP.md), opening and Physical acceptance; [Next pass](NEXT-PASS.md), USB/SD milestone; [Current state](CURRENT-STATE.md), C2. |
| Managed no-launch / explicit-only loading | Historical or superseded requirement: older managed checkpoints are explicitly superseded for GUI, partial-root discovery, restoration and D64 launch by PA-5.11–13. Do not infer managed CRT, unrestricted import or recovery support. | [Managed Library](MANAGED-LIBRARY.md), Identity and discovery / earlier no-launch checkpoint; [Roadmap](ARGONAUT-ROADMAP.md), Phase 3A; [Current state](CURRENT-STATE.md), Current Game Library State; [Game Library](GAME-LIBRARY.md), Current managed Game Library status. |
| Duplicate root-warning work | Implemented and accepted behavior: PA-5.12 already handles inaccessible roots during library discovery. The supplied Files SD warning is a different surface; preserve its distinction without duplicating the discovery fix. | [Current state](CURRENT-STATE.md), PA-5.12; UI-00 Files observation. |
| Status bar as a new subsystem | Implemented and accepted behavior: B5 already owns contextual status/cancellation. The new visual distinction must build on it, not introduce a second operation owner or resurrect permanent Cancel buttons. | [Current state](CURRENT-STATE.md), B5; [Roadmap](ARGONAUT-ROADMAP.md), B5; UI-00 Global controls. |
| Old release guidance | Historical or superseded requirement: 1.8 screenshots/checklists and candidate-era release notes are evidence for their versions, not current release gates or instructions to restore old controls. | [Quick start](QUICK-START.md), introduction; [Development test](DEVELOPMENT-TEST.md), historical notice; [Releasing](RELEASING.md), Other retained workflows. |

### Approved reconciliation resolutions and remaining audit decisions

The user's UI-00 Reconciliation Resolution resolves the material HOLD. Test Lab
navigation/channel behavior, contextual connection controls and B5 preservation
are **Approved design decisions**, not Implemented or Accepted changes. No
remaining material conflict was identified in the UI-00 resolution pass; UI-01
source-inspection questions are recorded separately in sections 11–12. Detailed
visual choices and the remaining audit still require later review.

| Decision | Earlier discrepancy or requirement and sources | Approved resolution / remaining work |
| --- | --- | --- |
| Test Lab navigation and channel behavior | UI-00 and [Roadmap](ARGONAUT-ROADMAP.md), I, request removal from the normal top-level experience and Developer Mode access. [Developer Mode](DEVELOPER-MODE.md), opening/channel paragraphs, already gates Stable after restart and always enables Test Lab in Development; [Next pass](NEXT-PASS.md), Stable 1.9 boundary, records that gating. | **Approved:** Settings → Developer → Open Test Lab; remove the normal top-level Test Lab tab in both Stable and Development. Preserve Stable restart/enablement gating without bypass and Development always-available access without additional restrictions. Preserve all functionality, diagnostics, regression capabilities, service shutdown/isolation and reports. Documentation only; implementation remains unauthorized. |
| Connected reconnect access | UI-00 approves one contextual Connect/Disconnect header control but requires reconnect/recovery. [Current state](CURRENT-STATE.md), B4, and [Roadmap](ARGONAUT-ROADMAP.md), B4, retain an explicit connected Reconnect path and stale-settings protections. | **Superseded presentation:** UI-00 retained a secondary Reconnect action. **Approved UI-02B.1b:** remove manual Reconnect from the global header without relocating it. Preserve automatic recovery, internal reconnect, identity/session semantics, keyboard access and stale-settings protections. The historical B4 acceptance remains evidence for those technical contracts. |
| Status-bar composition | UI-00 requests distinct connection versus operation messages. [Current state](CURRENT-STATE.md), B5, protects active operation/Cancelling from ordinary messages and uses phase/counts without a progress bar. | **Approved:** redesigned status bar preserves existing B5 cancellation, progress, error, uncertain-outcome and foreground-job behavior; lifecycle and device-operation safety must not weaken. Separate connection state from operation warnings. Exact visual composition remains Proposed; separate regions are an option, not an approved layout. No new progress model is authorized. |
| Switch consistency versus credential state | UI-00 General and [Roadmap](ARGONAUT-ROADMAP.md), Design principles, prefer switches for persistent binary preferences; [Device Details](DEVICE-DETAILS-STABILIZATION.md), UNKNOWN correction, requires disabled/indeterminate Remember and explicit Save Profile semantics. | Treat Remember password as an action-specific credential choice, retain the current tri-state presentation and save boundary. Do not convert it to an immediate-saving binary switch. This is a preservation constraint, not authorization to redesign credentials. |
| New inventory numbering | UI-00 initially lacked the original meanings. The final UI-01 attachment supplies 01–78; section 5 preserves the full original-to-work mapping. | Four exact overlaps have explicit aliases; distinct screen requirements remain separate. UI-26–78 remain provisional references, and all seven additional candidates remain unnumbered. No final IDs are invented or silently reassigned. |

The source-level discrepancies with explicit supersession (Device Details placement,
B4 presentation, C2 retirement, PA-5.13 capabilities) are recorded above rather
than resolved by declaring one whole document superior. No technical contract is
changed by these approved presentation decisions or remaining design proposals.

### Additional punch-list candidates — unnumbered pending deduplication

These are **Proposed audit candidates**, not observed new visual defects or new
implementation authorization. Their identities are retained separately from the
now-supplied 78-entry mapping. No new final IDs are assigned; per the approved
resolution, final candidate IDs wait until the remaining visual audit is complete.
Section 10 maps their acceptance scope without collapsing them into screenshot tasks.

| Candidate | Existing work / source | Proposed handling |
| --- | --- | --- |
| Regression acceptance matrix for status/Cancel | Current-state B5; UI-00 status bar and UI-G. | Attach accepted cancellation/foreground invariants to existing status work; likely duplicate, not a new subsystem. |
| Settings Undo/defaults preserve hidden state | Current-state C2; Managed Library, Data and remaining work; UI-D. | Add backup-root and separately saved library-location checks to existing General acceptance. |
| Credential loading/UNKNOWN/failure presentation | Device Details stabilization, UNKNOWN correction and Persistence failure boundary; UI-E. | Include loading, indeterminate, retry and partial-save failure states in existing Device Details audit. |
| Managed launch lifecycle follow-up | Current-state PA-5.13, Outstanding work: three optional P3 lifecycle tests remain deferred. | Carry as an existing deferred candidate for UI-G review, not a newly discovered defect or silently mandatory test expansion. |
| Native chooser/focus/lifecycle limitations | Current-state Phase 3A and Settings physical acceptance; Managed Library corresponding sections. | Recover unresolved warnings/lifecycle faults for audit triage; do not call them fixed based on visual polish. |
| About/build and release-document consistency | Current-state B6; Releasing, Local Debian Development build; older screenshots/guides. | Inspect About and cross-platform identity presentation later; propose a separately authorized documentation-refresh task after design acceptance. |
| Developer Mode entry-point behavior | Review decision above; Roadmap I; Developer Mode contract. | Channel/navigation scope is now Approved above. Map this preserved candidate to the existing Test Lab finding during audit follow-up and test the eventual functional change separately. |

No fresh visual findings are claimed for pending screens. Roadmap sequencing,
P0 streaming and LED gates, historical acceptance limits, technical contracts and
all source-document contents remain intact. The material reconciliation HOLD is
resolved. At that UI-00 checkpoint the original mapping was still an audit
follow-up; section 5 now resolves it. Seven unnumbered candidates and remaining
interaction/state inspection are retained, not claimed complete. **UI-00 checkpoint: PASS — ready for documentation review.** This is historical
UI-00 disposition; the UI-01 inventory gate in section 12 is separate. No source
changes, application tests, implementation, commits, pushes, publication or C64U
contact are authorized by this resolution.

## 10. UI-01 first-pass visual audit consolidation

### Baseline and evidence

UI-01 baseline: detached HEAD and local `origin/development` both
`f82153ddd89c613b4f9a82292288b385670a580c`; clean working tree before edits.
Local references were checked without fetching or contacting hardware.
The 40-file reconciliation in section 9 remains the source inventory. The required
roadmap/current-state/feature documents were compared with the previously inspected
baseline: their content is unchanged except the already-published roadmap link to
UI.md. Existing section references and technical contracts therefore remain relevant.
Streams, Drives and Ultimate Menu direction is recorded in roadmap sections E–G;
there is no need to invent replacement feature documents.

The following **Approved** directions are explicitly supplied in UI-01 sections
4–6. Suggested slice boundaries, release recommendations and unspecified exact
layouts are **Proposed**. No new change is Implemented or Accepted. These are
user-reported audit directions, not independently observed screenshot defects.

### Screen decisions and provenance

| Area / provenance in supplied UI-01 brief | Approved direction | Contract preservation and unresolved detail | Proposed planning group |
| --- | --- | --- | --- |
| Shared/header — §4 | Native GTK, subtle branding, consistent buttons/type/spacing/icons and all disabled/loading/warning/error states. Contextual primary Connect/Disconnect; no manual Reconnect (UI-02B.1b); compact Chicken Lips Ultimate Power. Structured status bar. | Preserve qualified Reset/Reboot and B5 cancellation/progress/errors/uncertainty/foreground ownership. Exact visual composition remains to be reviewed; no new lifecycle model. | UI-A, UI-B |
| Files — §6 Files | Retain two panes; remove permanent blue borders while retaining keyboard focus; improve toolbar grouping, storage shortcuts, row alignment and headings. | Preserve selection, context menus, root permissions and C0–C4 accepted behavior. An inaccessible SD root must not imply overall disconnection. Exact root-warning copy remains Proposed. | UI-C |
| General — §5 General | Group by function, standardize switches/checkboxes, improve folder rows and Undo/Defaults placement; retain autosave. Graduated slider; Fit to Window in Streams. | 100–600% at 25% remains Proposed subject to renderer qualification. Preserve hidden preference values; remove replay only after dependency/stability review. | UI-D, UI-F Streams |
| Device Details — §5 Device Details | Saved Connections first; compact form; Advanced Connection Settings, Hardware & REST Information and Network Discovery independently collapsed by default; expansion lasts only for open Settings session. | Preserve identity, credentials, Test/Connect, profiles and Development session-only behavior. Scroll expanded content; do not turn Remember into immediate-saving preference. | UI-E |
| About — §5 About | Final Settings tab; preserve artwork/aspect ratio; clearer version/build/platform, consistent links/copyright. | Existing artwork uses contain fit and build identity is selectable. Reordering must update all page-navigation routes; it is not merely moving the tab label. | UI-D About |
| Settings Game Library — §5 Game Library Settings | Compact current-library summary; secondary technical details; grouped discovery/selection/Forget controls; clearer empty/unavailable states. | Keep partial-discovery warnings, strict selection and separate persistence, confirmed host-only Forget; no auto-adoption or file deletion. | UI-D Library |
| Ultimate Menu — §6 Ultimate Menu | Preserve separately approved Regedit-style tree/property sheet; only shared styling on current accordions. | Preserve physical menu/F2 Advanced grouping and capability-filtering requirements. LED Rainbow P0 device-safety investigation cannot be bypassed. Tree redesign is separately scoped. | UI-A; UI-F Ultimate |
| Drives — §6 Drives | One enable switch, compact three-mode write selector (revised UI-36), Run label, shared C64U image picker and consistent A/B cards. | Preserve current Run consequence/confirmation. Investigate type/ROM placement before relocation/removal. All three source-defined mount-write modes remain under the revised UI-36 decision. | UI-F Drives |
| SIDJuke — §6 SIDJuke | Rename user-facing SID Jukebox to SIDJuke; retain two columns; simplify tune metadata; group playlist management; dedicated Now Playing panel; relocate subtune controls appropriately. | Keep reviewed playback, cursor versus selection distinction, manual navigation and duration uncertainty. Now Playing already has a section; polish it rather than invent a second playback owner. Exact subtune placement remains Proposed. | UI-F SID |
| Streams — §6 Streams | Responsive preview, uncropped Fit to Window, graduated manual scale, intentional stopped state, grouped preview/recording/audio/BASIC controls. Replay removal after review. | P0 streaming/navigation hang remains a release gate. Preserve session/media lifecycle and existing BASIC behavior. Remote controls and keyboard overlay are separate functional work, not styling. | UI-F Streams |
| Main Game Library — §6 Game Library | Compact summary, styled selectable rows, selection-associated launch, contextual Retry Load, secondary Library Settings and clear planning-versus-import wording. | Preserve managed D64 review/confirmation, identity protections and explicit outcomes. No managed CRT execution. Existing selection/launch/retry routes are styled, not reimplemented. | UI-F Library |
| Test Lab — §6 Test Lab | No normal top-level tab in either channel; Settings → Developer → Open Test Lab; existing Stable gating and always-available Development access. | Preserve diagnostics, history, AI bridge, automation and evidence. Larger four-section developer workspace is deferred, not authorized by relocation. | UI-F Test Lab |

### Cross-screen integration and candidate traceability

- Header and Files outline work remains one shared/Files concern, not one new task
  for every screenshot. Preserve per-screen keyboard/selection acceptance.
- General default scale and Streams manual scale share `scale_control`; use one
  qualified manual-scale task with both consumers, and a separate Fit to Window task.
- Settings and main Game Library share `ManagedLibraryView`; reuse summary/state
  presentation while keeping discovery/selection/Forget distinct from launch/import review.
- Files warnings and managed-library partial-root discovery share truthful state
  language, but remain separate behaviors. PA-5.12 is already accepted, not a new fix.
- C4 filename/tooltips/context-menu work, existing picker consumers, B5 status and
  existing SID Now Playing structure are preservation baselines, not newly completed
  polish. A missing final visual treatment does not erase earlier acceptance.
- Keep all seven section-9 candidates: status/Cancel and hidden preferences map to
  UI-B/UI-D acceptance; credential state to UI-E; launch lifecycle to UI-F Library;
  chooser/focus limitations to UI-G; About/build to UI-D/UI-G; Developer entry point
  to UI-F Test Lab. These are proposed acceptance/slice mappings; candidates remain unnumbered.

The thematic rows preserve every supplied screen. Section 5 now accounts for all
78 original review identifiers, four exact overlaps and explicit approval status.
The source mapping does not supply screenshot filenames or independent acceptance
evidence; neither is inferred.

## 11. Read-only GTK structural inspection

Source observations below are at the UI-01 baseline. They describe code structure,
not new acceptance or a claim that the application was run. Recommendations are
**Proposed**. Source files and tests remain unchanged.

| Surface | Inspected source / symbol | Observation and centralized styling opportunity |
| --- | --- | --- |
| CSS/provider | [gui.py](../c64u_browser/gui.py), `Browser.do_activate` | Repository Python search finds the CSS provider here: pane border/active border and hard-coded error color. Propose one application style provider with scoped semantic classes and shared spacing/type rules. Preserve native selected/focus/disabled rendering; avoid broad widget selectors or per-tab providers. |
| Buttons/toolbars/header | [gui.py](../c64u_browser/gui.py), `button`, `icon_button`, `do_activate`, `update_connection_header` | Shared button helpers coexist with direct Gtk.Button construction in tabs. Add optional presentation roles without changing callbacks or operation admission. Header owns separate Reconnect/Disconnect and accessible 24 px power artwork. Split connection behavior migration from CSS. |
| Status | [gui.py](../c64u_browser/gui.py), `render_operation`; [operation_status.py](../c64u_browser/operation_status.py), `OperationPresentation`, `progress_text`; [foreground.py](../c64u_browser/foreground.py) | Bottom label/Cancel are bound to an existing presenter; ordinary status shares precedence. Style that view, keeping Cancel outside disabled feature controls. No second job owner, fabricated percentage or inferred overall total. |
| Settings navigation | [app_preferences.py](../c64u_browser/app_preferences.py), `show_preferences`, `GAME_LIBRARY_PAGE`; [about.py](../c64u_browser/about.py), `show_about` | Current order is General, Device details, About, Game Library. Library page constant is 3; About opens page 2. Propose named page lookup before moving About last or adding Developer. Preserve open-dialog reuse, detach/close and parent focus restoration. |
| Forms/sections | [connection_dialog.py](../c64u_browser/connection_dialog.py), constructor-local `section`; [app_preferences.py](../c64u_browser/app_preferences.py), General/folder rows; [managed_library_view.py](../c64u_browser/managed_library_view.py), `column` | Repeated Gtk.Box margins, label/entry rows and section headings can share small presentation helpers. Keep credential callbacks, UNKNOWN state, dirty-profile close handling, autosave and discovery generations in their current owners. Do not extract a new persistence/controller layer for visual uniformity. |
| About | [about.py](../c64u_browser/about.py), `about_page` | Gtk.Picture uses CONTAIN; version/build/platform label is selectable, links use Gtk.FlowBox. Reuse common heading/secondary-text spacing; preserve asset and ratio, link targets and accurate build source. |
| Shared picker | [file_picker.py](../c64u_browser/file_picker.py), `FilePicker`; [picker_model.py](../c64u_browser/picker_model.py) | Existing scope/filter/mode-based picker with native selection, named accessible path/list, session checks and exactly-once callback. Style reusable rows/toolbars; consumer authorization remains outside picker. Drives is already a remote-only consumer. |
| Lists and focus | [gui.py](../c64u_browser/gui.py), `pane`, `menu`; [file_selection.py](../c64u_browser/file_selection.py); [sid_jukebox_tab.py](../c64u_browser/sid_jukebox_tab.py); [managed_library_view.py](../c64u_browser/managed_library_view.py) | Gtk.ListBox is reused with different selection modes, keyboard controllers and drag semantics. Centralize visual row roles only; do not unify activation or selection policies. Preserve accessible labels, Menu/Shift+F10, Escape and restored focus. |
| Drives cards | [drives_tab.py](../c64u_browser/drives_tab.py), constructor, `choose_image`, `mount`, `mount_run` | A/B are already built by one loop; keep a shared card factory. Picker uses `scopes=('c64u',)`. Mount offers readonly/readwrite/unlinked; Run uses a temporary copy independent of that selector. Styling must not collapse these distinctions. |
| SID organization | [sid_jukebox_tab.py](../c64u_browser/sid_jukebox_tab.py), constructor, `_sync_now_playing`, `_choose_sid` | Existing Gtk.Paned, library summary, playlist section and Now Playing section support modular presentation work. Keep metadata/details, subtune selection and playback cursor semantics while adjusting visual grouping. |
| Scale/viewport | [app_preferences.py](../c64u_browser/app_preferences.py), `normalize_scale`, `scale_control`; [streams_tab.py](../c64u_browser/streams_tab.py), constructor, `scale_preview`, `apply_scale` | Shared control normalizes to 100–300% at 25%; preference validation rejects above 300. Preview requests width 384 × scale and frame height × scale inside a scroller. 600% requires coordinated qualification, not a label-only edit. No runtime renderer/4K logical-pixel validation was performed. |
| Managed library | [managed_library_view.py](../c64u_browser/managed_library_view.py), constructor, `open_settings`; [managed_launch_review.py](../c64u_browser/managed_launch_review.py); [import_review.py](../c64u_browser/import_review.py) | Main and Settings share a controller. Existing single-selection rows notify launch review; Retry Load is wired separately. Reuse common summary/warning styles without merging launch, discovery and import authority. Legacy `game_library_tab.py` is a distinct client, not the displayed managed tab. |
| Ultimate Menu | [settings_tab.py](../c64u_browser/settings_tab.py), `show_results`, `require_fresh_settings`; [settings_sections.py](../c64u_browser/settings_sections.py) | Rows currently use Gtk.Expander with dependency sensitivity and staged-value feedback. Apply shared styling only; future tree/property view must preserve draft, validation, capability and stale-session safeguards. |
| Test Lab | [gui.py](../c64u_browser/gui.py), conditional tab construction/busy controls; [test_lab_access.py](../c64u_browser/test_lab_access.py), `enabled`; [test_lab_tab.py](../c64u_browser/test_lab_tab.py) | Availability is Development OR saved developer-mode flag. Relocation must preserve instance lifetime, busy controls, reports and automation; removing append_page alone is not a complete navigation change. Settings open/close must not implicitly start/stop diagnostics or bridges. |

### Revised UI-36 — approved three-mode drive-write presentation

The final HOLD resolution explicitly supersedes original UI-36 “Replace
write-protect dropdown with checkbox” and roadmap E's checkbox direction. Preserve
all three modes using a compact GTK selector or another control representing all
three states. Improve labels/contextual explanations without changing device/API
semantics, validation, confirmation, session binding or safety checks. No drive
behavior changes in this audit. The earlier proposed checkbox plus separate
memory-only control is not the current design requirement.

Read-only source inspection: [drives_tab.py](../c64u_browser/drives_tab.py),
constructor and `mount`, maps the three displayed choices directly to mode tokens;
[core.py](../c64u_browser/core.py), `execute_drive_image`, validates mode and bound
selection under session/device admission; [api.py](../c64u_browser/api.py),
`mount_disk`, accepts exactly these tokens and forwards `mode` to the mount API.

| Current source label | API token | Meaning preserved | Proposed concise label and explanation |
| --- | --- | --- | --- |
| Write-protected | `readonly` | Writes are blocked for the mounted image. | **Write-protected** — disk writes are blocked. |
| Read/write image | `readwrite` | Disk writes target the mounted image, preserving persistent-write behavior. | **Write to disk image** — changes can modify the image on storage. |
| Changes in memory only | `unlinked` | Changes stay in memory rather than being saved to the source image. | **Changes in memory only** — changes are not saved to the source image. |

Exact revised wording is **Proposed**; the three-state distinction and unchanged
behavior are **Approved**. The explanation does not promise atomic/durable writes,
new persistence guarantees or a particular memory lifetime. Retain the source
mapping even if presentation order changes. No new default or automatic mode
selection is authorized. `mount_run` independently uses a temporary copy, states
that changes are not saved to the original, and ignores the selected mount-write
mode. Renaming that action to Run preserves its explanation and confirmation.

The affected [roadmap](ARGONAUT-ROADMAP.md), **E. Drives redesign**, is recorded here
as superseded only on the Write Protect checkbox point. Its enabled switch,
Run direction, shared-picker work and ROM/type investigation remain. Per scope,
no roadmap text is modified; propose updating that sentence in a later authorized
documentation pass to reference this three-mode decision.

### Remaining nonblocking design details

**Picker scope:** roadmap E describes local plus C64U selection, while UI-01
specifies a shared C64U image picker and the existing Drives consumer is C64U-only.
For this pass preserve the remote-only consumer; local-image staging/upload is a
separate proposed expansion requiring functional review. Record this scope
recommendation for plan approval; do not claim local upload already exists.

**Scale and navigation:** 600% remains a proposal requiring qualification. About-last
and Developer navigation require updating named/positional entry routes together.
These are implementation dependencies, not reasons to discard approved direction.

## 12. Proposed implementation sequence and public 1.10 scope

All slice boundaries and release classifications below are **Proposed** for plan
review. Approved visual direction does not authorize implementation. Preserve
UI-A–UI-G parent meanings; suffixes identify planning sub-slices, not new finding IDs.
Every slice requires its own bounded diff and applicable existing regression/visual
acceptance. The checks below are future requirements; no application tests ran here.

Release classes:

- **Required before public 1.10 release:** existing P0 stability, safety preservation
  and final release acceptance. Any included change must pass its relevant regression,
  accessibility and state checks; failed safety checks cannot be waived as cosmetic.
- **Recommended before release:** bounded visual consistency and approved usability
  work. A proposed polish item is not automatically a blocker; confirm the release
  cut at plan review. Postpone unfinished slices rather than claiming acceptance.
- **Deferred larger redesign:** modular work outside the initial spit-shine cut.
- **Future feature:** new functional capability requiring its own design and approval.

| Slice | Bounded work | Dependencies | Future acceptance / completion boundary | Proposed release class |
| --- | --- | --- | --- | --- |
| UI-A1 — shared foundation | One scoped style provider; semantic button/heading/state roles; reusable spacing and small form/toolbar helpers. Migrate a representative surface first, then consumers per slice. | Inventory mapping is complete; use source survey in section 11 and obtain implementation authorization. | Native focus/selection/disabled states survive; no global style leaks, clipping or callback changes. | Recommended before release |
| UI-B1 — header | Primary contextual Connect/Disconnect without manual Reconnect, Settings and retained compact power control (UI-02B.1b). | UI-A1; connection/recovery route review. | Connected/disconnected/recovering/blocked states, keyboard access, identity binding, stale-settings gate and qualified Reset/Reboot unchanged. | Recommended before release; safety preservation required |
| UI-B2 — status | Restyle existing B5 row and distinguish connection from operation warning. | UI-A1; coordinate header status text with UI-B1. | Active jobs retain ownership; sticky Cancelling, contextual Cancel, truthful progress/errors and uncertain outcomes survive. | Recommended before release; B5 contract required |
| UI-C1 — Files | Pane headings/borders, navigation versus action grouping, shortcuts and row alignment. | UI-A1; UI-B2 for global status integration. | Native selection and focus, tooltips, menus, root restrictions and inaccessible-root-versus-disconnection wording. | Recommended before release |
| UI-D1 — General presentation | Functional preference groups, switch/checkbox roles, folder rows, Undo/Defaults placement. Keep scale/replay behavior unchanged until their slices. | UI-A1. | Autosave/Undo, hidden backup-root/library-location persistence and close/chooser focus semantics preserved. | Recommended before release |
| UI-D2 — Settings navigation/About | Named navigation destinations, About final, artwork/identity/links. Prepare Developer page without bypassing gating. | UI-A1; coordinate UI-F Test Lab entry point. | About and Library routes open correct pages on new/reused dialog; image ratio, build identity, links and keyboard focus. | Recommended before release |
| UI-D3 — Library Settings | Compact summary/details and grouped discovery/selection/Forget with truthful states. | UI-A1, UI-D2 navigation. | Strict explicit selection, separate persistence, partial-discovery warnings and host-only confirmed Forget. | Recommended before release |
| UI-E1 — Device Details | Saved Connections first; compact form; three independent collapsed sections with session-only expansion (UI-DD.1a supersedes the original two-section plan). | UI-A1, UI-D2 navigation stable. | UNKNOWN/loading/error credentials, Test/Connect distinction, identity/profile semantics, scroll/resize, reopen defaults and Development session-only behavior. | Recommended before release |
| UI-F Drives-1 — card presentation | Match A/B cards; keep existing picker, type/ROM actions and write modes. | UI-A1; inspect relevant state interactions. | Consistent cards without hidden functionality; C64U-only selector and confirmations unchanged. | Recommended before release |
| UI-F Drives-2 — control changes | Enable switch, compact three-mode write selector with contextual explanations, and Run label. | Drives-1; preserve revised UI-36 mapping; type/ROM investigation before any relocation. | All three mount modes remain reachable; switch does not bypass action review; Run retains temporary-copy, reset/interruption and uncertainty semantics. | Recommended before release; revised UI-36 decision resolved |
| UI-F SID-1 — SIDJuke presentation | User-facing rename, metadata hierarchy, playlist grouping, dedicated Now Playing and subtune placement within existing two columns. | UI-A1; agreed subtune layout. | Playback review, selected items versus playback cursor, playlist navigation/drag/keyboard, duration uncertainty and exactly scoped subtune change preserved. | Recommended before release |
| UI-F Streams-1 — stability | Diagnose P0 navigation/stream hang; implement a bounded root-cause correction only after separate authorization. | Existing roadmap B1 evidence/instrumentation; may proceed independently of styling after authorization. | Repeated relevant streaming/navigation/lifecycle scenarios with evidence; do not infer success from replay removal. | Required before public 1.10 release |
| UI-F Streams-2 — replay dependency/removal | Review shared capture/recording dependencies, then remove replay-only UI/implementation as approved. | Streams-1 diagnosis and dependency review; preserve reusable media paths. | Preview/recording/audio/session cleanup survive; independently verify hang after removal. | Recommended before release; stability gate remains required regardless |
| UI-F Streams-3 — scale/viewport | One shared graduated manual scale for General/Streams; responsive viewport, uncropped Fit to Window and stopped state. | UI-A1; renderer/range and logical-pixel qualification; stable media baseline. | 4K at 150% desktop scaling, supported range/25% grid, persistence, aspect ratio, resize and no cropping; manual versus fit behavior explicit. | Recommended before release; 600% contingent on qualification |
| UI-F Streams-4 — control grouping | Group preview, recording, audio and existing BASIC interaction. | UI-A1; Streams-2/3 settled to avoid repeated layout work. | Existing media lifecycle, enabled states and BASIC send/Return/focus behavior preserved. | Recommended before release |
| UI-F Library-1 — main managed view | Compact summary, selectable rows, selection-associated launch, contextual Retry Load, secondary settings and planning-versus-import wording. | UI-A1, UI-B2, UI-D3 shared summary treatment. | Managed D64 explicit review/Launch and identity/session checks; no implied import completion or managed CRT support. | Recommended before release |
| UI-F Test Lab-1 — navigation only | Settings → Developer → Open Test Lab; remove normal tab in both channels, retain capabilities. | UI-D2; lifecycle design for existing TestLabTab instance and settings close/reopen. | Stable restart gating; Development always available; diagnostics/history/bridge/automation/evidence and busy-state lifecycle unchanged. | Recommended before release |
| UI-F Ultimate-1 — prerequisites | Firmware/capability investigation and LED Rainbow safety/transition contract. | Roadmap G1/G2; separate authorization for any device work. | Evidence-based filtering/grouping and safe apply ordering; no casual reproduction of lockup. | Required safety prerequisite before affected behavior changes; redesign itself deferred |
| UI-F Ultimate-2 — later redesign | Regedit-style GTK tree and persistent property sheet, F2 Advanced parity; existing accordion gets no bespoke polish. | Ultimate-1, UI-A1 and separate design review. | Preserve staged edits, reload/confirmation/session safety, capability dependencies and physical grouping. | Deferred larger redesign |
| UI-G1 — final acceptance | Focus/keyboard/tooltips/dialog/state coverage, contrast/resize/scaling, regression and applicable package/platform evidence. | Every included slice plus Streams-1; retain existing release gates. | Acceptance recorded per slice/platform; no claims for uninspected dialogs or unqualified devices. Release review chooses cut explicitly. | Required before public 1.10 release |

Recommended order: implementation-plan/design review → UI-A1 → UI-B1/B2 and
UI-C1 → UI-D1/D2/D3 → UI-E1 → bounded tab slices → UI-G1. Streams-1 retains
P0 priority and can progress independently of the styling chain once separately
authorized. A styling dependency must not delay diagnosis. Ultimate prerequisites
remain a separate safety workstream; no major redesign is prerequisite for ordinary
Files/Settings polish.

Combine only genuinely shared presentation: General/Streams scale control;
Settings/main-library summary styling; shared status/toolbar/form roles. Keep
connection semantics, credential restructuring, replay removal, Test Lab navigation
and Drives mode changes independently reviewable. UI-F is an umbrella, never one
large implementation change. If a listed slice grows beyond one behavioral boundary,
split it further while retaining these references.

### Deferred and future scope

| Work | Proposed release class | Boundary |
| --- | --- | --- |
| Four-section developer workspace | Deferred larger redesign | Test Lab navigation does not authorize reorganizing diagnostics or automation. |
| Ultimate tree/property sheet and later LED enhancements | Deferred larger redesign | Capability and Rainbow safety gates remain mandatory; no bespoke accordion investment. |
| Remote Streams controls and C64 keyboard overlay | Future feature | Separate interaction, keyboard-capture and device-operation scope; do not steal app shortcuts. |
| Managed CRT execution and new Game Library features | Future feature | No expansion during this polish pass; preserve referenced CRT versus managed D64 distinction. |
| Local Drives image staging/upload | Future feature | Shared remote picker does not authorize upload; reconcile roadmap's broader future intent separately. |
| Theme preference, broader power/recovery capabilities, OBS/YouTube, emulators/offline libraries/PWA | Future feature | Existing roadmap M/N ordering and feature-specific safety review remain in force. |

All section-10 approved polish items map to the recommended slices above; no
unmapped screenshot proposal is automatically classified as required. Existing
P0 streaming stability and final release gates remain required. Preserve the LED
P0 investigation gate and do not publish affected unsafe behavior on the strength
of cosmetic changes; this plan neither resolves the hazard nor waives existing gates.

### Review gates, proposed roadmap correction and validation

1. **Identifier evidence resolved:** all 78 original review IDs are accounted for
   in section 5. UI-01–25 meanings are preserved verbatim. UI-26–78 remain provisional
   historical references; UI-28/54/55/71 have explicit aliases without losing their
   original text or screen scope. Seven documentation candidates remain unnumbered.
2. **Drives decision resolved:** UI-36 preserves `readonly`, `readwrite` and
   `unlinked` through a compact three-state selector. Only the earlier checkbox
   direction is superseded. Exact label copy and control appearance remain normal
   design details; no write-mode semantics change is authorized. Type/ROM placement
   remains investigation, not an unresolved blocker for the documented selector.
3. **Plan review:** approve slice boundaries and release cut; settle scale maximum,
   manual/fit behavior and subtune placement during their
   designs. These open details do not revoke the approved overall directions.
4. **Roadmap proposal only:** section D still lists Drives among remaining picker
   consumers and section E describes replacing the split workflow with local/C64U
   selection. Source already has `Select Disk Image…` using the shared C64U-only
   picker. Propose a scoped status note acknowledging that structure while retaining
   local-source support as separate work and avoiding unverified acceptance claims.
   Also propose updating E's superseded Write Protect checkbox sentence to reference
   revised UI-36. No roadmap modification is made in UI-01.

Documentation validation checks all 78 source IDs, initial meaning/candidate preservation,
source links, Markdown structure and whitespace, approved versus proposed wording,
and the one-file change boundary. Historical technical contracts stay in their
original documents; section 9's historical inventory and UI-00 disposition remain.
No tests, GTK runtime, source edits, hardware contact, commits or pushes are part
of this pass. Both final audit HOLD issues are resolved; no remaining material
conflict was identified. Proposed visual details, deferred recommendations and
implementation/release-cut approval remain future review, not claims of completed
implementation. **PASS — ready for UI implementation-plan review.**

## 13. UI-FR.4 — upload cancellation and future Transfer Recovery

Historical design checkpoint: cancellation-action wording and cleanup promises
below are superseded by [the approved 1.10 best-effort policy](#15-ui-fr4e2--approved-best-effort-upload-cleanup).
Technical authority and lifecycle requirements remain applicable.

Historical inspection record: section 14 supersedes the two-confirmation proposal
and resolves this section's HOLD. Its single-dialog interaction is the current
approved design; the lifecycle findings below remain relevant.

### Authority and implementation status

The UI-FR.4 request approves the three-choice upload-cancellation design below.
This section records design and read-only lifecycle findings, not an implemented
or accepted feature. Existing UI identifiers, seven unnumbered audit candidates,
historical milestone evidence and feature contracts remain unchanged. No new
numbered audit identifiers or release sequencing are assigned here. The roadmap
remains authoritative for development priorities; no roadmap change is needed
for this design record.

Technical references remain [B5 in Current State](CURRENT-STATE.md),
[FTP upload/deletion and UI-FR.2/2a/3 contracts](C64U-FTP.md), and
[USB backup/restore](USB-BACKUP.md). The inspected UI-FR.2/2a/3 code is uncommitted
work, not a claim of published or physically accepted behavior.

### Approved cancellation choices

Present these choices **before requesting cancellation**, when Cancel is invoked
for an eligible active upload:

| Choice | Approved behavior |
|---|---|
| Continue Upload | Dismiss the confirmation; make no cancellation request and preserve the active transfer. |
| Cancel & Keep | Request cooperative cancellation once, wait for authoritative completion, retain any incomplete staging file and available recovery evidence, preserve completed batch files, and perform no deletion. |
| Cancel & Delete | Request cooperative cancellation once; wait for authoritative completion and released transfer resources. If a verified incomplete staging file is available, use trusted file-only recovery to remove that file. Preserve completed files and published destinations. Never delete on uncertain publication. Report cleanup failure/uncertainty without automatic retry. |

**Cancel & Keep is the safe default selection.** Escape and window close instead
mean **Continue Upload**: they must not request cancellation. These response
routes must be distinct; a generic GTK Cancel response must not accidentally
activate Cancel & Keep. Cancellation is cooperative and does not promise to
interrupt an FTP command already in progress. A late request can still end in
acknowledged success or failure; terminal evidence wins over cancellation intent.

A Core-issued `staging-candidate` is provenance, not proof that the file presently
exists or is unchanged. "Verified incomplete staging file" requires fresh strict
recovery preparation plus execution revalidation, not inference from a pathname,
message text, a cancelled state, or the existence of a record alone. There is no
cleanup when no qualifying record exists, publication is unknown, the session
changed, authority is exhausted/consumed, or preparation cannot verify the file.
Retain truthful evidence and report the limitation instead.

### Inspected call paths and ownership

Source links are repository-relative; function names identify the inspected code.

| Stage | Current call path and consequence |
|---|---|
| Global Cancel | [Browser](../c64u_browser/gui.py) `bind_job_cancel()` installs a captured `job_cancel_callback(job)` with the foreground token. `cancel_transfer(job, token)` rejects stale/terminal jobs and selects Files, USB, Game Library or SID service cancellation. |
| B5 request | [OperationPresentation](../c64u_browser/operation_status.py) `request_cancel()` consumes its one-shot presentation action before calling the service. Accepted requests enter sticky Cancelling; progress cannot overwrite it. Refusal is reported while awaiting the terminal result. |
| Core cancellation | Service `cancel(job.id)` delegates to [CoreScheduler.cancel()](../c64u_browser/scheduler.py), then [CoreJob.request_cancel()](../c64u_browser/jobs.py). The request sets the cancellation event/state; only a cooperative check raising `JobCancelled` establishes cancellation as the terminal outcome. A request is not completion. |
| Foreground admission | `Browser.run_file_job(submit, done)` reserves [ForegroundSlot](../c64u_browser/foreground.py) before invoking the submit factory, binds the returned job, then `begin_file_job()` disables busy controls and binds B5. The status region remains outside busy controls. |
| Upload execution | `Browser.start_copy()` prepares a `CopyRequest`, resolves conflicts, then submits [FileService.execute_copy()](../c64u_browser/file_service.py). [folder_copy.execute_plan()](../c64u_browser/folder_copy.py) runs steps serially and [transfers.upload_managed()](../c64u_browser/transfers.py) handles staged additions. Folder steps and replacement evidence retain their separate contracts. |
| USB restore | [UsbBackupService.execute_restore()](../c64u_browser/usb_backup.py) verifies backup/storage/classification, builds a step plan, calls the same executor, and uses the shared FileService issuer. Current Files GUI has no USB backup/restore entry points; the service remains available. |
| Issuance | FileService `_partial_from_report()` registers the exact record only for qualifying copy/restore evidence and matching staging path/session. It runs after `execute_plan()` returns. Copy/restore preserve the result in failure or cancellation exceptions. |
| Terminal delivery | `CoreJob.run()` unwinds the task, assigns authoritative state/result, sets its completion event, then emits `finished`. `run_file_job()` observes events, the initial snapshot and a 250 ms snapshot fallback; all converge on one guarded `finish()` callback. This is observation, not retry. |
| Foreground release | `finish()` rejects stale ownership/duplicate delivery, calls `end_file_job()` to restore sensitivity and release the exact token, then `operation.finish()` and feature `done(snapshot)`. `render_operation()` restores usable focus when Cancel disappears. |
| Existing recovery | `Browser.delete_partial()` opens `delete_dialog()`. Its preparation callback displays the exact reviewed target; its response callback executes only after explicit Delete. FileService `prepare_partial_delete()` reserves authority; `execute_delete()` consumes authority/plan before dispatch. [deletion._delete_recovery_file()](../c64u_browser/deletion.py) performs only DELE after fresh file/session checks; [strict Files readers](../c64u_browser/files.py) reject returned-directory mismatch. |
| Session replacement | [Core](../c64u_browser/core.py) `_begin_session()`, `_end_session()` and `close()` invalidate recovery. `reconnect()` creates a new session even for the same device. [Recovery](../c64u_browser/recovery.py) cannot transfer old cleanup authority into that new session. |

### Timing and safe cleanup handoff — implementation proposal

B5 exposes Cancel for a foreground job marked cancellable while RUNNING and before
its one-shot attempt; this includes queued work and does not mean every wire
phase is immediately interruptible. Streaming checks and per-step checks are
cooperative. The managed FTP layer defers cooperative cancellation around
consequential mutation reply capture, including publication, so accepted outcomes
are not relabelled as cancelled. Device/binding validation remains active.

The managed adapter operation scopes unwind before the copy executor returns.
[FtpReadAdapter.operation()](../c64u_browser/ftp_reads.py) releases its context/lease
stack; [C64UFtpLeaseManager.lease()](../c64u_browser/c64u_ftp.py) closes the client and
removes the lease in `finally`. Recovery issuance follows executor return and
precedes terminal result publication. Do not trigger cleanup merely because
issuance occurred or `cancel-requested` was received; wait for the terminal result
and GTK foreground release.

`CoreScheduler._worker()` calls `queue.task_done()` only after `job.run()` returns;
a terminal callback may therefore arrive before that bookkeeping completes.
Submitting the next job to the FIFO lane is safe; waiting for it inside the
previous worker/listener is not. Never block GTK, call `wait()` from completion
listeners, acquire nested device admission, or retain the previous foreground token.

Use new submission factories and new foreground reservations for recovery
preparation and deletion execution. Gate each continuation on captured job,
device/session, dialog intent and exact issued record. Preserve plan discard on
abandoned review, and consume a cleanup-intent latch before dispatch. Cancel &
Delete is not permission to scan old records or clean other jobs' leftovers.

The existing GUI provides a suitable released-foreground `done(snapshot)` point,
but does **not** yet implement the chain safely: `start_copy().finished()` starts
`self.run(refresh, refreshed)` immediately, which marks the application busy.
A new coordinator must choose cleanup/review before refresh, or wait for an
explicit refresh completion before requesting admission. It must also avoid
stale refresh/status writes overwriting the cleanup result. Do not append a
cleanup call after the current completion callback and assume admission succeeds.

### Single-file, folder and batch evidence

`folder_copy.Report` has one `partial` path, while `CopyResult` and `RestoreResult`
have one optional `partial_upload`. Their upload/replacement/folder-step sequences
retain per-step evidence and their completed/skipped/remaining lists retain batch
accounting. Execution stops at the first failed/cancelled step; therefore a single
current execution offers at most one recoverable incomplete staging file. This
applies to one selected file, recursive folder plans, multiple selected files and
USB restore plans. A directory-creation failure is not a staged-file authority;
a completed publication or replacement uncertainty is not a cleanup shortcut.

The FileService store can hold up to 32 unresolved records from different jobs,
but `Browser.partial_upload` is a single presentation reference and can be
replaced by a later result. It is not a batch manifest or an enumeration API.
There is no current result field for multiple incomplete staging authorities.
Never use one record to authorize deletion of an entire folder or batch, or
expand cleanup from the current record to all retained records. A future recovery
collection needs explicit per-record provenance, selection, accounting and
consumption; it must not be inferred from historical paths.

### Native GTK integration — implementation proposal

Use a compact transient modal GTK dialog with natural word/character wrapping,
20 logical pixels outer padding, 12 between text sections, 16 before actions and
8 between buttons, following [power_dialog._content() and _text()](../c64u_browser/power_dialog.py).
Do not reuse Ultimate Power's busy-operation admission rule: this dialog must open
while the upload owns the foreground. Keep its actions outside disabled busy
controls. Prefer about 480 logical pixels natural width, with narrow-width review
and meaningful accessible labels/tooltips; no new CSS/theme is required.

Bind the dialog to the captured upload job/token and allow only one live instance.
Keep does not send a request until activated. Give Keep the default selection;
map Escape/window close explicitly to Continue. Restore focus to a live sensitive
control. Terminal completion while the dialog is open closes/disables its choices
without retroactive cancellation or deletion. Duplicate responses and late
callbacks are ignored. Maintain B5 status/progress while the dialog is open and
sticky Cancelling only after a request is accepted. Preserve refusal reporting.

Route only eligible staged-upload execution through this dialog; leave downloads,
copy preparation, native Flash upload, managed publication, launches and other
non-upload B5 cancellation on their existing route. Use explicit operation/request
metadata rather than message parsing or the `file.copy.execute` name alone, since
that operation also covers downloads and local copies. Existing modal cancellation
surfaces must share one intent/one-shot authority rather than issuing parallel
requests. Extension to future USB restore UI needs explicit eligibility metadata.

### Future Transfer Recovery and standalone-control transition

**Future design, not implemented:** a separate Transfer Recovery interface offers
Resume, Restart and Discard where individually supported and authorized.

- Verified batch-level recovery means revalidating sources, destinations and
  completed items before preparing remaining work; it is not blind replay.
- Byte-level FTP upload resumption is separate. FTP `REST` + `STOR` firmware
  behavior, offsets, source identity, prefix integrity and interrupted publication
  must be qualified before advertising Resume. Support is unverified here.
- Persistent evidence is another workstream. Current authority is in-memory,
  session-scoped and lost on restart/reconnect. A persisted journal or record must
  not reconstruct deletion or resume authority without a separately reviewed design.
- Restart requires fresh validation and conflict decisions, preserving already
  published files. Discard means explicit reviewed cleanup of a specific supported
  target, never recursive cleanup inferred from a batch or journal.

Do not delete retained uploads merely because Resume is unavailable. No Resume
implementation or firmware qualification is claimed, and no release milestone is
silently inserted into the roadmap.

Plan a transition from the standalone Files Delete Partial Upload control to
contextual results/Transfer Recovery; **do not remove the existing control yet**.
It is already contextual (hidden without matching session evidence), not an
always-visible permanent button. The fallback assessment is:

| Situation | Safe fallback requirement |
|---|---|
| Cancel & Keep or interruption without this dialog | Keep a discoverable reviewed-cleanup route for still-valid unconsumed authority. |
| Network interruption | Retain evidence; cleanup is possible only if the original session/authority remains valid. Reconnection invalidates it. Never promise reconnect-and-delete using the old record. |
| Failed/cancelled preparation or abandoned review | Reservation may be released within the same session, allowing a new explicit review. |
| Failed, refused, cancelled or uncertain execution | Authority is already consumed. The old record cannot retry; offer outcome inspection and a separately reviewed ordinary deletion workflow where appropriate, not automatic reuse. |
| Multiple jobs/restart/expired session | Preserve available historical evidence without inventing authority. A future collection/persistence design is required. |

The current button visibility checks device/session and busy state, not authority
consumption; a failed cleanup can leave it visible although another request is
rejected by Core. Its existing copy suggesting reconnecting to the original
session also does not grant authority across reconnect. These are future
presentation corrections, not changes made in this documentation pass.

### Implementation slices, decisions and acceptance plan

Proposed slices, each requiring implementation authorization:

1. Define explicit staged-upload eligibility and a job-bound cancellation intent
   coordinator; preserve unrelated Cancel routes and B5 one-shot ownership.
2. Implement the native choice dialog and terminal/stale-response lifecycle.
3. Implement terminal-to-fresh-review-to-file-only-cleanup orchestration, ordered
   before refresh, with separate admission and truthful combined result reporting.
4. Replace stale fallback presentation with contextual recovery/outcome inspection;
   only then consider removing the standalone control.
5. Separately design multi-record recovery, verified batch restart/resume and
   persistent evidence. Qualify byte-level REST/STOR before any Resume claim.

**Historical safety decision — superseded by UI-FR.4a, section 14:** At this
checkpoint, Cancel & Delete was approved as
an early choice, but the existing GUI confirms an exact target only after fresh
deletion preparation. The record/target might not yet exist when the early dialog
is shown. Decide whether to retain a second exact-target review (recommended to
preserve the current confirmation contract), or explicitly approve a narrowly
scoped job-bound deferred confirmation contract after reviewing its presentation
and safety conditions. Do not silently treat early intent as existing reviewed
confirmation or bypass the post-interruption preparation/execution checks.

Other implementation decisions: the structured eligibility metadata, handling
natural completion while the dialog is open, combined transfer/cleanup result
copy, and a future multi-record/persistence schema. Proposed handling of natural
completion is no cancellation or cleanup when no eligible incomplete record is
returned. None of these changes is implemented by this section.

Deterministic test plan: fake Core/FTP services, isolated GTK and blocked physical
networking; assert Continue/Escape/close send nothing, Keep sends once and never
deletes, and Delete waits for terminal result plus lease/foreground release.
Exercise queued cancellation, streaming, publication deferral, natural completion,
refused cancellation, unknown publication, empty/no record, completed batch prefix,
and multiple retained records without broad cleanup. Assert new FIFO submissions
without nested waits, strict directory identity, DELE-only dispatch, session
replacement, capacity exhaustion, discarded review, single-use plans, duplicate
responses, late callbacks and admission failure. Fail/lose cleanup responses and
verify exact acknowledged counts, uncertainty and no retries. Verify refresh
ordering, shared B5 status, sticky Cancelling and usable focus restoration.

Physical acceptance is a later separately authorized activity: first review the
confirmation decision and deterministic results, then use disposable data to
qualify observed cancellation timing, light/dark layout, narrow widths, keyboard
routes, retained/completed files and failure presentation. REST/STOR qualification
is a separate firmware/version-specific investigation, not implied by ordinary
upload acceptance. No application launch, tests or device commands occur in this
inspection. **Historical UI-FR.4 outcome: HOLD — subsequently resolved by the
explicit single-dialog authorization in section 14.**


## 14. UI-FR.4a — single-dialog cancellation and deferred cleanup

Historical design checkpoint: the user-facing “Cancel & Delete” label is now
“Cancel & Clean Up”; see [section 15](#15-ui-fr4e2--approved-best-effort-upload-cleanup).
The internal Delete intent and technical safety contracts remain unchanged.

### Final approved interaction; earlier confirmation proposal superseded

The UI-FR.4a authorization resolves section 13's confirmation HOLD. Show exactly
one **Cancel Upload?** dialog for an eligible upload. There is **no second
confirmation dialog**. The earlier recommendation for post-interruption user
confirmation is superseded, retained above only as historical context. This
changes the approved future interaction, not the current implemented GUI.
Fresh service preparation and execution revalidation remain mandatory; automatic
continuation after the approved choice does not bypass those checks.

| Action | Final approved behavior |
|---|---|
| Continue Upload | Dismiss; do not request cancellation or create cleanup intent. Leave the transfer running. |
| Cancel & Keep | Request cooperative cancellation once, wait for the authoritative result, retain incomplete staging/evidence and completed batch files, and perform no deletion. |
| Cancel & Delete | Capture cleanup intent for this transfer and cancellation request, request cooperative cancellation, wait for authoritative completion and released resources, then clean only a qualifying Core-issued staging file through the trusted file-only service. Preserve completed/published files. Never clean unknown publication or retry uncertain cleanup. Report acknowledged cleanup success, failure or uncertainty. |

**Cancel & Keep is the default cancellation choice. Escape and window close mean
Continue Upload.** The dialog must explain that Delete applies only to this
upload's eligible incomplete staging file; it does not roll back completed files
or a whole folder. Cancellation is cooperative, not an immediate FTP stop.

### Inspected authority gaps and proposed minimal mechanism

Existing building blocks are useful but insufficient alone:

- Browser's captured B5 job/token and `ForegroundSlot.owns()` reject stale GUI
  actions. A Browser token is not a Core-issued deletion capability and cannot
  authorize cleanup after it has been released.
- `FileService._Recovery` retains exact record identity, session, staging path,
  operation name, evidence, state and deletion-plan identity. It currently lacks
  the **originating job identity**; `file.copy.execute` or `usb.restore.execute`
  alone cannot distinguish different transfers.
- `CoreJob.request_cancel()` currently returns a boolean, not a unique request
  receipt. Repeated calls before terminal state can return true. B5's one-shot
  guard is valuable but cannot prove which Core cancellation request authorized
  later cleanup.
- Recovery reservation/consumption, strict snapshots and DELE-only execution
  already provide the remaining target and mutation controls. Keep them.

**Proposed mechanism, not implemented:** retain one optional, private, ephemeral
cleanup-intent entry on the exact Core-owned transfer job (or its existing
service-owned execution context). Do not add a persistent journal or make caller
supplied UUIDs, paths, serialized results or Browser tokens into authority.

At service submission, capture immutable eligibility metadata from the actual
copy request/plan or restore plan, the originating CoreJob object, service owner,
and DeviceSession. Extend the private recovery entry's issuance metadata to retain
that originating job identity for both Files and USB restore. Its visible record
can remain evidence; internal object registration proves provenance.

For Cancel & Delete, the service must atomically associate a one-use request
receipt with the accepted cancellation transition on that exact job and install
the pending intent **before** notification can reenter completion handling. Use
short state-only critical sections and a documented lock order; invoke listeners
outside locks. CoreJob's existing `_mark_cancel_requested()`/notification split
is a starting point, not an already-complete atomic intent API. Reject terminal
jobs, duplicate receipts and attempts to upgrade a previously requested Keep or
unrelated cancellation to Delete. An admission/request exception or refused
cancellation invalidates the pending intent and never authorizes cleanup.

The intent binds: exact job identity, owning service/Core, device/session,
accepted cancellation receipt, lifecycle generation, and a one-use state. The
Browser keeps the originating job/token only for UI response validation and
continuation correlation; cleanup itself takes new foreground tokens.

On authoritative completion, the service reads its own terminal job/result and
requires all of the following before claiming the intent:

1. The intent and cancellation receipt are still registered to this exact job,
   owner and unchanged device/session; the lifecycle generation remains valid.
2. The job ended as a qualifying interrupted execution (failed or cancelled),
   not successful publication. Cancellation-request state alone is insufficient.
3. The exact `partial_upload` object in that job's result is still registered
   and available, with its private issuance origin equal to this job. Do not
   accept another job's genuine record, even on the same device/session.
4. Trusted evidence still classifies the stored staging path as a qualifying
   staging candidate. Exclude unknown/completed publication, replacements,
   directory uncertainty, absent authority and arbitrary caller paths.

Claim intent once before cleanup preparation. Fresh preparation reserves the
existing recovery authority and verifies the exact current file and returned
parent-directory identity. Associate the resulting deletion plan with the claimed
intent. A private deferred-execution gate accepts only that association, then
consumes the intent and existing plan/recovery authority before dispatch. No
caller-selected generic deletion plan can be substituted. Execute only the stored
staging file with the existing file-only DELE boundary, snapshot/session checks
and uncertainty accounting; never enter recursive deletion.

Intent states are proposed as pending terminal result → claimed/preparing →
prepared → consumed/finished, with invalidation from every live state. Duplicate
claims, completion callbacks and execution responses cannot start another job.
Preparation/admission failure ends this automatic chain without retry. Existing
recovery reservation release may still permit a later explicit manual recovery
workflow, but cannot resurrect the spent deferred intent. Once execution is
requested, the existing recovery authority remains consumed even on rejection.

Invalidate intent on terminal no-op classification, another session/device,
Core/service shutdown, owner/coordinator closure, abandoned continuation, expired
associated review plan, or completion of the chain. Session/lifecycle generation
checks must also reject late issuance and callbacks after disconnect, even if the
physical device is unchanged. Keep retention bounded with the originating job
and existing recovery/plan bounds; no indefinite detached queue. If a scheduling
conflict prevents the one continuation, report cleanup not started and retain
available evidence rather than installing an automatic retry loop. Restart never
restores this authority. No new persistent recovery journal is needed.

### Exact post-completion handoff and refresh sequencing

Current source path remains section 13's traced path:
`bind_job_cancel()` → captured `job_cancel_callback()` → `cancel_transfer()` →
`OperationPresentation.request_cancel()` → service/scheduler cancellation →
`CoreJob.request_cancel()`. The proposed eligible-upload route first shows the
single dialog; its confirmed action then uses B5's one-shot sender, with the
Delete variant calling the intent-aware service transition described above.
Unsupported jobs retain the current direct Cancel route.

Upload adapter/lease scopes unwind before `execute_plan()` returns and before
Core publishes the terminal result. `CoreJob.run()` assigns result/state, sets
its completion event and emits `finished`. The GUI's event, initial-snapshot and
snapshot-fallback paths converge on guarded `run_file_job().finish()`.
That calls `end_file_job()` to release the old token and restore sensitivity,
then `operation.finish()`, then the feature completion callback. **The cleanup
coordinator begins from this released-foreground callback, on the GTK thread.**
Do not begin from progress, cancel-requested, recovery issuance, or a worker-side
listener; do not block GTK or wait inside a scheduler task.

Refactor `start_copy().finished()` conceptually into outcome capture, optional
cleanup chain, then refresh/report. The current callback immediately invokes
`self.run(refresh, refreshed)` and would compete for busy/foreground admission.
Do not run it first and then attempt cleanup. Capture the original result and
intent; submit fresh preparation through `run_file_job()`; after preparation's
own foreground release, submit its bound execution plan through a new factory.
This internal review/validation has **no additional confirmation dialog**.
Perform the ordinary refresh once after the chain has completed or been safely
declined, with job/session/generation guards on its status updates.

Scheduler lane bookkeeping can finish after terminal notification, but subsequent
jobs queue normally on the same FIFO lane. Never acquire an inline nested lane or
wait for queued cleanup from the old worker. If another action wins admission,
stop/report the cleanup chain; do not steal ownership. Close/reconnect and managed
restoration callbacks must not revive old intent. Old transfer progress and late
refresh callbacks cannot overwrite a new cleanup job's B5 status.

### Eligibility derived from actual execution plans

| Operation | Proposed eligibility and exclusions |
|---|---|
| Single local-to-C64U staged addition | Eligible execution job; cancellation may still produce no partial file. |
| Multiple selected files or folder upload | Eligible when the actual plan includes remote staged file additions. Only the interrupted file's issued record can be cleaned; retain completed files, created directories and remaining-step accounting. Directory-only and replacement-only plans are ineligible. |
| Mixed addition/replacement upload plan | Eligible because additions can produce candidates, but a replacement interruption never authorizes cleanup. Explain this narrow scope rather than promise rollback. |
| USB restore | Service design can support restore additions through the shared issuer and original restore job; replacement-only restore is ineligible. Current Files GUI has no restore entry point, so this is future UI eligibility, not a newly exposed control. |
| Download, local copy, copy preparation | Ineligible; retain existing Cancel behavior. A `file.copy.execute` name alone cannot identify upload direction. |
| Native Flash, managed transaction publication, launch, SID and other foreground jobs | Ineligible for this staged-upload dialog; retain existing feature-specific cancellation contracts. |

Use explicit plan/request metadata, not message parsing or operation-name
prefixes. Current serial batch execution stops at its first interruption and
returns at most one `PartialUpload`; multiple historical records do not expand
intent. If future code returns multiple records, require separately bound,
explicit per-record semantics before extending this design. Do not silently
iterate the recovery store. Resume and persisted recovery remain the separate,
unimplemented work described in section 13.

### Failure, uncertainty and closing policy

| Condition | Required behavior |
|---|---|
| Transfer finishes while the choice dialog is open | Close/disable stale choices; no retroactive request or cleanup. |
| Cancellation accepted too late; job succeeds | Preserve acknowledged completion; invalidate intent and report no eligible cleanup. |
| No partial record | No deletion, even if job is cancelled; report the actual transfer result. |
| Unknown publication | No staging/final-path guessing; no cleanup; retain uncertainty and inspection guidance. |
| Changed device/session or lost authority | Reject the deferred chain; retain history, never reconnect-and-delete with old authority. |
| Preparation fails, file absent/changed/directory, or returned-directory mismatch | No dispatch. End intent without retry; retain the exact failure and available evidence. |
| Cleanup submission/admission rejected | Report not started/rejected according to evidence. Do not silently restore consumed execution authority or retry. |
| DELE acknowledged | Count only the acknowledged staging-file removal; keep the original upload/batch result alongside cleanup outcome. |
| DELE response lost | Report uncertain cleanup, not success or definite rejection. Do not retry or reuse authority. |
| User closes Argonaut during cleanup | Preserve `Browser.close()` refusal while busy; closing is not deletion cancellation or another confirmation. At gaps before dispatch, closure invalidates pending intent. Forced shutdown can lose in-memory evidence; never claim cleanup completed or replay after restart. |

No automatic cleanup follows Keep, Continue, Escape or window close. A later
manual recovery action remains separately authorized. The standalone recovery
control transition and consumed-record limitations from section 13 remain; this
single-dialog design does not remove the fallback yet.

### GTK interaction and implementation sequence

Use one compact native transient modal **Cancel Upload?** dialog with 20 logical
pixels outer padding, 12 section spacing, 16 before the footer and 8 between
buttons, following `power_dialog._content()`/`_text()` conventions. Wrap long text
and test narrow allocations without changing the application minimum dimensions.
Keep dialog controls outside busy controls so an active upload does not disable
them. One instance per captured job; no blocking waits.

Give Cancel & Keep a dedicated response ID, default response and initial keyboard
focus. Give Continue a different response ID. Explicitly map Escape, delete-event
and close-request to Continue, never to the Keep default. Enter follows the
focused/default action; Delete requires explicit activation and must never be
triggered by dismissal. Use a responded latch before any callback, retain captured
job/token/session validation, and restore focus to an existing sensitive widget.
Use B5 for subsequent cancellation/preparation/cleanup status, preserving sticky
Cancelling, one-shot requests, terminal precedence and focus restoration. No
second dialog is introduced by internal cleanup preparation.

Proposed implementation slices and dependencies:

1. Core metadata and one-use intent/request receipt; exact origin-job registration
   for Files and USB; lifecycle invalidation and authoritative terminal matching.
2. Single GTK choice dialog and eligible-job routing; preserve unsupported jobs'
   existing Cancel behavior and deduplicate all cancellation surfaces.
3. Foreground-safe preparation/execution continuation, no second confirmation,
   refresh sequencing and combined outcome presentation; depends on slices 1–2
   and UI-FR.2/2a/3 safety boundaries.
4. Independent review and deterministic acceptance, then separately authorized
   physical qualification. Transfer Recovery collections/persistence/Resume remain
   later work, not dependencies for this single-record workflow.

### Regression and acceptance plan; disposition

Use fake Core/FTP, isolated GTK and blocked physical networking. Test Continue,
Keep and Delete separately, exact job/device/session/request binding, forged or
other-job evidence, terminal races around intent registration, and duplicate
responses/callbacks. Test no partial, queued cancellation, accepted late success,
unknown publication, completed batch prefixes, mixed replacement/addition plans,
capacity limits and consumed/reconstructed records. Assert lease release and old
foreground release precede new admission, no nested waits, refresh-after-cleanup
ordering, session replacement/close at every handoff, and no stale status updates.
Exercise strict directory identity and DELE-only behavior, failed preparation,
admission refusal, acknowledged removal, lost reply, single use and no retry.
Verify Enter's Keep default separately from Escape/window-close Continue, busy
close refusal and B5 focus restoration. Preserve existing generic deletion,
unsupported-job cancellation and managed-library regression suites.

Later physical acceptance requires separate authorization and disposable data:
check actual timing and acknowledged outcomes, keyboard/dismissal behavior,
light/dark and narrow-layout readability, retained completed files and contextual
failure messages. FTP still cannot guarantee durable remote object identity;
physical observations do not establish byte-level Resume or REST/STOR support.
No application launch, networking, tests or device commands are part of this pass.

The confirmation-policy decision is resolved by explicit UI-FR.4a authorization.
Exact internal API/field names, lock ordering and expiry wiring remain implementation
review details with the invariants above; they do not require a second dialog or
a persistent journal. No unresolved authorization design blocker remains.
**PASS — ready for UI-FR.4a implementation planning.** No implementation or
publication is authorized by this documentation checkpoint.


## 15. UI-FR.4e.2 — approved best-effort upload cleanup

Argonaut 1.10 provides one cancellation dialog: **Continue Upload**,
**Cancel & Keep**, and **Cancel & Clean Up**. The upload continues while the dialog
is open. Cancellation is cooperative. Cancel & Keep remains the default
cancellation choice; Escape and window close act as Continue Upload.

Cancel & Clean Up authorizes one safe cleanup preparation/execution sequence
after authoritative transfer completion and local resource release. It attempts
to remove only the verified incomplete staging file from that upload. Cleanup is
best effort: the C64U may still be updating the file, and verification may refuse
cleanup. No second confirmation, fixed delay, stability polling, or automatic
mutation retry is introduced. Any earlier deletion promise or proposed mandatory
stabilization is superseded by this policy; historical evidence above is retained.

Presentation distinguishes acknowledged removal, cleanup not necessary, unsafe
verification/admission, definite deletion rejection, and uncertain outcome.
Acknowledged removal is required to report success. When a verified partial file
remains or may remain, report its captured remote path and suggest manual review;
never substitute current selection or assert definite presence after uncertainty.

Core-issued, job-bound authority, session checks, strict directory identity,
file-only DELE, single-use plans, and uncertainty accounting remain mandatory.
Completed files and uncertain publication are never cleanup candidates. Existing
Delete Partial Upload remains in place with unchanged eligibility; consumed
authority is never recreated automatically. Users can inspect the folder and use
ordinary reviewed deletion where appropriate. UI-FR.4e.1 diagnostics remain intact.
See [FTP recovery contracts](C64U-FTP.md#best-effort-cancel--clean-up-presentation).

Implementation remains pending independent review and controlled physical visual
acceptance; this entry does not mark the UI audit Accepted.


## UI-Files.1 — standalone recovery control superseded

The approved Files UI removes the standalone **Delete Partial Upload** button
and its exclusive Browser plumbing. Earlier requirements above to retain that
control are historical and superseded. Ordinary reviewed Delete is the manual
fallback after inspecting the remote folder; it remains a separate operation.
Cancel & Clean Up, service recovery authority, diagnostics, and future resumable
upload plans are unchanged. Rename, ordinary Delete and Paste conflict dialogs
use native padded content and wrapped, selectable paths. This does not mark
visual acceptance complete or change deletion/copy lifecycle contracts.

## UC-1 read-only REST inspection

Device Details offers **Inspect REST Compatibility** in its collapsible hardware section. Recognition validates both
`/v1/version` and `/v1/info` envelopes and identity field types, accepting API
`0.1` regardless of product spelling. Other API versions require qualification.
This is protocol evidence, not authenticated hardware attestation or a grant to
operate the device. Raw product and firmware identity remain diagnostic data.

Inspection enumerates `/v1/configs` through the existing configuration parser.
It retains up to 64 advertised categories and inspects at most four categories,
256 settings per category, with the existing 64 KiB response and timeout limits.
Unavailable categories/metadata remain unknown. Credential values are never
returned in inspection observations. Existing hidden fields, validation and
qualified read-only exceptions are unchanged. No settings are written or saved.

Inspection never installs an operational Core session, saves credentials or
persists capability grants. Reset/reboot, memory/DMA, cartridge execution, SID
playback, streaming, drive/configuration mutation and FTP publication remain
unqualified by inspection. FTP requires separate qualification. Existing
operational admission and physically verified Beige/Founder's Edition behavior
remain unchanged. Future capability-based command gating needs independent
hardware/firmware and operation-specific evidence. Historical evidence above
remains valid; recognition does not upgrade its qualification level.

### UC-1a inspection diagnostics

Configuration enumeration and each inspected category carry an immutable
observation status: Available, Unsupported, Authentication required,
Communication failed, Invalid response, or Unknown. Unsupported requires
structured endpoint/operation evidence (HTTP 404/405/501); a timeout or invalid
response does not establish lack of support. Error kinds, HTTP status codes and
typed exception causes determine the status; exception messages are neither
parsed nor displayed. Unclassified failures remain Unknown.

Successful category observations survive failures elsewhere. Authentication
failure stops further metadata requests, preserving earlier results and marking
remaining categories Not inspected. Unexpected unclassified exceptions also stop
further inspection. Existing request counts, limits, credential
redaction and operational restrictions remain unchanged. Available describes
read-only inspection evidence and grants no operational compatibility.

### UC-1b compact hardware and REST presentation

The dedicated Capabilities tab proposal is superseded. Device Details now groups
hardware fields and REST inspection in the native **Hardware & REST Information**
expander (the heading was shortened by UI-DD.1a). It starts collapsed, retains expansion while Settings
remains open, and resets after actual destruction. Expansion is not persisted
and does not contact the device. Existing scrolling and native spacing are used;
other Settings pages are unchanged. The accepted UI-DD.1/UI-DD.1a layout adds
independent Advanced Connection Settings and Network Discovery expanders; all
three start collapsed, retain state during Settings reuse and Keep editing, and
reset after actual destruction. Advanced contains the existing REST/FTP ports.
Saved Connections, hostname/password, ordinary actions and shared feedback remain
outside the expanders. Expansion itself performs no device operations.

The summary shows reported product, firmware, API version, REST recognition,
category count, successful metadata inspections, attempted metadata requests,
and sanitized failure states. Failed enumeration shows an unknown count, not
zero. No category list or configuration values are duplicated: Ultimate Menu
remains the configuration browser/editor. REST recognition grants no operational
qualification; the existing qualified-device admission remains unchanged.

Inspection uses the Device Details editor endpoint and password, including valid
unsaved drafts labeled **Unsaved endpoint**, never an unrelated active device.
The endpoint is visible; invalid targets disable inspection. Saved identity and
credential binding remain enforced by Core. One request sequence may be in
flight; duplicate actions are blocked. Editing the endpoint/password, switching
profiles or replacing the session invalidates results without claiming to cancel
running transport work. Actual closure retires callbacks and listeners; Keep
editing does not. No retries, polling, automatic inspection, or new REST requests
were added. No credentials, profiles, or inspection results are saved by inspection.

## UI-DD.1 — compact Device Details implementation

Historical milestone: the port placement and two-expander presentation below
were superseded by UI-DD.1a. Geometry and test observations remain historical
evidence; the current accepted layout is recorded in UC-1c below.

This bounded implementation advances the previously approved Device Details
layout; it does not implement the separate UI-22 credential redesign or UI-25
instructional-text reduction. The four Settings pages and 740 × 680 default
remain unchanged. The Capabilities tab proposal remains superseded.

Device Details now places Saved Network Connections and profile status first,
then connection name, host, a shared REST/FTP port row, password/visibility,
existing credential status and Remember/Forget/Retry controls, automatic-connect,
grouped New/Save/Delete, distinct Test/Connect, and shared operation feedback.
All ordinary connection controls remain outside the optional sections. Existing
instructions are retained. Credential controls use native wrapping layout only;
tri-state UNKNOWN, explicit-save semantics, stored-credential binding, and
Development/Portable behavior are unchanged. Long selector names ellipsize with
the full name available in a tooltip and the existing editable name field.

Hardware Information & REST Compatibility and Network Discovery are independent
native expanders, initially collapsed. Tab changes, Settings reuse and Keep
editing retain each state; actual destruction/recreation resets both. Expansion
neither dirties profiles nor starts device/credential operations. Collapse keeps
candidate lists, subnet input, progress, feedback and running work intact. Shared
operation feedback remains outside the expanders. Late operation completions no
longer update destroyed dialog widgets. Core, transport, discovery and persistence
semantics are unchanged, including UC-1/UC-1a/UC-1b inspection safeguards.

### Measured X11/Xvfb geometry

Measurements below are actual GTK logical allocations, not requested sizes.
Temporary preferences, fake credentials/transports and pre-construction network
guards were used. No physical device was contacted.

| Scenario | Requested window | Actual window | Device Details viewport | Content extent / viewport height |
| --- | --- | --- | --- | --- |
| Normal Sans 10, collapsed | 740 × 680 | 740 × 680 | 738 × 607 | 607 / 607; no vertical scrolling required |
| Normal Sans 10, narrow | 520 × 480 | 520 × 485 | 518 × 412 | 592 / 412; vertical scrolling |
| Sans 18, long content, light | 520 × 480 | 637 × 689 | 635 × 612 | 2796 / 612; vertical scrolling |
| Sans 18, long content, dark | 520 × 480 | 637 × 689 | 635 × 612 | 2796 / 612; vertical scrolling |

At default size, ordinary connection and credential controls fit; the Test/Connect
row ends at viewport y=472. At narrow size every ordinary control and the Close
action remains reachable, with no horizontal clipping. Device Details' measured
minimum width is 349 pixels at normal text and 507 at 18 points. The existing
notebook tab strip and non-scrolling Game Library Settings page impose the shared
window minimum at larger text, including the five-pixel normal narrow height
excess. Those unrelated surfaces were not changed. Initial long-profile width
growth was corrected locally using selector ellipsization, wrapped labels and
native credential-control wrapping; no global CSS or dependencies were added.

### Keyboard and remaining acceptance

Isolated XTest Tab/Shift+Tab checks traverse ordinary controls and exclude
collapsed children. Password Enter still invokes Connect, never Save. Native
keyboard expansion works; collapse does not leave focus in hidden content.
Focus remains usable after inspection, discovery and Settings closure. The
normal native light/dark presentations and enlarged-text allocations were checked.

The installed GTK emits a `gtk_root_get_focus` critical warning when traversing
collapsed selectable labels. This was reproduced with a minimal native
Gtk.Expander/selectable-label fixture without Argonaut; traversal assertions
still pass. Retain it for toolkit/platform review rather than claiming it fixed.
At this milestone, independent physical visual acceptance remained required:
check both themes, normal and enlarged fonts, desktop scaling, long names/errors,
both expanders, keyboard focus/reveal controls, scrolling and Close. This visual
review can use fake devices; it does not authorize or qualify hardware operations.

### UI-DD.1a — Device Details presentation refinement

The connection form keeps Saved Network Connections first. Connection name,
Hostname / IP and Password now use matching 16-character label columns with
native wrapping; Connection name occupies one line at the normal Settings width.
Input expansion, password visibility, validation and callbacks are unchanged.

After the ordinary actions and shared feedback, three independent native
expanders appear: **Advanced Connection Settings**, **Hardware & REST Information**,
and **Network Discovery**. Advanced contains the existing compact REST/FTP port
row (defaults 80/21). Custom ports, validation while collapsed, saved profile
round trips and endpoint identity rules remain unchanged. Hardware's shorter
heading replaces Hardware Information & REST Compatibility; its content and
inspection contracts are unchanged.

All three sections start collapsed, retain state across tab changes, Settings
reuse and Keep editing, and reset after destruction. Collapse retains values
and results. Expansion itself does not perform device, credential or persistence
operations. Ordinary hostname/password fields and connection actions remain
outside the expanders. Native Tab/Shift+Tab excludes collapsed ports and other
collapsed content; expansion and focus recovery remain keyboard accessible.

Offline X11/Xvfb measurements (actual allocations, not requested sizes):

| Scenario | Requested | Actual Settings | Device Details viewport |
| --- | --- | --- | --- |
| Normal text, collapsed | 740 × 680 | 740 × 680 | 738 × 607 |
| Narrow, normal text | 520 × 480 | 520 × 485 | 518 × 412 |
| 18-point, long content, all expanded, light/dark | 520 × 480 | 637 × 689 | 635 × 612 |

At normal default size ordinary controls fit without vertical scrolling; the
Test/Connect row ends at y=430 in the viewport. Narrow and enlarged layouts use
vertical scrolling without horizontal clipping. Device Details minimum width
remains 349 pixels normally and 507 pixels at 18 points. Existing shared Settings
minima described in UI-DD.1 remain unchanged; no shared window or global CSS
changes were needed.

The UI-DD.1a acceptance procedure, subsequently accepted within the supplied
desktop scope recorded below, called for opening Settings with offline fake
fixtures at normal and 18-point text in both themes, checking the aligned labels,
all eight expansion combinations, long values, scrolling, visible focus and
password Enter → Connect. The previously documented native GTK focus warnings
remain a platform review item; automated focus assertions pass. No physical
C64U or live REST/FTP operation is required for this presentation review.

### UC-1c — supplied acceptance and publication reconciliation

The supplied final review records acceptance of the UI-DD.1/UI-DD.1a desktop
layout, independent expansion, keyboard navigation and focus checks. The current
layout is Saved Connections first, aligned name/hostname/password labels,
ordinary actions and shared feedback, followed by three independent, initially
collapsed expanders: **Advanced Connection Settings**, **Hardware & REST
Information**, and **Network Discovery**. REST/FTP ports belong to Advanced;
hardware fields and the compact REST inspection summary belong to Hardware.
Earlier two-expander and always-visible-port requirements are superseded.

The supplied Beige and Founder's Edition read-only REST acceptance is recorded
in [Ultimate compatibility](ULTIMATE-COMPATIBILITY.md#uc-1c--supplied-read-only-acceptance).
This acceptance was supplied for publication reconciliation; UC-1c itself made
no physical device contact. It does not newly qualify FTP or consequential
machine operations. Desktop acceptance is limited to the supplied checks, not
all platforms, themes, fonts, scaling or display configurations. The historical
Xvfb geometry and GTK warning records above remain valid; other desktop/font/
scaling combinations still need qualification, and the warnings are not claimed
fixed by this documentation update.
