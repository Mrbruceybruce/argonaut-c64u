# Issue #25 — LED mode-write containment review gate

## Scope and implementation

Approved isolated implementation based on published development
`2cd5a60549e08cf734f192e0cfc38882f583c3db`, 25 October 2026.
The new checkout is `issue25-mode-containment` beside the retained prior candidates.
It has detached HEAD and a local primary-repository origin; it is not a publication
repository. No primary integration, Git staging/commit/push, GitHub mutation or
C64U contact is authorized or performed.

The shared headless `configuration_policy.py` rejects any explicit LED mode key
before dispatch/history, independent of value, firmware or supplied metadata.
`execute` applies it after detaching intent and checking the session; `validate`
also applies it to previews. Case-folded identity matching covers both exact LED
stores. `enabled` exposes modes as read-only with a specific containment reason.
No other source module changes. Parameter-only edits retain existing admission.

This is an Argonaut restriction, not a discovered firmware constraint or proof of
lockup resolution. Direct Core/public-client Apply, selected preview/Restore/Undo
and supported native-file staging share the refusal. A mixed requested batch is
refused whole without POST or history mutation. Snapshot values that are unchanged
are omitted by preview diff generation and are not write intent; an explicit
same-value request at the Core boundary is always refused.

## Validation

- Affected suite: **120/120 normal and 120/120 optimized**, zero failures,
  errors or skips, using a verified network namespace, no capabilities,
  no-new-privileges and Python socket/DNS guards.
- Real-GTK Gate A: **35/35**, comprising 11 GTK, 22 Core and 2 existing LED
  methods, zero failures/errors/skips. Private Xvfb/D-Bus, temporary HOME/XDG,
  network namespace and socket/DNS guards were verified by the existing runner.
- Source CI inventory audit and `git diff --check` passed.
- Initial namespace setup was blocked by the sandbox; approved escalation ran
  the same isolated protocol. An initial affected-suite run had one headless
  import failure because the evidence launcher used the parent directory.
  Correcting that launch directory produced the passing final results above;
  no product change was needed for that failure.

Retained local evidence (not published artifacts) is in sibling directories
`issue25-mode-containment-evidence/` (normal-reviewed.json/log,
optimized-reviewed.json/log, affected.py), `issue25-mode-containment-gate-a-reviewed/`
(summary.json, network.json, environment.json and per-class results/logs), and
`issue25-mode-containment-audit-reviewed/` (coverage.json). The affected launcher explicitly
loads configuration dependencies, configuration, dependencies, backups, settings
safety, native files, Core, API, C64 AI launch, scheduler, recovery and CI runner
modules. The exhaustive pair loops are subcases, not 85 separate test methods.

A review refinement keeps the containment predicate free of identity-validation
exceptions during unrelated UI rendering. Authoritative request identity checks
remain in `detach`/`validate`; an unrelated-metadata regression assertion covers
the presentation behavior. The final source was revalidated in all three runs.

Independent engineering review **PASS**, with no remaining actionable defects.
The reviewer inspected final source/call paths and refreshed evidence, independently
reran all 22 Core tests successfully, and confirmed the rendering correction.
The report is retained at `../issue25-mode-containment-evidence/independent-review.txt`.
This verdict covers the isolated implementation only; it grants no integration,
publication, hardware acceptance or closure authorization.
The 85 ordered mode pairs comprise 36 keyboard and 49 strip pairs, including all
13 same-value pairs. Parameter matrix checks still cover all active/inactive
fields and the mode-independent Auto SID/SID Select fields. Other coverage includes
case variants, missing metadata, mixed field/category orders, existing and absent
history, UI bypass, stale controller/session, unknown firmware/product, malformed
metadata, public-client POST interception, Restore, actual Undo and native preview.

## Changed-file inventory

- `c64u_browser/configuration_policy.py`: shared refusal and read-only mode state.
- `tests/test_configuration_dependencies.py`: exhaustive pair refusal, mixed/bypass
  and preserved parameter/safeguard coverage.
- `tests/test_ultimate_menu_gate_a.py`: real-GTK read-only mode, refusal and parameter checks.
- `tests/run_gate_a.py`: expected Core count increases from 20 to 22.
- `tests/ci_suites.json`: matching Core inventory count.
- `docs/CONFIGURATION-DEPENDENCIES.md`: policy and historical-scope reconciliation.
- `docs/CURRENT-STATE.md`: current isolated candidate checkpoint.
- `docs/ARGONAUT-ROADMAP.md`: RM-027 candidate checkpoint and unchanged dependencies.
- `docs/ISSUE25-MODE-CONTAINMENT.md`: this review/evidence record (new).

All nine files remain unstaged/uncommitted in the new isolated checkout. The
primary and prior candidates retain their original HEADs, branches, remotes and
working-tree inventories. Primary still has exactly seven untracked artifacts;
its tracked files and index are clean, with the historical stash retained.

## Limits and next decision

No hardware contact or new physical qualification. No claim of safe mode
transitions, prolonged stability, device-side atomicity, physical-header mapping,
firmware 1.1.0s2 support, hosted CI, package or cross-platform acceptance. C1's
incomplete protocol and executor termination remain unresolved. The original
intermittent lockup remains unexplained and unproven resolved.

Issue #25 remains Open / P0 / In Progress. Review completion permits the user to
decide whether to authorize verified integration into the primary checkout.
Staging, commit, push, publication verification and issue closure remain separate
user-controlled gates. Preserve this candidate and all prior unpublished work.
