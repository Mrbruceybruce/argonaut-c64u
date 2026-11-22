# Issue #24 — identity evidence and regression design

## Scope and baseline

This documentation-only slice records the source investigation preceding it;
it does not adopt a new compatibility or admission policy. Argonaut baseline:
`9140f3146c9c012fce391aca439e684e8932b767` on `development`, equal to live
GitHub at the pre-edit check on 29 October 2026 UTC (28 October in Chicago).
Tracked files and staging were clean. Seven legacy untracked artifacts and
migration stash `1cd2cdad5f4e42c508d596f9e6181839c3a38934` were preserved.
Other branches/workspaces retain their own unqualified publication status.

Live [Argonaut Development](https://github.com/users/Mrbruceybruce/projects/1)
showed [#24](https://github.com/Mrbruceybruce/argonaut-c64u/issues/24)
Open / P1 / Backlog, with no native blockers. This identity slice does not
complete its broader capability/dependency mapping acceptance criteria.
[#26](https://github.com/Mrbruceybruce/argonaut-c64u/issues/26) remains blocked:
its native dependencies are #24 Open, #49 Open and #25 Closed. No tracking
mutation is part of this slice.

## Pinned official evidence

- **S1:** [7b628eb166872965ea59d66f90ffd9bcf7d71d8a](https://github.com/GideonZ/1541ultimate/tree/7b628eb166872965ea59d66f90ffd9bcf7d71d8a), declaring firmware `1.1.0`.
- **S2:** [2a97c79e91258826e1b85cb3ec57ffa7ffba3284](https://github.com/GideonZ/1541ultimate/tree/2a97c79e91258826e1b85cb3ec57ffa7ffba3284), resolved from `v3.12` during the prior investigation, declaring `3.12`.

These revisions identify source evidence, not the bytes of an installed image.
S1 does not qualify firmware `1.1.0s2`. Tag resolution, version declarations,
build flags and serializer findings below are retained from the prior source
investigation; this documentation pass is not a build or firmware qualification.

| Evidence class | Finding and source | Boundary |
| --- | --- | --- |
| Official source: product | [S2 product.cc](https://github.com/GideonZ/1541ultimate/blob/2a97c79e91258826e1b85cb3ec57ffa7ffba3284/software/system/product.cc): `U64 == 1` selects `Ultimate 64` or `Ultimate 64 Elite`; `U64 == 2` selects `Ultimate 64-II`. `U2P == 1` and `U2P == 2` select `Ultimate II+` and `Ultimate II+L`. | Compile-time family selection does not identify the reporting user's actual device or installed build. |
| Official source: branding | [S1 product.cc](https://github.com/GideonZ/1541ultimate/blob/7b628eb166872965ea59d66f90ffd9bcf7d71d8a/software/system/product.cc): `COMMODORE` substitutes `C64 Ultimate (MK1)` and `C64 Ultimate` for the two Elite-family labels. The prior investigation found `COMMODORE=1` in both inspected Ultimate build Makefiles. | Product spelling depends on build configuration and is not a capability description. |
| Official source: revision | Both pinned `product.cc` implementations use `U2PIO_BOARDREV >> 3`. Elite detection accepts `0x13` and `0x15–0x17`; `0x14` additionally checks joystick-control bit `0x80`. Revision descriptions differ between S1 and S2. | Neither inspected `/v1/info` handler exports board revision. A source register mapping is not a physical observation. |
| Official source: API | [S1 routes.cc](https://github.com/GideonZ/1541ultimate/blob/7b628eb166872965ea59d66f90ffd9bcf7d71d8a/software/api/routes.cc) and [S2 routes.cc](https://github.com/GideonZ/1541ultimate/blob/2a97c79e91258826e1b85cb3ec57ffa7ffba3284/software/api/routes.cc): `/v1/version` returns `version: "0.1"`. `/v1/info` emits `product`, `firmware_version`, `fpga_version`, conditional `core_version`, `hostname`, and optional `unique_id`. | No board revision, model or capability bits are exported by these handlers. Identity and ID are not authenticated hardware/image attestation. |
| Official source: field construction | FPGA is formatted as `1%02x`; core as `1.%02x` under `#ifdef U64`; firmware comes from `APPL_VERSION_ASCII`. A nonempty configured unique ID is emitted; `Default` is replaced by the generated product ID. | Version formatting does not establish capability equivalence; a configured ID does not prove components or shipping edition. |
| Official source: model | [S1 u64_config.cc](https://github.com/GideonZ/1541ultimate/blob/7b628eb166872965ea59d66f90ffd9bcf7d71d8a/software/u64/u64_config.cc) defines `C64U Model`: `BASIC Beige`, `Starlight Edition`, `Founders Edition`, default Starlight. The ordinary menu disables editing; firmware boot-key code can assign it. | Configuration metadata cannot attest installed components or shipping edition. |
| Official source: REST metadata | [S1 route_configs.cc](https://github.com/GideonZ/1541ultimate/blob/7b628eb166872965ea59d66f90ffd9bcf7d71d8a/software/api/route_configs.cc) serializes registered configuration stores/items without exporting their menu disabled/hidden state. | Advertisement does not establish physical presence, menu availability or write permission. |
| Official documentation example | The prior investigation inspected the [official API example](https://1541u-documentation.readthedocs.io/en/master/api/api_calls.html): `Ultimate 64`, firmware `3.12`, API `0.1`, optional unique ID. | This unpinned documentation example is neither an Elite II observation nor an exhaustive identity specification. |
| Historical physical observations | [Compatibility record](ULTIMATE-COMPATIBILITY.md): Beige `1.1.0s2` and Founder `1.1.0`, both `C64 Ultimate`, API `0.1`, FPGA `122`, core `1.49`. | Retained observations only; no fresh hardware verification or expanded operation qualification. |
| Community report and inference | [#14](https://github.com/Mrbruceybruce/argonaut-c64u/issues/14) reported Elite II identity refusal without a supplied identity response in the prior investigation. Source spelling `Ultimate 64-II` could explain it. | Hypothesis only; the actual response and installed firmware are still needed for diagnosis. |
| Unknown | Actual Elite II/Starlight identities, installed-image provenance and operation-specific capabilities remain unverified here. | No SID, networking, video, bus, user-port, drive or LED capability follows from a name. |

## API admission and UI acceptance — 15 November 2026

The API admission change is published on `development` in
`ba8d1a56db7eb9ca231e91ec875ef58a229f5bd3`, together with About relocation and
the Drive Reset correction. Shared
`compatibility.validate_api_version` accepts exactly `0.1` for inspection and
operational connection testing; malformed/missing/nonstring versions are refused
as `malformed`, and other numeric major.minor versions as `unsupported_api`,
before MAC lookup or candidate session adoption. Existing product, identity,
credential and LED containment boundaries remain. Protocol recognition does not
qualify installed capabilities. Independent Class C and integration review PASS;
208/208 normal and 208/208 optimized tests, 17/17 offline checks, inventory and
whitespace checks PASS. Full Markdown: 50 documents/zero errors; 36 validator tests
PASS. Offline suites used verified nonroot, zero-capability, loopback-only network
namespaces and temporary preferences. No hardware was contacted by those suites.

The separately reviewed three-file About relocation is published in the same
commit: General → Device details → Game Library → About. Focused tests
passed 18/18 normal and optimized, including shortcut destinations and reconnect.
Independent implementation and integrated-diff reviews PASS.

### Physical and operator acceptance

Founders (firmware `1.1.0`) and Beige (`1.1.0s2`) each reported API `0.1`. Retained
GET-only baselines cover 22 categories including actual LED, SID and network
settings. Recognition, disconnect/connect, and configuration comparisons passed;
70 displayed fields matched per cycle, with two sensitive fields excluded. Both
inspection dialogs and integrated-source About identity/final tab order received
operator visual confirmation. Current settings were observations, not prescribed
LED/SID prerequisites. No device configuration writes were authorized or performed
by acceptance helpers; credentials were session-only and their processes ended.

**Founders and Beige Export: PASS under operator-controlled conditions.** Founders
connected Export success is operator-reported evidence distinct from its earlier
stopped helper attempt. Beige succeeded through the primary source launcher in
normal GNOME services with isolated preferences and no GTK automation. Its saved
`argonaut-settings.json`, created `2026-11-15T18:33:39.175678+00:00`, is a valid
version-1 backup with 22 categories/206 settings, matching the retained sanitized
baseline and omitting prohibited credential fields. SHA-256:
`10407e78a0be8b272fd9bc58012357c0c8aef082ba3805c30851bfb81bb9e369`.
The original export contains private network values and is not a public attachment.

Work-launched GTK chooser failures remain an environment-dependent limitation;
precise cause is unconfirmed. An instrumented Beige retry recorded connected,
loaded, idle state and a GTK-visible native chooser, while the operator saw no
save dialog. A disconnected-button no-op does not explain that retry. Earlier
synthetic exports succeeded, and the final operator-controlled launch succeeded.
Neither result proves a portal, application or helper root cause. Failed attempts
remain historical evidence; no application export-code correction was made.

Local evidence is retained in `/tmp/argonaut-issue24-authenticated-20261115`,
`/tmp/argonaut-issue24-ui-final-20261115`,
`/tmp/argonaut-issue24-remaining-ui-20261115`,
`/tmp/argonaut-issue24-export-retry-20261115`, and
`/tmp/argonaut-issue24-operator-export-20261115`. These temporary artifacts must
be retained for review; they are not committed/public evidence. Redacted baseline
values cannot establish equality of private values. Snapshots are non-atomic;
there is no flash-persistence, fault-recovery or exhaustive all-settings visual
qualification. Successful Export does not establish all-tab operational safety.

### Drive Reset confirmation safety candidate

A deterministic probe found that the shared client facade survives reconnection:
a stale Drive Reset dialog could dispatch against a renewed session. This
pre-existing finding is separate from API/About admission and presentation changes.
The bounded correction captures the originating `DeviceSession` when Reset is
opened, rejects stale UI responses, and dispatches through Core with the same
session revalidated under admission and device-lane exclusion. Reset/readback use
one captured transport; reconnect cannot replace it mid-operation. A consumed,
cancelled or refused dialog cannot retry. Uncertain reset/readback errors do not
retry. Valid same-session confirmation still sends exactly one reset and readback.
The response-to-worker delay is checked in Core, not just in GTK.

The reviewed source is retained in `/tmp/argonaut-issue24-drive-reset-20261115`.
Its seven-file correction was integrated with the API/About changes and published
in `ba8d1a56db7eb9ca231e91ec875ef58a229f5bd3`. The retained integration review
verified the implementation/test/CI bytes and three-document status overlay.
The seven older untracked artifacts remain preserved. The Reset-only patch, status-only overlay and combined validation/
independent integration review evidence are retained separately in
`/tmp/argonaut-issue24-drive-reset-integration-20261115`. Publication supersedes
the earlier uncommitted status; it does not establish installation, physical Reset
acceptance or issue closure.

Candidate validation: **223/223 normal and 223/223 optimized unit tests PASS**,
including 15 new Reset contracts; **35/35 normal and 35/35 optimized adjacent
Drive/picker/machine tests PASS**; **17/17 offline checks PASS**. Unit/offline suites
used verified loopback-only network namespaces; adjacent tests used fake transports
and inert dialogs without a namespace. CI inventory and whitespace checks PASS.
Full Markdown: **50 documents/zero errors**, with unchanged historical diagnostics.
The validator used the existing pinned tooling and a Git-derived inventory file;
no software was installed. **Independent Class C review: PASS, no actionable
findings**, including independent 15/15 normal and 15/15 optimized Reset contracts
with network/DNS blocked. Exact diff, hashes, review and validation evidence are
retained in `/tmp/argonaut-issue24-drive-reset-evidence-20261115`.
Fifteen deterministic Reset contracts cover valid,
cancelled, disconnected, lost, reconnected, replaced and different-device sessions;
worker delay; admission/device-lane contention; single dispatch and uncertain
outcomes. All transports are synthetic and GTK dialogs inert. Rejected paths must
perform zero device commands, configuration writes and readback.

This corrects **Reset only**. On/off/eject/type confirmations and Flash-file guards
are not qualified by it. The broader disconnected-button redesign remains deferred
under Ultimate Menu; initial eight-button sensitivity is not a safety boundary.
Category-wide LED Apply containment remains unchanged. Original intermittent LED
lockup and indirect/Auto SID risks remain unresolved; transferred #49 obligations
and #26 dependencies remain in force. Any separately required physical qualification,
release acceptance and issue closure remain separate gates. Integration
validation/review does not establish physical Reset or all-tab safety acceptance.

### Beige Drive A Reset — operator-reported acceptance

On 15 November 2026, the operator reported successful bounded physical acceptance
for Drive A on Beige (`192.168.68.70`). Evidence is separated as follows:

- **Retained pre-reset UI observations:** screenshots from Work task
  `01a1e0c2-23b0-7fb2-9772-8c2d42d1c245` show firmware `1.1.0s2`, API `0.1`,
  Drive A On / Device 8 / Type 1541 / No disk mounted, and a blank bottom status
  after the drive read. These screenshots were re-inspected for this record;
  they do not establish physical idleness or post-reset state.
- **Operator-confirmed provenance and prerequisites:** the operator confirmed
  About `1.10-dev / 0bbc4014170d-modified`, selected Drive A, and confirmed no
  physical drive activity or valuable unsaved work. The running build identity
  is operator-reported, not independently verified from an About capture.
- **Operator-reported cancellation:** “cancelled and everything is working” in
  conversation `6af0e31f-b0d8-83ea-919f-681a71f30feb` records successful cancellation
  and continued responsiveness. No transport trace establishes zero Reset dispatch
  on cancellation; prior synthetic cancellation contracts are separate evidence.
- **Operator-reported physical Reset:** after separate authorization, one physical
  Drive A Reset was performed, followed by “works normally”. The current owner
  handoff identifies this as the result of that one authorized Reset. No exact
  post-reset UI text, explicit drive-status readback or physical observation was
  supplied. Reset dispatch count, logs and post-reset media state were not
  independently verified. This is bounded operator-reported success, not a claim
  of instrumented hardware qualification or exhaustive operation safety.

This subsequent report supersedes the earlier stopped/no-physical-Reset wording
only for this bounded Beige Drive A attempt. It does not qualify Drive B, Founders,
other devices, fault/reconnect recovery, other Drive actions or all-tab safety.
On/off/eject/type confirmations, Flash-file stale-session safeguards and broader
disconnected-button presentation remain follow-ups. Category-wide LED Apply
containment remains mandatory; intermittent LED lockup and indirect/Auto SID risks
remain unresolved. Transferred #49 criteria 2, 3, 5, 6, 7 and 8 remain unmet and
unwaived; C1, #26 dependencies and broader RM-026/028/029 gates remain outstanding.

Preparation verified primary and live GitHub `development` at
`0bbc4014170dd295fd7fdaefd9c96e93a2067c21`, clean tracked files, empty staging and
seven legacy artifacts matching retained hashes. Live #24 remains Open / Backlog /
P1 — High / Ultimate Menu. This acceptance record is published at
`5312370990e10d437bddb2e301098334da2cb5c6`, as confirmed by the
[published acceptance comment](https://github.com/Mrbruceybruce/argonaut-c64u/issues/24#issuecomment-6901618581).
That publication supersedes this record's former unpublished/comment-not-posted
wording; no Project fields changed. No hardware contact, application launch or
repeated hardware/regression test occurred during preparation. No broader
acceptance criterion, safety requirement or publication gate is waived.

### Beige Drive A/B — bounded operator-reported acceptance

Record published 15 November 2026 at
`033658dc9b0b60111cb73869f30ed01309e605f7`, confirmed by the
[final Issue #24 tracking comment](https://github.com/Mrbruceybruce/argonaut-c64u/issues/24#issuecomment-6903355263).
The implementation is separately published at
`152e3885590e9fe62e19e68eb30e83f1f3025c4f`, confirmed by the earlier
[implementation publication comment](https://github.com/Mrbruceybruce/argonaut-c64u/issues/24#issuecomment-6902156008).
Primary and live `development` HEADs were verified equal at `033658dc…` before
this documentation correction, with clean tracked files, empty staging and seven
preserved untracked artifacts. Current artifact hashes were recorded; equality
with historical hashes was not independently reverified. The integrated/unpublished
section below is a historical checkpoint, superseded only for publication and the
bounded acceptance recorded here.

**Evidence availability at this reconciliation:** the original directories
`/tmp/argonaut-issue24-drive-confirmations-integration-20261115` and
`/tmp/argonaut-issue24-drive-confirmations-evidence-20261115` are absent.
The historical test/review results remain recorded in published documentation and
GitHub; their original local reports cannot presently be reinspected. References
below to retained evidence and inspected results describe the original record,
not fresh inspection in this reconciliation. Screenshot observations below likewise
remain the published historical record; screenshots, application tests and hardware
acceptance were not repeated or reinspected for this correction.

Evidence sources are the operator reports and retained screenshots from
**Continue issue 24** (conversation `6af0e31f-b0d8-83ea-919f-681a71f30feb`),
the existing Work task **Prepare Issue 24 acceptance plan**
(`01a1e147-349c-7f90-ad59-3fddc09c5869`), and the owner's explicit continuation
summary. The retrieved prior assistant replies contain reference placeholders;
the case mapping below therefore relies on that explicit owner summary, not
reconstructed unseen instructions or invented per-step timestamps.

Re-inspected screenshots show About `1.10-dev / 152e3885590e-modified`,
connection address `192.168.68.70:80`, firmware `1.1.0s2`, API `0.1`, and the
baseline drive cards: A On / Device 8 / 1541 / `JiffyDOS_1541-II_6.00.bin`;
B Off / Device 9 / 1541 / `1541.rom`; both “No disk mounted”. The existing
source-launch plan explains the expected `-modified` suffix from the seven
preserved untracked artifacts. Screenshots establish displayed identity/status,
not authenticated physical identity or idleness; Beige identification and
physical idle/normal-operation statements remain operator-reported.

The configuration screenshots show A's configured 1541 JiffyDOS, `1571.rom`
and `1581.rom`; B's configured `1541.rom`, `1571.rom` and **`1541.rom` for
1581 mode**. Configuration display is not evidence of running every mode.

| Cancellation intent | Drive A | Drive B |
| --- | --- | --- |
| Turn on | Operator-reported PASS, later cancellation | Operator-reported PASS |
| Turn off | Operator-reported PASS | Operator-reported PASS |
| Eject | Operator-reported PASS | Operator-reported PASS |
| Type 1541 | Operator-reported PASS | Operator-reported PASS |
| Type 1571 | Operator-reported PASS | Operator-reported PASS |
| Type 1581 | Operator-reported PASS | Operator-reported PASS |

All 12 cancellations are operator-reported PASS. Cancellation does not itself
refresh drive status; a selected type is not proof of the running type.
Zero command dispatch on cancellation is not independently measured here.

**Separate procedural incident:** the initial Drive A Turn on was confirmed
instead of cancelled. The operator explicitly reported the mistake and later
“it's operating normally”. A retained screenshot shows “Command completed;
drive status refreshed” with the baseline cards. This is a normal-result
incident, not a cancellation pass or retroactive authorization. The implementation
warns that Turn on while already on resets the drive; no physical Reset dispatch
count is inferred. The later successful A Turn on cancellation supplies that
cancellation case.

| Confirmed command sequence | Disposition |
| --- | --- |
| A off, then on | Operator-reported PASS |
| A 1541 → 1571 → 1581 → 1541 | Operator-reported PASS |
| A empty Eject | Operator-reported PASS; no-media case only |
| B on, then off | Operator-reported PASS |
| B 1541 → 1571 → 1541 | Operator-reported PASS |
| B empty Eject | Operator-reported PASS; no-media case only |
| B transition to 1581 | **NOT TESTED — accepted exception** |

The owner accepted omission of B 1581 with no retesting this acceptance cycle;
its configured ROM was `1541.rom`. This is not a B 1581 pass, compatible-ROM
qualification or a general waiver. The B 1581 cancellation remains distinct.

Final A On / 1541 / JiffyDOS and B Off / 1541 / `1541.rom`, both with no media,
idle and operating normally, are operator-reported. Exact post-command messages,
ROM/status details and other-drive invariance for every step were not independently
observed and are not inferred from the planned expectations. The source/test
contract of one command and one readback remains synthetic evidence; physical
network dispatch counts were not captured. Mounted-media eject, stale-session
race physical qualification, Founders acceptance and recovery remain untested
by this cycle. No hardware operation or application launch was repeated for
this evidence preparation, and no application regression tests were rerun.

Retained implementation review/test results below are unchanged, including the
known 114/115 adjacent suite. Flash-file stale-session safeguards, broader
disconnected-button presentation, mandatory category-wide LED Apply containment,
unresolved intermittent lockup and indirect/Auto SID risks remain outstanding.
Bruce's residual-risk ownership, unmet/unwaived #49 criteria 2, 3, 5, 6, 7 and 8,
incomplete C1, #48 tooling-only scope, #26 dependencies and RM-026/028/029 gates
remain unchanged. #24 remains Open / Backlog / P1 — High / Ultimate Menu.
This bounded operator-reported acceptance does not complete #24 or release
qualification. This acceptance record was published at `033658dc…` and its
[final tracking comment](https://github.com/Mrbruceybruce/argonaut-c64u/issues/24#issuecomment-6903355263)
was posted. These completed steps supersede the former approval/publication-pending
proposal wording. Publication of this documentation correction remains a separate
owner gate; no GitHub issue or Project fields are changed by the correction.

### Drive A/B command confirmation safety — integrated, unpublished

Historical integration checkpoint: the acceptance/publication record above
supersedes the pending status below within its stated bounds.

On 15 November 2026, the exact independently reviewed four-file candidate was
integrated into primary `development` at published HEAD
`5312370990e10d437bddb2e301098334da2cb5c6`. Local and live GitHub HEADs were
reverified equal during documentation reconciliation. The implementation and
this documentation remain **unstaged, uncommitted and unpublished**; the index
is empty. The four implementation files are `c64u_browser/core.py`,
`c64u_browser/drives_tab.py`, `tests/ci_suites.json` and the new, still untracked
`tests/test_drive_command_confirmation.py`. The seven legacy untracked artifacts
and other worktrees remain preserved.

For both A and B, on/off/eject (`remove`) and type changes to 1541/1571/1581
capture the originating `DeviceSession` and exact drive/action/type intent at
confirmation opening. The guarded dialog consumes its response before cancellation,
stale-session refusal, busy refusal or worker submission; repeated responses cannot
submit another command. Core's `execute_drive_command` validates arguments and
revalidates the session under fail-fast admission, captures one transport, then
revalidates inside the physical-device lane before dispatch. Admission covers
command and readback, excluding session replacement during that interval. A valid
command is followed by one status readback. Command uncertainty skips readback;
readback uncertainty repeats neither operation. No automatic retry or reconnect
is added. The Reset Core body, mount handling and transport routes are unchanged;
the shared dialog refactor preserves Reset's guarded-response behavior.

The retained integration evidence directory is
`/tmp/argonaut-issue24-drive-confirmations-integration-20261115`:
`REPORT.txt`, `validation.json`, suite logs/reports, `integrated.patch` and
`independent-integrated-review.txt`. The integrated patch is byte-identical to the
reviewed candidate, SHA-256
`83bd19d1362f6df32a36c566e51bdc3f12b808106ee09adb378494a43d1e29cc`.
The prior candidate evidence remains in
`/tmp/argonaut-issue24-drive-confirmations-evidence-20261115`.

| Retained integration check | Result | Execution boundary |
| --- | --- | --- |
| Unit | 260/260 in each Python mode | Verified isolated network namespaces |
| Broader Python regression | 356/356 in each mode | Verified isolated network namespaces |
| Focused synthetic regression | 93/93 in each mode | Socket and DNS blocked |
| Offline checks | 17/17 | Verified isolated network namespace |
| Independent new-command + Reset checks | 36/36 in each mode | Synthetic, socket and DNS blocked |
| Extended adjacent suite | 114/115 in each mode; one known baseline failure | Synthetic, socket and DNS blocked |

Each mode means normal and optimized Python. Passing suites record zero failures,
errors and skips. The 21 new command-suite tests include 20 contracts covering all
12 A/B command/type intents and one mount-preservation contract covering six A/B
access-mode combinations. Coverage includes cancellation, stale/disconnected/lost/
reconnected/replaced sessions, delayed workers, contention, exact intent, duplicate
responses and uncertain outcomes. **Independent Class C integrated-diff review:
PASS, no actionable findings; no waiver applies.** Retained integration Markdown
validation passed all 50 documents with zero errors; whitespace and CI source
inventory checks passed. These application-test results are inspected prior
evidence, not new executions for this documentation reconciliation.

The extended failure is
`MachineSafetyTests.test_worker_submission_failure_consumes_target_and_old_response`:
it expects “was not sent” but receives “Could not complete Reset C64 submission.
No automatic retry.” Prior independent evidence reproduces the same failure on
unchanged baseline. `power_dialog.py`, `gui.py` and `test_machine_safety.py` remain
baseline-identical. The extended suite is not fully passing and no repair is claimed.

Physical acceptance of on/off/eject/type on A/B remains pending. It requires a
separately reviewed and authorized procedure with identified build/device/firmware,
idle drives and safe disposable media as applicable. The earlier operator-reported
Beige Drive A Reset success does not qualify these commands. No application launch,
hardware contact, Git publication or GitHub tracking write is part of this
reconciliation. Manual publication and live verification remain separate gates;
this is not release acceptance or completion/closure of #24.

Flash-file stale-session gaps and broader disconnected-button presentation remain
follow-ups. Category-wide LED Apply containment, unresolved intermittent lockup and
indirect/Auto SID risks, Bruce's residual-risk ownership, unmet/unwaived #49 criteria
2, 3, 5, 6, 7 and 8, incomplete C1, #48 tooling-only scope, #26 dependencies and
RM-026/028/029 gates remain unchanged. Earlier on/off/eject/type follow-up wording
above describes the Reset-only checkpoint; this section updates implementation
status only, without extending physical acceptance.

## Publication and hosted GTK verification — 15 November 2026

Primary and live GitHub `development` were verified equal at
`765032f420e63c040393be86f388f0c981df17f0`, the direct child of `ba8d1a5`, with
clean tracked files, empty staging and the seven legacy artifacts unchanged.
This one-line test-only correction updates the Settings tab-order expectation in
`tests/test_uc1b_presentation.py`; lifecycle, close/reopen and geometry assertions
remain unchanged. Its retained independent review reports PASS, no actionable
findings, and local namespace-isolated GTK validation reports 27/27 PASS. Docker
was unavailable locally; that record is distinct from the subsequent hosted run.

[Run #225](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/43749999040)
at `ba8d1a5` remains a failed historical result: 26/27 GTK tests passed, with only
the stale Settings tab-order expectation failing. This was not the earlier
578-pixel geometry failure.
[Argonaut Test Lab #226](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/43751767750)
at the full correction SHA above passed all eight jobs. Its GTK artifact records
27/27 PASS, including the complete Settings close/reopen test and the narrow-window
geometry test; zero failures, errors, skips or timeouts; successful Docker network
isolation, GTK/private D-Bus preflight, runner cleanup and independent workflow
cleanup. These inspected CI results do not qualify physical Drive Reset, all-tab
safety, unresolved LED behavior or a release. No hardware tests were repeated for
this documentation reconciliation. Issue #24 remains Open / Backlog / P1 — High /
Ultimate Menu; no Project fields or acceptance criteria are changed.

## Two distinct Argonaut contracts

Historical baseline comparison: this section and the original regression design
below describe the pre-admission investigation. The published shared API `0.1`
validator supersedes the old API-validation gap; product allowlist and capability
limitations remain. Retain the original findings as historical evidence, not the
current API admission policy.

At the baseline, [compatibility.validate_protocol](../c64u_browser/compatibility.py)
requires both identity envelopes to be dictionaries with `errors == []`.
Required product/firmware fields must be nonblank strings, at most 256 characters,
without characters below ASCII 32. Optional FPGA/core/hostname/ID fields may be
absent or empty, but if present must be strings within those length/control
limits. API syntax is digits, a dot, digits; only `0.1` is supported.
Product spelling is not a gate. Inspection grants no operational session,
credentials persistence, FTP access or capability permissions.

[UltimateClient.test_connection](../c64u_browser/api.py) instead checks five
case-insensitive product literals: `C64 Ultimate`, `Commodore 64 Ultimate`,
`Ultimate 64`, `Ultimate 64 Elite`, `Ultimate 64 Elite II`. It does not trim
product whitespace. Firmware and API values must be strings, but this method
does not invoke UC-1's version or identity-field validator. Existing transport
and envelope handling still applies; subsequent saved-device binding and
operation-specific safeguards are separate gates. Passing this method alone
does not prove an operation is qualified.

Observed code gaps: source-exact `Ultimate 64-II` and `C64 Ultimate (MK1)` are
absent from the operational allowlist. Conversely, accepting the literal
`Ultimate 64 Elite II` is not physical qualification. Unsupported API versions
are not universally refused across these two paths. These are code comparisons,
not proof of the community report's cause or authorization to alter admission.

Argonaut reads `C64U Model` separately through configuration in
[Core](../c64u_browser/core.py); its Starlight fixture is synthetic. The shipping
box label is user-entered. Neither is an authenticated capability source.
Preserve the [server-first ownership contract](SERVER-FIRST.md) and
[UC-1 limits and diagnostics](ULTIMATE-COMPATIBILITY.md#uc-1-read-only-rest-inspection).

## Deterministic regression design — not executed

This matrix specifies a later separately authorized offline characterization.
Capture existing UC-1 and operational outcomes separately before proposing a
policy change; do not encode desired new admission as if already approved.

| Dimension | Cases | Required assertions |
| --- | --- | --- |
| Products | All five admitted literals; source-exact `Ultimate 64-II`, `C64 Ultimate (MK1)`, `Ultimate II+`, `Ultimate II+L`; unknown names; case and surrounding whitespace variants. | UC-1 accepts valid identity independently of spelling; operational path preserves its exact case-folded allowlist behavior. No additional operations become available. |
| Required identity | Missing, null, nonstring, empty, whitespace-only, control characters, 256/257-character product and firmware strings. | UC-1 classifies malformed fields; characterize differing operational outcomes explicitly. |
| Optional identity | Absent, empty, null, nonstring, control characters and 256/257-character FPGA/core/hostname/ID. | UC-1 permits absent/empty strings; rejects malformed present values. Do not assume identical operational validation. |
| API version | `0.1`, `0.2`, `1.0`, `0.1.0`, empty, missing, nonstring. | UC-1 recognizes only `0.1`; syntactically valid other versions are unsupported, invalid syntax/type malformed. Record operational string admission separately. |
| Saved binding | Matching/mismatching ID; absent/default ID; MAC fallback match/mismatch/unavailable; unbound manual versus required-bound connection. | Preserve Core binding/refusal outcomes; no credential or session adoption from inspection. Use fake peer-MAC lookup, no real network query. |
| Transport/metadata | Invalid envelopes/JSON, response/category/setting limits, redirects, authentication, 404/405/501, timeout, HTTP 500. | Preserve structured classifications and bounded request sequence; no retries. Unsupported endpoints differ from communication failure and unknown HTTP 500. Preserve partial observations and stop-on-authentication behavior. |
| Inspection isolation | Connected/disconnected success/failure; endpoint/password/profile/session changes; dialog closure and stale callbacks. | Preserve sessions, credentials and preferences; no FTP acquisition, persistence or stale presentation updates. Test closure separately from Keep editing. |
| Capability boundaries | Independently vary model/product/firmware; missing metadata and synthetic Starlight identity. | Unknown stays unknown; names, fixtures and inspection success grant no operations. Category-wide LED Apply refusal is unchanged. |

Existing [UC-1 tests](../tests/test_uc1_compatibility.py) cover portions of this
matrix; source inspection is not a new passing result. A follow-up must inventory
existing assertions before adding tests, specify expected result/error and
request counts per path, use synthetic transports and temporary preferences,
and verify network isolation before importing application/tests. Run meaningful
normal/optimized headless regressions and applicable native GTK lifecycle tests
under the [development test policy](DEVELOPMENT.md), with independent review.
Do not convert this design into hardware requests or execute the entire Test Lab.

## Acceptance limits and next decision

The prior investigation's independent review gave qualified agreement with its
bounded conclusions and regression approach, checking Argonaut validation and
isolation plus key pinned product/API/model sources. Build flags, tag resolution,
version headers and serializer findings were checked by that investigation's
primary author, not independently reverified then. A new independent review of
this exact documentation diff is recorded separately in session evidence; the
prior review does not substitute for it.

No executable tests, physical acceptance, compiled-firmware verification or
installed-image equivalence are claimed by this slice. Identification evidence
does not complete #24's SID, controller, network, video, expansion/user-port,
FPGA/core, drive or configuration-dependency mapping. The next decision is a
separately authorized bounded offline characterization/policy proposal; any
device-specific compatibility claim or operational change also requires its
separately authorized physical qualification procedure.

[#49 containment](ISSUE49-LED-APPLY-CONTAINMENT.md) continues to refuse all
explicit Apply writes to `Keyboard Lighting` and `LED Strip Settings`, including
same-value/unknown fields and entire mixed batches. The intermittent lockup and
indirect/Auto SID safety remain unresolved. #48 is tooling only; C1 physical
acceptance is incomplete. RM-026/028/029 gates and #26 blockers remain intact.
Documentation completion, acceptance, publication and issue closure are distinct;
staging, committing, pushing and issue updates remain outside this slice.
