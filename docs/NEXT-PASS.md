# Linux-first development roadmap

Linux is the active development and hardware-validation platform. It has both
C64 Ultimates, Ollama, the local AI bridge, health alerts, and unattended fleet
checks on one machine. Windows, Apple Silicon Mac, and Intel Mac packages are
built and physically tested at milestones instead of after each small change.

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

## Milestone boundary

After the Linux hardening items pass, build all desktop packages once. Run a
focused Windows and Mac regression covering package launch, build identity, the
fixed behaviors, and core file/media operations. Resolve portability failures,
then decide whether the result is another prerelease or the stable candidate.

The unresolved SuperCPU Detect freeze remains tracked in GitHub issue #1. Do not
change that setting during routine hardware tests; investigate it separately
with an explicit recovery plan.

As an initial defense, Development now marks SuperCPU Detect as a hardware
compatibility risk in Restore and Undo previews, leaves it unselected, and
requires a clearly labeled high-risk Apply confirmation. This protection has
automated coverage. The warning and high-risk Apply label were verified in the
installed Linux app on 2026-09-16; the change was canceled and discarded without
being sent to the C64U. This does not attempt to reproduce the reported freeze.
