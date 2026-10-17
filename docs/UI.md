# Argonaut UI design and audit — 1.10 spit-shine

## 1. Purpose and scope

This permanent design and audit record supports visual consistency, usability,
and release readiness for Argonaut 1.10. UI-00 authorizes documentation only.
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
are UI-01 through UI-25; their original mapping is awaiting the audit record.
Decision references below are stable descriptive anchors, not replacement finding IDs.
Section 9 reconciles repository evidence, records approved resolutions and
distinguishes remaining audit work from resolved material conflicts.

## 2. Design principles

The following direction is **Approved**:

- Native GNOME/GTK appearance with subtle Argonaut branding.
- Consistent typography, spacing, buttons, icons and status presentation.
- Preserve existing functionality and keyboard accessibility.
- Prefer shared styling components over duplicated per-tab CSS.
- Avoid unnecessary gradients, shadows and decorative elements.
- Preserve the established dual-pane Files layout.
- Inspect the complete interface before implementation.
- Implement changes in small, independently testable slices.
- Keep major Ultimate Menu redesign and new Game Library features outside the
  initial spit-shine scope.

## 3. Screen audit inventory

This document transcribes the observations and decisions supplied with UI-00;
it does not claim a fresh visual inspection or a completed whole-interface audit.

| Area | Evidence and coverage |
| --- | --- |
| Global header, styling and status | Supplied direction recorded below; state coverage still pending. |
| Files | Supplied findings and Beige storage observation recorded below. |
| Settings → General | Supplied direction recorded; renderer/dependency verification pending. |
| Settings → Device Details | Supplied structural direction recorded; behavior/regression verification pending. |
| Settings → About | Pending inspection. |
| Settings → Game Library | Pending inspection. |
| Ultimate Menu | Pending inspection; major redesign excluded. |
| Drives | Pending inspection. |
| SID Jukebox | Pending inspection. |
| Streams | Pending inspection; separate Fit to Window direction recorded. |
| Game Library | Pending inspection; new features excluded. |
| Test Lab / Developer Mode | Pending inspection; relocation requires separate functional testing. |
| Confirmation and error dialogs | Pending inspection. |
| Progress indicators | Pending inspection. |
| Context menus | Pending inspection. |
| Tooltips and keyboard navigation | Pending inspection across the complete interface. |
| Connected, disconnected, loading and error states | Pending inspection across relevant screens. |

No findings are inferred for screens awaiting inspection.

## 4. Approved design decisions

### Global controls and status

**Approved:** remove permanent blue active-file-pane outlines while retaining
keyboard focus indicators. Use consistent GTK button hierarchy and styling,
with Argonaut blue as a restrained accent. Improve disconnected and empty states.

Replace separate header Reconnect/Disconnect buttons with one contextual
primary Connect/Disconnect control. Preserve Reconnect as a secondary action
within an appropriate connection menu or recovery workflow. Preserve underlying
connection/session semantics, keyboard access and existing recovery protections;
the exact secondary-action placement is an implementation design detail.

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

**Approved structural direction:** keep Saved Connections at the top, followed
by the selected profile and accessible connection controls. Always visible:

- Selected profile and Hostname/IP.
- REST and FTP ports.
- Password field and visibility control.
- Test and Connect actions.
- Profile management actions.

Provide two independently expandable sections:

| Section | Default | Contents |
| --- | --- | --- |
| Hardware Information | Collapsed | Serial number, saved device ID, box model, firmware-reported C64U model, notes and relevant hardware details. |
| Network Discovery | Collapsed | Discover, subnet input, Scan Subnet and associated feedback. |

Both sections start collapsed. Either can expand independently, and expanded
state persists while Settings remains open. Reopening Settings restores collapsed
defaults. Reduce unnecessary window height and provide scrolling when expanded
content exceeds available space.

Preserve the distinction between editable box label and firmware-reported model.
Preserve saved Ethernet/Wi-Fi profile distinctions, device identity and credential
contracts, Development-mode session-only passwords, and Test versus Connect
semantics. Do not introduce implicit password persistence. Existing discovery
behavior and saved-connection semantics remain contractual constraints; see
[Device Details stabilization](DEVICE-DETAILS-STABILIZATION.md).

## 5. UI punch list

**Inventory reconciliation required:** UI-00 requests the original UI-01–UI-25
numbering, but supplies no ID-to-finding mapping. No existing mapping was found
in tracked repository text. The reservations below protect those identifiers;
they are not invented findings and do not constitute the completed punch list.
Replace each reservation with its original audit entry when supplied. Do not
assign the decisions above to guessed numbers.

All reservation statuses are **Proposed** solely for reconciliation. This does
not downgrade the explicitly Approved design directions in section 4. Priorities,
slice assignments and acceptance notes must be reconciled with the original audit.

| ID | Area | Finding | Proposed or approved change | Priority | Status | Implementation slice | Acceptance notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| UI-01 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-02 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-03 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-04 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-05 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-06 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-07 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-08 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-09 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-10 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-11 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-12 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-13 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-14 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-15 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-16 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-17 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-18 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-19 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-20 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-21 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-22 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-23 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-24 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |
| UI-25 | Awaiting original audit | Mapping unavailable | Reserved; no change assigned | Unassigned | Proposed | Unassigned | Original entry required; not implementation evidence. |

## 6. Proposed implementation slices

These are **Proposed** planning groups, not implementation authorization. Revise
boundaries after the full audit identifies shared components. Priorities and
finding-to-slice assignments require review with the original inventory.

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

Before implementation, complete the remaining screen/state audit, reconcile all
25 original findings, review proposals and shared-component boundaries, and obtain
separate implementation authorization. For each later slice record the baseline,
changed components, verification evidence, outstanding issues and reviewer decision.

- Verify native GTK presentation, consistent hierarchy/spacing and restrained branding.
- Verify pointer and keyboard workflows, visible focus, selected-file highlighting,
  tooltips, context menus and accessible controls across applicable states.
- Verify dual-pane navigation, file operations and shortcut behavior remain intact.
- Verify inaccessible storage identifies the affected root without a false
  disconnected-device state; keep operation warnings distinct from connection state.
- Verify contextual Connect/Disconnect and retained reconnect/recovery routes,
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
| Original UI-01–UI-25 inventory | Missing from supplied request and tracked repository text. Reserved IDs await original mapping, priorities and acceptance details. The resolution authorizes retaining these reservations for documentation review; mapping remains an audit follow-up, not an unresolved material design conflict. |
| Earlier header history | Roadmap B4 records separate Reconnect/Disconnect controls and prior acceptance. The new contextual control is Approved future direction; earlier behavior and acceptance remain historical evidence. Preserve recovery and stale-settings protections. |
| Earlier Device Details history | Roadmap B3 records Saved Network Connections near the bottom and prior layout acceptance. Saved Connections at the top and new collapsible sections are Approved future direction, not already implemented or accepted. |
| Scaling | 100%–600% and 25% steps remain Proposed; renderer range, maximum and GTK logical pixels require verification. |
| Presentation details | Storage-warning wording, exact preference groupings, status-bar layout and exact secondary Reconnect placement remain design details. Primary Connect/Disconnect, secondary Reconnect and preservation of B5 behavior are Approved. |
| Functional boundaries | Test Lab placement and channel behavior are Approved as resolved below. Streams Fit to Window details and Instant Replay dependency review remain outstanding. |
| UI-00 reconciliation resolution, 2026-10-17 | User resolved the Test Lab, connection-control and status-bar questions. Documentation-only approval; no implementation or acceptance claimed. Preserve UI-01–UI-25 and all seven unnumbered candidates, with final candidate IDs deferred until the remaining visual audit is complete. |
| Remaining audit | All pending coverage in section 3 must be inspected before implementation; no findings invented. |

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
| Drives | Current approved UI requirement | Recorded settled direction: Enabled switch, Write Protect checkbox, Run label preserving mount-if-needed, shared Select Disk Image. Removing model/ROM controls remains investigation, not approval. Visual inspection is still pending. | [Roadmap](ARGONAUT-ROADMAP.md), E. Drives redesign. |
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
| Quick Connect / Machine tab | Historical or superseded requirement: do not restore either. New contextual connection control supersedes the accepted separate-button presentation only; secondary Reconnect remains within an appropriate connection menu or recovery workflow, with unchanged session semantics. | [Release 1.6](../packaging/RELEASE-1.6.md), Quick Connect paragraph; [Current state](CURRENT-STATE.md), B4; UI-00 Global controls. |
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
remaining material conflict was identified in this documentation pass. Detailed
visual choices and the remaining audit still require later review.

| Decision | Earlier discrepancy or requirement and sources | Approved resolution / remaining work |
| --- | --- | --- |
| Test Lab navigation and channel behavior | UI-00 and [Roadmap](ARGONAUT-ROADMAP.md), I, request removal from the normal top-level experience and Developer Mode access. [Developer Mode](DEVELOPER-MODE.md), opening/channel paragraphs, already gates Stable after restart and always enables Test Lab in Development; [Next pass](NEXT-PASS.md), Stable 1.9 boundary, records that gating. | **Approved:** Settings → Developer → Open Test Lab; remove the normal top-level Test Lab tab in both Stable and Development. Preserve Stable restart/enablement gating without bypass and Development always-available access without additional restrictions. Preserve all functionality, diagnostics, regression capabilities, service shutdown/isolation and reports. Documentation only; implementation remains unauthorized. |
| Connected reconnect access | UI-00 approves one contextual Connect/Disconnect header control but requires reconnect/recovery. [Current state](CURRENT-STATE.md), B4, and [Roadmap](ARGONAUT-ROADMAP.md), B4, retain an explicit connected Reconnect path and stale-settings protections. | **Approved:** one contextual primary Connect/Disconnect button, with Reconnect retained as a secondary action in an appropriate connection menu or recovery workflow. Underlying connection/session semantics remain unchanged. Preserve keyboard access and stale-settings protections; exact placement remains a later design detail. |
| Status-bar composition | UI-00 requests distinct connection versus operation messages. [Current state](CURRENT-STATE.md), B5, protects active operation/Cancelling from ordinary messages and uses phase/counts without a progress bar. | **Approved:** redesigned status bar preserves existing B5 cancellation, progress, error, uncertain-outcome and foreground-job behavior; lifecycle and device-operation safety must not weaken. Separate connection state from operation warnings. Exact visual composition remains Proposed; separate regions are an option, not an approved layout. No new progress model is authorized. |
| Switch consistency versus credential state | UI-00 General and [Roadmap](ARGONAUT-ROADMAP.md), Design principles, prefer switches for persistent binary preferences; [Device Details](DEVICE-DETAILS-STABILIZATION.md), UNKNOWN correction, requires disabled/indeterminate Remember and explicit Save Profile semantics. | Treat Remember password as an action-specific credential choice, retain the current tri-state presentation and save boundary. Do not convert it to an immediate-saving binary switch. This is a preservation constraint, not authorization to redesign credentials. |
| New inventory numbering | UI-00 requires original UI-01–UI-25 mappings, still absent from tracked Markdown and the supplied request. The amendment forbids duplicate tasks or gratuitous new IDs. | Preserve UI-01–UI-25 and the seven additional unnumbered candidates. Obtain the original mapping and deduplicate during audit follow-up. Do not assign final IDs to new candidates until the remaining visual audit is complete and distinct findings are confirmed. |

The source-level discrepancies with explicit supersession (Device Details placement,
B4 presentation, C2 retirement, PA-5.13 capabilities) are recorded above rather
than resolved by declaring one whole document superior. No technical contract is
changed by these approved presentation decisions or remaining design proposals.

### Additional punch-list candidates — unnumbered pending deduplication

These are **Proposed audit candidates**, not observed new visual defects or new
implementation authorization. Without the original 25-entry mapping, uniqueness
cannot be established; therefore no UI-26 or later ID is assigned. Per the approved
resolution, final IDs must wait until the remaining visual audit is complete.

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
resolved. Original inventory mapping, seven unnumbered candidates and remaining
visual inspection are explicitly retained as audit follow-up, not claims of
completed audit coverage. **PASS — ready for documentation review.** No source
changes, application tests, implementation, commits, pushes, publication or C64U
contact are authorized by this resolution.
