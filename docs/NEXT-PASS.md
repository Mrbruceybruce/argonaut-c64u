# Linux-first development roadmap

Linux is the active development and hardware-validation platform. It has both
C64 Ultimates, Ollama, the local AI bridge, health alerts, and unattended fleet
checks on one machine. Complete every item and Linux acceptance gate in one
roadmap section before building and validating Windows, Apple Silicon Mac, and
Intel Mac packages. Begin the next roadmap section only after that cross-platform
release gate passes.

## Active Section 4: authentic disk-image management

Disk images must remain compatible with Commodore hardware and CBM DOS. D64
and D71 images have one flat directory; Argonaut must not invent folders or a
parent entry inside either format. A D81 may expose a valid Commodore 1581 CBM
partition explicitly, but it must not be presented as an ordinary host folder.

The original read-only and D64-editing milestone proceeded in this order:

1. Read and validate standard 35-track D64 images without changing any source
   byte. Recognized 40/42-track extended images remain readable but are labeled
   nonstandard.
2. Show the authentic disk header, file types and flags, block counts, and free
   blocks in a read-only flat directory window.
3. Extract PRG, SEQ, USR, and REL data by following CBM sector chains. Host
   extraction must be atomic and must never replace an existing file.
4. Add deterministic corruption checks, independent tool comparison, structured
   diagnostics, and Linux package self-tests.
5. Add staged D64 editing only after read-only handling passes physical Linux
   acceptance. Validate the complete image and preserve or back up the original
   before publishing a changed image.
6. Extend the validated model to D71, then D81 and genuine 1581 CBM partitions.

The first read-only parser uses a D64 created by VICE `c1541` as an independent
fixture. Its flat directory and extracted single- and multi-sector PRG data must
match `c1541` byte for byte.

Read-only D64 handling passed physical Linux acceptance on 2026-09-17. A real
`Downfall.d64` opened from the C64U, reported a standard 1541 directory and two
valid file chains, and extracted a file without changing the image. The installed
Test Lab reported all 15 checks passing and included **Read-only D64 parser**.

The staged D64 editor has completed automated acceptance and awaits physical
Linux acceptance. It is limited to standard 35-track images and authentic
flat-directory operations: rename, scratch, and adding PRG, SEQ, or USR files.
The original remains read-only; publishing requires complete validation and a
new local `.d64` filename that does not already exist. REL creation or removal
remains disabled until its 1541 side-sector structure is implemented and
independently verified. VICE `c1541` validated an edited image whose ninth entry
extended the real directory chain, then extracted its new multi-sector payload
byte for byte.

The first physical C64 directory listing exposed an important text-encoding
correction: VICE's host-text conversion had written uppercase names with their
high bit set, which BASIC displayed as graphic characters. Hardware-readable
directory names use PETSCII `$41-$5A`; the editor and regression fixture now
enforce those bytes before physical acceptance is repeated.

The next package also makes Return activate the primary action in disk filename
prompts, including **Stage addition** and **Stage rename**.

Staged D64 editing passed physical Linux acceptance on 2026-09-17. A newly saved
image mounted in the C64U, and `LOAD"$",8` displayed its disk label, original
files, and added `UCI PROBE` entry as ordinary readable text on the physical C64.

Read-only D71 work is now active. Its parser follows the documented 1571 layout:
70 tracks, the side-one BAM on 18/0, side-two allocation maps on 53/0, and the
side-two free counts in bytes `$DD-$FF` of 18/0. The initial independent fixture
is generated and validated by VICE `c1541`, includes a 670-block file whose chain
crosses onto the second physical side, and keeps the authentic flat directory.
Format details are checked against the
[VICE D71 specification](https://vice-emu.sourceforge.io/vice_17.html#SEC388).

Read-only D71 passed installed Linux and physical C64U acceptance on 2026-09-17.
The authentic 170,000-byte `CROSSSIDE` file extracted successfully. Mounted on
an emulated 1571 connected to a C64, the directory first reported zero free
blocks because a 1571 starts in single-sided 1541 compatibility mode. The
authentic `U0>M1` command enabled double-sided mode, after which BASIC displayed
the expected `657 BLOCKS FREE`. This confirms both the fixture and Argonaut's
geometry against real drive behavior.

The next package also hides dot-prefixed and operating-system-hidden entries in
the local Files pane by default. **Preferences → General → Show hidden local
files and folders** reveals them immediately when needed; C64U listings are
unchanged. Read-only D81 support is now active.

The D81 parser follows the documented 1581 layout: 80 tracks with 40 sectors
each, header at 40/0, BAMs at 40/1 and 40/2, and the fixed root directory at
40/3. Its VICE-generated fixture contains a 410,000-byte file that crosses both
BAM halves and a genuine contiguous CBM partition allocation that VICE retains
across validation. Argonaut labels CBM entries as partitions, validates their
linear allocation, and does not expose them as host folders or chained files.

Read-only D81 passed installed Linux and physical C64U acceptance on 2026-09-17.
The installed package opened the VICE fixture, validated both BAM halves and
its CBM partition, extracted the 410,000-byte cross-side file, and mounted it on
the C64U's emulated 1581 with the expected directory and free-block count.

The next package improves consecutive commands in Streams: Return sends the
current line, clears it only after success, and returns focus to the empty field.
A failed send preserves the text for retry.

Section 4 passed its final installed Linux acceptance gate on 2026-09-17 using
Development package `1.7-disk.7` at build `04a0904`. All 24 packaged checks
passed. On the physical C64U, consecutive Streams commands sent on Return,
cleared after each successful send, and retained keyboard focus for the next
line. The local Files pane hid dot entries by default and refreshed immediately
when **Show hidden local files and folders** was enabled or disabled. Section 4
is now frozen for the Windows, Apple Silicon Mac, and Intel Mac release gate.

The published `v1.7-disk.7` packages at build `a9a59bb` passed their hosted
package checks on Windows, Apple Silicon Mac, and Intel Mac. Physical Windows
and Apple Silicon testing passed on 2026-09-18. Physical Intel Mac acceptance
remains with contributor OldMan252.

Section 4 continues on Linux before another cross-platform release gate:

1. Create an authentic blank standard 35-track D64 with a user-selected disk
   label and two-character ID. Validate it before publishing, never replace an
   existing local file, and verify it independently with VICE `c1541` and a
   physical C64U.
2. Support safe REL removal only after its data and side-sector chains can be
   reclaimed and independently verified. Evaluate REL creation separately;
   do not synthesize a REL layout until record-length and side-sector behavior
   can be represented faithfully.
3. Extend staged flat-directory editing to standard D71 images, including both
   BAM regions and files that cross physical sides.
4. Extend staged editing to standard D81 images while preserving genuine CBM
   partition entries and both BAM halves.
5. Evaluate D80 and D82 support against documented 8050/8250 layouts and
   independent fixtures before deciding the supported read and edit scope.
6. Evaluate G64 as a bitstream preservation format. Prefer whole-image handling
   or an explicit read-only scope over pretending copy-protected tracks are a
   normal CBM DOS directory.

Blank D64 creation passed installed Linux and physical C64U acceptance on
2026-09-18. The generated image is exactly 174,848 bytes, reserves the BAM and
first directory sector, reports 664 blocks free, uses hardware-readable PETSCII
for its label and ID, and accepts the existing staged PRG/SEQ/USR editor. All 26
packaged checks passed at build `8b6a334`. VICE `c1541` independently listed and
validated the image; the physical C64U displayed `ARGONAUT BLANK`, ID `A8`, DOS
`2A`, and `664 BLOCKS FREE`.

Safe D64 REL removal passed installed Linux and physical C64U acceptance on
2026-09-18. It validates the directory record length, the complete side-sector
chain and group, and every indexed data-sector pointer before staging. Removal
releases both data and side sectors while preserving the source image. A VICE
`c1541` fixture with five data sectors and one side sector produced byte-identical
VICE and Argonaut results. All 28 packaged checks passed at build `4d559ac`; the
physical C64U displayed `RELTEST`, ID `RT`, no files, and `664 BLOCKS FREE`.

REL creation was evaluated separately. A raw host file does not carry the record
length and record-oriented meaning required by CBM DOS, and current VICE tooling
also cannot round-trip an image REL file as an ordinary host binary without
losing essential semantics. Argonaut therefore keeps authentic REL validation,
raw extraction, rename, and safe removal, but does not present arbitrary host
bytes as a newly created REL file. This avoids producing a misleading disk file.

Staged D71 editing passed installed Linux and physical C64U acceptance on
2026-09-18. Rename, safe removal, and PRG/SEQ/USR addition retain the authentic
flat 1571 directory, update the side-one BAM, side-two bitmap and side-two free
counts, and preserve an optional error table. All 28 packaged checks passed at
build `f2c6c00`. The physical C64U mounted the edited image in 1571 mode and
displayed `HELLO` at 1 block, `NEW CROSSSIDE` at 670 blocks, and `657 BLOCKS
FREE`. VICE independently extracted all 170,000 replacement bytes exactly.

Staged D81 editing is now implemented for standard 80-track images. Rename,
ordinary-file removal, and PRG/SEQ/USR addition update the correct 1581 BAM half,
extend the root directory only on track 40, preserve optional error tables, and
keep every validated CBM partition sector allocated. The VICE fixture removed
and replaced its 1,615-block cross-BAM file without changing its protected
partition; VICE validated the image and extracted all 410,000 bytes exactly.
Installed Linux and physical C64U acceptance passed on 2026-09-18. All 28
packaged checks passed at build `d7ca5c9`. The C64U's emulated 1581 displayed
the edited `NEW CROSS81` file at 1,615 blocks, retained the 10-block
`SMALLPART` CBM partition, and reported `1534 BLOCKS FREE`.

D80 and D82 were evaluated against the documented VICE 8050/8250 layouts.
They target 77-track and 154-track IEEE-drive media, while the C64 Ultimate
drive interface and Argonaut's connected-drive controls expose 1541, 1571, and
1581 operation. D80/D82 parsing and editing therefore remain outside the C64U
disk editor instead of presenting media the connected hardware cannot mount as
the corresponding drive type.

G64 remains a preservation image handled as an opaque whole file. Argonaut can
copy it and the C64U can mount it through the existing drive API, but Argonaut
does not interpret its bitstream tracks as a normal CBM DOS directory or offer
file-level editing that could discard protection or mastering details.

The final Linux polish pass renames **Save edited copy…** to **Save as…** and
keeps every successfully copied top-level source and destination item selected
after copy or drag-and-drop when those folders remain visible. Failed or
unfinished items are not selected as successful copies.

Section 4 completed its final Linux gate on 2026-09-18 with installed
Development package `1.7-disk.12` at exact build `b00a692`. All 29 packaged
checks passed. The shortened save label, Copy/Paste selection, and drag-and-drop
selection were confirmed in the installed UI. The section is frozen for its
Windows, Apple Silicon Mac, and Intel Mac build and physical regression gate;
no application-code changes follow this Linux-accepted build.

Windows physical testing of `1.7-disk.12` found two follow-ups. The supplied
VICE REL fixture retained VICE's high-bit host-text encoding in its original
disk label and REL filename, which rendered those original characters as
graphic/reverse-video text on the C64U even though newly edited names were
hardware-readable. The fixture is normalized to the same `$41-$5A` PETSCII
range already required by Argonaut's editor without changing any REL, BAM, or
sector-chain structure. **Save as…** also refreshes the visible local directory
and selects the newly published image, removing the need for a manual refresh.
Its file browser opens in the folder currently shown in Argonaut's local Files
pane so the save destination and subsequent selection are clear.

The `1.7-disk.13` correction passed installed Linux acceptance on 2026-09-18 at
exact build `9976230`. All 30 packaged checks passed. **Save as…** opened in the
visible local folder, refreshed it, and selected the published image. The
normalized REL fixture mounted on the physical C64U with both `RELTEST` and
`RELFILE` displayed as normal readable text. The corrected section is frozen
again for Windows, Apple Silicon Mac, and Intel Mac packaging and regression.

Windows and Apple Silicon physical testing of `1.7-disk.13` passed the disk
formats and core regressions while identifying a final usability pass. The next
Linux package makes **Extract selected…** start in the visible local folder,
then refreshes that folder and selects the extracted file. Closing Preferences
or a disk-directory window restores focus to the main window. A remote
D64/G64/D71/G71/D81 context menu can prepare the selected image for Drive A and
open **Drives**; mounting still uses the existing reviewed confirmation. The
C64U settings tab is now labeled **Ultimate Menu**. These changes pass all 433
source tests in normal and optimized modes. Installed Development package
`1.7-disk.14+linux.1` at exact build `593e0b7` passed all 32 package checks on
2026-09-19. Extraction folder/refresh/selection, both focus restorations,
right-click mount preparation and confirmation, and the **Ultimate Menu** label
all passed physical Linux acceptance. The section is frozen for the final
Windows, Apple Silicon Mac, and Intel Mac package and physical regression gate.

### Section 4 follow-up: create a D64 directly on the C64U

Add **New D64 disk…** to the remote Files pane when the current C64U folder is
writable. The action creates a formatted standard 35-track D64 in that folder,
without requiring the user to create it locally and upload it afterward.

1. Ask for the `.d64` filename and Commodore disk label before creating it.
2. Refuse an invalid name, a read-only destination, or an existing remote file;
   never replace a file implicitly.
3. Use the C64U's native `create_d64` operation only after confirming that the
   connected firmware supports it, and report unsupported firmware clearly.
4. Refresh the current remote folder and select the new image after success.
5. Read the completed image back, validate its size, header, directory, BAM, and
   free-block count with Argonaut's existing D64 parser, and keep the ordinary
   code-determined verdict separate from any AI diagnosis.
6. Record a sanitized structured operation result and add deterministic API,
   conflict, validation, and UI tests.
7. Complete installed Linux and physical C64U acceptance before including the
   feature in the next Section 4 package gate.

This follow-up and the remaining Section 4 presentation work passed installed
Linux acceptance in `1.7-disk.15+linux.5` at exact build `c72e0b6` on
2026-09-19. Native C64U D64 creation protects existing files, reads the result
back, and validates an empty 664-block image. Preferences recovers from stale
media folders; active and inactive Files panes remain distinguishable across
their complete control areas; local D64 creation selects without opening; and
the disk editor uses **Save image as…** and **Discard changes**. All reported
physical checks passed with no additional issue.

The final queued usability pass, `1.7-disk.16+linux.1`, passed installed Linux
acceptance on 2026-09-19 at exact build `df40074`. All 36 packaged checks passed.
Add File opened in the visible local folder and reviewed multiple selections in
one table. C64 names and PRG/SEQ/USR types remained editable, text `.bas` source
defaulted to SEQ, tokenized `$0801` BASIC defaulted to PRG, the complete batch
staged atomically, and Rename displayed a clear standard edit icon. The accepted
disk-image implementation remains Linux-first until the planned release gate.

The published `1.7-disk.16` Windows portable package passed all 13 checklist
tasks. Apple Silicon passed 12 and initially reported one Files regression;
follow-up reproduced the same behavior on Windows. In a long C64U listing, the
pane-wide pointer handler forced focus onto the list while GTK was deciding
whether two clicks formed a double-click. A fast double-click opened the folder,
while slower clicks could pull the viewport back to its first row. The local
pane was unaffected. Both platforms also requested clearer in-dialog feedback
when native C64U D64 creation encounters an existing filename.

## Active Section 5: replay buffer

Section 5 opens with the accepted cross-platform cleanup findings rather than
extending the completed disk-image roadmap:

1. **Complete:** Activate either Files pane from its complete visible area without forcing
   list focus or changing a long C64U directory's viewport.
2. **Complete:** Keep the local blank-D64 disk ID optional: blank by default to match the
   C64U's native formatter, while retaining a valid two-character custom ID.
3. **Complete:** Show ordinary C64-visible letters as uppercase while typing disk filenames,
   disk labels and Streams commands, matching the bytes Argonaut already writes
   or sends.
4. **Complete:** Validate local and native C64U D64 filenames against their visible directory
   while the user types. Disable creation and show a clear red, enlarged
   conflict message before submission; retain both no-replace checks for stale
   lists.
5. **Complete:** Present invalid General-preference folder messages one point larger and in
   red while leaving successful save messages neutral.

The installed Linux cleanup passed acceptance at `1.8-replay.1+linux.3`. The
replay implementation is now active in source behind a default-off General
preference. It keeps a bounded rolling VP8/Vorbis fragment history, defaults to
30 seconds, reports the actual retained duration, and remuxes an immutable
snapshot into a playable WebM while preview and ordinary recording continue.
Raw RGB history is not retained. Temporary ring and export fragments are
cleaned after stop, failure, export, and quit. Deterministic tests cover bounded
export duration, simultaneous recording input, low-space rejection, preference
validation, and cleanup. Installed `1.8-replay.1+linux.4` then passed the full
physical acceptance path: a 30-second audio/video replay exported successfully
while an ordinary recording continued, and both WebM files played correctly.
Section 5 is complete on Linux; cross-platform package validation follows.
Cross-platform packages wait until the complete section passes Linux acceptance.

The returned Apple Silicon `1.8-replay.1` checklist records 12 passed, 1 failed,
0 blocked, and 0 untested tasks. Its sole failure is a cross-platform UI
follow-up: while the **D64 disk directory** dialog is open, pointer movement over
the dialog can update hover highlighting in the underlying **C64 Ultimate files**
list. The supplied screen recording confirms visual pointer-event leakage through
the overlaid dialog. Separate click testing confirmed that underlying items cannot
be activated, so the defect is limited to hover presentation. Prevent the parent
Files window from updating hover state until the disk-directory dialog closes.
The returned Windows portable checklist records 13 passed, 0 failed, 0 blocked,
and 0 untested tasks. Its disk-directory control test passed, so the observed
hover leak is specific to the Mac presentation path in this release.
The `1.8-replay.2` correction explicitly makes the parent content insensitive
for the disk-directory dialog's lifetime and restores its exact previous state
on Close, with source and packaged-GTK checks covering both transitions. Apple
Silicon physical confirmation remains the release gate for this correction.

Apple Silicon physical testing of `1.8-replay.2` confirmed that pointer movement
over the disk-directory dialog no longer changes hover highlighting in the
underlying Files panes and that Files resumes normal interaction after Close.
Windows physical testing remains a complete 13-of-13 pass from `1.8-replay.1`;
the correction did not change its passing presentation path. Intel Mac physical
validation remains the final Section 5 platform gate.

## Current milestone: Linux hardening

1. Keep the installed Argonaut Development package, bridge, health monitor, and
   fleet timer on the same source build. Stable Argonaut remains separate.
2. **Complete (2026-09-16):** Verified the ai.2 Send Text fallback on a physical
   C64U at a BASIC READY prompt without starting a video preview. The command
   executed and the UI returned promptly from its working state.
3. **Complete (2026-09-16):** Used **Install & pair C64U** to upgrade the
   ai.1-generated C64 AI client on physical hardware. A question completed and
   Return at the next empty prompt exited cleanly to BASIC READY.
4. **Complete (2026-09-16):** Stopped and restored the dedicated Argonaut Ollama
   service. Health changed from `model_unavailable` back to `ready`; both C64Us
   retained identical passing verdicts before, during, and after the outage.
5. **Passing:** Both identity-bound C64Us pass all four read-only checks. The
   unattended 30-minute fleet timer remains active for continued monitoring.

The installed Linux package at build `807562f` passed all 18 package self-tests
against the real GTK desktop on 2026-09-16. The source suite also passed all 317
tests in normal and optimized Python modes.

Build-only milestone run 35173537738 passed at exact commit `c80a5a5`: Windows
passed 21 packaged checks, and Apple Silicon plus Intel Mac each passed 18.
These retained artifacts were not published because the ai.2 name already
identifies the earlier prerelease; physical cross-platform testing will use the
next numbered prerelease.

Prerelease 1.5-ai.3 was published from exact commit `c3b480c` after Windows and
both Mac architectures passed their source and packaged-app checks. One Windows
hosted runner exceeded the original 60-second cold-start allowance without a
failed check; an immediate clean retry passed, and future runs allow 90 seconds.

## Active Linux development

Test Lab now has an explicit end-to-end C64 AI bridge probe. It sends a fixed
readiness question through the deployed authenticated protocol and uses
ordinary code to verify the reply contract without judging, displaying, or
saving the model text. Both the visible button and the headless scheduled path
have passed against the real local Gemma 3 4B model.

The `1.5-ai.3+linux.1` installed UI was verified on 2026-09-16: **Test bridge
AI** passed the deployed bridge and Gemma path in 4.741 seconds and reported
that reply text was not saved. The `1.5-ai.3+linux.2` package adds its structured,
exportable `bridge.end_to_end` verdict, sanitized comparison history, headless
runner, and optional six-hour changed-state alert schedule. Installed Linux UI
and timer validation remain.

The structured bridge verdict also has a Linux headless entry point with stable
exit codes and sanitized JSON. An independent six-hour Linux timer can run the
identical test without an open Argonaut window, keep its private report history,
and notify only when the deterministic result changes or recovers.

The installed `1.5-ai.3+linux.2` package at build `84789e4` passed all 18
package self-tests. Its installed headless check passed against the real bridge
and Gemma model, and the enabled six-hour service completed its first scheduled
path successfully. The alert state is mode 0600 and the service journal contains
only sanitized structured evidence.

The installed timer controls were confirmed in Test Lab. A controlled local
bridge stop then produced a saved `network` failure, a `new_failures` comparison,
and a desktop alert. Restoring the bridge produced a passing result, a
`resolved` comparison, and the recovery alert. The bridge and six-hour timer
were left active.

The next Linux package adds **View latest result** beside the automatic AI-test
schedule so an unattended alert can be reopened after restarting Argonaut. It
uses the validated private history and reconstructs the comparison against the
prior verified bridge run. All 330 source tests pass in normal and optimized
Python modes. Installed build `37d02d9` passed all 18 package checks, retained
the active six-hour timer across the upgrade, and reopened the latest passing
bridge report with its resolved `bridge.end_to_end` comparison in Test Lab.

## Completed foundation

- Structured, sanitized REST, FTP, DMA, file, and background-operation records.
- Deterministic offline, simulation, package, hardware, regression, and fleet
  checks whose ordinary code decides pass, fail, and skip.
- Private saved history, comparisons, recovery tracking, and the Test Lab UI.
- Separate local Ollama and OpenAI analysis adapters that receive only bounded
  failed-check evidence and cannot change test verdicts.
- Local unattended failure diagnosis with cached results and changed-state
  desktop alerts.
- Paired C64-side PETSCII AI client and a narrow authenticated local bridge.
- Development/stable isolation, exact package build identity, and verified
  Windows, Apple Silicon, and Intel Mac package self-tests.
- File copy, Settings, Drives, Mount & Run, preview, screenshots, recordings,
  audio, persistence, and Quit regression coverage on physical hardware.

## Roadmap-section release boundary

Implement and physically validate an entire roadmap section on Linux. When the
section is complete, build all desktop packages and run a focused Windows and Mac
regression covering package launch, build identity, that section's changes, and
core file/media operations. Do not begin implementation of the next roadmap
section until this cross-platform release gate passes.

Stable promotion will use an opt-in **Developer Mode and Test Lab** preference.
The ordinary stable interface remains unchanged while the switch is off.
Enabling it reveals Test Lab after restart and starts nothing automatically;
disabling it stops Argonaut-managed Linux test timers but retains private
reports and settings. Stable and Development Linux packages now generate
separate bridge and timer identities so they can coexist without controlling
each other's automation. A guarded one-time migration preserves enabled legacy
Development services and cannot claim later stable units. All 340 source tests
pass in normal and optimized Python modes; installed migration validation is
next.

Installed build `2366daa` exposed an upgrade-order defect: package replacement
removed the legacy unit definitions before the app could read their enabled
state. The private settings and reports were intact, but the new scoped units
started disabled and the still-running legacy bridge temporarily held the
listener port. The legacy process was stopped, all four scoped services were
restored, and the new bridge passed end to end. Migration now also reconstructs
legacy enabled intent from the existing private bridge and alert-state files,
while continuing to reject genuine stable service definitions.

The unresolved SuperCPU Detect freeze remains tracked in GitHub issue #1. Do not
change that setting during routine hardware tests; investigate it separately
with an explicit recovery plan.

As an initial defense, Development now marks SuperCPU Detect as a hardware
compatibility risk in Restore and Undo previews, leaves it unselected, and
requires a clearly labeled high-risk Apply confirmation. This protection has
automated coverage. The warning and high-risk Apply label were verified in the
installed Linux app on 2026-09-16; the change was canceled and discarded without
being sent to the C64U. This does not attempt to reproduce the reported freeze.
