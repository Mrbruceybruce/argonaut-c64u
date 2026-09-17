# Developer Mode and Test Lab

Stable Argonaut keeps Developer Mode off by default. Everyday file management,
settings, drives, machine controls, media, and streaming remain unchanged.
Enable **Developer Mode and Test Lab after restart** in Preferences only when
the additional diagnostic tools are useful.

Developer Mode supports these use cases:

- Run deterministic offline simulations and read-only C64U checks while
  ordinary code decides every pass, fail, and skip result.
- Compare saved results, reopen unattended runs, inspect sanitized operation
  evidence, and export reports for regression or support work.
- Ask local Ollama or explicitly selected OpenAI cloud models to explain only
  sanitized failed-check evidence. AI output never changes a verdict.
- Schedule Linux fleet checks, bridge health monitoring, and an end-to-end
  local AI test that work without an open Argonaut window.
- Pair and launch the private PETSCII C64 AI client through the narrow local
  bridge.
- Validate a release or reproduce a fault with fixtures before touching real
  hardware.

Enabling Developer Mode reveals Test Lab after Argonaut restarts. It does not
start a check, model, bridge, network connection, or background timer.
Disabling it hides Test Lab after restart and stops Argonaut-managed background
test timers on Linux. Private preferences, reports, comparisons, and diagnoses
are retained in case Developer Mode is enabled again.

Argonaut Development always enables Test Lab and continues to use its separate
profiles, reports, settings, and session-only credentials.
