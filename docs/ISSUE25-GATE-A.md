# Issue #25 — offline Ultimate Menu Gate A

Baseline: `6ff217c9aaaec834875e51e8cbe55d37585b998d` (development).
Date: 25 October 2026 UTC / 24 October America/Chicago.

## Scope and preservation

This candidate is an independent `git clone --no-hardlinks` at
`/tmp/argonaut-issue25-gate-a`, with detached HEAD at the baseline. Its `origin`
is the primary local repository, **not GitHub**. Nothing is staged or committed.
No production behavior is changed. The primary checkout remains on development
at the same HEAD with clean tracked files and index. Its seven pre-existing
untracked artifacts remain present, with hashes checked before and after test
execution. All six original worktree registrations, including the already
prunable p44 registration, remain untouched. No cleanup is authorized.

Issue #25 and its comment were read using the GitHub connector. The issue is
open. Live Project fields and live development SHA could not be independently
verified: local GitHub access failed DNS/connection, and the branch connector
returned names without SHAs. Documentation says In Progress; the older issue
comment says Backlog. Neither is substituted for fresh Project evidence.
The explicit user-defined Gate A scope was followed; no new priority was selected.

## Candidate files

- `tests/run_gate_a.py`: bounded explicit runner with namespace verification,
  private display/session/environment, Python socket/DNS audit guard and reports.
- `tests/ultimate_menu_fixture.py`: reusable real SettingsTab fixture, injected
  synthetic REST/Core client, fake credentials, temporary preferences/history.
- `tests/test_ultimate_menu_gate_a.py`: eleven real GTK acceptance methods.
- `tests/ci_suites.json`: accounts for the new test module as deferred from hosted
  suites; local Gate A is explicit and separately reviewed.
- `docs/ISSUE25-GATE-A.md`: this evidence and limitation record.

## Isolation

The existing reviewed `run_ci_tests` namespace, security verification, bounded
process-group supervision, GTK preflight, and incremental unittest reporter are
reused. The host tool sandbox initially denied the local netlink socket. The
same unprivileged namespace procedure passed outside that tool sandbox; no
privileged container, sudo, host-network fallback or security setting change
was used.

Each class verifies a changed network namespace, normal nonroot UID/GID, zero
capability sets, NoNewPrivs=1, only active loopback addresses/routes, unreachable
IPv4/IPv6 documentation-address route lookups, and inherited child isolation.
The only network probe is a namespace-local loopback exchange; external route
lookups send no packets. Application imports follow that proof. A permanent
Python audit hook then denies non-Unix socket creation and DNS; IPv4/IPv6 TCP/UDP
denial self-checks are logged. Native code and subprocesses remain confined by
the network namespace. GTK gets Xvfb with TCP listening disabled, a private
D-Bus session, a clean environment and fresh HOME/XDG directories. There are no
saved profiles or real credentials. Core receives a synthetic client before
connection; the documentation-only address is never contacted.

## Coverage and interpretation

The eleven GTK methods use the production SettingsTab constructor, rendering,
real mapped widgets and dialogs. No inert GTK replacements or mocked renderer
are used. They cover both LED categories and all qualified modes (including
strip-only Sparkle), field visibility/editor availability and sensitivity,
collapsed/expanded controls, controller-driven draft discard, keyboard focus
reachability, real review cancellation, stale controller and queued-session
refusal, unqualified 1.1.0s2 refusal, reload gating, a valid qualified 1.1.0
controller/dependent transition with ordered dispatch and Undo history, Ethernet
and WiFi DHCP dependencies, and unrelated configuration edits.

Shared Restore preview validation, actual Undo history loading, and actual
native configuration preview parsing are exercised with real dialogs. Native
remote file bytes are supplied synthetically. The operating-system Restore file
chooser and real remote file transport are not qualified. The three shared
preview titles are not claimed as three distinct entry-path tests.

Twenty existing Core dependency methods additionally cover malformed and unknown
metadata, mixed-batch refusal, ordering, stale sessions/controllers, unchanged
history, all mode transitions, direct/raw admission and synthetic transport
construction. Two existing LED dependency tests are also selected. Subtests are
included inside method counts and are not counted as separate tests.

Focus qualification is bounded: real XTest Tab traversal after controller
rerender must reach a mapped sensitive widget without forcibly moving focus to
the Apply button. This does not establish comprehensive keyboard accessibility,
physical desktop behavior, or preservation of the exact previously focused widget.

## Reproduction and evidence

From this isolated checkout, choose a **new** output directory:

```sh
/usr/bin/python3 -B tests/run_gate_a.py --output /tmp/argonaut-gate-a-new-run
```

The runner refuses isolation failures; do not invoke ordinary unittest as an
isolation substitute. In the restricted tool environment, the documented
namespace launcher needed permission to run outside the tool sandbox.

Evidence directories:

- `/tmp/argonaut-gate-a-run1`: initial implementation run, 33 passed, zero
  failures/errors/skips. GTK 11, Core 20, existing dependencies 2.
- `/tmp/argonaut-gate-a-review`: independent repeat, 33 passed, zero
  failures/errors/skips, before the final focus assertion strengthening.
- `/tmp/argonaut-gate-a-review-final`: independent final-candidate execution.
- `/tmp/argonaut-gate-a-audit-final`: source inventory audit.
- `/tmp/argonaut-gate-a-preservation.json`: hashes of seven preserved artifacts.

Each run retains namespace evidence, environment, class logs, per-test JSON,
summary and launcher result. Private-session GVFS/FUSE/accessibility and D-Bus
shutdown messages occurred; passing checks do not imply warning-free desktop
acceptance. Source inventory and whitespace checks pass. No hosted workflow,
package, release or physical acceptance is claimed.

## Remaining gates

Independent review and final execution results are recorded below. Integration
into the primary checkout, manual staging/commit/push and publication require a
separate user decision. Physical Gates B/C remain unauthorized and unexecuted.
Issue #25 remains open: this work neither reproduces nor resolves the intermittent
lockup, qualifies firmware 1.1.0s2, proves device-side atomicity, or establishes
hardware capability coverage. No C64U operation, GitHub write, or primary edit
occurred. Live Project reconciliation remains outstanding.

## Final independent result

Final independent review found no actionable safety or implementation blocker.
The independent final-candidate run passed **33/33 methods**, with **0 failures,
0 errors and 0 skips**: 11 real GTK, 20 Core dependencies, 2 existing LED tests.
GTK test time was 3.167 seconds (4.081 seconds including the class wrapper).
Both controller rerenders retained a GTK Button focus; subsequent real Tab
reached a mapped sensitive widget without explicit refocusing. This is the final
focus-strengthened candidate, superseding the earlier focus-reset test evidence.

Gate A is PASS for the explicitly listed offline coverage. The Restore native
chooser, exhaustive keyboard traversal, physical Gates B/C, hosted/package and
release acceptance are not executed; these are untested scopes, not recorded
unittest skips. No production correction was needed or made. The next gate is
user review of this five-file candidate and separate authorization for any
integration/publication or physical acceptance procedure.
