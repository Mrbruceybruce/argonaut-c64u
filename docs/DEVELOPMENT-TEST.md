# Argonaut 1.8-replay.2 — Section 5 cross-platform testing

This build completes the instant-replay roadmap section and carries forward the
authentic disk-image management section. It keeps Development profiles,
preferences, reports, and build identity separate from the installed stable
app.

This correction build also prevents pointer hover from leaking through an open
disk-directory dialog into the underlying Files panes on macOS. The parent
window remains inactive until the dialog closes, while its previous interaction
state is restored immediately afterward.

Section 5 adds an explicit, default-off 30-second instant replay. While preview
is running, Argonaut keeps a bounded rolling history of encoded VP8 video and
optional Vorbis audio fragments. Streams reports the actual retained duration.
**Save recent 30 seconds…** writes a playable WebM while live preview and an
ordinary recording continue. Raw RGB history is not retained, and temporary
fragments are removed after stop, failure, export, and quit. Linux physical
testing confirmed that simultaneous replay and ordinary audio/video recording
both produce playable files.

Section 4 adds:

- read-only D64, D71, and D81 directory browsing and extraction with authentic
  CBM geometry, BAM, sector-chain, cross-link, and free-space validation;
- explicit D81 CBM partition labels without presenting partitions as folders;
- staged, validated D64, D71, and D81 rename, scratch, and PRG/SEQ/USR addition
  while leaving the source image unchanged;
- authentic blank 35-track D64 creation with a chosen label and disk ID;
- validated D64 REL removal that reclaims both data and side sectors;
- protected D81 CBM partitions that remain allocated and cannot be removed;
- **Save image as…** publication to a new validated local image without replacement;
- single- and multi-file disk additions through one batch review table, with
  editable C64 filenames and types and complete validation before staging;
- Add File, Extract, and Save Image choosers that open in the folder currently
  shown in the local Files pane;
- content-aware `.bas` imports that default tokenized `$0801` programs to PRG
  and text BASIC source to SEQ, while keeping the type editable before staging;
- native blank-D64 creation directly on supported C64U firmware, followed by a
  complete readback and ordinary-code structural validation;
- visible keyboard-focus identification for the active Files pane, with subdued
  selection in the inactive pane;
- local blank-D64 creation that refreshes and selects the result without
  opening a disk-directory window automatically;
- recovery from unavailable legacy screenshot or recording folders without
  trapping the Preferences window;
- extraction into the visible local folder with automatic refresh and selection;
- right-click **Mount…** preparation for remote D64/G64/D71/G71/D81 images;
- source and destination selection after successful copy/paste or drag-and-drop;
- a local-files preference that hides hidden entries by default;
- the C64U settings tab labeled **Ultimate Menu**, with main-window focus
  restored after closing Preferences or a disk directory;
- Return-to-send Streams input that clears after success and remains ready for
  the next command.

The Development Test Lab now includes:

- deterministic offline, simulated, and read-only C64U checks with structured
  operation evidence and retained regression history;
- optional failure-only AI explanations through local Ollama or OpenAI, kept
  separate from code-determined verdicts;
- opt-in unattended read-only checks for every identity-bound Development C64U,
  changed-failure and recovery notifications, and bounded local AI diagnoses;
- a paired local C64 AI bridge and interactive USB2 PETSCII client;
- deterministic bridge, network, Ollama, and downloaded-model health checks;
- separate controls for five-minute AI health alerts, six-hour end-to-end AI
  tests, persistent 30-minute fleet checks, and the temporary schedule that runs
  only while the window is open;
- reopening the latest saved automatic AI test directly in Test Lab.

Fixes carried forward from the ai.1 physical Mac test and verified on Linux:

- unavailable AI analysis now appears clearly in the diagnosis panel and status
  bar, with local setup guidance and no change to deterministic verdicts;
- pressing Return at an empty C64 AI prompt now exits after previous questions;
- Send Text limits an unavailable DMA connection attempt and falls back to the
  REST keyboard buffer before queuing any text;
- an exact ai.1 C64 AI client is upgraded through the verified replacement path;
  unknown or modified files remain untouched.
- SuperCPU Detect changes are marked as a hardware compatibility risk in
  Restore, Undo, and Apply reviews and require a high-risk confirmation.

The Debian Development package includes the local bridge, health monitor, and
fleet-check user services. These now use Development-scoped service identities
so a future stable Developer Mode installation cannot control them. The first
updated launch migrates enabled legacy services once. Ollama, a downloaded
model, and the narrow TCP 6464 firewall rules for paired C64U addresses remain
explicit prerequisites. The pairing token and saved diagnostic material stay
private and are not committed.

Windows: extract the portable ZIP to a writable folder and run `Argonaut.exe`.
Mac: open the DMG and copy Argonaut Development.app to Applications, or extract
the ZIP. Apple Silicon and Intel packages require macOS 15 or newer. The Mac app
is ad-hoc signed, not notarized. If blocked, use System Settings → Privacy &
Security → Open Anyway. Linux background-service controls require systemd and
will report unavailable on other platforms.

## Automated package evidence

Every Windows and Mac build runs the packaged application from its final bundle
before the installer archive is retained. The package self-test uses explicit
ordinary-code checks in normal and optimized Python modes. It records a structured
JSON report with stable check IDs for the bundled GTK and media runtime, build
identity, Development settings isolation, Preferences, Streams and Test Lab
controls, local network enumeration, About and Quit behavior, and local file
publication. A failed check exits unsuccessfully and blocks publication.

GitHub retains separate reports for Windows, Apple Silicon Mac, and Intel Mac with
the build artifacts. These checks do not contact a C64U, alter its files, or ask an
AI model to decide the result. The physical-machine checklist below verifies the
remaining display, network, media, and C64U hardware behavior.

## Test checklist

1. Confirm About shows `1.8-replay.2` and the source commit shown for this release.
2. Open Preferences with a previously saved screenshot or recording folder
   unavailable. Confirm **Close** and the window close button work immediately
   without using Restore defaults. Confirm a newly entered nonexistent folder
   is still rejected.
3. Click each Files pane. Confirm its **Active** label and border follow keyboard
   focus and the inactive selection is subdued. Create a local blank D64 and
   confirm the new image is selected without opening its directory. Repeat that
   filename and confirm Create is disabled with visible red feedback.
4. Open a D64 directory. Confirm Extract, Add, Rename, and Remove show clear
   icons with identifying tooltips; **Discard changes** and **Save image as…**
   are separated at the right; the title does not show an I-beam; and closing
   staged edits still asks for confirmation. Move the pointer over the dialog
   above rows in the underlying Files panes and confirm those rows do not show
   hover highlighting. Close the dialog and confirm Files responds normally.
5. Choose **Add file…** and confirm the chooser starts in the folder shown in
   the local Files pane. Select at least two small host files and confirm one
   review table shows every host file with an editable C64 filename and type.
   Include a text `.bas` file and confirm it defaults to SEQ; a tokenized `$0801`
   `.bas` defaults to PRG. Confirm once, save, reopen, and verify every file.
6. In the C64U Files pane, choose **New D64 disk on C64U…**. Create a unique
   image and confirm Argonaut refreshes, selects, reads back, and validates an
   empty standard D64 with 664 blocks free. Repeat its name and confirm the
   existing image is protected.
7. Open the supplied D64, D71, D81, and REL fixtures. Confirm each validates,
   reports expected free blocks, and extracts a file. Confirm D81 CBM partitions
   remain protected and REL removal reclaims data and side sectors.
8. Right-click a remote D64, G64, D71, G71, or D81 and choose **Mount…**.
   Confirm Drives opens with the full path prepared for Drive A and no mount
   occurs before review is accepted.
9. Copy one item between local and C64U panes with Copy/Paste, then another with
   drag-and-drop. Confirm source and destination copies remain selected and the
   destination pane becomes visibly active when focused.
10. Confirm hidden local entries are absent by default. Enable **Preferences →
    General → Show hidden local files and folders**, confirm they appear, then
    disable it and confirm they disappear.
11. Confirm instant replay is off by default. Enable **Keep a 30-second instant
    replay while previewing** in Preferences, start an audio preview, and wait
    at least 35 seconds. Confirm Streams reports about 30 seconds retained.
    Start an ordinary recording, save the recent replay while recording
    continues, then stop recording. Play both WebM files and confirm video and
    audio. Stop preview and confirm replay history clears.
12. Run offline checks and connected read-only C64U checks in Test Lab. Confirm
    ordinary-code verdicts complete and optional AI text does not alter them.
13. Check upload/download, Ultimate Menu, Drives, video/audio preview,
    screenshot, recording, Streams Return-to-send, Mount & Run, Preferences persistence,
    disconnect/reconnect, and Quit.

The attached ODS checklist contains the same numbered tasks and provides a
result selector plus a comments field for every item. Record the exact message
and attach a task-numbered screenshot for any failure or unexpected result.
Complete the Tester, Platform, OS version, Test date, and package fields, then
return the filled sheet as
`Argonaut-1.8-replay.2-testing-results-PLATFORM-TESTER.ods`. For example, use
`Windows-Bruce`, `macOS-AppleSilicon-Bruce`, or `macOS-Intel-OldMan2525` for the
final two filename fields.

Operations still affect the connected real C64U and its files. The hardware
suite itself is read-only. Mount & Run requires the DMA network service. The
C64 AI launcher can enable Command Interface for the current runtime but does
not save the C64U configuration to flash. This prerelease does not replace the
stable 1.5 installation.

SuperCPU Detect is marked as a hardware compatibility risk in Restore, Undo,
and Apply reviews because an earlier combined settings change was associated
with an unresponsive C64U. The cause remains unconfirmed. Routine testing must
leave this setting unselected; a controlled reproduction requires a separate
recovery plan and no unsaved work on the device.
