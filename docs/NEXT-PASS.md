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

Section 4 proceeds in this order:

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

The D71 directory and cross-side extraction passed installed Linux acceptance:
the authentic 170,000-byte `CROSSSIDE` file was extracted successfully. The
next package also hides dot-prefixed and operating-system-hidden entries in the
local Files pane by default. **Preferences → General → Show hidden local files
and folders** reveals them immediately when needed; C64U listings are unchanged.

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
