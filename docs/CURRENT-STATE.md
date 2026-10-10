# Current development state

## C3 — Flash/Temp design review complete: current policy retained

The C3 design review is complete. Bruce approved retaining the published C1
Flash/Temp behavior as the final current policy; no production implementation or
additional generic Files operations are approved.

Authority for this documentation closure: HEAD/local origin/development
`522906e9f8f4c31fda226a9dfe501d52c934e898`, subject
`Update file listing test selection mocks`, divergence 0 0, clean index/worktree.

- Flash remains visible and browsable through its actual directory tree. Generic
  Files mutation remains disabled; specialized Flash workflows remain separate.
- Temp remains visible and browsable with generic mutation disabled. Its temporary
  nature is explicit; no persistence guarantee is made.
- C1 remains directory-browsing-only for these roots: no new generic download,
  upload, copy, rename, delete, overwrite, folder creation or mount/launch route.
- Existing R6 validated Flash publication, save-copy, configuration preview and
  reviewed exact-file cleanup retain their existing scope and safeguards.

Generic Flash/Temp mutation is deferred. Flash export/snapshot, Flash recovery,
Flash restore and incremental backup systems are future possibilities only, not
planned implementation items. Any future Flash export/recovery or other expansion
requires separate design review and approval; Flash restore remains unapproved.
No backup/export UI is introduced.

This policy supersedes the roadmap's earlier generic Flash copy/add and Temp
copyable-storage direction while retaining both locations' visibility. Storage
authorization, file-service permissions, C0 selection, C1 browsing and B5 operation
handling are unchanged. This closure changes documentation only; validation is
limited to documentation consistency and hygiene, with no device contact.

C4 — final Files polish and acceptance — remains pending and has not begun.
Section C is not complete. Shared file-picker work remains Section D; no D/E work
is included in this closure.

## C2 — Redundant Backup/Restore UI removed: pending review

Bruce approved retiring the dedicated Backup/Restore interface after the bounded
storage benchmarks. No replacement Storage & Backups tab or dialog is planned.
The preferred bulk-media workflow is preparation on a PC/Mac with the source
library retained there; ordinary Argonaut Files copying remains supported.

Starting HEAD/local origin/development was
`4b77705510d99af2cba940064cfd7ca987a25082`, divergence 0 0, clean index/worktree.
C0/C1 are published and complete at that checkpoint. C2 removes the Files
`Back up USB/SD…` and `Restore USB/SD…` buttons, their row, chooser/review/result
callbacks, chooser helper and obsolete sensitivity/busy-control references.
Files now contains contextual partial-upload recovery above the normal two panes;
B5 status and contextual Cancel remain at the bottom of the main window.

Settings no longer displays the unused USB/SD backup-root editor. Its stored
`usb_backup_root` value, config round-trip and Core accessor remain compatible;
ordinary Settings edits, Undo and Restore defaults must preserve this hidden value.
All backup/restore Core/service methods and existing service regressions remain.
No managed FTP, scheduler, session binding, replacement, cancellation, cleanup,
C0 selection or C1 storage-authorization implementation changed.

The controlled Founder benchmark observed comparable 16 MiB reads of 0.357 MiB/s
on SD, 0.489 on USB1 and 0.488 on USB0. These are measurements from one device,
firmware and workload, not universal media specifications. USB3.2 media showed no
meaningful network read advantage. Small-file overhead was substantial. File
modification timestamps advanced on tested same-size replacements, but directory
timestamps did not track child changes; apparent two-second granularity and a
clock offset further limit metadata-only conclusions. The earlier benchmark used
separately approved temporary content and verified its removal on all three roots.
This implementation pass makes no device contact.

Verification: **94 focused tests and 44 explicit offline GTK checks passed, no
skips**. The focused run covers retained backup/restore services, partial-upload
and replacement consequence reporting, legacy preferences, foreground admission,
operation status, C1 managed restrictions and disk-image navigation. GTK checks
cover removal/no replacement entry point, two-pane layout at 900x650 and 1200x850,
keyboard traversal, Copy/Paste upload/download routing, context/disk actions,
partial-upload recovery, hidden preference survival through settings/defaults,
C0 pointer/key/drag behavior and C1/B5 nonregression. Tests used fake devices,
loopback-only networking and an isolated nested X11 display with memory GSettings.
The initial restricted run could not open local test sockets; the permitted rerun
passed. GTK emitted one GtkText focus-out warning with passing focus assertions;
this remains a nonblocking limitation, not an upstream GTK fix. No broad
normal/optimized suite or physical acceptance was run.

Incremental USB/SD backup and PC-created baseline adoption are deferred indefinitely.
Flash backup is only a possible future feature requiring separate feasibility and
safety review; Flash restore is unapproved. No Temp backup expansion is planned.
C3 design review is complete with C1 policy retained; C4 remains pending.
Section C is not complete. D/E, Test Lab and Streams work are
out of scope. Streaming remains **OPEN / intermittent / instrumented**.


## C0 — Conventional file selection and activation: published

C0 passed final narrow re-review and combined read-only C0/C1 physical acceptance.
C0 and C1 are **published and complete** at `4b77705510d99af2cba940064cfd7ca987a25082`.
Section C is not complete; C3 retains C1 policy as recorded above, with C4 pending.
Starting authority was published HEAD/local origin/development
`c26da8e73b6e8604895ba9da67a32b099c900629`, divergence 0 0, empty index, with
exactly 15 pending C1 files (+559/-51). C1 production/tests/assets are preserved
byte-for-byte except the necessary shared Files presentation changes in gui.py.

Both Files panes retain Gtk.ListBox MULTIPLE selection. GTK owns Ctrl toggling,
Shift ranges, Ctrl+A, arrow navigation and theme-native highlighting. Hard-coded
inactive selection colors are removed; the theme-colored border and Active label
identify the active pane. Focus tracking now covers path entries and toolbar
controls as well as lists. Pointer motion does not change focus or the active pane.
The parent row remains activatable but is nonselectable, including with Ctrl+A.
Plain empty-background clicks clear only that pane; background dragging does not.

Optional read-only Nautilus click-policy compatibility supports single/double and
live changes; missing/invalid/unreadable preferences fall back to double. Argonaut
never writes this desktop setting. GTK's single-click property stays disabled:
the small activation adapter lets GTK complete native selection, then dispatches
one qualified plain single/double-click activation after release. Modifiers, right-click, drag,
replaced rows, navigation, policy changes and canceled/stale sequences cannot
trigger that deferred activation. Double-click and Enter retain existing directory,
parent and disk-viewer meanings; no automatic mount/launch/transfer is introduced.

Same-directory refresh retains surviving selected names. Navigation clears
selection, and remote preservation also requires the same client and exact path.
Pane selections remain independent; clipboard/operation targets remain separately
captured. Existing context menus, COPY-only internal cross-pane dragging, reviewed
delete/rename, C1 storage authorization and B5 cancellation contracts are retained.
No Core, FTP, session or managed operation execution code changed for C0.

Initial verification: **20 C0 checks, 140 focused/affected existing tests, and the same 16
C1/B5 offline GTK checks passed, no skips**. C0 uses real X11/XTest pointer/key
sequences and memory-only GSettings, including native drag/drop, modifiers, parent
navigation, refresh, focus, text Ctrl+A, context menus and captured operation
routing. Fixtures forbid device connections; backend tests allow synthetic loopback
only. The 16 GTK checks again emitted two GtkText focus-out warnings, matching the
previous baseline count; focus assertions passed. C0's X11 run emitted none, which
does not establish that the native-backend warning is fixed. No upstream GTK fix
or full-application test rerun was attempted.

Compact C0 review found a missing rapid click-then-drag case: GTK emitted native
activation on the second button-down before drag recognition. The approved narrow
correction suppresses pointer-origin native activation and dispatches only after
a qualifying release (count 1 for single mode, count 2 for double mode), once GTK
has completed selection. The existing UI-idle boundary adds no timer or arbitrary
wait. Enter remains synchronous. Drag/cancellation, modifiers, row replacement,
root/client transitions and mismatched rows discard pending pointer activation.
Only file_selection.py changed in production; GUI, C1 authorization, Core, FTP,
scheduler and foreground execution remain byte-identical to the reviewed baseline.

Correction verification: **28 C0 GTK checks (including eight new real-pointer
regressions), 33 affected selection/navigation/Files/C1 tests, and 16 C1/B5 GTK
checks passed, no skips**. Rapid select-click followed immediately by dragging
both a directory and disk-image row produces zero activation, navigation or viewer
opening while a drag begins with the correct captured source. Completed single
and double clicks activate once after release; no third click or timer is needed.
Canceled/rebuilt-row/root-client-change cases activate zero times. Existing COPY
routing and Flash/Temp restrictions pass. The C1/B5 run again emitted two GtkText
focus-out warnings with passing focus assertions; these remain a nonblocking
limitation, not an upstream GTK fix. No broad application suites were rerun.

### Combined C0/C1 physical acceptance — 2026-10-10

Accepted on the actual GNOME Wayland desktop using source `./run-development`,
not the installed dev2 package. HEAD/local origin/development remained
`c26da8e73b6e8604895ba9da67a32b099c900629`, divergence 0 0, index empty;
starting scope was exactly 18 files (+1288/-70). The saved C64 Founders profile
connected with firmware 1.1.0 / API 0.1; Bruce confirmed device identity and entered
session-only credentials directly in the app.

Bruce explicitly approved the visual appearance: familiar GNOME Files selection,
clear active pane, no clipping/overlap. He confirmed single-click selection,
double-click directory opening, Ctrl toggle, Shift range, Ctrl+A excluding `..`,
arrows/Enter, path-entry Ctrl+A and independent pane selections. Right-click on
selected groups, unselected rows and empty background passed. Selected-group and
rapid click-then-drag gestures did not activate or start a transfer; drags were
canceled without a cross-pane drop. Refresh retained selections; directory and
parent navigation cleared them. No focus trap, unexpected scrolling or freeze was
reported. GNOME click-policy was `double` and was not changed.

USB1 and SD listings/navigation worked, including the existing SD/arm2sid path;
normal SD file controls remained available but were not invoked. Accessible root
labels matched /USB1, /SD, /Flash and /Temp. Bruce approved the USB thumb-drive,
SD-card, internal-storage and memory icons. Flash exposed its actual carts, html
and roms directories; Bruce confirmed browsing all three with clear paths.
Flash/Temp generic file controls were unavailable. Temp displayed its temporary
RAM-disk description without a persistence promise; its current listing was empty
apart from `..`, so no Temp child-directory traversal was exercised.

Normal window-close shutdown exited Development with code 0 and no remaining
Argonaut GUI process. The application runtime log was empty: no GTK focus warning,
traceback or other logged error occurred in this session. The two existing offline
GtkText focus-out warnings remain a documented nonblocking limitation. Based on
the performed actions and Bruce's confirmation, no transfer, remote mutation or
machine command was invoked; this was not a packet-level network audit.

Limits: physical single-click mode remains unqualified; existing deterministic
single-click evidence applies. No unavailable-root fault was induced because all
advertised roots were available; deterministic error-path tests remain the evidence.
No writes, deletes, restores, mount/launch, reboot or persistence experiments were
performed. Other themes/platforms and cross-pane transfer execution were not tested.
Existing 28 C0 GTK, 33 affected and 16 C1/B5 GTK passing checks (no skips) were not
rerun. Production, test and asset hashes were unchanged by acceptance; only this
file and ARGONAUT-ROADMAP were updated. No staging, commit, push, package or release
occurred. C2/C3/C4 and D/E remain untouched. C0/C1 are approved for a separately
executed, allowlisted commit/push; Section C is not complete.

## C1 — Storage roots and safe browsing: published

C1 is implemented, deterministically verified, compact-review approved and
**read-only physical acceptance passed; published in 4b77705510d9**. See the combined
acceptance record above. Section C is not complete.
Starting HEAD/local origin/development was
`c26da8e73b6e8604895ba9da67a32b099c900629`, parent
`627698b1dd0a3e0a7ebd7b9384a86b0332a507eb`, subject
`Polish Debian development packaging`; divergence 0 0, clean index/worktree.

Discovery recognizes only advertised exact directory roots `/USB[digits]`, `/SD`,
`/Flash`, `/Temp`. `recognized_root` classifies browsing paths; `storage_root`
retains the USB/SD operation gate, with absolute-path, component, control-character
and backslash validation. Visibility does not confer file-operation permission.
The existing managed directory-listing adapter supports arbitrary Flash/Temp
subdirectories, including Flash/html; exact returned paths are checked. No FTP
ownership, scheduler, service execution or cancellation redesign was needed.
USB/SD startup preference/fallback remains ahead of newly visible internal roots.

Files keeps its two panes, labeled This Computer and C64 Ultimate. Flash and Temp
have concise contextual descriptions. Temp says RAM Disk and temporary storage;
it promises neither reboot erasure nor persistence. System solid-state artwork
represents Flash. Three small symbolic vectors represent SD cards, USB thumb drives
and RAM because the installed theme lacks suitable symbols. Accessible location
labels remain. Local mounted-media buttons use the thumb-drive symbol; local
filesystem behavior is unchanged.

C1 is directory browsing only for Flash/Temp in Files: Copy, Paste, folder/D64
creation and mutation/launch context actions are unavailable. Keyboard, drag,
direct handlers and captured copy targets enforce the same policy. Core file
services independently refuse generic Flash/Temp copy, delete, rename and folder
creation; REST create/mount/path-based launch operations enforce the storage gate
at execution, separate from syntax-only SID parameter validation. Existing job
failure timing is retained. Storage roots themselves cannot be renamed/deleted or
used as replacement files. No generic internal download route is added.

The separate R6 native Flash upload, save-copy, configuration-preview and reviewed
exact-file cleanup contracts are unchanged. At the C1 checkpoint, USB/SD backup/restore remained scoped
and in Files; C2 above retires that UI while preserving its services. No C2/C3 operations are introduced. Existing
two-pane COPY-only dragging remains; external/same-pane drops are not added.
B5 foreground admission/global contextual cancellation is unchanged.

Unreadable or redirected roots report errors, never successful empty listings.
Refresh updates discovered location buttons even when the current root disappears;
the previous listing/path remain with the error, rather than becoming an empty
success. Connection failure classification is preserved. No polling is added.

Verification: **444 focused/affected deterministic tests and 16 explicit offline
GTK checks passed, no skips.** Coverage includes exact discovery/path mappings,
arbitrary Flash/Temp managed listings on a synthetic loopback server, permission
refusal before device access, root/traversal protection, REST launch/create guards,
USB/SD transfers/deletion/replacement/backup, R6 publication/cleanup, session safety,
foreground/cancellation, GTK history/parent navigation, unavailable-root reporting,
icons/action sensitivity, keyboard/context/Paste/drop parity, retained USB folder
confirmation targets, resize/focus sanity and existing USB D64 conflict handling.
The runner refused non-loopback networking; GTK fixtures trapped connections and
used temporary preferences. GTK emitted two GtkText focus-out warnings during the
test run; assertions passed, so this is not evidence of warning-free physical UX.

Initial sandbox runs could not open loopback sockets or the display. Reruns used
the required local permissions. Earlier iterations corrected obsolete hidden-Flash
test expectations, navigation fixtures, asynchronous root-refusal timing and a
syntax-only SID validation regression. No assertions were skipped or removed to
obtain the final results. Syntax/whitespace and bounded change review passed.

Combined read-only physical acceptance passed as recorded above. Hardware mutation
workflows were not exercised; Files retains the C1 browsing-only restrictions.

- C2: dedicated backup UI retired by the later approved decision; review pending.
- C3: design review complete; current C1 policy retained, generic mutation deferred.
- C4: final Files polish and acceptance pending.
- Shared file picker remains D; no D/E implementation.

The implementation/test pass made no C64U contact; the subsequent authorized
acceptance used read-only connection/browsing as recorded above. No staging, commit,
push, package or release occurred. Test Lab and Streams implementation is unchanged. Streaming remains **OPEN / intermittent /
instrumented**.


## B6 — Debian Development package accepted and installed

B6 implementation and compact review passed; local archive/self-test/offline smoke
acceptance passed. Bruce subsequently confirmed installation of the reviewed dev2 package.
Stable stays 1.9. Source Development now displays `1.10-dev` with the existing
checkout/build identity. The reviewed, installed local Debian package is `1.10~dev2`,
displaying `1.10-dev2`; no public Stable 1.10 tag/release is implied.

Debian Development deliberately selects maintained `RELEASE-DEVELOPMENT.md` and
fails before staging if it is missing. Stable note selection and strict release
checks remain separate. The builder exposes staging for deterministic tests without
running dpkg. Package self-test verifies Debian version/notes identity and current
resources, including Commodore SVG/attribution and B5 modules; existing credential
isolation checks remain intact. General module/asset-copy coverage is tested.

README, DEVELOPMENT and RELEASING now distinguish released Stable 1.9 from current
1.10 Development. The single local build command is in RELEASING. Historical
notes/screenshots are retained. The shared `1.8-replay.3` packaging workflow is
explicitly deferred and must not be dispatched as current 1.10 guidance. No
Windows/macOS packaging changed; the shared source Development label changes there
naturally. Public-release trademark review remains pending.

Verification: 52 focused Debian staging/package/version/channel/credential/resource
and Stable-contract tests passed with no skips. The existing full GTK package
self-test also passed 49 checks against temporary staged Development modules and
metadata, with isolated configuration and socket connections forbidden. Its notes
lookup was redirected to the temporary staged documentation directory; no archive
was built, installed or represented as final package acceptance. Version reported
`1.10-dev2` with the current commit plus `-modified`. Syntax, whitespace, modes,
bounded secret scan and current documentation references were checked.

Compact review confirmed the exact 13-file implementation scope (+376/-86) and
reran 52 focused tests successfully. Review approved B6 package acceptance. Exactly
one local Debian Development package was built using the documented command:

- Artifact: `/tmp/argonaut-b6-dev2/argonaut-c64u-development_1.10~dev2_all.deb`
- Size: 3,837,840 bytes.
- SHA-256: `cd647750ae1cc4a134e55111def695e89302544b49252af5d3843e5885d0c329`
- Control: `argonaut-c64u-development`, `1.10~dev2`, architecture `all`.
- Stamp: display `1.10-dev2`, Development true, build
  `627698b1dd0a3e0a7ebd7b9384a86b0332a507eb-modified`.

This is the reviewed uncommitted B6 worktree on published B5, not a published B6
commit. Archive inspection matched all application modules/assets against the
reviewed worktree, including B5 modules and Commodore SVG/attribution. Active notes
matched RELEASE-DEVELOPMENT.md byte-for-byte and by stamped SHA-256; no old 0.1.0
notes were selected. Desktop entry and launchers use Development identities.

The extracted archive's actual launcher and unmodified packaged self-test ran in
a read-only filesystem namespace, with extracted application/docs/launcher mounted
at their normal paths, fresh XDG configuration, and a separate network namespace.
All 49 packaged checks passed. The first harness attempt lacked writable temporary
storage; supplying an isolated TMPDIR fixed the test environment without changing
or rebuilding the package. Read-only desktop isolation emitted dconf/GVFS warnings;
they did not fail the self-test and are not evidence of an installed-package fault.

A separate launch of the extracted package passed the minimal offline smoke:
Development title; About `1.10-dev2` and matching modified build stamp; disconnected
idle status with no stale Cancel; session-only credential messaging; B5 imports;
and Commodore SVG decoding (130 x 122). Settings closed and normal Quit exited 0.
No C64U, stream, native Stable keyring persistence test or external network was used.

Only CURRENT-STATE and roadmap changed after the reviewed build; implementation,
tests and packaged resources stayed unchanged. Bruce subsequently installed the
reviewed `1.10~dev2` package. Read-only closure verification confirms installed
`1.10~dev2`, display `1.10-dev2`, and the original B5-plus-modified build stamp.
All 122 installed application modules/assets and Development notes match current
source byte-for-byte. The offline smoke above used the extracted package; no new
installed-app launch is claimed. The temporary archive directory is gone; no
rebuild or reinstall was needed. Source publication follows the final review and
remote-base safety gates. Stable remains 1.9; public 1.10, cross-platform qualification,
shared-workflow modernization and trademark-release review remain future work.
Streaming remains **OPEN / intermittent / instrumented**.

## B5 — contextual operation status/cancellation, published

**B5 COMPLETE AND PUBLISHED** at `627698b1dd0a3e0a7ebd7b9384a86b0332a507eb`,
parent `5cb37571fa5192d71b012aa57027cc3d9459a518`, subject
`Centralize foreground operation status and cancellation`. Publication verified
local/remote equality, divergence 0 0 and clean index/worktree; 17 files, +1267/-177.
Compact review passed with 40 focused tests and eight offline GTK checks, no skips.
Streaming remains **OPEN / intermittent / instrumented**.

One GTK-independent Browser presenter owns IDLE, RUNNING,
CANCELLATION_REQUESTED and TERMINAL views for the admitted job/token. The compact
bottom status row has one contextual **Cancel**, absent when unavailable. Files,
SIDJuke and Game Library permanent Cancel controls are retired. Bulk Import retains
its modal **Cancel import**, subscribing to the same view and cancellation authority.
Both routes consume one request before invoking the existing service; accepted
cancellation stays sticky until authoritative completion and retains foreground
admission. Refusal/error is reported without claiming acceptance or automatic retry.

Progress uses service phase text and truthful counts/optional totals, with no
percentage or progress bar. Ordinary status cannot replace an active operation or
Cancelling. Identity checks reject stale progress/cancel/completion; the existing
completion fallback remains. Terminal messages and existing feature consequence
handlers retain publication/cleanup/uncertain-outcome distinctions. After terminal
completion the next ordinary message replaces status, following the existing
lifetime convention. Malformed progress yields generic diagnostic evidence and
safe text; no raw malformed payload is logged. Current managed Core jobs retain
existing cooperative cancellation; explicit noncancellable presentation is supported,
and ordinary workers gain no cancellation. Core, scheduler, recovery and services
are unchanged; independent scheduler lanes are preserved.

Deterministic evidence: 446 focused/affected tests and 17 offline real-GTK checks
passed, no skips. Coverage includes known/unknown counts, malformed progress,
noncancellable jobs, sticky one-shot cancellation, stale SID progress and retained
live callbacks, foreground retention, completion/fallback races, terminal consequences,
modal/global synchronization, keyboard focus recovery, transfers, native Flash,
SID/Game/Bulk workflows, USB backup/restore and late-publication cleanup semantics.
No full normal/optimized suites were rerun. Global Cancel has accessible name Cancel;
GTK checks exercise focus while visible and recovery when unavailable/terminal.

Physical acceptance used `./run-development` from the current modified source
worktree, with Development identity verified, and the saved C64 Founders profile
(firmware 1.1.0 / API 0.1). Initial authentication required Bruce to enter a
session-only credential through normal Device details; no credential was recorded.
Bruce assisted with file-pane navigation where desktop accessibility was incomplete.

Exactly one remote-to-local download was started: the existing
`/USB1/GAMES/NTSC & PAL/Lykia - The Lost Island/Lykia - The Lost Island.crt`
(993,232 bytes), to an empty local `/tmp/argonaut-b5-acceptance-*` directory.
Idle Files had neither permanent Cancel transfer nor contextual Cancel. During the
managed copy, the bottom presenter showed Preparing copy, Copying, then truthful
Transferred byte counts without percentages, with contextual Cancel available.
One global Cancel activation was issued after byte progress. Bruce visually
confirmed Cancelling appeared and did not revert before the terminal result.
Automated accessibility sampling did not capture that brief intermediate state;
its sticky-state physical evidence is Bruce's direct observation, supported by the
deterministic regressions, not an inferred screenshot or sampled status.

Authoritative terminal text: "0 items completed; 0 skipped; 1 unfinished. Stopped:
Operation cancelled by request." Cancel disappeared. The temporary destination
was empty, including no staging file, consistent with managed-download cleanup.
A subsequent ordinary read-only remote refresh succeeded; ordinary Connected status
returned and no stale progress/Cancel reappeared. Brief keyboard navigation caused
no observed error; no UI hang or GTK warning/error was emitted during this run.
The accessibility Cancel activation did not establish keyboard focus on that button;
focused-control disappearance remains covered by the prior offline GTK checks.
Normal application Quit exited with status 0; no Development worker/process remained.
Core.close clears session credentials; process exit removed the in-memory session.

No remote mutation, second download, stream, hardware command, or unrelated physical
qualification occurred. Production and tests were unchanged during acceptance;
only these acceptance notes and the roadmap were updated at that time. Starting cumulative scope
was 17 files, +1230/-177 against published B4
`5cb37571fa5192d71b012aa57027cc3d9459a518`; the index remains empty. No staging,
commit, push, package, tag, release or later-roadmap work occurred during acceptance.
The subsequent approved B5 publication is recorded above.

## B5 prerequisite history — now approved

The following records the prerequisite before final approval and before B5
implementation; its old review gate and permanent-button references are historical.

Compact prerequisite review found two blockers: live Cancel handlers could resolve
replacement jobs, and the admission mutex was held for the entire operation. Both
approved narrow corrections are implemented. Files/SID/Game button signal handlers
now capture the admitted job and reservation, replace their previous live binding,
and validate authority before cancellation. Bulk Import captures the same authority
for its modal route. Terminal invalidation makes retained callbacks harmless even
when their widgets survive; no fallback to the current job exists. Repeated requests
for the same active job retain existing cooperative service semantics.

The mutex now protects only in-memory reserve/bind/inspect/release transitions.
State/token retain exclusive ownership between transitions. Submission, execution,
UI callbacks and service cancellation run outside the mutex. Admission acquisition
is nonblocking; a second request refuses based on RESERVED/ACTIVE state without
queueing. Failed reservation release and active terminal release require matching
identity; active release additionally requires the matching job. A stale failure
handler cannot clear a replacement operation's busy state or status. Synchronous
submission has no normal path that invalidates its own reservation before binding.

New deterministic checks retain actual registered permanent-button and modal
callbacks, verify current cancellation still works, and prove stale/repeated handlers
leave replacement jobs RUNNING with zero cancellation calls. Short-mutex tests
inspect availability during RESERVED, ACTIVE, submission, execution and cancellation;
existing barrier/reentrant races still prove exclusive admission. CoreScheduler and
service execution/cancellation contracts remain unchanged. No presenter, button
retirement, sticky Cancelling state or Bulk Import presentation redesign was added.

Starting authority: HEAD = local origin/development =
`5cb37571fa5192d71b012aa57027cc3d9459a518`, parent
`9d0c543b7f7497428463a4890098fae6c30d937b`, subject
`Refine global navigation and session-safe machine controls`; divergence 0 0,
clean worktree/index. B4 is published; its older pre-publication text below is history.

Inspection proved that independent foreground submissions could replace Browser's
single tracked job, leaving the original running without its completion/cancel route.
Bruce approved ONE Browser-managed foreground operation at a time, with refusal
before service submission and no automatic queue. This is a Browser admission policy;
CoreScheduler's independent local-computer/device execution lanes are unchanged.

Foreground means managed jobs presented through Browser.run_file_job: Files copy,
delete, folder/rename, USB backup/restore, native Flash file operations, SID catalog
and playback jobs, Game Library catalog/scan/relink/launch, and Bulk Import execution.
Preparation and execution acquire separately; reviews hold no reservation. Existing
sequential multi-file additions continue through terminal callbacks. Bulk Import is
one scan job followed, after review, by one execution job, not concurrent children.
Ordinary Browser.run workers keep their existing mutual busy exclusion and cannot
enter during a reservation; no new cancellation is exposed for them. Recovery,
internal/background work, synchronous metadata editing and Core scheduling are unchanged.

The small ForegroundSlot uses nonblocking admission and an opaque reservation identity.
GTK owns binding/release. Browser reserves and marks busy before invoking a submission
factory, then binds its returned job. Busy/reserved attempts refuse without invoking
the factory. Submission failure/refusal releases the reservation before error handling.
Inspected service/client paths return the scheduler's job directly; no fallible UI
work remains between scheduling and returning that handle. No ambiguous post-submit
exception path was found in those launchers.

All managed launch boundaries now defer service calls, including delayed Game Library
and SID choosers, USB review/choosers, Files confirmations, SID/Game launch/relink,
Flash upload/save and Bulk Import. Completion observation is installed before feature
presentation. Cancellation retains ownership until authoritative terminal state.
Normal completion and the existing 250-ms snapshot fallback release only their own
reservation; stale completion/progress cannot clear or overwrite a newer job. Tab
cancellation passes its admitted job identity. SID and Bulk Import queued progress
check active-job identity. Existing consequence reporting and service cancellation
semantics remain intact. No new polling, queue, timeout/retry or execution policy.

Verification: **221 focused tests passed**, including **21 new admission regressions**,
plus **14 explicit/affected offline GTK checks**, no skips. Coverage includes atomic
concurrent/reentrant admission, zero second submission, submission failure/refusal,
late completion/progress/cancel, cancellation retention, missed-event fallback,
delayed SID/Game chooser acceptance, USB/SID/Game/Flash/Files confirmations,
Bulk Import refusal and actual execution, sequential additions, and independent
Core local/device execution. Development GTK checks use synthetic/local fixtures;
Python socket connections are trapped. Real chooser response signals and continued
GTK heartbeat passed. Cancel controls remain in their existing locations.

Focused modules: test_foreground_admission, test_app_lifecycle, test_ftp_mutations,
test_game_library_client, test_sid_jukebox_client, test_jobs, test_scheduler,
test_machine_safety, test_header_navigation, test_usb_backup_preferences,
test_game_library_bulk, test_sid_playback, test_game_launch, test_cancel_copy.
GTK: foreground_gtk_check plus nine affected PreferencesUI methods covering the
heartbeat, SID preparation/cursor behavior, Game launch/batch addition, and Bulk Import.
Initial fixture assumptions were updated for deferred factories; local fake FTP
sockets required sandbox permission. Final checks pass; no tests were removed.

Syntax, tracked and explicit-untracked whitespace, file modes and bounded added-line
privacy checks passed. Worktree contains only this prerequisite; index remains empty.
No physical qualification is required. No device contact, staging, commit/push,
packaging, tag/release or later-roadmap work. Streaming remains OPEN / intermittent /
instrumented. Stop for compact prerequisite re-review before starting the B5 presenter.

## B4 — bounded physical acceptance passed; publication approved, not executed

**APPROVE COMMIT/PUSH — not executed.** The approved bounded physical acceptance
used this current worktree through `./run-development`, not the installed package.
Starting HEAD/local origin was `9d0c543b7f7497428463a4890098fae6c30d937b`, divergence
0 0, empty index; pending scope was 19 files (+1359/-142). The following acceptance
supersedes earlier B4 review/physical-pending stop markers without rewriting history.

Development session-only mode connected once through the normal saved connection
flow to **C64 Founders / Founder 25BE71**, firmware 1.1.0, API 0.1. The user entered
the password locally; persistence controls were hidden and storage was unchanged.
One explicit Reconnect preserved the active profile, host and verified identity,
created a new session and completed without duplicate reconnect/recovery.

Read-only Ultimate Menu loading returned 213 settings in 17 sections before
Reconnect. Afterward the stale rows, Apply and Save to Flash were disabled, with
truthful reload guidance and the Core connection valid. A deliberate read-only
reload restored fresh rows/normal eligibility. No edits, Apply or Flash save.

Header order, original blue/red 24-pixel Commodore artwork, Settings title/pages,
and keyboard traversal through all four actions passed. The user verified the
Ultimate Power hover tooltip and that the physical C64U stayed normal. Ultimate
Power exposed only Reset/Reboot; both real confirmations opened and were CANCELLED.
Zero machine-command submissions, no unexpected recovery. Machine and Quick Connect
were absent; saved connection management remained available in Device details.

Header remained usable without overlap/clipping at actual sizes 1121x850 and
1300x1000. A requested 900-pixel width was constrained by the existing full-window
minimum; smaller-width header evidence remains the prior offline GTK qualification.
Normal close exited the Development process and cleared all session credentials;
no recovery worker remained. Observation tooling/screenshots stayed outside the
repository. Production/test files were unchanged by physical acceptance.

No device configuration/storage/power mutation, stream, discovery/scan, command
execution or repeated qualification. Prior 207 focused and 16 offline GTK results
remain unchanged; suites were not rerun. Streaming remains **OPEN / intermittent /
instrumented**. Section H remains pending broader power/memory capability review.
Only this status and the roadmap were updated; no staging/publication/package work.

**Stale Flash confirmation correction implemented; pending final B4 re-review.**
Final narrow review exposed an already-open Save to Flash confirmation surviving
loss/restoration: Core's reusable facade passed the dialog identity check, while
the final callback omitted the freshness guard. `save_to_flash` now rechecks
`requires_refresh` in that callback before worker submission, refusing with reload
guidance. It preserves stale settings/drafts and the valid restored Core session;
no worker, reload, retry or replacement confirmation is started on refusal.
The existing fresh-confirmation behavior is unchanged. No separate settings
version token exists; the correction uses the established authoritative gate.

Four new offline real-GTK regressions passed: old confirmation across loss/recovery,
old confirmation across actual connected Reconnect, retained drafts, and a fresh
confirmation executing exactly once. Stale tests repeat the real dialog response
and verify zero submissions/writes. All **207 focused B4/settings/Flash tests**
and **16 explicit offline GTK checks** passed, no skips. Production amendment is
three lines in SettingsTab only; Core/scheduler/recovery and other B4 contracts
are unchanged. No broad suite rerun or device contact. Earlier evidence below
remains history. **READY FOR FINAL B4 RE-REVIEW**; physical acceptance stays
blocked until review approves this correction.

**Fresh-settings correction implemented; pending compact B4 re-review.** The
compact review found that connected Reconnect bypassed the loss callback which
previously established Ultimate Menu's stale-settings gate. Restoration displayed
reload guidance but could leave Apply and Save to Flash enabled. The existing
`requires_refresh` transition is now centralized in
`SettingsTab.require_fresh_settings()` and invoked on both loss and restoration.
It retains drafts/pending edits, disables stale rows and recalculates actions;
the restored Core session remains valid. Existing Apply/apply-reviewed/Flash
controller guards refuse stale operations. Discard followed by a fresh reload
clears the gate normally; no draft replay or automatic discard occurs. Even with
no edits, Save to Flash remains unavailable until reload.

Correction verification: four new offline real-GTK regressions exercise actual
connected Reconnect and loss/recovery, each with/without drafts, including stale
programmatic action refusal, retained edits, discard/reload and session validity.
All **159 focused tests** passed (the previous 146-test B4 set plus configuration
and settings-safety tests), followed by all **12 explicit offline GTK checks**,
with no skips. GTK traps Python socket connections. No Core/scheduler/recovery,
Reset/Reboot, credential, discovery, header layout or asset changes in this
correction. Earlier broad prerequisite evidence remains applicable and was not
rerun. No device contact. **READY FOR B4 RE-REVIEW**; physical acceptance remains
pending, and the earlier B4 review stop below is superseded by this re-review gate.

**APPROVE PREREQUISITE — B4 MAY RESUME.** Final compact re-review of the amended
Reset/Reboot prerequisite passed before B4 implementation. Its immutable target,
one-shot response before destruction/scheduling, failed-handoff disposal, privately
retained transport, atomic admission/dispatch, nonblocking GTK handoff and no-replay
contracts remain intact. Admission → device reservation has no reverse waiting
path: session transitions refuse contention. Earlier prerequisite stop markers
below record the review history and are superseded by this final-review result.
No physical qualification was required for that deterministic race correction.

B4 started at HEAD = local `origin/development` =
`9d0c543b7f7497428463a4890098fae6c30d937b`, parent
`b075bddd795b1b104dc5632477444bd85bb7ba39`, subject
`Refine Device Details connection profile layout`; divergence `0 0`, empty index,
and exactly nine pending prerequisite files (+595/-27), including its new test.

Header is now **Reconnect → Disconnect → Settings → original blue/red Commodore
C= icon**. Quick Connect's button and route are retired; two obsolete lifecycle
tests were replaced by eight explicit Reconnect routing tests. Connected or
retained-offline Reconnect invokes existing Core reconnect for the ACTIVE profile,
ignoring unrelated selection. Disconnected Reconnect uses Core connect-selected
with required saved identity binding; absent/unbound selection refuses. The GUI
shares Recovery's in-flight guard, refuses concurrent attempts, and sends results
through existing recovery/activation paths. Neither route persists credentials.
Core/session/scheduler/recovery implementations are unchanged by B4 itself.

The Settings header, dialog title, messages and related navigation guidance use
Settings; General / Device details / About and persistence semantics are unchanged.
Internal preferences APIs retain their names. Feature-specific legacy wording
outside this header/dialog scope, including Streams, was not edited.

Ultimate Power is an icon-only global button with accessible name `Ultimate Power`
and tooltip `Ultimate Power` / `Power, reset, and memory actions for the connected
C64 Ultimate.` It opens a closeable/reopenable dialog containing only Reset C64
and Reboot C64 plus the existing operational explanation. Machine contained no
other operation and its top-level tab/module/routes are retired. The reviewed
command handler moved structurally unchanged into `power_dialog.UltimatePower`;
all 22 machine-safety tests now exercise that class. Real GTK button-route tests
also prove cancellation, exactly-once dispatch, stale refusal and failed-handoff
cleanup. No expanded F1 commands; section H remains deferred.

Asset: `c64u_browser/assets/commodore-c-equals.svg`, the unchanged 454-byte Commons
`Commodore C= logo.svg` by Alien426, canvas crop by DigitalIceAge. CC BY-SA 4.0;
source/revision/license links and trademark/public-release review note are bundled
in `assets/COMMODORE-ATTRIBUTION.txt`. Original blue/red paths, no fonts, no recolor.
GTK loads it through module-relative ASSETS at a verified 24×24 allocation. Native
SVG decoding passed. Debian copies the complete asset directory; Windows/macOS
specifications include it likewise. No manifest redesign or package build.

Verification: **146 focused/affected tests passed**, including 22 machine safety,
eight Reconnect, lifecycle, Core, recovery, scheduler, API machine routes,
credential/device-details, discovery, connection layout and preferences/channel
regressions. **Eight explicit offline real-GTK checks passed**, with Python socket
connections trapped, testing widget order, accessible label assignment, SVG decode,
header keyboard traversal and non-overlap at 640/740/900 widths, existing Settings
pages, Power close/reopen, action keyboard access and actual button safety routes.
These display checks live in `tests/b4_gtk_check.py` and are invoked explicitly;
no default-suite skips were added. Two existing display-test tab indices now resolve
the Streams page by widget, avoiding a stale numeric index after Machine removal.

Commands: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python3 -m unittest
 test_header_navigation test_machine_safety test_app_lifecycle test_recovery
 test_core test_scheduler test_drives test_connections test_connection_layout
 test_device_details test_package_credential_channel test_app_preferences`;
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python3 -m unittest b4_gtk_check`.
The first GTK run exposed delayed destroy-signal cleanup of the Power dialog;
explicit response/close-request cleanup fixed it before the passing rerun.
The unchanged prerequisite full-suite/Offline Test Lab evidence below remains
prior evidence, not a new B4 full-suite result. B4 is presentation/wiring only.

No C64U contact. Physical acceptance remains pending: inspect header/icon and
Settings, explicitly Reconnect once and verify identity/status, open Ultimate
Power, and CANCEL both confirmations. Executing either hardware command requires
separate explicit authorization. Streaming remains **OPEN / intermittent /
instrumented**. Test Lab/Developer Mode, expanded section H and later roadmap work
are unchanged. No staging, commit, push, package, tag or release. **READY FOR B4
REVIEW**; stop before physical acceptance or publication.

## B4 prerequisite — Machine confirmation safety, pending review

**Amended after compact review — pending final re-review:** a failure before
Core execution could retain the confirmation target. The response handler now
marks itself one-shot before dialog destruction or scheduling, discards the target
on synchronous handoff errors and terminal completion, and rejects all repeated
responses. `Browser.run` now explicitly returns submission acceptance/refusal;
refusal discards authorization without recovery. Core's reviewed binding, admission,
reservation and uncertain-outcome lifecycle are unchanged.

Five new regressions cover both Reset and Reboot: actual worker-submission failure
and old-callback reuse, synchronous handoff exception, busy submission refusal,
dialog-destruction exception, and reentrant destruction/double response with an
accepted deferred worker. All five passed, then all **22 machine-safety tests**
and **48 directly related Core/scheduler/recovery/API-route/connection/layout tests**
passed without skips. Syntax and whitespace passed. Earlier full normal/optimized,
credential and Offline Test Lab results below remain prior evidence, not reruns
of this amendment. No device contact or broader B4 work. **PREREQUISITE READY FOR
FINAL RE-REVIEW**; B4 stays paused.

B4 inspection exposed a pre-existing Reset/Reboot race: confirmation retained
Core's reusable facade, so recovery could replace the intended session before
confirmation and the old dialog would dispatch through the replacement transport.
The explicitly approved prerequisite correction is implemented and deterministically
verified; broader B4 implementation remains paused pending review.

Starting authority: HEAD = local `origin/development` =
`9d0c543b7f7497428463a4890098fae6c30d937b`, parent
`b075bddd795b1b104dc5632477444bd85bb7ba39`, subject
`Refine Device Details connection profile layout`; divergence `0 0`, clean index
and worktree. That layout checkpoint is published; its older publication-pending
wording below is historical.

Confirmation now captures a frozen, single-use Core target: action, physical-device
session, profile ID, host and opaque token. Core privately retains the exact client;
no transport or credential is returned to GTK. Cancellation discards the target.
Core validates session, profile, target identity and exact client before dispatch.
A per-Core nonblocking admission gate is shared with connect, reconnect, disconnect
and connection-loss transitions, covering validation through command outcome.
The existing `CoreScheduler.inline` / `JobBinding.device` reservation serializes
machine commands with device jobs; its new opt-in busy refusal does not queue a
machine action behind existing work. Default FIFO diagnostic behavior is unchanged.
GTK only captures the target and submits worker work; it never waits on admission.

Both Reset and Reboot consume the target on admission/refusal/uncertainty. Stale
confirmation reports `Connection changed. Reset was not sent.` (or Reboot).
The unguarded machine route on the reusable facade is removed. Existing API
allowlisting and post-command recovery remain; contention is not a network loss.
Disconnect refuses contention without cancelling the recovery watch. Late command
completion cannot invalidate a newer session. No automatic command replay exists.

Verification: 109 focused/affected methods passed (machine confirmation, Core,
scheduler, recovery, API, connection/layout and R5 diagnostic reservation tests);
52 credential/device-details/channel checks passed. Normal and optimized full
suites each ran **1,253 methods: 1,217 passed, 36 unchanged display skips**.
Seventeen new machine regressions plus one recovery regression; no tests removed
and no new skips. Offline Test Lab passed **17/17**. Syntax and whitespace checks
passed. Deterministic cases cover cancellation, stale and reused sessions/bindings,
worker admission races, busy lane/recovery refusal, no redirection at dispatch,
nonblocking callbacks, and no replay after uncertain responses.

The initial sandbox full run hit 660 loopback-socket permission errors. With local
fixture sockets permitted, two R5 diagnostic observer tests exposed an optional
argument compatibility regression; preserving the original default submission call
resolved it before the passing focused and full reruns. No C64U was contacted.
No physical acceptance is needed for this prerequisite. No header, logo, Settings,
Machine-tab removal, new power command, streaming, credential or discovery change.
Streaming remains **OPEN / intermittent / instrumented**. No staging, commit,
push, package, tag or release. **PREREQUISITE READY FOR REVIEW**; resume B4 only
once this correction passes review.

## Device Details / connection-profile layout — accepted, publication pending (7 October 2026)

Starting authority: HEAD = local `origin/development` =
`b075bddd795b1b104dc5632477444bd85bb7ba39`, parent
`17ad4e2bb7acd441560a3160fbcc224d13d30536`, subject
`Stabilize Device Details credentials and discovery`; divergence `0 0`, clean
worktree and empty index. That credential/discovery checkpoint is published;
its older pre-publication wording below is historical. Its contracts stay intact.

The current selector contains only saved Core profiles (ID/name), not a mixture
of machines and discovery candidates. Selection copies that profile into the
form and reconstructs exact-bound credential state. Discovery has a separate
address/port result list; selection starts an unsaved form, without binding an
advertised device ID or automatically saving. Existing profile semantics remain:
rename/metadata edits retain ID; host/port changes follow Core's new-ID rule;
New clears the editor; Delete removes the selected profile through the same Core
path and disconnects it if active. No persistence or confirmation policy changed.

Layout now reads identity/details → credentials → status/errors → Network
Discovery → Saved Network Connections/profile actions → separate Test/Connect.
The saved selector moved from the top to the bottom; it is labeled Connection.
New / Save Profile / Delete Profile share one group, with Test / Connect separate.
Read-only Saved device ID describes the existing binding, not live verification.
Saved, new and discovered-unsaved editing states are explicit. Ethernet/Wi-Fi
remain separate network profiles for a physical C64 Ultimate. Quick Connect is
owned by the global header in gui.py; its planned removal stays with header cleanup.

Validation: **117 focused tests passed** (109 preserved plus eight layout/controller
regressions). Real GTK offline construction, rendered-layout inspection and keyboard
traversal passed in Installed, Development and Portable modes with synthetic profiles,
fake stores and mocked network enumeration. Password Enter still invokes Connect;
no persistence action is a window default. The initial new-test run exposed a fixture
method-binding error; it was corrected before the passing run. Broad suites were
not rerun: production edits are widget construction and presentation-state labels.
Authentication/persistence/discovery execution bodies and existing tests are unchanged.

Small user-authorized physical/UI acceptance subsequently passed through the current
worktree's `./run-development`, build `b075bddd795b-modified`, using the existing
Development configuration and Founder profile. The installed Debian package was
not used or rebuilt. Starting acceptance inventory was exactly the reviewed four
files, +344/-44; index empty, authority and divergence unchanged.

Acceptance observations:

- At normal 740×680 Device Details size, identity/details → credentials → safe
  status → discovery → saved connections → Test/Connect remained clearly grouped.
  Vertical scrolling is required; this is a long form, with no overlap or broken
  grouping observed. Saved Network Connections / Connection and the separate
  profile-action and connection-action groups were clear.
- Founder `.69` populated the saved name, endpoint and stored ID `25BE71`, with
  `Editing saved connection: C64 Founders`. New showed the unsaved state; returning
  to the existing profile left the preferences file byte-for-byte unchanged.
  No Save Profile, Delete Profile or new-profile persistence was exercised.
- The exact Development session-only text was visible; Remember/Forget remained
  hidden and disabled. The user entered the valid password locally; no secret
  text was printed or saved in acceptance artifacts.
- Real GTK forward-Tab traversal reached name, host, ports, identity/metadata,
  model controls, Password, status, Discover, subnet/Scan Subnet, discovery area,
  saved selector, New/Save/Delete, automatic-connect, Test and Connect in visual
  order. Read-only/selectable and composite-widget focus stops also occurred;
  no focus trap or unexpected jump back to an upper control was observed.
- One PasswordEntry activation (the Enter action) invoked Connect. The normal
  Core path verified Founder `25BE71`, hostname `C64-Ultimate-2B02C3`, firmware
  `1.1.0`, API `0.1`. Status explicitly said `Connected · Authenticated. Connection
  profile updated; password storage unchanged.` A separate Test ran once and
  succeeded. No second Connect was performed.
- Discover ran once, remained responsive and completed with `2 network connections
  found`: verified Beige `.70:80` / `25EA78`; password-required Founder `.69:80`
  advertisement. Saved selection, form name/host and typed input remained intact;
  results stayed separate from saved profiles. No Scan Subnet invocation occurred.
- Device Details was rendered and inspected at 640×600, 740×680 and 900×850 while
  the main app was also resized smaller/larger. Labels/results wrapped readably,
  buttons did not overlap, no horizontal clipping was seen, and saved connections
  and Test/Connect remained reachable. Normal size was restored before closing.
- Normal close cleared the session dictionary; no Development GUI/discovery
  worker remained. Credential backend method counters stayed at zero. The external
  observer attempted one snapshot after the dialog was destroyed; that observer-only
  error did not affect normal app exit (exit 0) or cleanup verification.

This was automated inspection of the real desktop GTK workflow with user-entered
credentials; focus traversal and PasswordEntry activation used GTK's own APIs.
No device configuration/storage/power changes, stream, subnet scan, repeated 403
or credential-state qualification, or broad test rerun occurred. Screenshots and
observer data stayed outside the repository. Production/test file hashes remained
unchanged throughout acceptance; only these current-state/roadmap notes were updated.

**APPROVE COMMIT/PUSH — not executed.** Index remains empty. No staging, commit,
push, package, tag, release or next-roadmap work. Streaming remains
**OPEN / intermittent / instrumented**. Historical R4–R6/FTP records are untouched.

## Device Details stabilization — publication gate passed (7 October 2026)

Credential UX and Discover / Scan Subnet are implemented against published
`17ad4e2bb7acd441560a3160fbcc224d13d30536`, preserving the pending roadmap.
Test/Connect never persist passwords; Save Profile owns the Remember decision,
including removing the exact-profile stored password when unchecked. Fixed saved
indication uses a boolean existence boundary, including the explicitly approved
Windows opaque-buffer exception. UNKNOWN blocks Save before persistence; deliberate
retry preserves edits without replaying Save. Development and Portable are session-only.

Compact re-review passed; all 109 focused tests passed again. Earlier broad suites
remain historical evidence, not rerun results. User-authorized `./run-development`
physical acceptance passed with existing profiles: Founder typed-password Test,
Connect, one visible HTTP 403 rejection, restored valid authentication, and clean
session clearing across normal close/restart. Development labels and hidden/disabled
persistence controls were verified, with no credential-store calls.

One Discover found two network connections. One `192.168.68.0/24` scan within the
host's actual connected `/22` completed with 254-host progress to 100%, finding
Beige. Password-protected Founder was retained by Discover's Ident advertisement
but excluded by the existing credential-free subnet verification policy. Invalid
input started no scan; GTK remained responsive. No device mutations or lingering
acceptance processes. See [detailed evidence and limitations](DEVICE-DETAILS-STABILIZATION.md).

Installed native Secret Service/macOS/Windows store acceptance remains later
packaging/release work. The installed Debian package was not rebuilt or replaced;
this qualifies the current source worktree using supported Development semantics.
Streaming P0 remains **OPEN / intermittent / instrumented**, untouched.
**APPROVE COMMIT/PUSH — not executed.** Index empty; no staging, commit, push,
package, tag, release or next-roadmap work. Include the reviewed pending roadmap
consolidation with its narrow current-state updates in the same coherent commit.
Earlier documentation-only statements below record the preceding consolidation.

## Roadmap consolidation — documentation only, pending review

[ARGONAUT-ROADMAP.md](ARGONAUT-ROADMAP.md) consolidates the current product
priorities, settled walkthrough decisions, deferred scope, and open investigations.
It supersedes older next-work sequencing, not historical qualification evidence.
No roadmap implementation or item #1 diagnosis has begun in this pass.

Verified consolidation baseline: HEAD = local `origin/development` =
`17ad4e2bb7acd441560a3160fbcc224d13d30536`, parent
`f9457acd3bcef4269d9d98e95ef3c6dc33f90ff1`, subject
`Close FTP ownership compatibility paths`; divergence `0 0`, initially clean.
FTP ownership closure is published and complete; earlier uncommitted/review
wording below is historical. Do not reopen ownership work without evidence.
Per the current handoff, local Debian `argonaut-c64u-development` `1.10~dev1`
was built from that exact commit for walkthrough; ignored packaging output stays
out of Git. No public 1.10 release/tag yet. Stop for Bruce/ChatGPT roadmap review.

## Authority and workspace

This document describes the current accepted development state and next work.
[C64U-FTP.md](C64U-FTP.md) and [SERVER-FIRST.md](SERVER-FIRST.md) provide detailed
subsystem and Core architecture/contracts. Older roadmap/pass documents,
including NEXT-PASS.md, remain useful context, but sequencing demonstrably
superseded by completed development and release history does not override the
current state recorded here.

- Stable 1.9 is released as `v1.9`. Its release artifacts are immutable.
- `main` and `v1.9` are not the 1.10 development workspace. Current 1.10 work
  belongs on `development`.
- Verified post-R5 development authority:
  `dab627979b9d3bb085c955c6e3bea8cdaff8b338`
  (`Implement R5 Core-owned headless reads`), parent
  `8ac1b24cb70f996b877b3eef81fd1c5817748bff`. R5 is accepted, committed and pushed.
  On 4 October 2026, HEAD and local `origin/development` matched with divergence
  `0 0` and a clean worktree before the R6 documentation-only design pass.
  R2–R5 physical acceptance evidence remains recorded below and in their docs.
- Argonaut 1.10 direction: **C64U Network Foundation**.

## Completed FTP work

**Slice 1 — dedicated compatibility layer:** `C64UFtpClient` provides typed
capabilities/errors and session lifecycle, IPv4/classic PASV, explicit binary
behavior, FEAT negotiation, bounded byte-oriented MLSD and controlled LIST
fallback. A real socket-level fake C64U FTP server exercises the protocol.
Transport objects and credentials do not escape to clients.

**Slice 2 — read-only production migration and physical acceptance complete:**
ordinary listings, raw/octet-preserving identity listings and bounded remote
reads use the new client. Full-volume fingerprint traversal reuses one
operation-scoped lease. At that checkpoint, mutation/write paths and remaining
streaming downloads retained their legacy implementation. The Development
package self-test now enforces channel-specific credential behavior; credential
implementations are unchanged.

Slice 2 automated baseline: normal and optimized suites each ran 791 tests
with 36 opt-in display skips; 78 focused FTP/adapter/credential tests passed.
See C64U-FTP.md for migration boundaries and detailed acceptance evidence.

## Architectural decisions to preserve

- Use specialized protocol clients, not a generic `C64UNetworkClient`.
- Core owns physical-device identity and connection-session binding. An FTP
  session is not a Core connection epoch; opening a lease must not regenerate it.
- Prefer negotiated and observed/verified capabilities over firmware-version
  assumptions. Advertisement alone is not verification.
- Use IPv4/classic PASV with no EPSV dependency. Prefer MLSD; permit only the
  narrowly defined LIST fallback.
- Preserve raw filename octets independently from display text.
- Default to one operation-scoped FTP lease per device, no idle FTP pool.
  Nested helpers reuse the existing lease; do not retain it across user review.
- Never automatically replay an uncertain mutation.
- Transport completion is distinct from higher-level content integrity,
  conflict/replacement policy and destructive authorization.
- Keep device rules, credentials, scheduling and safety in headless Core;
  user interfaces remain clients.

## Physical FTP acceptance

Both devices passed on their currently installed firmware; no firmware changes
were required. FEAT, MLSD, PASV, SIZE and RETR were verified without LIST fallback.

| Device | Address | Physical ID | Firmware | API | Accepted evidence |
|---|---|---|---|---|---|
| Beige C64 Ultimate | `192.168.68.70` | `25EA78` | `1.1.0s2` | `0.1` | GUI/root/PWD/USB1/USB2 browsing; deterministic full USB1 fingerprint; SID catalog validation and repeated 8,952-byte reads; cancellation/reconnect |
| Founder's Edition C64 Ultimate | `192.168.68.69` | `25BE71` | `1.1.0` | `0.1` | Root, USB1 and SD browsing; `/SD/test.txt`; repeated SIZE → RETR → SIZE and exact four-byte reads |

Beige full USB1 scans used **34 directory listings through one control
connection, one authentication and one FEAT negotiation**. Repeated digest:

`40922faa550ffb0beab47992263af1167d015db10512cbfd5a5bae1792b899f5`

Elapsed times were approximately **10.992 s / 10.943 s**. Cancellation after
five directory listings, fresh reconnect and post-cancel root browsing passed.
No relevant FTP behavioral difference or compatibility quirk was observed on
the Founder's Edition; the firmware strings do not establish materially
different FTP implementations.

## Known observations and planned improvements

- An advertised storage root may lack accessible media; startup-root selection
  can therefore receive FTP 550. The external acceptance probe's assumption that
  connecting with `/` would remain there was corrected separately. Acceptance
  used the corrected probe; production initial-folder behavior is unchanged.
- No Stable 1.9 physical fingerprint timing benchmark exists. Do not claim a
  measured wall-clock speedup. Reduced connection churn is physically proven by
  the complete 34-directory traversal using a single session.
- Cancellation during blocking I/O can remain bounded by the socket timeout.
- Improved Reset/Reboot recovery UX remains future work.
- Quick Connect → Reconnect is planned.
- A System/Light/Dark theme preference is planned.

## Slice 3A — accepted, committed and pushed

Slice 3A was physically accepted on both C64Us and committed/pushed to
`development` as `0f5b77f88f4fac6bddac0fa5e3cc2f5929ab544a`, with parent
`4f7a86745239e60b3c6f4e2287d94af8b3c00508`. Authorized read-only physical
checks passed on 27 September 2026; final review and the approved commit/push
are complete.

Core-bound streaming downloads and USB content hashing now use the managed FTP
client. Their SIZE → RETR → SIZE observations preserve exact counts and received
hashes, including zero-byte files. Downloads retain local staging, flush/fsync,
no-replace publication and failure/cancellation cleanup. USB backup retains its
preview read, execution download, local reread and independent remote reread;
the execution listing and two remote reads share one per-file lease. Preview
and execution remain separate lifetimes.

The private operation lifetime is shared by nested read helpers: fixed Core
binding, lazy acquisition, outermost release and operation-owned cancellation.
Structured transport outcome/count evidence survives translation. Binding and
recovery checks remain independent of cooperative cancellation. Context exit
does not itself check cancellation. A failed lease cannot implicitly reconnect;
the existing preferred-directory fallback explicitly ends its read attempt.
Bounded reads and full-volume fingerprints preserve their existing contracts.

3A automated verification: **139 focused tests passed**; complete normal and
optimized suites each ran **806 tests with 36 opt-in display skips**, no failures.
The increase over the accepted 791-test baseline is 15 new integration tests;
no existing tests were removed and the skip count is unchanged.

Physical 3A coverage: normal Core file-copy download, nested streaming download
and independent USB hash, selected-file backup preview/execution, local reread
verification, idle Core reconnect and rejection of the old binding before wire
access. Beige `25EA78` (`192.168.68.70`, firmware `1.1.0s2`) used the existing
8,952-byte `/USB1/sid/arcademem.sid`; Founder's `25BE71` (`192.168.68.69`, firmware
`1.1.0`) used the existing four-byte `/SD/test.txt`. Both retain API `0.1`.

Nested listing/download/hash and each backup file's execution verification used
one FTP session, one authentication and one FEAT. Preview and execution retained
separate observations; no active leases remained after measured operations.
Hashes matched the existing Slice 2 file evidence and local backup manifests.
No zero-byte file existed in the inspected source directories; none was created.
No remote mutation, active-transfer interruption or production code change was
performed during acceptance. See C64U-FTP.md for counts, hashes and limitations.

## Slice 3B — accepted, committed and pushed

Slice 3B was physically accepted on both C64Us and committed/pushed to
`development` as `fd0e205deece43865293d2a61d64bdc3834b3c05`, with parent
`0f5b77f88f4fac6bddac0fa5e3cc2f5929ab544a`. Authorized physical checks passed
on 27 September 2026, including automated actual-display GTK rename
qualification. Final acceptance review and the approved commit/push are complete.

Managed RNFR/RNTO, MKD, DELE and RMD retain structured mutation certainty,
submission evidence, actual reply codes and acknowledged prior steps. No result
authorizes replay. Remote rename now enters a dedicated FileService device job.
Standalone FileService folder creation and reviewed remote deletion explicitly
use the same private operation owner as reads; nested validation listings reuse
one lease. Deletion preview and execution remain separate operations.

Cooperative cancellation is deferred through each submitted mutation's reply,
through RNFR/RNTO as one serialized pair, and across both case-only rename pairs.
Binding/recovery and transport failures remain effective. Case verification
restores cancellation and retains both completed steps if verification stops.
Reviewed deletion records only acknowledged removals, the stopped target and
its mutation evidence, and unattempted reviewed items. Existing review, expiry,
session, revalidation, ordering, bounds and root protections remain in force.

After the approved GUI session-guard correction, deterministic verification is
**7 GUI/routing tests and 223 focused tests passed**. Complete normal and
optimized suites each ran **849 tests, 36 opt-in display skips, no failures**.
The original 38 mutation tests plus five GUI regressions add 43 tests to the
accepted 806-test / 36-skip baseline. The existing in-memory USB partial
cleanup test now supplies the managed cleanup seam; socket coverage verifies
real managed partial cleanup. No prior test was removed.

Physical results: beige `192.168.68.70` / `25EA78`, firmware `1.1.0s2`, and
Founder's `192.168.68.69` / `25BE71`, firmware `1.1.0`, both API `0.1`, passed
managed standalone MKD, ordinary and case-only file/directory rename, content
readback, and reviewed DELE/RMD. Unique disposable trees under beige `/USB2`
and Founder's `/SD` were emptied and removed through reviewed deletion only.

Each managed mutation operation used one session, one authentication and one
FEAT, including both case-only rename pairs and nested validation. Leases were
released and connection epochs stayed unchanged within each phase. The real GTK
prompt, busy controls, completion and refreshed name were exercised by an
external driver on display `:0`; this is automated GUI qualification, not human
visual sign-off. The stale-session GUI race remains deterministically covered;
no active mutation was interrupted and no uncertain-outcome fault was induced.
Production/test source hashes were unchanged throughout qualification. Details,
hashes, disposable paths and external probe limitations are in C64U-FTP.md.

## Slice 3C — accepted, committed and pushed

The approved 3C implementation is based on accepted 3B commit
`fd0e205deece43865293d2a61d64bdc3834b3c05`. It migrates normal FileService
Core-host → C64U file additions, including folder-plan files, and USB restore
addition files. Explicit routing leaves legacy `upload()` consumers unchanged.
Authorized physical 3C checks passed on both devices on 27 September 2026.
Final acceptance review passed; 3C was committed and pushed as
`6a09af5b8559df73d83e12db3eeeeba3d8106a1a`, with parent
`fd0e205deece43865293d2a61d64bdc3834b3c05`. No package or release was created.

Each file's plan validation and preflight listings, STOR, independent bounded
RETR/hash, SIZE, destination recheck and publication rename reuse one managed
operation lease. Files do not share a batch-wide lease. Publication uses 3B
RNFR/RNTO; no post-publication read or cancellation check is added.

The source is opened once and sized with fstat on the transferred descriptor.
Short/overlong sources fail; same-length rewrites remain outside the guarantee.
No source locking, snapshot, second source open or mtime/inode stability check
is introduced. Verification RETR is bounded by the sent count and rejects an
excess block before accepting it. Its order remains RETR/hash → SIZE.

Structured results retain STOR submission/replies/count/length evidence,
verification states and publication evidence. A lost RNTO reply yields
location-unknown evidence with both possible paths, without a staging-only
cleanup shortcut. Acknowledged publication remains completed despite late
cancellation. Staging candidates still require fresh, session-bound reviewed
deletion; they are not proof of existence or exclusive ownership. No automatic
retry, rollback or remote cleanup is introduced.

After the pre-physical evidence correction, **234 focused tests passed**; normal
and optimized suites each ran **883 tests with 36 opt-in display skips, no
failures**. This is the accepted 849-test baseline plus 34 new tests (29 initial
3C tests and five correction regressions); no existing tests were removed.
Pre-STOR setup failures now retain STOR not-started evidence separately from
the sanitized setup failure, including its phase and reply code.
Details are recorded in C64U-FTP.md. Implementation/pre-physical review and
the evidence correction were approved before physical qualification.

Both devices passed zero-byte and 1,076-byte known-content FileService uploads,
independent published-file readback, case-insensitive collision refusal, and a
genuine USB backup/restore addition with verified manifest and result accounting.
Beige `25EA78` used `/USB2` (firmware `1.1.0s2`); Founder's `25BE71` used `/SD`
(firmware `1.1.0`); both reported API `0.1`. Each normal upload and each restore
file upload used one session/authentication/FEAT across preflight, STOR, RETR,
SIZE, recheck and publication. All measured operations released their leases
and preserved the Core epoch. Independently inspected disposable trees were
removed through accepted reviewed deletion and verified absent.

Physical cancellation/partial cleanup was intentionally not attempted: no safe
controlled timing boundary was available. Fault injection and uncertain outcomes
remain qualified by deterministic fixtures. Production/test source hashes were
unchanged during qualification; only this document and C64U-FTP.md were updated.
C64U-FTP.md records exact paths, hashes, external evidence and limitations.

At the 3C checkpoint, replacement, composites, Flash, CLI and AI provisioning
remained deferred. The implemented 3D boundary and remaining exceptions follow.

## Slice 3D — accepted, committed and pushed

The approved 3D implementation is based on the accepted 3C commit above.
`managed_replacement.replace_managed` is selected explicitly for FileService
reviewed local-source and remote-source replacements with a C64U destination,
and USB restore replacement steps. Legacy `replace_file()` is unchanged; AI
upgrade and local-destination replacement do not silently migrate.

Each replacement owns one managed lifetime across execution validation, staging
MKD, original observation, staged copy, signature revalidation, independent
original observation, backup inspection and protected exchange/cleanup. Nested
listings, 3A reads/downloads, 3C uploads and 3B mutations reuse its fixed-binding
lease. A failed operation cannot reconnect, replay, reset as a read fallback or
continue cleanup. Preview and subsequent failure inspection are separate operations.

Both original observations now use exact SIZE → RETR/hash → SIZE. This approved
change rejects unavailable/malformed/changing SIZE and short/overlong reads.
Generic remote review still contains name/size only; these two execution reads
provide neither a review-time hash nor a source snapshot or atomic exchange.
USB restore retains content-bound comparison only where its existing equal-size
classification hashes the destination; different-size classification remains
size-based. Independent observations are never replaced with cached hashes.

Local sources use managed upload into the unique staging directory. Remote
sources first use managed download into a private local temporary directory,
then managed upload; local temporary cleanup runs on all exits. The nested
upload's published state means publication inside staging, not final replacement.

After backup-name inspection, a final binding/cooperative-cancellation check
precedes the protected original→backup, staged→final, DELE backup, RMD staging
sequence. Cooperative cancellation alone is deferred across that finite sequence.
There is no exit cancellation check or automatic rollback. Completed replacements
remain completed; pending cancellation takes effect before the next item.
Binding/recovery/transport failures and unrelated exceptions still stop work.

Ordered replacement evidence is carried separately in copy/restore results:
staging MKD/upload, original observations/signatures, each exchange/cleanup
mutation, acknowledged prefix, uncertain paths and publication versus cleanup
status. Publication-completed/cleanup-failed is explicitly reported, even though
whole-workflow accounting leaves that item unfinished. Replacement evidence never
authorizes cleanup and does not become an ordinary PartialUpload shortcut.
Later inspection and explicitly selected reviewed deletion require new operations.

The pre-physical corrections preserve normalized remote/cancellation evidence
before local temporary cleanup. A cleanup error is recorded separately with a
sanitized category; acknowledged remote success remains success in the remote
state even when local cleanup fails. Core-formatted inspection summaries now
reach copy and USB reports, including cancelled copy jobs with replacement
evidence. They identify relevant paths and uncertainty without granting replay,
rollback or cleanup authorization. Ordinary PartialUpload behavior is unchanged.

After the pre-physical corrections, **8 targeted and 266 focused tests passed**.
Complete normal and optimized suites each ran **939 tests with 36 opt-in display
skips, no failures** (931 reviewed tests + 8 correction regressions; equivalently
883 accepted tests + 48 replacement tests + 8 corrections; no removals/skip changes).
The separately authorized physical pass passed on both C64Us on 27 September
2026, with 65 recorded checks per device. Beige `25EA78` (`192.168.68.70`,
firmware `1.1.0s2`, API `0.1`) used a unique disposable tree under `/USB2`;
Founder’s `25BE71` (`192.168.68.69`, firmware `1.1.0`, API `0.1`) used `/SD`.
Reviewed local-source and remote-source replacement and genuine USB backup/restore
replacement passed with independent 640-byte SHA-256 readbacks. Remote source
and sentinel were preserved; backup/staging artifacts and local temporary data
were removed. Each replacement reused one FTP session, one USER and one FEAT;
leases released and Core epochs stayed stable. Final reviewed deletion removed
each disposable tree and absence was independently verified. Cancellation and
fault injection were intentionally omitted. Source/test hashes are unchanged
from the reviewed implementation; the deterministic baseline remains 939/36.
See C64U-FTP.md for exact paths, hashes, evidence and physical-test limitations.
No commit, push, package or release was performed.

**At the 3D checkpoint, deferred:** Flash; CLI fresh-folder uploads;
AI installation/upgrade/provisioning; general compatibility/raw-FTP retirement
and final ownership audit. R1 has since migrated remote-to-remote nonreplacement
additions and general folder-plan directory creation; R2 has migrated CLI
fresh-folder uploads, as recorded below.
Local-destination replacement retains its existing behavior. Slice 3 as a whole
is not complete. Slice 3D is accepted, physically qualified, committed and
pushed at `8315985317086e52460c981a8135bffb359da958`.

## Later Network Foundation boundaries

Likely specialized boundaries are `C64URestClient`, `C64UStreamService`, a DMA
client where justified, and the existing Ident discovery capability. Shared
concepts may include identity, connection epoch, capabilities, credentials,
recovery, cancellation and structured diagnostics. Protocol-specific behavior
and consequence-specific safety remain explicit.
## Current checkpoint

R1 — Managed Folder Composites is implemented and physically qualified on both
C64 Ultimates. The authoritative contract and detailed physical acceptance
record are in
[R1-MANAGED-FOLDER-COMPOSITES.md](R1-MANAGED-FOLDER-COMPOSITES.md).

R1 migrates remote folder-plan MKD and same-device remote-to-remote
nonreplacement additions while preserving the accepted 3C addition and 3D
replacement boundaries. Implementation review added truthful pre-validation
`setup` evidence and explicit ancestor-change and genuine USB restore
missing-directory coverage.

Authorized physical qualification passed on 29 September 2026. Beige `25EA78`
used `/USB2`; Founder's `25BE71` used `/SD`. Both devices passed managed nested
directory creation, normal and zero-byte same-device remote-to-remote additions,
source preservation, independent destination verification, genuine backup and
missing-directory restore, stable Core epoch, zero remaining leases, reviewed
cleanup and independent absence verification.

Immediately after physical qualification, the focused R1 suite passed **20/20**,
the USB backup/restore regression suite passed **19/19**, and the FTP regression
family passed **186/186**. `git diff --check` was clean.

R1 is committed and pushed at
`d0e605ebdc29cca15558d7fb6c5bf2dcfc6690bc`.

R2 — Managed CLI Fresh-Folder Upload is implemented and physically qualified
on both C64 Ultimates as of 3 October 2026. The approved contract, implementation
boundary, deterministic evidence and physical acceptance record are in
[R2-MANAGED-CLI-FRESH-FOLDER.md](R2-MANAGED-CLI-FRESH-FOLDER.md).
Only production CLI put-new now uses saved bound profile authority and the
Core/FileService fresh-folder composite. Legacy read CLI, compatibility
upload_new_folder, Flash and AI routes remain unchanged. The opt-in nonempty
source descriptor guard preserves default 3C zero-byte support.

Final pre-physical deterministic verification passed **66 focused R2 methods**,
**276 affected regression methods**, and **17 offline Test Lab checks**. Normal
and optimized full suites each ran **1025 methods: 989 passed, 36 existing opt-in
display skips, zero failures**. No existing test was removed or renamed and
`git diff --check` passed.

Authorized physical qualification then passed independently on Beige `25EA78`
using `/USB2` and Founder's `25BE71` using `/SD` through the actual CLI put-new
path and saved identity-bound profiles. Independent readback verified the exact
byte counts and SHA-256 hashes, no staging artifacts remained, Core epochs stayed
stable, and active leases returned to zero. Reviewed cleanup removed exactly each
disposable acceptance tree and fresh-session listings independently verified
absence.

R2 is complete, committed and pushed at
`13bbc8a85d02cf75b1e58efde4e20b35d575e0df`. Pre-commit language in the R2
append-only design/acceptance record describes historical stages, not its
current status.

The post-R2 ownership assessment found four live raw-FTP consumer groups:
legacy CLI `ls`/`browse`/`get`, headless Test Lab `hardware.storage`, native Flash
writes, and AI installation/upgrade. CLI `info` remains an unmanaged REST read,
not a raw-FTP consumer. Their ownership is unchanged by R3.

**R3 — Compatibility Retirement is complete, committed and pushed.**
See [R3-COMPATIBILITY-RETIREMENT.md](R3-COMPATIBILITY-RETIREMENT.md) for the
approved contract, static audit and deterministic evidence. Removed
`transfers.upload_new_folder`, `_upload_new_folder`, `ConnectionDialog.credential`,
`file_copy.conflicts` and `CoreDeviceOperations.info`; renamed the Core resolver
to private `_credential_for` with unchanged signature/body and exactly four
internal callers. Only the explicitly commented saved-report diagnostic label
retains the old fresh-folder name in application source.

The four unreachable raw read fallbacks and folder-copy compatibility closure
remain deferred. The four live raw consumer groups listed above remain unchanged.
Physical qualification is not required because no live transfer workflow changed;
no C64U was contacted. R3 was committed and pushed as
`a081b01c4a62198b35b88199c4c8e48f9c535f90`; no package or release was created.

R3 deterministic acceptance: **162 focused methods** (including all 66 R2),
**257 FTP/USB regression methods**, and **17/17 offline checks** passed.
Normal and optimized suites each ran **1032 methods: 996 passed, 36 existing
opt-in display skips, zero failures/errors**. Three obsolete helper-only methods
were removed and ten added; useful assertions were re-homed or strengthened.
`git diff --check` passed. Earlier final-review/uncommitted wording in the R3
record describes historical stages, not current status.

## R4 — accepted, committed and pushed

The following qualification record preserves the pre-commit evidence; the
post-R4 authority above supersedes its former final-review stop.

[R4 — Managed C64 AI Installation](R4-MANAGED-C64-AI-INSTALL.md) now routes AI
file work through a single-use Core capability and the captured device's scheduler
lane. Exact-current verification uses full bytes at execution. Missing files use
3C; recognized same-config ai.1 uses 3D with full-byte predicates at both original
observations. Generic 3D defaults remain unchanged.

Private pending configuration precedes file work; publication, pairing, service
activation and health enablement require trustworthy file evidence and matching
configuration/session immediately before each new consequential command and the
active-config publication. File success and bridge failure remain separate, with
safe bridge command outcomes. Eligible retained pending configuration is reviewed
and reused before token generation; ambiguous/stale/context-mismatched candidates
stop safely. Every explicit re-entry has fresh Core binding/classification.
Successful verified commit consumes the private pending copy. Pre-submission
errors have safe phase categories and no private exception text/chains. Neither
remote rollback nor automatic replay is introduced. The accepted final-observation-to-rename external-writer window remains.

Corrected deterministic R4 evidence: 160 focused methods, 257 FTP/USB regressions,
normal and optimized suites each 1093 methods (1057 passed, 36 existing display
skips), and 17/17 offline checks. This pass adds 17 methods and renames two to
accurately describe session-field invalidation and mutation-before-reply
cancellation; no methods were retired and no skips added. Total additions since
R3 are 61. Historical implementation and review evidence remains in the R4
record, including failed iterations and exact commands. Static ownership/privacy
and whitespace checks pass, including untracked files.

`CoreDeviceOperations.open_ftp` is retained: automatic approval review rejected
its conditional removal because the production `transfers.connect` dynamic call
remains. AI has no raw/facade transport route. This leaves the conditional
retirement proof for review, without expanding into other consumers. Flash,
legacy CLI, headless Test Lab and broader ownership closure remain deferred.
Authorized controlled physical qualification passed on 4 October 2026: Beige
`25EA78` under `/USB2`, then Founder `25BE71` under `/SD`. Both passed actual Core
missing installation, exact-current no-op with zero mutation commands, synthetic
ai.1 upgrade with both authoritative full-byte matches, foreign/directory
refusals, independent byte/hash verification, stable session/epoch, zero leases,
exact reviewed cleanup and fresh absence verification. No staging/backup residue
remained. See the R4 physical record for exact roots, identities and hashes.
Only disposable files and synthetic private configuration were used; deployed
client, production bridge configuration, pairing/services/health and launch
were untouched. No commit, push, branch/worktree, package or release was performed.
The final review and subsequent R4 commit/push are complete (authority above).

## R5 — Core-owned headless reads: accepted, committed and pushed

[R5 implementation record](R5-CORE-OWNED-HEADLESS-READS.md) records the approved
saved-bound-profile CLI ls/get migration, retirement of browse, REST-only info,
and managed headless Test Lab storage. Core now supports optional initial browsing
without changing default GUI connection behavior. Identity establishes the session;
storage performs the first FTP read. Directly obsolete raw listing/download and
`Profile.client()` are retired; Flash and broader compatibility remain deferred.

Starting implementation RU baseline: **55% remaining**. Deterministic verification:
normal and optimized suites each **1,123 methods = 1,087 pass + 36 existing skips**;
104 focused tests, 120 affected regressions, and 17 Offline Test Lab checks passed.
R5 adds 30 methods to the R4 baseline, with no new skips. See the R5 record for
commands, corrected iterations, ownership proof and complete changed-file inventory.

**Read-only physically qualified on Beige and Founder on 4 October 2026;
subsequently accepted, committed and pushed at the authority above.** Actual bound-profile CLI ls/get
and all four headless hardware checks passed on both devices. Separate local
readbacks matched historical sizes/hashes (8,952 and 4 bytes), followed by local
cleanup. No initial FTP browse, stable per-run sessions, zero terminal leases
and successful shutdown were observed. No remote writes occurred; evidence is
send-boundary diagnostics, not packet capture. See the R5 physical record for
exact profiles, paths, hashes and observer limitations. The R5 document's older
final-review/unpublished wording records the pre-publication checkpoint; the
verified R5 authority above supersedes it. Flash and Network Foundation remain
incomplete.

## R6 — Managed Flash publication: published

[R6 design, historical stop and resumed evidence](R6-MANAGED-FLASH-PUBLICATION.md)
records the original approved design, the stopped partial implementation and the
explicitly authorized resumption at user-supplied RU baseline 41% remaining.
The original stop history is preserved: a 16-byte CRT slice was compared against
a 17-byte literal, rejecting every CRT. Review authorized only correction to the
exact 16-byte space-padded signature. All other Flash validation rules remain.
The independent directory-race fixture now models CWD plus argument-free MLSD.

Both source workflows now use private bounded immutable snapshots and one managed
Flash publisher, including optional known-directory MKD, exact-length STOR,
independent readback/hash/SIZE and destination recheck before managed rename.
Structured consequences survive job cancellation/failure and GUI rendering;
queued refusal releases consumed snapshot bytes. The raw Flash publisher is
retired. Shared/deferred compatibility and generic 3C behavior remain unchanged.

Deterministic verification passed: 56 focused methods; 274 affected regressions;
normal and optimized suites each 1,153 methods / 1,117 passed +36 existing skips;
Offline Test Lab 17 checks. Thirty added methods, none removed/renamed, no new
skips. R6 records the sandbox socket failures, original stopped iteration and
later obsolete raw-Flash ownership assertion correction, with passing reruns.
Ownership/policy, bounded privacy and tracked/untracked whitespace checks passed.

R6 is **physically qualified, accepted, committed and published** at
`f9457acd3bcef4269d9d98e95ef3c6dc33f90ff1`, parent R5
`dab627979b9d3bb085c955c6e3bea8cdaff8b338`, subject
`Implement R6 managed Flash publication`. The final-closure starting inspection
verified HEAD = local `origin/development`, divergence `0 0`, clean worktree.
The exact-path cleanup prerequisite added 18 tests after the 1,153-test run above:
published R6 contains 1,171 discovered test methods (1,135 plus 36 display skips).
Its focused/affected verification passed 293/293 tests. Older unpublished wording
in the R6 checkpoint record describes history, superseded by this authority.

Controlled physical qualification passed on 4 October 2026, Beige fully finished
before Founder. Saved bound Development profiles reported Beige `25EA78` at
`192.168.68.70` / firmware `1.1.0s2`, and Founder `25BE71` at `192.168.68.69` /
firmware `1.1.0`, both API `0.1`. Each used existing `/Flash/roms` and one unique
one-byte disposable `.bin`: actual FileService R6 publication, independent full
readback/hash, staging inspection, reviewed exact-path cleanup with one acknowledged
DELE, cleanup absence and fresh final absence all passed. Stable separate Core
sessions and zero terminal leases were verified. No fixture or staging remained.
Missing-directory MKD stayed deterministic-only; Founder's absent configs was not
created. No activation/application/reset/reboot/settings mutation occurred.

The R6 physical record contains exact paths, hashes, identities, sessions, managed
send/reply evidence and limitations (not packet capture; external-writer races
remain). Implementation/tests were preserved through publication.

## Final FTP ownership closure — implementation for final review

The final bounded compatibility deletion and fixture conversion is implemented
against published R6, with starting user-supplied RU baseline 32% remaining.
Supported live FTP has one owner: `C64UFtpLeaseManager` / `C64UFtpClient`, through
managed adapters and accepted primitives. Missing managed context refuses; raw
factories, remote alternatives, and raw-selecting switches are removed. Offline
fixtures remain explicit and cannot be selected as a production fallback.

[Closure evidence and complete inventory](FTP-OWNERSHIP-CLOSURE.md) records exact
commands, test accounting, corrected iterations and ownership checks. Verification:
125 closure/affected tests and 466 managed/R4/R5/R6 tests passed; normal and
optimized full suites each ran 1,177 tests (1,141 passed, 36 unchanged display
skips); Offline Test Lab passed 17/17 checks. Six methods added, none deleted,
four renamed. Syntax, ownership, whitespace and bounded privacy/secret scans pass.
No supported
managed wire sequencing or policy changed, so no new physical qualification was
needed or performed. This work remains uncommitted for compact final review.
FTP ownership closure does not complete all Network Foundation/product work:
Streams, Ultimate Menu and cartdumper remain separate roadmap features.
