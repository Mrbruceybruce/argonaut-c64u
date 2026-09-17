# Linux-first development roadmap

Linux is the active development and hardware-validation platform. It has both
C64 Ultimates, Ollama, the local AI bridge, health alerts, and unattended fleet
checks on one machine. Windows, Apple Silicon Mac, and Intel Mac packages are
built and physically tested at milestones instead of after each small change.

## Current milestone: Linux hardening

1. Keep the installed Argonaut Development package, bridge, health monitor, and
   fleet timer on the same source build. Stable Argonaut remains separate.
2. Verify the ai.2 Send Text fallback at a BASIC READY prompt without requiring
   a video preview.
3. Use **Install & pair C64U** to upgrade an exact ai.1-generated C64 AI client,
   then verify that Return at an empty prompt exits after a completed question.
4. Exercise the local-model outage and recovery path while confirming that AI
   availability never changes saved deterministic C64U verdicts.
5. Keep the four read-only checks passing for every identity-bound C64U through
   the unattended 30-minute fleet timer.

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
