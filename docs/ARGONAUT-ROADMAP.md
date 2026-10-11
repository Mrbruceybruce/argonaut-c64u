# Argonaut roadmap

## Managed Import Phase 3B-2A — authorization and host snapshots approved; pending manual publication

Published compatibility baseline: `9b04bbe748a2216c32114116f3e2880c72d87cb5`
(`Add versioned managed import resource policies`). Earlier publication/status
entries below describe historical checkpoints.

Core now exposes internal review, explicit confirmation, one-use preparation and
owned-snapshot discard methods. No new UI action is exposed; Import remains
disabled. Confirmation states: “Stage and Verify prepares files but does not
import them into the Game Library.” In this slice all preparation is host-only;
there is no remote staging, upload, remote readback or manifest publication.

Consent lives only in bounded Core memory, binds the immutable schema-2 transaction,
device/session/library, manifest and policy, and expires after 120 seconds
(including preparation). A copied token, transaction UUID or journal is not consent.
Reconnect/selection changes invalidate pending consent. Preparation consumes it
once, even on admission failure, and uses the existing device scheduler lane with
busy rejection. Manifest identity/revision/digest are reread before and after
snapshots; state and captured policy are checked between streaming chunks.

Local sources are revalidated and read with fixed 8192-byte buffers; remote sources
use the existing session-bound managed FTP streaming reader. Exact size and SHA-256
must match the approved transaction. Source bytes consumed are charged even on
failure/cancellation, separately from payload and planned future transfers.
Private host snapshots enforce disk limits using allocated file blocks/logical
size and directory allocation, with space checks and bounded writes.

Snapshot ownership is descriptor-based, exclusive, restrictive and rejects symlinks.
Failure/cancellation cleans only proven owned files, releases FTP leases and returns
non-ready accounting evidence. Successful snapshots need explicit discard or Core
shutdown; restart never adopts/resumes or automatically cleans old directories.
Uncertain cleanup preserves unexpected content and blocks further preparation in
that Core session. Runtime evidence is volatile; durable transaction journals
remain separate and unchanged. No journal schema or reserved state is added.

Validation: 341 combined affected offline tests passed without skips, followed by
31 passing snapshot/admission tests including four additional lifecycle probes.
Fake FTP checks verified lease release and absence of mutation verbs. No physical
C64U contact or acceptance. Phase 3A's 256 MiB planning-read budget, schema-1/2
compatibility and POSIX/cooperating-writer journal limitations remain unchanged.
Remote staging, execution/publication, importing and Phases 3B-2B/3B-2C/3C remain
unimplemented by this checkpoint.

Independent final review approved this authorization and host-snapshot checkpoint
for publication. The review confirmed Core-owned one-use authorization with a
120-second deadline and captured transaction/device/session/library/manifest/policy
identity; bounded 8192-byte local and remote streaming; exact size and SHA-256
verification; actual source-read and temporary-disk accounting; and incremental
filesystem allocation accounting. Cleanup retains admission until proven complete.
Initialization failures preserve primary and cleanup-error evidence; uncertain
cleanup blocks further preparation. Cancellation and managed FTP lease release
remain protected. No remote mutation or enabled Import action was introduced.

Evidence: 178 previously passing targeted offline tests; 23 independently rerun
focused tests all passed with no skips, including the eight initialization-cleanup
regressions and the original allocation-setup/interrupted-removal reproduction.
No physical acceptance is required for this offline checkpoint.

Limits remain: POSIX filesystem assumptions, allocation races and conservative
estimates rather than OS disk quotas, no implemented recovery for uncertain
cleanup, and non-resumable snapshots. No remote staging, upload, readback or
manifest publication exists. Phases 3B-2B/3B-2C/3C remain unimplemented.

### Bounded cleanup/admission and disk-accounting correction — approved in final review

Cleanup now retains snapshot ownership/admission until its definitive outcome.
Concurrent preparation and repeated discard are refused while cleanup runs.
Failure or interruption retains a blocking uncertainty state and cleanup evidence;
shutdown neither races active cleanup nor retries uncertain content. No recovery
mechanism or deletion of unrelated files is introduced.

Disk reservation now charges only the increase beyond already-counted allocation.
Fragmented writes reuse existing capacity, including a one-byte append at the
1 MiB allocation boundary. Runtime evidence records host bytes written separately
from peak disk footprint. Actual allocation is checked after partial writes and
exceptions. Missing/insufficient allocation evidence uses a labeled conservative
rounded-logical-size fallback; an unavailable allocation unit stops preparation.

Validation: 170 targeted offline tests passed without skips, including 15 new
cleanup/admission and disk regressions, existing snapshots, managed FTP,
foreground/scheduler and schema-1/2 compatibility tests. No physical acceptance,
remote mutation or transfer execution is claimed. Authorization, session/library/
manifest guards, hashes, journals and Phase 3A planning remain unchanged.

## Managed Import Phase 3B-2A — approved; pending manual publication

Baseline: `d2e37e3949690f935f4bf79388db9f33f47c15e0`, published
Phase 3B-1 transaction/journal foundation. Older pending-publication entries
below are historical.

This checkpoint adds an explicit schema-2 offline transaction policy alongside
unchanged schema-1 budget semantics. Schema-1 journals retain their original
128 MiB ceilings and validation/state restrictions; loading never upgrades,
resumes or authorizes either version. Execution/publication states remain reserved.

Validated host preferences use existing atomic preference persistence:
Maximum Import Batch Size (`import_batch_mib`) defaults to 128 MiB, range
1–4096 MiB; Maximum Temporary Disk Usage (`import_temp_mib`) defaults to
512 MiB, range 1–8192 MiB. These are preference-model fields, without new
Settings controls in this compatibility checkpoint. Invalid values are rejected;
missing fields receive bounded defaults. There is no unlimited option.

New explicit schema-2 attempts freeze the effective policy, separately recording
selected payload, temporary disk ceiling, planned upload/readback payload,
cumulative I/O allowances and measured accounting evidence. Preference changes
do not alter existing attempts. Verification rereads are not additional game
payload. These records are contracts and evidence, not actual I/O enforcement,
free-disk checks or consent.

Phase 3A is unchanged: its aggregate 256 MiB source-read budget includes
verification rereads. A configured 4096 MiB batch does not guarantee eligibility.
No snapshots, execution admission, transfers, remote staging/readback, manifest
publication, recovery cleanup, retries or Import UI are added. POSIX journal
publication and cooperating-writer locking retain their existing guarantees.
Phase 3B-2B and later work remain pending.

Validation: 142 affected offline tests passed, no skips (49 existing transaction/
journal, 44 planner, 27 managed-library, eight existing preference and 14 new
compatibility/preference tests). No physical device acceptance was performed.

Independent compact review approved this schema-2 compatibility checkpoint for
publication. It confirmed unchanged schema-1 limits and state restrictions,
byte-for-byte round trips for five existing schema-1 journal fixtures, immutable
schema-2 policy capture and separation of payload, temporary disk, planned
transfers and actual-I/O allowances. Reserved execution states remain unavailable.

Review evidence: 142 previously passing tests, plus 63 independently rerun focused
tests, all passing with no skips. Additional published-format compatibility and
eight schema-version/evidence rejection probes passed with network access forbidden.
No physical acceptance was required for this offline-only checkpoint.

Documentation closure prepares manual publication only. No actual transfer
metering, execution or remote staging exists; Phase 3A's 256 MiB planning-read
budget and POSIX/cooperating-writer journal limitations remain unchanged.
No later-phase work is complete, and no staging, commit or push was performed.

## Managed Import Phase 3B-1 — approved; pending manual publication

Published Phase 3A baseline: `5996d7081411dfd1a17f55112ddad7679165c054`
(`Add managed game import planning and review`). The older pending-publication
headings below record the pre-publication checkpoint and are historical.

Phase 3B-1, including the reviewed safety correction, adds immutable
transaction/item/budget/evidence records, strict matching
original/revalidated plan admission, safe visible staging-path construction, an
offline state model and bounded durable host journals. It has no Core execution
entry point, network operation, source spooling, remote directory/record creation,
upload, remote readback, cleanup or UI changes. Import remains unavailable.

Proposed offline limits are 64 selected files, separately capped 128 MiB source
snapshots, 128 MiB host spool, 128 MiB upload and 128 MiB readback, 1 MiB per
journal/record, 256 operation records per journal and 64 journals per store.
Phase 3A's 268,435,456-byte planning-read allowance is unchanged. Execution policy,
resource accounting and physical staging qualification require later approval.

Host journals record intents before outcomes, preserve partial/uncertain evidence,
and use private files, file fsync, atomic host replacement and directory fsync.
Unsupported directory fsync is reported; other persistence errors stop the caller.
Loading is inspection only, never transfer/retry/cleanup permission. Prepared and
awaiting-confirmation remain available; staging, verifying, verified-staged and
published are reserved and rejected on construction, transition and journal load.
Canceled/failed/uncertain recovery records cannot resume. Fields, nesting and
collections are bounded before incremental UTF-8 JSON encoding; contradictory
operation/checkpoint evidence is rejected. Planned payload ceilings are not actual
I/O metering, which remains a 3B-2 concern.

Correction validation: 120 affected offline tests passed, including 49
transaction/journal tests (14 added safety regressions), 44 Phase 3A tests and
27 managed-library tests; no skips. Production modules
from Phase 3A and existing tests are unchanged. No physical acceptance is claimed.
See MANAGED-LIBRARY.md for the contract, durability scope and future authorization
boundary. Phases 3B-2, 3B-3 and 3C remain pending; transfers/imports are not operational.

Independent compact re-review approved Phase 3B-1 for publication. Reviewed
capabilities include immutable transaction/recovery contracts, strict plan
eligibility and safe staging paths, reserved execution/publication states and
rejection of forged authorization fields, consistent operation ordering and
acknowledged checkpoints, bounded encoding/validation, durable POSIX host-journal
publication and inspection-only restart recovery.

Evidence: 120 previously passing tests, no skips (49 contract/journal, 44 planner,
27 managed-library). The final review additionally passed the 1 MiB journal-load
boundary, one-byte overflow, quoted structural-character and multibyte UTF-8
encoding boundary probes. These are prior results; tests were not rerun during
documentation closure. No physical acceptance is required for this offline-only
checkpoint.

Limitations remain: POSIX host filesystem guarantees and cooperating-process
locking only; planned payload ceilings are not actual-I/O metering. There is no
execution admission, FTP upload, remote staging, automatic retry, recovery cleanup,
manifest publication or enabled Import action. Phases 3B-2, 3B-3 and 3C remain
pending. Documentation closure prepares manual publication only; no Git staging,
commit or push was performed in this pass.

## Managed Library Phase 3A — accepted; pending manual publication

Against published Settings baseline `b45828c39d7521732569a6ec3350a84de397cb81`,
Add Games now offers shared-picker selection, explicit Prepare Plan and read-only
review in the main Game Library tab. Import remains unavailable; configuration
stays exclusively in Settings. No game importing is operational.

Immutable plans bind typed sources to the selected device/session/root/path/UUID,
manifest revision and exact-byte digest. Local and managed remote reads validate
D64/CRT content and SHA-256. Relevant catalog duplicates require actual-byte
verification; missing/unverified content and filename conflicts block candidates.
Identical content is skipped deterministically. Sources and relevant destination
content are reread before completion. Revalidate Review rejects changed evidence.
Plans are point-in-time observations, never execution authority.

Preparation uses existing Core scheduling, B5 foreground admission and contextual
Cancel. No writes, staging, metadata publication, manifest changes, legacy catalog
changes, mount/launch, recovery or cleanup are implemented. Phase 3B/3C/3D remain
pending. Review bounds are 64 sources, 256 MiB of aggregate source bytes read
(including failed reads and verification rereads), and at most 128 relevant
catalog entries totaling 256 MiB. Required verification must fit the source budget.

Validation: 227 affected unit tests passed, including 31 new planner/Core/managed
wire tests. The 38 planning/managed-library/creation GTK checks passed, including
10 new planning UI/foreground checks. Tests use fake or localhost transports;
no physical C64U was contacted. The old foreground chooser test still calls
`FilePicker.emit`, which does not exist; the same error was reproduced on an
isolated copy of the published baseline. Dedicated B5 and picker regressions pass.
The previously documented GTK focus warning and native lifecycle issue are not
claimed fixed. Compact re-review and bounded physical acceptance subsequently
passed; their evidence and limitations are recorded below.


Source-budget correction — re-review passed: the original success-only counter
was replaced by one operation-wide 268,435,456-byte source-read allowance. Known
sizes are checked before payload reads; local reads and optional managed FTP
receives are capped to the remaining allowance and charged before buffering.
Failed/rejected reads retain their charges, including final-reply/length failures.
Verification rereads use the same allowance. Exhaustion returns
`import-source-budget` and no complete plan; it never skips hashing/verification.
Manifest and relevant-catalog reads retain their separate existing bounds.
The existing read stack gained an optional budget; no-budget consumers retain
existing behavior. No transfer execution or mutation was added.

Correction validation: the combined planner/FTP/foreground selection passed 286
tests; the final planner suite passed 44 tests after one additional end-to-end
case (13 new budget regressions in total). All 11 focused planning GTK checks
passed, including a new budget-error review-invalidation check. Localhost wire
checks cover misleading SIZE, exact EOF, streaming exhaustion, cancellation,
lease release, unchanged files/preferences and no mutation commands. Those checks
were offline; subsequent physical acceptance is recorded below. Earlier broad-suite
evidence below is historical.

Additional offline GTK checks passed: B5 (3), shared picker (16), game picker (9),
SID picker (4), Drives picker (3), C1 storage (6) and C4 layout (6): 47 checks,
or 85 with the 38 checks above. Broader foreground testing has one baseline
native-chooser error. Full C0 input testing reported six failures in 28 checks
on both current and baseline, with differing cases; two current keyboard failures
passed individually, while one also failed individually on baseline. C0 input
qualification remains incomplete; no new 3A-attributable failure was established.

### Phase 3A GNOME Wayland physical acceptance — passed; pending manual publication

Read-only acceptance used source Development on C64 Founder's Edition `25BE71`,
with destination `/USB1/ARGONAUT_LIBRARY`, revision `0`. UI results were reported
by Bruce; process exit and repository authority were checked separately.

- Local planning classified one new game, proposing 1,050,688 transfer bytes.
  Explicit revalidation passed with unchanged classification and workload.
- Remote planning classified one new game, proposing 174,848 transfer bytes.
- Cancellation reported "operation canceled by request": no completed plan was
  returned, the UI returned to idle, and no automatic retry occurred.
- USB1 remained at revision `0`, with zero games. Import remained disabled;
  no game import or device-storage mutation occurred.
- Normal shutdown returned exit code `0`; no Argonaut runtime or launcher remained.

Limits: source filenames and SHA-256 values were not independently inspected;
the displayed library UUID and SD contents were not independently verified.
Session/library-change invalidation was not physically exercised. This is bounded,
user-reported UI acceptance, not broader physical qualification. The known
`GtkText - did not receive a focus-out event` warning appeared and remains
unresolved. No crash occurred in this run; the previously documented native
GTK/PyGObject lifecycle fault remains unresolved.

The source-budget re-review approved physical acceptance: 77 targeted tests
passed (44 planner, including 13 budget regressions, plus 33 shared-read/download
tests), as did 11 focused GTK checks and 10 additional exact-limit/one-byte-over
wire probes. No skips were reported; these are prior review results, not test
runs repeated during documentation closure. Phase 3B/3C/3D remain unimplemented.
Publication is prepared only; no staging, commit or push was performed in closure.

## Game Library Settings relocation — accepted; pending manual publication

The pending Forget correction is retained within a dedicated native Settings →
Game Library page. Current identity/status, explicit discovery and selection,
Create Library and confirmed host-only Forget now live there. The main Game
Library tab presents the selected library and read-only catalog, or an explicit
unconfigured/unavailable state with Go to Settings. Importing remains deferred.
Discovery lists candidates without adoption or merging. Selection revalidates the
captured device/session/path/UUID before saving; persistence must succeed before
the selected view changes. Creation protocol and storage restrictions are unchanged.

Physical evidence supplied by Bruce is separate from these offline implementation
checks: SD recognition passed for Founder `25BE71`, `/SD/ARGONAUT_LIBRARY`, UUID
`2b8b17e2-6778-49f1-9fef-f8ee9bd5a691`. Subsequent USB1 fresh creation also passed,
for `/USB1/ARGONAUT_LIBRARY`, UUID `56dc72d1-d607-4a7e-9174-d72f82155fb6`.
Both libraries are revision 0 with zero games. The prior outstanding-fresh-creation
wording below is historical and superseded by this supplied USB1 acceptance.
Neither library was contacted or changed during this implementation. This does
not qualify importing, populated manifests, recovery, moves, deletion or scanning.
Compact review approved physical acceptance; the user-confirmed result is recorded
below. No packaging, release or Phase 3 work is included.

### User-confirmed Settings physical acceptance — passed

Bruce confirmed the following on GNOME Wayland using C64 Founder's Edition
`25BE71`. The two existing libraries remained distinct:

- SD: `/SD/ARGONAUT_LIBRARY`, UUID `2b8b17e2-6778-49f1-9fef-f8ee9bd5a691`.
- USB1: `/USB1/ARGONAUT_LIBRARY`, UUID `56dc72d1-d607-4a7e-9174-d72f82155fb6`.

Both were revision `0` with zero games. Settings → Game Library displayed
correctly and discovered both libraries. Explicit USB1 selection updated the
main Game Library without restarting; the selected library persisted after an
application restart. Explicit Discover Libraries populated the available choices.
Switching from USB1 to SD then updated the main Game Library to SD. Cancelling
the Forget Library confirmation preserved the selected host association.
Normal shutdown returned to the terminal with exit code `0`, as reported by Bruce.
No game imports or device-storage mutations were performed during this acceptance.

The existing warning `GtkText - did not receive a focus-out event` appeared;
it remains unresolved and is nonblocking for this acceptance. The separately
reproduced native GTK/PyGObject lifecycle crash also remains unresolved; no fix
is claimed. This acceptance does not certify screen-reader use, comprehensive
keyboard navigation, or new library creation. The earlier USB1 fresh-creation
acceptance and SD recognition evidence remain separate.

The reviewed Settings/Forget implementation and this acceptance record are ready
for manual publication preparation, but remain uncommitted and unpublished.
No Managed Import, Folder Scan, migration, Move Library, Delete Library or Phase 3
work is included.


## Managed Library Forget correction — historical implementation checkpoint

Against published Phases 1–2 baseline `74f0a766f208404e688e6718966e0b9533119742`,
Game Library now offers confirmed **Forget Library** for a loaded library or a
stored association. Confirmation identifies device, path and UUID and explains
that files are not deleted. Forget clears only the host library association and
current view, returning to the unconfigured state with Create Library available.
The existing library remains discoverable through explicit Load managed library;
there is no automatic rediscovery, replacement selection or remote mutation.
Active foreground operations and stale confirmations refuse the action.

This historical implementation checkpoint preceded review and the physical
acceptance recorded above. The correction remains uncommitted and unpublished.
SD recognition and subsequent USB1 fresh creation passed in separate acceptance
work; no USB1 creation or device contact was part of this implementation.
Creation protocol, manifest format, picker, legacy catalog, SIDJuke, Drives,
storage permissions and B5 handling are unchanged. Move/Delete Library, managed
imports, Folder Scan and migration remain outside this correction.

**7 October 2026 layout follow-up:** broader B3 Device Details grouping and saved
network-connection/profile relocation passed review and small physical/UI acceptance against
published credential/discovery checkpoint `b075bddd795b1b104dc5632477444bd85bb7ba39`.
117 focused tests and offline real-GTK checks passed before acceptance. The current
Development worktree then passed saved-profile/New-return, keyboard, Password Enter,
one Test, one Discover and resize checks on Founder; no subnet scan or device mutation.
**Commit/push approved, not executed.** Production/tests were unchanged by acceptance.
Credential/discovery contracts remain unchanged. Quick Connect removal belongs to
B4 header cleanup and is not included. Streaming remains OPEN / intermittent /
instrumented. See CURRENT-STATE for scope, acceptance observations and limitations.

**7 October 2026 update:** B2 credentials and the bounded Discover / Scan Subnet
portion of B3 passed compact review and bounded Development physical acceptance.
Publication is approved but not executed. UNKNOWN blocks persistence until an
authoritative retry; 109 focused tests pass. One Discover and one /24 scan passed
with the documented password-protected subnet-discovery limitation. Live native
credential-store acceptance remains later packaging/release work. See
[Device Details stabilization](DEVICE-DETAILS-STABILIZATION.md) for the approved
contract, Windows exception, mechanisms, safety and deterministic evidence.
Streaming B1 remains **OPEN / intermittent / instrumented**. Other decisions and
scope below are preserved. The documentation-only status immediately below is
historical context for the preceding consolidation, not the current pass.

**Status: documentation-only consolidation, pending Bruce/ChatGPT review.**
No roadmap implementation has begun in this pass, including item B1. This is the
single consolidated product roadmap for future work; settled directions below
are recorded decisions, not claims that the UI already implements them.

## Authority, sources, and status vocabulary

Consolidated on 6 October 2026 from the explicit roadmap handoff, the referenced
[Branch · Plan Slice 3 Inspection conversation](chatgpt-conversation://6ac26cc1-6c2c-83ea-9a3e-53f63517059b),
and repository records. The retrieved conversation confirms Flash/Temp, shared
picker/SIDJuke, contextual cancellation, Developer Mode, and stability-first
sequencing; the detailed handoff supplies the full walkthrough decision set.
Walkthrough observations below are user-reported unless linked repository
evidence establishes otherwise. No device or behavior investigation occurred here.

- **Complete:** accepted foundation; preserve it.
- **Settled / planned:** recorded product direction, awaiting implementation.
- **Investigate / candidate:** evidence or review required; do not silently decide.
- **Later / deferred:** retained scope without a new implementation commitment.
- **P0:** highest reliability or device-safety concern. B1 is the first work item;
  G2 is a safety gate within the major Ultimate Menu redesign, not permission to
  reproduce the device lockup now.

[CURRENT-STATE.md](CURRENT-STATE.md) records accepted implementation.
[NEXT-PASS.md](NEXT-PASS.md) retains historical release/milestone evidence;
this roadmap supersedes its older next-work sequencing. Historical R1–R6 and
closure reports remain intact, including their contemporaneous stop markers.

## A. Baseline / completed foundation

- Verified checkout: `/home/bruce/Documents/ChatGPT/Local Projects/argonaut-network-slice2`.
  Starting worktree clean; HEAD = local `origin/development` =
  `17ad4e2bb7acd441560a3160fbcc224d13d30536`, divergence `0 0`.
  Subject: `Close FTP ownership compatibility paths`; parent R6:
  `f9457acd3bcef4269d9d98e95ef3c6dc33f90ff1`. No fetch was needed.
- [FTP ownership closure](FTP-OWNERSHIP-CLOSURE.md) is published at that baseline:
  supported FTP uses managed ownership; raw compatibility paths are removed.
  FTP/Network Foundation ownership work is complete. Do not reopen without
  evidence. Separate product work below remains outstanding.
- [R4](R4-MANAGED-C64-AI-INSTALL.md): managed C64 AI installation/upgrade;
  [R5](R5-CORE-OWNED-HEADLESS-READS.md): Core-owned headless reads;
  [R6](R6-MANAGED-FLASH-PUBLICATION.md): managed Flash publication and exact-path
  cleanup. Physical qualification on Beige and Founder is recorded in those
  documents. Preserve their scope/limitations: R5 was read-only; R6 used existing
  `/Flash/roms` and disposable one-byte fixtures, without activation or reset;
  missing-directory MKD remained deterministic-only. Closure required no new
  physical qualification. These are prior results, not tests rerun in this pass.
- Per the current handoff, local Debian `argonaut-c64u-development` version
  `1.10~dev1` was built from this exact closure commit for packaged walkthrough.
  Packaging output is ignored and must not be added to Git. Stable `v1.9` remains
  the released baseline; there is no public 1.10 release/tag yet.

## B. Stabilization / spit-shine — do first

Highest priority: reliability and UI clarity before major redesigns.

### 1. P0 — streaming/navigation permanent hang

Observed in the packaged Debian build with a C64U stream active while navigating,
especially Streams ↔ Ultimate Menu comparison. GNOME reports Argonaut Development
not responding; Wait does not recover; Force Quit is required. Instant Replay is
suspected, not proven causal. Diagnose the hung process/thread state before
assuming replay removal fixes it. Replay removal is independently settled (F).

### 2. Credential / saved-network-connection UX

**Reviewed; bounded Development acceptance passed:** Test and Connect never persist passwords.
Save Profile + Remember stores a real typed password without implicit validation;
unchecked Save Profile removes the exact-profile stored credential while the
session credential may remain. Forget removes both stored and session fallback,
retaining the active connection/profile. Fixed saved indication uses boolean
metadata state; Windows may read/free an opaque credential buffer without touching
the blob, as explicitly approved. Development and Portable have distinct
session-only labels and no persistence controls. Final Core close clears its
session-password dictionary. Connect reports the connection outcome truthfully.
The prior investigation bullets below are retained as history; their unresolved
semantics are superseded by this approved implementation contract.

Verify working behavior and keyring mechanisms before changing them.

- Observed experiment: Forget Password → type password → Connect succeeds →
  `Profile saved` → restart → connect without password fails authentication.
  Connect can save/update the connection profile while the typed password remains
  session-only. This does not establish what Save Profile writes to the keyring.
- Investigate exactly when Save Profile and other paths write, replace, retrieve,
  or remove credentials. Add an explicit **Remember password** choice; do not add
  a separate Save Password button.
- Intended semantics, **subject to verification/review**: Test/Connect do not
  persist; Save Profile + Remember password persists to the system keyring;
  unchecked saves the connection without a password; Forget Password removes the
  stored credential without deleting the connection. Resolve what unchecked Save
  Profile does to a previously stored credential explicitly, not by assumption.
- Show a fixed masked placeholder when a saved keyring credential exists, never
  its actual length or secret. Reconnect must preserve the saved-credential
  indication. Preserve useful HTTP rejection status such as `403`.
- Replace misleading `Profile saved` after ordinary Connect with clear connection
  outcome reporting; distinguish profile changes from connection results.
- Portable Mode Password is reported disabled/nonfunctional even in portable
  release. Desired portable model: passwords live only in session memory; never
  persist or retrieve installed-mode keyring credentials; discard on exit.
  Replace/remove the misleading checkbox with informational state such as
  `Portable mode — passwords are not saved`.

### 3. Device Details / connection-profile UX

**Reviewed and physically qualified portion:** separate **Discover** and **Scan Subnet**.
The normal discovery mechanisms are unchanged. Explicit subnet probing accepts
and normalizes IPv4 CIDR, requires a connected private LAN and at most 1,024
addresses, gates invalid input, reports actual completed-host progress, displays
incremental subnet results, and counts network connections. Existing prepopulation
is retained without overwriting input. No cancellation framework or physical-device
grouping was added. The following layout follow-up does not change those contracts.

**Layout follow-up reviewed and physically accepted:** saved entries are network
**connections**, not physical machines; one C64U may have Ethernet and Wi-Fi entries.
The selector contains saved profiles only. Device identity/details, credentials,
status/errors, and Network Discovery are visually separated. Saved Network
Connections now sits toward the bottom with a Connection selector and grouped
New / Save Profile / Delete Profile actions; Test / Connect is a separate row.
Saved versus new/discovered-unsaved form state is explicit. The saved device ID is
read-only binding metadata, not a new physical-device grouping model. Existing
selection, identity, save/delete, credential and discovery semantics are preserved.

Argonaut connects using multiple services; this area is not called FTP Connection.
**Remove Quick Connect** remains settled but belongs to the global header (B4),
so it is deliberately unchanged by this component layout pass.

### 4. Global header/navigation cleanup

**Bounded physical acceptance passed; commit/push approved, not executed.**
Current `./run-development` worktree connected to saved C64 Founders / Founder
25BE71 in session-only Development mode. One Reconnect preserved active identity;
previously loaded Ultimate Menu settings became stale with rows/Apply/Flash gated,
and read-only reload restored usability. Settings, original blue/red icon, tooltip
(user-confirmed), keyboard access, Machine/Quick Connect retirement and modest
resize passed. Actual widths were 1121 and 1300 pixels; the full-window minimum
constrained the smaller requested width. Reset and Reboot confirmations were both
cancelled: zero machine commands and no device mutation. Normal close cleared
session credentials and exited. Prior 207 focused / 16 GTK evidence is unchanged;
no suites rerun. Streaming stays OPEN/intermittent/instrumented; H stays pending.
This acceptance supersedes the historical B4 review/pending markers below.

Compact B4 review exposed a connected-Reconnect stale-settings gate defect.
The narrow correction now shares the existing refresh gate across loss and
restoration: retain drafts, block stale editing/Apply/Flash even without edits,
and require the existing discard/reload flow while keeping Core connected.
159 focused tests and 12 offline real-GTK checks pass, including four new real
restoration-path regressions. **Pending compact B4 re-review before physical
acceptance.** Broader prerequisite evidence remains unchanged; no device contact.

Final narrow review additionally found an already-open Save to Flash confirmation
could bypass the gate after restoration. Its final callback now rechecks freshness
before submission. Four new real-dialog regressions prove stale refusal after
recovery/Reconnect (including repeated responses and retained drafts), and exactly
one save while fresh. 207 focused tests and 16 offline GTK checks pass, no skips.
**Pending final B4 re-review; physical acceptance remains blocked until approval.**
No other B4 behavior or later scope changes; no device contact.

Final amended prerequisite review: **APPROVE PREREQUISITE — B4 MAY RESUME**.
The one-shot, exact-session Reset/Reboot admission path is preserved unchanged
in the global dialog. See CURRENT-STATE for prerequisite review/test history.

Settled and implemented order: `[ Reconnect ] [ Disconnect ] [ Settings ] [ C= ]`.
Connected Reconnect targets the active identity-bound profile; disconnected
Reconnect targets the selected saved bound profile. Missing/unbound selection and
busy recovery refuse. Existing Core/recovery machinery owns connection semantics;
no credential persistence. Quick Connect's old route is retired.

Settings replaces user-facing Preferences in the header/dialog without redesigning
its pages. Far-right Ultimate Power uses the original blue/red Commodore SVG,
24 px, icon-only with accessible name `Ultimate Power` and tooltip description
`Power, reset, and memory actions for the connected C64 Ultimate.` Source/license
(CC BY-SA 4.0) and trademark review note are bundled alongside the asset.

Ultimate Power contains only the existing Reset C64 / Reboot C64 operations.
Machine removal is earned: no other live functionality existed, both operations
retain confirmations, captured-session safety, recovery/reporting and keyboard
access, and actual GTK button-route regressions pass. No duplicate Machine tab.
Broader physical F1 capabilities remain H; Test Lab relocation remains I.

146 focused/affected tests and eight explicit offline real-GTK checks passed;
no new skips and no device contact. Existing full prerequisite evidence was not
rerun for this presentation/wiring change. Normal resource inclusion covers SVG
and attribution without a package build. Before physical acceptance, stop for B4
review. Later acceptance should reconnect once and CANCEL Reset/Reboot prompts;
executing a hardware command requires separate authorization.

### 5. Contextual operation status/cancellation

**B5 COMPLETE / PUBLISHED** at `627698b1dd0a3e0a7ebd7b9384a86b0332a507eb`.
Foreground-admission prerequisite and contextual presenter passed review and physical acceptance.
One Browser-managed foreground operation is reserved before submission, with busy
attempts refused without queueing. Cancellation retains admission until terminal
cleanup. The short ownership mutex never spans submission/execution/cancellation.
CoreScheduler's independent local/device lanes and service semantics are unchanged.

The bottom presenter now owns IDLE/RUNNING/CANCELLATION_REQUESTED/TERMINAL for the
admitted job/token. One contextual **Cancel** replaces permanent Files/SIDJuke/Game
Library controls. Bulk Import keeps **Cancel import**, sharing the same view and
one-shot cancellation authority. Cancelling remains sticky against delayed progress
and ordinary messages; stale callbacks cannot affect a newer job. Completion/fallback
uses authoritative results and preserves existing nuanced consequence handlers.
Phase text/counts/optional totals are shown without invented percentages. Ordinary
workers have no new cancellation; noncancellable foreground presentation hides Cancel.

446 focused/affected tests and 17 offline GTK checks passed with no skips; compact
review reran 40 focused tests and eight offline GTK checks successfully.
Bounded physical acceptance then passed using the current `./run-development`
worktree and saved C64 Founders profile. One existing 993,232-byte Lykia CRT on USB1
was downloaded toward temporary local storage and cancelled once through global
Cancel. Bruce visually confirmed sticky Cancelling (too brief for automated sampling).
The authoritative result reported zero completed and one unfinished, cancelled by
request; local staging was cleaned. Read-only browsing and ordinary status recovered,
Cancel stayed absent, and normal Quit exited cleanly. No remote mutation or stream.
Details and physical-observation limitations are in CURRENT-STATE.

Publication verified local/remote equality, divergence 0 0 and clean worktree.
Streaming remains OPEN / intermittent / instrumented. B6 is the current section.

### 6. Packaging spit-shine

**Review and local package acceptance PASSED; reviewed dev2 installed.**
Stable remains 1.9; source Development is `1.10-dev`. Reviewed, installed local Debian
Development version is `1.10~dev2`, displaying `1.10-dev2`. Development uses explicit
maintained notes with missing-note failure instead of the historical 0.1.0 fallback.
Stable release checks and Development isolation/session-only credentials remain.
General module/asset staging and package self-test cover current B4/B5 resources.

Current packaging/build docs are reconciled, with one local build command in
RELEASING; historical evidence is preserved. Shared `1.8-replay.3` workflow
modernization is deferred; do not dispatch it for B6. Windows/macOS packaging,
public Stable 1.10 and trademark-release review remain future work.
52 focused tests and 49 offline staged-runtime GTK self-test checks passed; no skips.
Compact review reran 52 focused tests. Exactly one local `1.10~dev2` Development
archive was built and inspected; extracted-package self-test passed all 49 checks
in an isolated offline namespace. Offline Development/About/status/session-credential
smoke, Commodore SVG decoding and normal Quit passed. Build stamp is published B5
`627698b1dd0a3e0a7ebd7b9384a86b0332a507eb-modified`, not a published B6 commit.
Artifact size/hash and isolation limitations are recorded in CURRENT-STATE.
Bruce subsequently confirmed installation of the reviewed `1.10~dev2` package.
Read-only closure checks confirm its version and all 122 modules/assets plus notes
match current source. The offline smoke above was on the extracted package.
Source publication follows final review and remote-base safety gates; no rebuild,
reinstall, device contact or workflow dispatch is part of closure.
Streaming remains OPEN / intermittent / instrumented.

## C. Files / storage UX

Approved bounded checkpoints:

- **C0 — Conventional file selection and activation:** implemented/deterministically
  verified, final re-review and combined read-only physical acceptance passed;
  published and complete in `4b77705510d9`.
  Native GTK multiple selection/theme highlighting, independent panes, focus,
  nonselectable parent rows and refresh retention are retained or corrected.
  Optional read-only live Nautilus activation policy uses a modifier/drag-safe
  adapter; GTK continues owning selection. Existing operation safety is unchanged.
  Compact review's rapid click-then-drag blocker is corrected: pointer activation
  waits for a qualified release; Enter stays immediate and GTK owns selection.
  28 C0 checks (eight new regressions), 33 affected tests and 16 C1/B5 GTK checks
  passed after correction, no skips; the prior broader affected evidence remains.
  Bruce approved the native selection/highlighting on actual GNOME Wayland using
  source Development and C64 Founders. Selection, keyboard, right-click, canceled
  rapid drag and normal shutdown passed without transfer or remote mutation.
  GNOME policy stayed double; physical single-click remains unqualified.
  Full acceptance evidence and limitations are in CURRENT-STATE.
- **C1 — Storage roots and safe browsing:** implemented/deterministically verified,
  compact-review and read-only physical acceptance passed; published and complete
  in `4b77705510d9`.
  Advertised exact
  USB/SD/Flash/Temp locations are visible. Flash/Temp directory browsing uses the
  existing managed listing, independently of USB/SD operation authorization.
  No generic Flash/Temp copy, download, mutation, backup or launch capability is
  added; separate validated R6 Flash workflows remain available. Unavailable roots
  report errors rather than empty success. 444 focused tests and 16 offline GTK
  checks passed, no skips. Physical USB/SD, Flash carts/html/roms and empty Temp
  browsing passed; Bruce approved icons and read-only restrictions. Unavailable-root
  faults were not induced. Acceptance changed documentation only; limitations are
  recorded in CURRENT-STATE.
- **C2 — Remove redundant Backup/Restore UI:** published in `9dbbb29d3e95`.
  This approved product decision supersedes the dedicated Storage & Backups page.
  Files backup/restore controls and unreachable UI callbacks are removed; no new
  backup tab, dialog or alternative entry point is planned. Ordinary copying,
  managed transfers and contextual partial-upload recovery remain supported.
  Tested Core/service implementations and legacy backup-root configuration remain;
  the unused backup-root editor is hidden from Settings.
  Controlled Founder 16 MiB reads measured SD 0.357, USB1 0.489 and USB0 0.488 MiB/s;
  these workload-specific observations are not hardware specifications. Bruce
  prefers preparing bulk removable media and retaining source libraries on PC/Mac.
  Incremental USB/SD backup and PC-created baseline adoption are deferred
  indefinitely. Flash backup remains a possible future feature requiring separate
  feasibility/safety review; Flash restore is unapproved. No Temp backup expansion.
  94 focused tests and 44 offline GTK checks passed, no skips; C2 is published.
- **C3 — Flash/Temp operations design review:** complete; Bruce approved retaining
  current C1 behavior as the final current policy. No production implementation or
  additional generic Files operations are approved. Generic Flash/Temp mutation is
  deferred; specialized Flash workflows remain separate and unchanged.
- **C4 — Files polish and acceptance:** compact review and physical acceptance
  passed; published in `43a3f6ae28e41a6a3a3a6ae604e281d3062eb11e`.
  Filename labels are bounded with aligned sizes and full-name tooltips/accessibility.
  Menu/Shift+F10 opens existing context actions without changing selection;
  dismissal restores focus. Path/list accessible names, contextual recovery
  visibility and Files terminology/disconnected wording are refined. Core,
  C0/C1/C2/C3 and B5 contracts are preserved. 93 affected unit tests and 49
  distinct offline GTK checks passed, no skips; evidence and warning limits are
  recorded in CURRENT-STATE. Bruce passed the read-only checklist on actual GNOME
  Wayland using source Development and C64 Founders: layout/long-name tooltips,
  native selection, keyboard menus/focus, right-click, canceled drags, roots/icons,
  Flash/Temp restrictions and normal shutdown. Exit code 0, no remaining GUI
  process and an empty runtime log were verified. No transfers or remote mutations
  were exercised; accessibility and recovery limitations are in CURRENT-STATE.

Section C is **complete**, with C4 published in
`43a3f6ae28e41a6a3a3a6ae604e281d3062eb11e`. The acceptance evidence above remains
historical: no staging, commit or push occurred during that acceptance pass.
Shared picker remains Section D.
Streaming remains **OPEN / intermittent / instrumented**.

**Approved C3 closure: retain current C1 Flash/Temp behavior.** This supersedes
older generic Flash copy/add and Temp copyable-storage direction; visibility does
not confer permission to perform file operations.

- **Flash — Internal Memory:** visible and browsable, including its actual
  directory tree. Generic Files mutation remains disabled. Existing specialized
  R6 validated publication, save-copy, configuration preview and reviewed exact-file
  cleanup remain separate, with their existing validation and safety contracts.
- **Temp — RAM Disk:** visible and browsable; generic mutation remains disabled.
  Identify its temporary nature without any persistence guarantee.
- No additional generic download, upload, copy, delete, rename, overwrite,
  folder creation or mount/launch capability is approved for either root.
- Preserve distinct storage icons and existing C1 root authorization, file-service
  permissions, C0 selection and B5 foreground/cancellation handling.
- Flash export/snapshot, Flash recovery workflows, Flash restore and incremental
  backup systems are future possibilities only, not planned implementation items.
  Future Flash export/recovery or any other expansion requires separate design
  review and approval. Flash restore remains unapproved; no backup/export UI is
  introduced by C3.

C3 closure is documentation-only. No production implementation or physical device
acceptance is part of this closure.

## D. Shared Argonaut file picker — reusable component

**Published:** picker foundation and SIDJuke migration are complete in
`fbb974c7ef04ab539188de232817189e6c55d566`
(`Integrate SIDJuke with shared file picker`). Section D remains open for the
remaining consumers. Migration order and bounded scope require separate design
review; this status reconciliation authorizes no further implementation.

Provide one picker for **This Computer** (local filesystem) and connected
**C64 Ultimate** storage (USB/SD/Flash/Temp as appropriate). Do not require a
selection on Files followed by a return to another tab. Each context supplies
allowed types and actions; preserve Core ownership of filesystem semantics.

Remaining consumers: Drives disk images; Game Library supported
media including CRT/disk images; Cartridge Tools and other suitable workflows;
ROM/config selection where appropriate after safety review. SIDJuke multi-select
or directory add is a possible later enhancement, not an initial requirement.

## E. Drives redesign

**Drives tab = operate drives; Ultimate Menu = configure drives.**

Settled: Drive Enabled becomes one GTK-style toggle switch instead of On/Off
buttons; Write Protect becomes a checkbox; `Mount & Run` becomes `Run`, retaining
mount-if-needed then run behavior. Replace `Use selected C64U file` and the split
local workflow with shared `Select Disk Image…` supporting local and C64U files.

Investigate before removing controls:

- Physical Ultimate has separate configured 1541/1571/1581 ROMs for each drive.
  Determine firmware behavior for D64/D71/D81 and the active drive mode.
- Determine whether operational drive-model/ROM controls are needed. Removal is
  only a candidate if firmware handles format/mode and ROM configuration belongs
  in Ultimate Menu Memory & ROMs.
- JiffyDOS is the main user-interest case; investigate whether configured ROMs
  alone cover it instead of per-mount controls.
- Validate image format where useful without inventing firmware-owned
  compatibility logic. Keep enable/disable if operationally useful for physical
  IEC conflicts, represented by one switch.

## F. Streams — stability then interaction

Near-term sequence:

1. Fix the P0 streaming/navigation permanent hang (B1).
2. Remove Instant Replay entirely: UI and replay-specific implementation if
   unneeded elsewhere. Verify the hang independently after removal.
3. Increase scale limit; add Fit to Window with aspect-ratio-preserving resizing.
4. Integrate remote control into Streams.
5. Support real-time keyboard input sufficient to interact at BASIC `READY.`.
6. Make keyboard capture obvious and escapable; do not unexpectedly steal app
   shortcuts.
7. Add a C64 keyboard map/visual overlay for RUN/STOP, RESTORE, C=, and other
   C64-specific keys.
8. Polish Streams UI/audio.

Move Ultimate Menu `Video Setup → Stream VIC` and `Audio Setup → Stream Audio`
into a Streams group because these configure streaming. Later OBS/YouTube work
is separate from Instant Replay and is not current priority (M).

## G. Ultimate Menu redesign — major category, not spit-shine

### 1. Firmware/hardware capability investigation — first engineering phase

Study official Ultimate firmware/menu source **before structural implementation**.
Trace U64/U64E/C64U hardware/product/revision/capability detection → config objects
→ conditional menu visibility → REST exposure. Determine whether Argonaut exposes
settings without firmware hardware filtering/dependency rules; this is a possible
common cause of menu problems, not an established diagnosis.

Go beyond LEDs: SID sockets/voltage/filter capabilities; keyboard/LED controller;
Wi-Fi/Ethernet; video/HDMI; cartridge/bus generation; user-port; FPGA/core
generation; drives; and Founder/Beige/Starlight differences. Use source/API
evidence, not assumptions imported from older Ultimate 64 hardware.

### 2. LED safety investigation — P0 device-safety gate

Observed: Ultimate Menu `LED Lighting → Mode = Rainbow` then Review & Apply
locked up the C64U itself. Rainbow is a profile/mode name. Do not casually
reproduce until the transaction can be observed safely. The walkthrough reports
that its public search found no matching C64U LED-setting hang; that is not proof
of absence and was not independently searched again in this documentation pass.

Compare Beige versus Founder/Starlight hardware and valid fields per mode/profile.
Inspect exactly what Review & Apply sends and its ordering; investigate stale or
inactive fields after Mode changes and combinations REST permits that the
physical menu prevents. Establish a safe transition contract before enhancements.

### 3. Tree/property-sheet redesign — settled direction

Remove Favorites. Replace left navigation with a Regedit-style hierarchical tree
using GTK disclosure presentation, not literal Windows styling. Fully collapsed
shows major Ultimate categories; meaningful groups provide controlled depth,
not a node for every setting. Keep a persistent right property pane whose
settings do not collapse; labels left, corresponding controls/values aligned right.

Preserve physical menu organization/familiarity wherever practical. Memory & ROMs
example: General, Drive A, Drive B, Advanced. Advanced corresponds to physical F2
expanded settings; the user confirmed close parity. **Keep Advanced and physical
menu/F2 grouping parity.** Keep Command Interface and Ultimate Audio in their
traditional Memory & ROMs location. Stream VIC/Stream Audio moving to Streams is
the explicit desktop-workflow exception, not license for general reorganization.

### 4. LED enhancements — later within redesign

Saved LED profiles, random generator, and single-color swatch/selector/wheel/dial.
The keyboard appears to have about 25 selections; verify rather than treating
that as a capability specification. Hardware/capability and lockup investigation
must finish before implementation.

## H. Machine / global power controls

B4 retired the Reset/Reboot-only Machine tab after safe global migration. Physical
F1 Power & Reset offers more, including Reboot C64, Reboot C64 (Mem), Power Off,
Power Cycle, Save C64 Memory, and Save REU Memory. Do not simply expand Machine:
the settled destination is the global Commodore C= icon, hover `Ultimate Power`,
opening Ultimate Power. B4 exposes only the existing Reset/Reboot pair. Verify safe API support for each action before exposure.
Power Off likely needs deliberate confirmation; confirm its exact interaction in
review. Remove Machine only if global controls cover all useful existing actions.

Configuration → Ultimate Menu; feature operation → feature tab; global machine
actions → global header.

## I. Test Lab / Developer Mode

Remove Test Lab from the normal top-level user experience while preserving its
functionality, offline simulation, hardware diagnostics, structured evidence,
and regression tests. Expose through Developer Mode, likely
Settings → Developer / Open Test Lab; exact placement remains for review.
Long-term AI analysis may diagnose structured deterministic results; AI does
not decide pass/fail. Preserve the existing foundation described in
[TEST-LAB.md](TEST-LAB.md) and [DEVELOPER-MODE.md](DEVELOPER-MODE.md).

## J. SIDJuke

Rename user-facing SID Jukebox to **SIDJuke**. Integrate the shared local/C64U SID
picker. Preserve playlists/playback behavior; consider multi-select/directory add
later. Internal class/module renames are unnecessary without separate justification.
Retain [SID duration policy](SID-JUKEBOX.md#duration-policy-and-deferred-work):
manual navigation remains; timer/silence alone is not trustworthy tune duration.

## K. Game Library

CRT images are first-class media alongside disk games; existing CRT launch
acceptance (for example Bomberland in walkthrough evidence) must carry forward.
Show media type cleanly and let users launch without understanding the mechanism.
Consider Disk/Cartridge distinction/icons, missing/moved files, and later
search/filter/artwork polish as justified; verify existing capabilities before
calling them new. Preserve current launch/import/identity safety documented in
[GAME-LIBRARY.md](GAME-LIBRARY.md).

Physical cartridge dumping belongs to Cartridge Tools. A successful dump should
naturally offer adding the resulting `.crt` to Game Library.

## L. Cartridge Tools — separate feature category

Integrate the planned MIT-licensed `darkuni/c64-ultimate-cartdumper` (Go), as
recorded in the handoff. Prior physical success: Planet X2.1 GMOD2 dumped to CRT
and the result launched successfully. These are existing walkthrough claims,
not new integration or qualification in this pass.

Safety prerequisite: C64U must clean reboot without a cartridge saved to Flash
before dumping. Investigate configuration capture/restore or another guard to
avoid leaving machine state wrong. Keep dumping distinct from launching/copying
existing CRTs. Intended handoff: physical cartridge → dump `.crt` → optionally
add to Game Library → later launch without the physical cart.

## M. Later / deferred — including recovered existing roadmap items

- OBS/YouTube: audit existing code and settle UI/scope later, separate from replay.
  NEXT-PASS records reviewed capture/worker/diagnostic components on
  `feature/obs-capture`, outside then-current Development and not fully qualified
  across platforms. Audit current state before reuse; do not merge wholesale.
  Preserve its direct-YouTube go/no-go decision after OBS/media qualification.
- Public 1.10 packaging/release/tag only after stabilization/spit-shine acceptance.
- Recovered from CURRENT-STATE: System/Light/Dark theme preference and improved
  Reset/Reboot recovery UX. Retain as planned/later; header power work alone does
  not establish recovery behavior.
- Recovered from NEXT-PASS and [SERVER-FIRST.md](SERVER-FIRST.md): persistent Core
  hosting/versioned API with CLI/automation proof client; remote-client artifact
  staging/ownership/limits/cleanup; then iPad/browser PWA. Preserve Core-first
  contracts and Core-host versus client filesystem distinction. These remain
  later work; old sequencing does not displace stabilization.
- Recovered from SID-JUKEBOX: song-length database, silence detection, automatic
  advance, and SID socket/model/address reconfiguration remain deferred. Any
  automatic advance needs trustworthy duration evidence, initial opt-in, and
  manual navigation when duration is unknown.
- Recovered from GAME-LIBRARY/NEXT-PASS: ZIP/7z sources, additional media formats
  (including earlier PRG deferral), Tested/Playable user state, and Game Launch
  fingerprint-performance optimization. Structural validity is not playability.
- Tape/Datasette and physical cassette-to-`.TAP` imaging remain later
  hardware/firmware/API investigations, retained from GAME-LIBRARY and R2;
  neither is ordinary file copying or included in Cartridge Tools by inference.
- Preserve NEXT-PASS Linux-first development/hardware acceptance and major-release
  cross-platform qualification principles, with portable code and automated
  platform checks throughout. Old Stable 1.9 gates are completed history, not a
  newly reopened release task.

## Design principles

- Preserve proven managed ownership/safety; UI redesign must not regress Network
  Foundation. Keep device rules, credentials, scheduling, and safety in Core.
- Physical Ultimate menu parity/familiarity first; improve presentation without
  gratuitous relocation of established settings.
- Configuration belongs in Ultimate Menu; operation in feature tabs; global
  machine actions in the global header.
- Expose power-user capability without forcing it into everyday UI; use
  Developer Mode/Advanced where appropriate.
- Prefer intent labels (`Run`) to implementation labels (`Mount & Run`).
- Persistent binary state → switch; option/property → checkbox; action → button.
- Do not hide real storage because destructive operations need stronger safeguards.
- Verify current behavior before changing working credential/security mechanisms.
- Derive hardware/capability awareness from firmware/source/API evidence, not
  assumptions about older U64 hardware.

## Open investigations and review reconciliation

| Investigation | Required evidence / unresolved decision |
| --- | --- |
| Streaming hang | Hung process/thread state; root cause; independent verification after replay removal. |
| Credential/keyring Save Profile | Reviewed; bounded Development credential UX/403/session-clearing acceptance passed. UNKNOWN correction and native existence tests passed; live native stores remain later acceptance. See Device Details stabilization record. |
| Discover / Scan Subnet | Reviewed; one Discover and one /24 scan physically passed, including progress and network-connection counts. Password-protected subnet omission remains documented; existing scan scope preserved. |
| Firmware capability/menu filtering | Detection → config → visibility/dependencies → REST; variant-specific settings. |
| LED lockup | Exact apply payload/order, inactive fields, safe transitions, and hardware-valid combinations; no casual reproduction. |
| Drive image/mode/ROM | Firmware handling of D64/D71/D81, configured ROMs/JiffyDOS, and whether operational controls can be removed. |
| Power & Reset API | Per-action support/safety, confirmation needs, and sufficient coverage before Machine removal. |
| Existing OBS integration | Current branch/code state and qualification; later UI/scope and YouTube decision. |

Older CURRENT-STATE says Quick Connect → Reconnect; the latest settled instruction
is removal of Quick Connect with a distinct global Reconnect action. Historical
replay completion remains valid evidence, but the new decision is removal; neither
proves replay caused the hang. Older pre-publication stop markers do not override
verified closure HEAD. The handoff's intended credential non-persistence differs
from observed Connect profile saving: record both, investigate, and review before
changing behavior. Exact Developer Mode placement, Machine removal, drive-control
removal, and power confirmation details remain candidates, not silently chosen.

**Review stop:** this consolidation changes documentation only. No implementation,
including B1 diagnosis, tests, device contact, packaging, staging, commit, push,
tag, release, or branch/worktree creation is authorized by this document.
