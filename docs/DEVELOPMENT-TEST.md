# Argonaut 1.7-disk.7 — Section 4 cross-platform testing

This build completes the authentic disk-image management roadmap section. It
keeps Development profiles, preferences, reports, and build identity separate
from the installed stable app.

Section 4 adds:

- read-only D64, D71, and D81 directory browsing and extraction with authentic
  CBM geometry, BAM, sector-chain, cross-link, and free-space validation;
- explicit D81 CBM partition labels without presenting partitions as folders;
- staged, validated D64 rename, scratch, and PRG/SEQ/USR addition while leaving
  the source image unchanged;
- a local-files preference that hides hidden entries by default;
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

1. Confirm About shows `1.7-disk.7` and the source commit shown for this release.
2. Open the supplied **Test Disk Images** D64, D71, and D81 fixtures. Confirm
   each directory opens, validates, reports free blocks, and extracts its large
   test file. Confirm the D81 CBM entry is labeled as a partition and cannot be
   opened as a folder.
3. On a copied standard D64, stage a rename and add a small PRG. Save to a new
   filename, reopen it, and confirm both changes. Cancel another staged edit and
   confirm the source file remains unchanged.
4. In the local Files pane, confirm hidden files are initially absent. Enable
   **Preferences → General → Show hidden local files and folders**, confirm they
   appear, then disable it and confirm they disappear.
5. Connect to a C64U at BASIC READY. In Streams, enter `PRINT "ONE"` and press
   Return, then enter `PRINT "TWO"` without clicking the input again. Confirm
   each command sends, the field clears, and focus remains ready for the next
   line. Video preview is not required.
6. Run **Run offline checks** in Test Lab and confirm every check passes. Connect
   the C64U, run **Run C64U checks**, and confirm all read-only checks pass.
7. Check upload/download, Settings, Drives, video/audio preview, screenshot,
   recording, Mount & Run, Preferences persistence, and Quit as core regression
   checks.

The release's source commit differs from Linux-accepted build `04a0904` only in
this cross-platform checklist, bundle metadata, and fixture packaging. No
application code changed after Linux acceptance.

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
