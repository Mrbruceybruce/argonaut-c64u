# Issue #49 — bounded offline LED characterization

## Issue #49 offline characterization — integrated and validated, 27 October 2026

The seven-file offline characterization is integrated into primary `development`
at unchanged HEAD `cfcc88fcfb9f383497f53ce7657d5f8162652ada` and has completed
bounded integrated validation. Changes remain **unstaged, uncommitted and
unpublished**. This entry supersedes validation-pending and next-authorization
language in the preserved integration and isolated-candidate checkpoints below.

Retained primary results are **135/135 normal and 135/135 optimized**, each with
13 characterization methods plus 122 regressions, zero failures/errors/skips.
Verified network isolation preceded test imports. All seven exported traces match
across modes and the original candidate. Independent integration review reports
**QUALIFIED PASS** for this bounded source-derived model. These results were
inspected, not rerun for this documentation reconciliation. They do not establish
compiled-firmware behavior, installed-image equivalence, FPGA routing, physical
C64U safety, lockup reproduction or resolution, or broader release qualification.

Evidence is retained under project workspace
`/home/bruce/.codex/.chatgpt-projects/g-p-6ab45977554c8191ac3a40c7db115846/`:
`issue49-offline-primary-validation-evidence/validation-report.txt` and
`issue49-offline-primary-validation-evidence/independent-integration-review.txt`.
That validation verified all 23 checkouts and 14,592 unaffected file hashes,
including the original candidate, legacy artifacts and migration stash. Its exact
seven-file hashes precede this documentation-only reconciliation; refreshed hashes
and the independent documentation review belong in separate
`issue49-offline-doc-reconciliation-evidence/`. The four model/test/allowlist files
remain unchanged. Original candidate and historical evidence remain preserved.

Fresh pre-edit verification found primary and live GitHub `development` at the
same baseline, empty staging, and #49 Open / P0 — Critical / In Progress /
Ultimate Menu in Argonaut Development (Project 1). The original intermittent LED
lockup and root cause remain unresolved. Category-wide LED Apply refusal remains
intact; #48 remains tooling only, C1 physical acceptance remains incomplete, and
RM-026/028/029 gates remain outstanding. No hardware operation, runtime containment
change or GitHub mutation is part of this reconciliation.

Next gates, in order: independently review this documentation reconciliation;
refresh the complete changed-file inventory, hashes, branch, local/live HEADs,
remotes and empty staging; then review the proposed manual staging/commit/push
procedure. The user retains Git publication control, with separate staged-diff,
commit and live-publication verification gates. No publication or issue closure
is established by this checkpoint.

## Primary integration checkpoint — 27 October 2026 (America/Chicago)

The reviewed seven-file candidate was applied to the primary checkout
`/home/bruce/Documents/ChatGPT/Local Projects/argonaut-repository` on `development`
at unchanged HEAD `cfcc88fcfb9f383497f53ce7657d5f8162652ada`. Primary and live GitHub
matched at the gate, with clean tracked files/index before integration. All seven
candidate hashes matched the reviewed inventory and then matched the destination
bytes. Only this report, CURRENT-STATE and ARGONAUT-ROADMAP receive the subsequent
documentation reconciliation; the four test/model/allowlist files remain exact.

The original candidate checkpoint below, including its validation results and
then-pending integration/maintainer gates, is retained as historical evidence.
Its status language is superseded by this checkpoint: integration is complete;
changes remain **unstaged, uncommitted and unpublished**. The 135/135 normal and
optimized results and implementation QUALIFIED PASS are retained candidate
evidence, not fresh primary test results. No tests were run for integration.
Fresh integrated validation and subsequent independent integration review remain
pending; no hardware acceptance, firmware-safety or lockup-resolution claim follows.

Evidence locations under the project workspace
`/home/bruce/.codex/.chatgpt-projects/g-p-6ab45977554c8191ac3a40c7db115846/`:

- `issue49-offline-characterization/`: unchanged original isolated candidate.
- `issue49-offline-characterization-evidence/`: unchanged original specification,
  source ledger, results, traces, independent review and reviewed SHA-256 inventory.
- `issue49-offline-integration-evidence/`: new patch, preservation snapshots,
  exact-copy verification, documentation reconciliation/review and final inventory.

The sibling evidence references in the original checkpoint below resolve relative
to the original isolated candidate, not the primary repository. Evidence was not
moved into the publication inventory. All 22 previously preserved checkouts matched
the recorded baseline before integration (11,549 file hashes); the primary's seven
legacy untracked artifacts and migration stash remain protected.

Next separately authorized gate: validate integrated bytes using bounded normal
and optimized characterization/containment regressions and source inventory,
with verified network isolation before test imports; retain new evidence separately
and obtain independent integration review. Reverify complete changed-file inventory,
index, branch, local HEAD and live remote HEAD before later manual publication.
#49 remains Open / P0 — Critical / In Progress / Ultimate Menu; category-wide LED
Apply refusal, #48 tooling-only scope, incomplete C1 physical acceptance and
RM-026/028/029 gates are unchanged. Hardware and issue closure remain separately gated.

## Original isolated candidate checkpoint (preserved)

Uncommitted, unpublished isolated candidate based on Argonaut `development`
`cfcc88fcfb9f383497f53ce7657d5f8162652ada`. This is a separately written Python
model of selected source behavior, **not compiled firmware execution**, an FPGA
emulator, a lockup reproduction, or physical safety acceptance. No product code
or LED Apply containment changes. Issue #49 remains open, P0 / In Progress.

## Source and specification

Source pin: [GideonZ/1541ultimate at 7b628eb166872965ea59d66f90ffd9bcf7d71d8a](https://github.com/GideonZ/1541ultimate/tree/7b628eb166872965ea59d66f90ffd9bcf7d71d8a).
The independently reviewed QUALIFIED PASS specification from the preceding session
is retained verbatim in sibling `issue49-offline-characterization-evidence/qualified-specification.txt`.
Its pass covers source expectations and conditionally feasible schedules only.

The source ledger retains `software/u64/bling_board.cc`, `software/u64/led_strip.cc`,
`software/FreeRTOS/Source/FreeRTOSConfig.h`, `software/network/httpd.cc`,
`software/api/route_configs.cc`, and `software/components/config.h`/`config.cc`.
`firmware-manifest.json` records the pin and normalized-source SHA-256 values.
The pin does not attest the installed device image.

`tests/led_characterization.py` models the Off/Fixed/SID branches, callback
reloading and pattern dispatch. `tests/led_mapping_tables.json` contains source-
derived ordered mapping writes. Tests do not produce expected traces by invoking
these implementation tables. Full independent byte oracles cover keyboard
single-color mapping (including LED70 override) and strip left-to-right mapping;
strip Serpentine is independently enumerated for the Off-resume trace oracle.
Other table-backed mappings are dispatch coverage only.

## Fixture and scheduling contract

Fixtures are synthetic installed/model-2 post-boot boundaries. All seven stored
fields are explicit in the `Stored` record: Off, Auto SID disabled, Pattern0,
Intensity1, selector0, Red, Pure unless overridden by the case. Runtime copies
are effectuated; offset, timeout, rainbow hue and soft-start are zero; keyboard
speed starts at10. Mapping/color observation arrays and register banks begin at
zero before setup effectuation. Each model instance has its own bank, 32 envelope
bytes, empty queue, and no pending receive until `start()`. Setup effectuation is
excluded from measured hook/effectuation counts. Prior mapping fixtures explicitly
apply Direct, Single or Right before measurement.

Scheduling is a bounded single-renderer cut-point model, not a general FreeRTOS
scheduler. HTTP is priority1, renderer priority3, ticks200Hz; other tasks are
assumed blocked. A generator preserves locals and continuation across source
queue/delay boundaries. A wake runs to the next real block, draining declared
queued bytes, before HTTP resumes. Pending queue deadlines retain entry-time
speed. Explicit wake/deadline checks reject premature delay wake and HTTP entry
from a running renderer. Source statements between cut points are assumed to fit
the declared tick intervals; this is conditional feasibility, not measured timing.

The keyboard interrupt fixture has receive-data-available and shift-lock set,
byte0x41, and consume writes clearing receive availability. The finite burst case
has three bytes in one declared IRQ at tick1 and no HTTP resumption until all
three iterations reach an empty receive. Simultaneous enqueue/tick orderings are
not qualified. Raw writes carry tick, actor, bank-by-fixture, address, value and
mapping-enable context. Mapping/color arrays are observation buckets; their
routing is not evidence of FPGA behavior or damage.

## Covered slice

- Four strip Off activity/silence reversal schedules at ticks0/100/200, with and
  without Mode→Fixed callback. Both the resume landmark and next actual block
  are asserted, along with every ordered register/data write.
- Current Auto SID enable/disable, Pattern and selector callbacks during Off
  sleep; stale sampled activity remains distinct from current runtime fields.
- Keyboard mapping-enable cut: key wake, timeout wake, and no-wake control;
  exact shift-lock/render/map writes and HTTP continuation after the next block.
- Pending receive speed, finite queue drain, invalid wake rejection, Mode/Pattern
  order, explicit versus automatic Pattern3 entry, and callback disturbance.
- Same-value hooks and valid–invalid–valid ordered field model; these simulate
  parsed setters, not the actual REST parser or transport.
- Timeout0/1/d/d+1 and600 for keyboard16/12 and strip3; automatic keyboard5
  covers600→restoration on silent iteration121. Positive activity refresh and
  disabled Auto SID retention are checked.
- Intensity0/1/31, all eight selected envelope groups, unselected activity,
  selected silence and maximum three-byte activity; full strip mapping retention.

A known anomaly passing its expected trace is a characterization PASS, not a fix.
Unittest failures report the mismatching event/value; invalid scheduling raises
`InvalidFixture`. The external runner bounds execution and treats failures,
errors, skips and timeout as non-passing. No physical-lockup evidence is produced.

## Validation and review

Retained normal and optimized runs each pass **135/135**, zero failures/errors/
skips: 13 new characterization methods plus 122 existing containment-related
regressions. Totals count test methods; additional parameterized subcases inside
the 13 new methods are not counted separately. All seven named core
trace exports are byte-identical between normal and optimized execution. The first
run had four subcase assertion failures because scheduler wake events were labeled
HTTP; corrected actor labeling and independent-review fixture/oracle corrections
are covered by the final reruns. The initial failed report is retained separately.
Independent implementation review gives **QUALIFIED PASS** for this bounded
model-only slice after correcting the queue fixture and strip write oracle.
The source inventory audit passes. All 22 pre-existing checkouts match their
before-run HEAD/branch/remotes/status and tracked/nonignored-untracked file hashes.
The seven primary untracked artifacts and migration stash remain preserved.
GTK was not rerun: no UI/product change was made; prior GTK results are historical.
No hosted CI or publication was performed. The CI allowlist adds
`test_led_characterization.LEDCharacterization` with exactly13 methods. Existing
source inventory audit includes the new class. Standard future execution uses
`tests/run_ci_tests.py --suite python-unit --output NEW_DIRECTORY` (and
`--optimized`) through the documented verified isolation backend. Do not invoke
tests directly on the host as an isolation substitute.

The implementation pass uses the previously reviewed unprivileged namespace
launcher: clean temporary HOME/XDG, changed network namespace, nonroot identity,
zero capabilities, no-new-privileges, only loopback routes/interfaces, child
namespace inheritance, and socket/DNS guards before test imports. Reserved-address
route lookups send no external packets. Only an in-namespace loopback check sends
traffic. Initial sandbox loopback setup failed before any test imports; the same
runner was then executed through the approved escalation, without privileged
namespaces, host networking or weaker checks.

## Limits and next gate

Deferred: actual compiled firmware, physical FPGA behavior, real interrupt timing,
physical-menu enablement, Default rendering, Rainbow/Sparkle rendering, full
Color/Tint coverage, automatic speed5 short timeout boundaries, simultaneous tick/
enqueue alternatives, equal-priority dual-renderer schedules, general queue
capacity/overflow, and exhaustive configuration/state coverage. Fixed rendering
supports only Red/Pure/Bright and rejects unsupported fixtures. No causal link to
the intermittent lockup, installed-image equivalence, broader firmware version,
header mapping, hardware acceptance, hosted CI, package or release qualification.

Primary and existing isolated work remain preserved. This candidate is not
integrated or published. Review of this bounded model is separate from approval
to extend coverage or integrate. The next approval gate is maintainer assessment
of the reviewed offline candidate and its limits; integration and manual Git
publication require separate authorization. Hardware remains separately gated.
#48 tooling scope, incomplete C1 acceptance and RM-026/028/029 gates are unchanged.
