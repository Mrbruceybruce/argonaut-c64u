# Linux-first development roadmap status

Linux is the active development and hardware-validation platform. It has both
C64 Ultimates, Ollama, the local AI bridge, health alerts, and unattended fleet
checks on one machine. Feature sections are implemented and physically accepted
on Linux first. Windows, Apple Silicon Mac, and Intel Mac qualification is
consolidated at major Stable release boundaries rather than repeated after every
section. Portable code and automated platform checks remain required throughout.

Every new roadmap section is implemented first as an Argonaut Core capability
with a headless contract. Client work then exposes that capability without
duplicating its rules.

The original feature roadmap remains historical context: it was written against
Stable 1.5 before the server-first architecture and before later feature
reordering. The implementation and release sequence below describes the current
Development line; it does not rewrite the older roadmap to imply that today's
sequence was always planned.

## Authoritative milestone sequence

1. **Complete on Linux:** USB/SD Backup & Restore.
2. **Complete on Linux:** Game Library MVP for D64 and CRT at
   `b66faa5da9119417fb7e38b695122c7d39403b54`.
3. **Complete on Linux:** SID Jukebox, implemented Core first and then exposed
   by GTK, with Core-host and C64U-resident playback physically accepted.
4. **Complete on Linux:** Game Library Bulk Import, including bounded local/C64U
   scanning, reviewed atomic admission, thin GTK client, large-catalog
   responsiveness, and the octet-preserving Game Launch/USB fingerprint fix.
5. **Next — Stable 1.9 consolidated platform gate:** build and validate Debian,
   Windows, Apple Silicon Mac, and Intel Mac packages for the server-first Core
   foundation, USB/SD Backup & Restore, Game Library including Bulk Import, and
   SID Jukebox.
6. **Architecture milestone:** persistent Argonaut Core hosting with a versioned
   API and a CLI/automation proof client.
7. **Remote-client filesystem milestone:** define and implement client-upload
   artifact staging, ownership, limits, cleanup, and Core-host versus client
   filesystem semantics.
8. **Client milestone:** begin the iPad/browser PWA against the established
   transport and artifact contracts.
9. **Media reconciliation:** reuse reviewed components and evidence from
   `feature/obs-capture` without merging that branch wholesale; place streaming,
   recording, capture, and diagnostics behind appropriate Core contracts.
10. **Decision milestone:** make the written direct-YouTube go/no-go assessment
   only after the OBS/media path is qualified.

Test Lab, structured logging, deterministic checks, local/cloud failure-analysis
adapters, unattended monitoring, and the paired PETSCII C64 AI bridge are an
existing foundation. Ordinary code continues to decide pass, fail, and skip;
AI analyzes bounded sanitized evidence and cannot change a verdict. A future
persistent AI Gateway is an extension of this foundation, not its beginning.

The clean OBS capture window, independent media worker, specialized stream
diagnostics, guide, and their development evidence exist on
`feature/obs-capture`. That branch is not part of current Development and its
cross-platform qualification was not completed. It is a source of reviewed
components and evidence for the later media milestone.

## Linux-complete milestone: SID Jukebox

The MVP supports referenced SID files on the Core host and on an identified
C64U. Core owns a versioned, atomically written and
Stable/Development-isolated store for playlists, favorites, and Jukebox
metadata. GTK remains a client of that contract.

The Core service owns source validation, SID requirement parsing and
reporting, playback previews, device/session safety, jobs, cancellation,
sequencing, and structured outcomes. Initial multi-SID support reports the SID
requirements and uses firmware-compatible playback; it does not automatically
reconfigure SID sockets. A lost or ambiguous playback response is never retried
automatically.

C64U-resident SID playback uses consequence-specific authorized-content
identity rather than a recursive removable-volume fingerprint. Core binds the
operation to the physical C64U and connection session, reads the exact
volume/path, revalidates the complete SID SHA-256, parser result and subtune,
then submits those same bytes through attached SID playback. Byte-identical
content at the expected location remains authorized even when the firmware
cannot prove that it resides on the same physical medium. This non-destructive
SID rule does not apply to USB Backup/Restore, Game Library, file replacement
or deletion. See [SID-JUKEBOX.md](SID-JUKEBOX.md).

Manual Previous/Next and shuffle are implemented. Unknown duration always
requires manual Next. Automatic advance may be offered only when trustworthy
duration metadata exists, and it is initially opt-in. Explicit one-based
subtune selection, takeover review, Files-pane catalog handoff, playlist-owned
transport and the compact Now Playing state form the accepted Jukebox client.

Playlist editing selection is client state and may contain multiple rows; the
logical playback cursor is a single Core-owned playlist item. Turning Shuffle
off keeps that current item and clears shuffle history/bag state, after which
ordered Previous/Next continues from the item's actual playlist position.
Library or playlist row selection never changes that cursor by itself.

Linux physical acceptance passed on 2026-09-21. Core-host and C64U-resident SID
playback were both audibly verified. Real PSID metadata, real 3SID addresses and
requested models, explicit subtune playback, playlist persistence and editing,
Previous/Next, non-repeating Shuffle, Shuffle Previous/forward history,
Shuffle-off ordered navigation from the actual Core cursor, and playlist
boundaries all passed. Multi-row editing selection remained independent from
the Core playback cursor. Reconnection invalidated playlist authorization, and
a reviewed Play made stale by disconnect/reconnect was rejected before any
playback request. Command-accepted presentation continued to state that audible
playback was not verified by Argonaut.

C64U-resident authorized-content playback also passed. Replacing recursive
full-volume scanning with an exact bounded SID read, SHA-256/parser/subtune
revalidation, and attached playback improved an observed resident transition
from approximately 44 seconds to approximately 1.5 seconds. This measurement is
physical acceptance evidence, not a fixed performance guarantee.

Manual Next remains the Stable 1.9 behavior. The C64U's apparent five-minute
SID timer is not trustworthy duration metadata: SpaceFight subtune 2 produced
roughly 30 seconds of meaningful audio followed by silence while playback
continued, while Astrolabe could become silent briefly and then loop/restart.
Silence detection and automatic advance therefore remain a future
investigation. The GTK workflow keeps Library browsing, the active Playlist
queue, and Core's logical Now Playing snapshot as separate states; only an
accepted Core playback transition changes Now Playing, and command acceptance
does not claim audible playback was verified. The Stable 1.9 client follows one
normal playback path: Library selections are added to the active Playlist, and
only the Playlist transport requests playback. Library double-click/Enter adds
rather than plays, multiple catalog selections may be appended together, and a
compact Library summary plus Details dialog keeps metadata subordinate to the
two primary scrolling Library and Playlist surfaces.

The completed milestone includes headless Core tests, a thin GTK client,
installed Linux package validation, and physical C64U acceptance of both
supported source scopes, subtunes, sequencing, takeover disclosure,
disconnect/session safety, and known- versus unknown-duration behavior. It does
not include socket
reconfiguration, guessed durations, HTTP/PWA transport, or unrelated media work.

## Linux-complete Stable 1.9 enhancement: Game Library Bulk Import

Core-owned bounded discovery, reviewed atomic catalog admission and the thin GTK
client are implemented with automated coverage and completed Linux physical
acceptance. The existing
**Add local files…** workflow remains available alongside **Scan local
folder…**, multiple selected C64U files and **Scan C64U folder…**.

Core scans only D64 and CRT candidates, validates and hashes them, and applies
the existing source and content-identity rules. Sources remain references: bulk
import never copies, moves, uploads, mounts, launches, deletes, or otherwise
modifies game files. Large scans produce a serializable review before any
catalog mutation, distinguishing new records, already-cataloged sources,
duplicate content, changed existing sources where relevant, and invalid or
unsupported files. The review presents unsupported files in their own summary
and filter category rather than counting them as invalid/inaccessible. Invalid
candidates are reported individually without unnecessarily aborting the scan.

Traversal is bounded and cancellation-aware. C64U scans preserve physical
device, volume and session safety and use authorized-content identity for this
read-only catalog admission. GTK only chooses source/options, presents
structured progress and review, and submits the approved subset. The Linux
acceptance checklist is maintained in [GAME-LIBRARY.md](GAME-LIBRARY.md). No new
formats, metadata scraping, managed storage or automatic source changes belong
to this enhancement.

Large real-world C64U acceptance reached the original 2,000-candidate ceiling
and aborted safely. The measured workload held 5,498 files, 3,159 D64/CRT
candidates, 33 directories and 527.1 MiB of candidate content. The defensive
defaults are now 10,000 directories, 100,000 total entries, 50,000 D64/CRT
candidates, depth 32 and 32 cumulative GiB. These stop pathological traversal;
they are not normal catalog capacity limits. Exceeding a bound still aborts with
partial diagnostic counts, and scans are never silently truncated. Structural
image validation establishes format, structure and content identity, not that a
game boots, is complete, works correctly or uses a CRT type supported by C64U
firmware.

The final physical scan reviewed 4,797 entries and 2,743 D64/CRT candidates:
2,606 new game images, 10 duplicates, 0 changed, 128 invalid/inaccessible and
2,022 unsupported. The reviewed execution added all 2,606 approved games with
no skipped/reclassified or failed results, leaving 2,616 Development records.
Persistence across restart, large-library scrolling/filtering and the 300 ms
search debounce passed. A Bulk-Imported C64U D64 also completed reviewed launch
and loaded successfully.

The acceptance volume exposed two filenames containing raw byte `0x84`. The
corrected Core identity listing now fingerprints exact filename octets with a
deterministic length-delimited representation. Game Launch retains full-volume
before/after safety, distinguishes `storage-changed` from
`storage-unverifiable`, and reports structured progress. USB Backup/Restore uses
the same corrected fingerprint without weakening its conservative policy.
Final GTK/GNOME use remained responsive during the long verification.

Stable 1.9 has therefore reached feature freeze. The consolidated Debian,
Windows, Apple Silicon Mac and Intel Mac qualification gate is next and has not
started. ZIP/7z sources, more Game Library formats, Tested/Playable state, Game
Launch fingerprint optimization, SID duration/silence/automatic advancement,
and tape/Datasette support remain deferred beyond this completed milestone.

## Linux-complete milestone: USB/SD backup and restore

Manifest-backed USB/SD backup and restore is implemented as a headless Core
capability and exposed by the GTK Files tab. Automated acceptance covers verified
backup, empty folders and files, restore additions and reviewed replacements,
unchanged/conflicting paths, changed source or destination state, device-session
changes, queued and running cancellation, partial results, recovery, plan
serialization, and headless imports. Restore never deletes destination extras.
The optional Core-owned backup-root preference starts destination selection in
the configured Core-host parent while preserving one self-contained directory
per backup and compatibility with every existing backup.

Linux physical USB/SD backup and restore acceptance passed on 2026-09-20,
including cancellation, incomplete-backup rejection, reviewed partial-upload
cleanup, stale-session rejection, and physical media-swap rejection. The
partial-upload cleanup issue found during qualification was corrected and
physically retested in commit `b340fd3146b3920a65b5323b9af2701e948bf6eb`.
The completed Core contract and qualification record are documented in
[USB-BACKUP.md](USB-BACKUP.md). Its Windows and Mac qualification is pending as
part of the consolidated Stable 1.9 gate.

## Linux-complete milestone: Cartridge Support / Game Library MVP

The Game Library MVP supports referenced **D64 and CRT** files. Argonaut Core
owns the versioned catalog, explicit Core-host or physical-C64U source identity,
validation and SHA-256 content identity, search, favorites, notes, user-associated
Core-host artwork references, missing/changed/unavailable state, and reviewed
Locate/Relink behavior. Adding an entry records metadata only: it never moves,
copies, mounts, uploads, launches, or otherwise modifies the game file.

PRG support is deferred. SID remains part of the active SID Jukebox milestone.
The catalog, headless reviewed launch service, and thin GTK Game Library client
are implemented with automated coverage. Linux physical acceptance passed on
the beige C64U (`C64-Ultimate-7F01C9`) for all four Core-host/C64U and D64/CRT
launch combinations, catalog persistence and Relink behavior. Temporary CRT
Reset/Reboot behavior also matched the documented warning. A transient health
timeout found during acceptance was corrected by confirming retryable failures
before replacing the Core session; normal launch and real-disconnect stale-plan
rejection then passed physical retesting. Cross-platform acceptance remains
open for the consolidated Stable 1.9 gate. Artwork selection and display exist
and have automated coverage, but the Linux physical-acceptance record did not
explicitly record that presentation check; this documentation gap does not
reopen the completed implementation. The record is documented in
[GAME-LIBRARY.md](GAME-LIBRARY.md).

## Completed historical Section 4: authentic disk-image management

This section is retained as a chronological implementation and acceptance
record. Interim statements below that described work as active, next, or
awaiting acceptance were resolved by the later completion paragraphs and do
not describe the current milestone.

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

## Completed historical Section 5: replay buffer

This section is likewise retained as chronological release evidence. Its
interim active and pending language is superseded by the Stable 1.8 completion
record at the end of the section.

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
the correction did not change its passing presentation path. The Intel Mac
package passed its native hosted build, relocated-app launch, and packaged GTK
self-test at the exact release commit. Physical Intel testing remains desirable
when a tester is available, but it is deferred and does not block development.

Development release `1.8-replay.3` makes Debian a required release platform.
GitHub now builds and installs the exact-commit `.deb`, runs the source suite in
normal and optimized modes, runs the installed GTK package self-test, retains
the JSON evidence, and blocks publication if Debian fails. The published Debian
asset and checksum were verified after download, and the same package installed
locally with all 40 packaged checks passing at exact build `4bf09c3`.

**Section 5 complete:** Linux physical replay acceptance, Apple Silicon physical
acceptance of the only reported cross-platform correction, Windows 13-of-13
physical regression results, and native hosted Intel package validation all
passed. Development may proceed without waiting for an Intel Mac tester.

Stable Argonaut 1.8 was published on 2026-09-19 from exact tested commit
`46b0d90`. The required Debian, Windows, Apple Silicon, and Intel jobs all
passed before publication. Each desktop package completed its packaged-app
gate; both Mac applications also passed after relocation under a minimal
environment. The public release contains the Debian package, Windows installer
and portable ZIP, Apple Silicon and Intel DMG/ZIP pairs, source archive, and a
checksum manifest covering all eight deliverables. Tag `v1.8` resolves to the
tested commit. Physical Intel validation remains a deferred confidence check.

## Completed historical milestone: Linux hardening

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

## Completed Test Lab and AI foundation development

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

## Stable 1.9 consolidated release boundary

USB/SD Backup & Restore, Game Library, SID Jukebox, and Game Library Bulk Import
are complete and physically accepted on Linux. Stable 1.9 is now feature-frozen
for one consolidated platform gate. Build all desktop
packages and run focused Windows and Mac regression covering package launch,
build identity, these feature areas, Development/Stable isolation, and core
file/media operations. A platform without an available physical tester may pass
through a native hosted build, relocated packaged-app launch, and packaged GTK
self-test; record its physical pass as deferred. The gate blocks declaring and
publishing Stable 1.9, not implementation of the Linux-first sections leading
to that release.

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
