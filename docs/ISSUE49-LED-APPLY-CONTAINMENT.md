# Issue #49 — temporary LED Apply containment

## Authorization and baseline

Maintainer-authorized bounded OFFLINE implementation, 26 October 2026
(America/Chicago), based on `d0925f2130daa213bf118f24dc064e9c35736ae9`.
Primary and live GitHub development matched that commit before implementation.
[Argonaut Development](https://github.com/users/Mrbruceybruce/projects/1) verified
[#49](https://github.com/Mrbruceybruce/argonaut-c64u/issues/49) Open / P0 — Critical /
In Progress. #25 remains qualified closure history; #49 retains safety ownership.

The 11-file containment was independently reviewed, integrated into the primary
repository and published on `development` at
`28d123b04a56d8eb172b1be4995cc8c5cbc06245` (parent baseline above).
Primary and live GitHub HEADs matched before this documentation reconciliation;
tracked files/index were clean, with all seven legacy untracked artifacts preserved.
The original `issue49-led-containment` detached clone and its sibling evidence
remain in the Argonaut project workspace; its origin is the primary filesystem
repository, not GitHub. It remains separate from the publication checkout.

## Contract and implementation

The shared headless `configuration_policy.py` adds a temporary category-wide
Apply refusal, independent of firmware, mode, metadata or requested value.
`execute` detaches/validates intent and checks the session, then refuses before
any configuration/identity read, history mutation or dispatch. `validate` also
refuses before metadata canonicalization. Exact category matching is case-folded;
malformed/wildcard/path identities still fail existing shape/identity validation.
Unknown fields in either category are refused as well as known fields. No
partial filtering occurs: a mixed requested batch fails as a whole, including
unrelated edits. Explicit same-value fields are write intent and are refused.

The published explicit mode-write guard is still called. The firmware dependency
registry and LED implementation are retained. `enabled` makes all LED fields
read-only with a temporary safety-qualification explanation; loading/reading
values remains available. Other categories retain their existing admission,
controller ordering, staleness, session and history behavior.

Shared entry paths: Core device operations, public `UltimateClient` Apply,
GUI stage/review/Apply, selected Restore/Undo previews, actual Undo history, and
supported native `.cfg` preview/staging. UI-admission bypass still reaches Core
refusal. Preview preparation may read settings/native file bytes to display
values; selected mutation intent is refused before staging or subsequent Apply
reads/writes. Unchanged snapshot fields omitted by preview difference generation
are not explicit writes. Selecting only unrelated differences remains supported.
Uploading a native file without activation remains its existing separate
operation. Private validated transport sinks are implementation internals, not
public bypass APIs or a sandbox against arbitrary injected Python.

## Deterministic validation and review

The affected suite includes configuration dependencies, configuration,
dependencies, backups, settings safety, native files, Core, API, C64 AI launch,
scheduler, recovery and CI runner tests. It uses synthetic transports, temporary
preferences/history, verified network namespaces, no capabilities,
no-new-privileges and socket/DNS guards. The GTK runner uses private Xvfb/D-Bus
and temporary HOME/XDG directories inside the verified network boundary.

Coverage includes both categories, all known fields and modes, same-value
requests, unknown fields, case variants, mixed field/category orders, absent and
existing history, zero reads/POST on refusal, retained dependency rules, unrelated
successful writes, caller mutation, stale snapshots/sessions, Core/UI bypass,
public transport interception, Restore, actual Undo and native previews. Existing
85 mode-pair checks remain. GTK verifies visible read-only rows and preserved
unrelated editing/history. Python optimization must not disable the safety rule.

Original implementation execution evidence is retained in sibling
`issue49-led-containment-evidence/`: **122/122 normal**, **122/122 optimized**,
and **37/37 GTK gate** (11 real GTK, 24 Core, 2 LED), zero failures/errors/skips.
See `normal-reviewed.json/log`, `optimized-reviewed.json/log`, and `gtk-reviewed/summary.json`
with its per-class reports, isolation evidence and logs. Source CI inventory
audit (`audit/coverage.json`) and `git diff --check` pass. Independent review is
recorded as PASS in `independent-review.txt`; implementation, review, acceptance
and publication remain distinct. Review strengthened the refusal tests with explicit
zero-call assertions for configuration and identity reads, because a raised mock
error alone could be converted into an expected refusal. The results above cover
those strengthened assertions. Initial sandbox namespace setup failed before any test/application
execution; the approved isolated runner is used instead. No device contact occurs.

Primary integration reruns passed **122/122 normal**, **122/122 optimized** and
**37/37 GTK** (11 real GTK, 24 Core, 2 LED), with zero failures/errors/skips.
Retained `issue49-led-integration-evidence/` contains `integration-report.txt`,
`normal-primary.json/log`, `optimized-primary.json/log`, `gtk-primary/summary.json`
and `independent-integration-review.txt` (PASS). Both evidence directories are
under `/home/bruce/.codex/.chatgpt-projects/g-p-6ab45977554c8191ac3a40c7db115846/`,
not the primary repository. Results were inspected, not rerun for this
documentation-only reconciliation.

## Published containment changed-file inventory (11 files)

- `c64u_browser/configuration_policy.py`: category-wide shared refusal and read-only presentation.
- `tests/test_configuration_dependencies.py`: Core/public-client/controller refusal and preserved unrelated behavior.
- `tests/test_dependencies.py`: read-only LED presentation contract.
- `tests/test_ultimate_menu_gate_a.py`: real GTK read-only/refusal and unrelated-write coverage.
- `tests/run_gate_a.py`, `tests/ci_suites.json`: expected Core test count 24 (previously 22).
- `docs/CURRENT-STATE.md`, `docs/ARGONAUT-ROADMAP.md`, `docs/CONFIGURATION-DEPENDENCIES.md`, `docs/ISSUE25-MODE-CONTAINMENT.md`: containment precedence and unchanged gates.
- `docs/ISSUE49-LED-APPLY-CONTAINMENT.md`: this scope/evidence record.

## Acceptance limitations

No hardware test or physical acceptance. No claim of lockup resolution, general
configuration safety, device-side atomicity, runtime Auto SID containment,
control of other clients/device menus/firmware reset or load, physical-header
mapping, firmware 1.1.0s2 qualification, hosted CI, packaging or cross-platform
acceptance. Save to Flash is a separate existing operation, not per-edit Apply
admission. Unrelated actions that indirectly affect firmware LED behavior are
outside this bounded category-write policy.

C1's original 14-request protocol remains incomplete; supplemental evidence does
not complete it or create its missing final manifest. #48 retains tooling-only
scope. #49 remains **Open / P0 — Critical / In Progress** with unresolved safety acceptance criteria. Bruce / Argonaut
maintainer retains residual-risk ownership; RM-026/028/029 gates do not change.
C1 physical acceptance remains incomplete. Containment review, integration and
publication do not establish lockup resolution or satisfy physical acceptance.
