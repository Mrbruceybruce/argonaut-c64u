# Configuration dependency validation — Issue #25 / RM-007 foundation

## Gate C1 functional disposition — 25 October 2026 UTC

The approved [C1 disposition](CURRENT-STATE.md#gate-c1-functional-disposition--25-october-2026-utc)
records bounded keyboard intensity **6→16** success in Fixed Color / Red, supported
by the validated POST response, operator observations and a subsequent separately
authorized authenticated keyboard-category GET (HTTP 200, empty errors, intensity
16 and otherwise expected values/metadata). The attempt baseline had LED Strip
Settings mode Off; C1 sent no strip write or mode transition.

The original attempt stopped before requests 9–14; its two scheduled readback and
observation rounds did not complete. The later GET did not reverify identity or
the strip category. **The original 14-request protocol did not pass**, and its
terminal completion/acceptance/evidence flags remain false. The complete evidence
record and pending retention needs are linked above.

This changes no dependency rule or firmware qualification. It does not establish
safe mode transitions, prolonged stability, header mapping, device-side atomicity
or lockup resolution. The executor termination remains unresolved; Issue #25
remains **Open / P0 / In Progress**, with dependent work still gated. The isolated
executor is unpublished; independent documentation review found no actionable findings, and manual
publication remains pending. Earlier Gate A/B statements describe their historical checkpoints.

## Gate A/B evidence checkpoint — 25 October 2026 UTC

Gate A infrastructure is published at `89c8eea956dc66d52124da5969fc14ede9a5a27b`.
Its **33/33 isolated offline methods** passed; all eight jobs in
[hosted run 40154324070](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/40154324070)
passed separately. The real-GTK Gate A module remains deferred from hosted suites.
See [current publication and acceptance evidence](CURRENT-STATE.md#gate-a-publication-and-gate-b-read-only-acceptance--25-october-2026-utc).

[Accepted Gate B read-only evidence](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25#issuecomment-6393217684)
records **5/5 validated GETs** on operator-identified Founder `25BE71`, product
`C64 Ultimate`, firmware `1.1.0`, API `0.1`. Both Keyboard Lighting and LED Strip
Settings expose exactly seven expected fields. Enum arrays and defaults match
the full pinned source vocabularies in order; enum objects contain exactly
`current/values/default`. Intensity objects contain exactly
`current/min/max/format/default`, bounds 0–31 and format `%d`, with defaults
6 keyboard / 25 strip. Captured modes/intensities are Fixed Color / 6 for keyboard
and Rainbow / 25 for strip. Exact distinctions remain: standalone Sparkle is
strip-only; keyboard `Single Color` versus strip `SingleColor`; keyboard Circular
versus strip Serpentine. No metadata/source/published-rule discrepancy was found
within this capture. The linked acceptance record retains full values and the
sanitized local journal's path/hash.

The [pinned REST serializer](https://github.com/GideonZ/1541ultimate/blob/7b628eb166872965ea59d66f90ffd9bcf7d71d8a/software/api/route_configs.cc)
emits neither enabled/disabled nor hardware-presence flags. The captured keyboard
Outward pattern is dormant under Fixed Color; the strip Royal Blue fixed color
is dormant under Rainbow. These retained values are consistent with the unchanged
menu dependency matrix below, not permission to edit inactive fields.

The two RGB headers beneath the main board and keyboard are operator-reported;
physical-header-to-REST-category mapping remains unverified. This acceptance
establishes bounded identity/metadata reads only, not every physical mode, safe
writes, prolonged stability or other hardware qualification. **Gate C remains
unauthorized and unaccepted; the original lockup remains unexplained and unproven
resolved.** Firmware `1.1.0s2` remains unqualified. Issue #25 remains Open / P0 /
In Progress; capability, redesign and enhancement dependencies remain unchanged.
The earlier publication and original implementation checkpoints below retain
their historical scope, including inert-widget fixture limitations. This evidence
update changes no dependency rule and does not publish the isolated Gate B executor.

## Publication checkpoint — 24 October 2026

The reviewed slice is integrated and published on `development` at
`c3a4984a1a4754830cf2b02aa202e3d75b0b37a7`.
[Hosted Test Lab run 40150212361](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/40150212361)
passed all eight configured jobs, including GTK regression. The offline fixtures
and their limitations described below are unchanged. This hosted result does not
establish physical C64U, package, cross-platform or release acceptance, qualify
firmware `1.1.0s2`, or prove the device lockup resolved. Issue #25 is verified as
P0 / In Progress / Open in Argonaut Development; the Project status update is complete.
Physical acceptance and root-cause investigation remain pending.
Earlier candidate/integration-authorization statements below describe the
pre-publication checkpoint; they are not the current publication state or new
hardware authorization. See CURRENT-STATE for integration tests and review.

## Original implementation checkpoint

Offline implementation candidate, 24 October 2026, based on published
`development` commit `c6db7da2be7bc4f65d2bdad41491712e35b9718a`.
This is reusable Core infrastructure for the Ultimate Menu renovation
([#20](https://github.com/Mrbruceybruce/argonaut-c64u/issues/20)), scoped to
[#25](https://github.com/Mrbruceybruce/argonaut-c64u/issues/25) and the bounded
capability evidence relevant to [#24](https://github.com/Mrbruceybruce/argonaut-c64u/issues/24).
It does not implement the tree/property-sheet redesign or LED enhancements.

## Official source qualification

Pinned official GideonZ/1541ultimate revision:
`7b628eb166872965ea59d66f90ffd9bcf7d71d8a`.
The [version commit](https://github.com/GideonZ/1541ultimate/commit/7b628eb166872965ea59d66f90ffd9bcf7d71d8a)
is titled “Set version to 1.1.0” and changes `software/application/versions.h`
`APPL_VERSION_NUMBER` to `1.1.0`. Qualification uses the commit, not a movable tag
or the current upstream branch.

- [Keyboard definitions and rules](https://github.com/GideonZ/1541ultimate/blob/7b628eb166872965ea59d66f90ffd9bcf7d71d8a/software/u64/bling_board.cc):
  mode/field definitions at lines 35–49; `update_menu` at 789–821.
- [Strip definitions and rules](https://github.com/GideonZ/1541ultimate/blob/7b628eb166872965ea59d66f90ffd9bcf7d71d8a/software/u64/led_strip.cc):
  enum/field definitions at 55–74; `update_menu` at 655–688.

Both categories use REST identity `LedStrip Mode`, despite the physical menu's
shortened label `Mode`. Keyboard modes are Off, Fixed Color, SID Music, Rainbow,
Rainbow Sparkle, and Default. The strip additionally supports Sparkle.

| Proposed mode | Pattern | Intensity | Fixed Color | Color tint |
| --- | --- | --- | --- | --- |
| Off | inactive | inactive | inactive | inactive |
| Default | inactive | active | inactive | inactive |
| Fixed Color | inactive | active | active | active |
| SID Music | active | active | inactive | inactive |
| Rainbow | active | active | inactive | active |
| Rainbow Sparkle | active | active | inactive | active |
| Sparkle (strip only) | inactive | active | inactive | inactive |

Auto SID Mode and SID Select have no mode-dependent disable rule in either
`update_menu`; advertised qualified choices remain available in every known mode.
The existing UI DHCP/static-IP dependency is also represented in the shared
registry and now enforced at the Core boundary.

Runtime LED admission requires a fresh `/v1/info` reporting exactly product
`C64 Ultimate` and firmware `1.1.0`, plus fresh category/field metadata: a known
current/controller choice, a nonempty subset of the qualified mode vocabulary,
known enum choices, and integer intensity bounds 0–31. Unknown versions,
including `1.1.0s2`, are not silently mapped to official `1.1.0`. They require
separate source qualification. This product/version scope follows the existing
[compatibility evidence](ULTIMATE-COMPATIBILITY.md); identity strings do not
attest the running image cryptographically.

Store exposure is configuration-contract evidence, not proof that LEDs are
physically installed. The firmware registers stores independently of installation,
and the strip physical-menu heading explicitly allows “if installed”. This slice
does not invent a hardware-presence probe or claim physical qualification across
Beige, Founder, Starlight, or other hardware.

## Shared ownership and admission

`configuration_policy.py` is headless Core policy. Its dependency registry,
`enabled`, and `validate` functions are shared by Ultimate Menu presentation,
Restore/Undo/native-file staging, direct Core calls, and the internal raw-client
public Apply entry point. `dependencies.py` retains compatibility imports for
existing UI callers. Future property sheets can use the same policy.

1. Detach and validate the full intent: plain dictionaries, unambiguous identities,
   finite scalar values. Reject case-colliding names and wildcard/path identities.
2. Read fresh settings for every touched category. For LED edits, read fresh
   firmware/product identity. Validate all selected values and capabilities.
3. Overlay every proposed controller before checking dependent edits. Retained
   dormant values are not edits and do not prohibit valid controller-only changes.
   Same-value explicit edits to inactive fields still fail admission.
4. For reviewed Apply, compare changed values and controlling settings against
   the review snapshot, including a mode the user did not edit. A stale controller
   refuses even if the requested dependent is active in both old and new modes.
5. Reject the entire invalid mixed batch before any REST write or history write.
   Never partially filter/apply a refused batch.
6. For an admitted batch, place enabling controllers before dependent fields,
   save the prior changed values for Undo if requested, then make one REST POST.
   Transport failure is uncertain and is not retried or automatically rolled back.

Core holds its session-admission gate through fresh reads, validation, history,
and dispatch. Reviewed UI work captures a session identity; reconnect invalidates
it. The raw public `UltimateClient.apply_configuration` uses the same admission;
`_apply_configuration_validated` is only the internal transport sink after Core
admission, not a public client capability. Core does not expose raw transports.

The UI uses the same final-state validator before review and before staging a
Restore/Undo/native-file selection. Invalid selections preserve existing state.
A preview cannot clear an existing reload gate. Ordinary interactive controller
changes retain the established behavior of discarding newly inactive local
field edits; selection previews validate the complete set before any staging.
Core rechecks independently, so bypassing UI admission cannot permit a bad write.
Definite refusal reports `Configuration not sent`; post-dispatch failures retain
uncertainty feedback and the prior-value recovery point.

## Limits and acceptance gates

- This enforces the evidenced menu contract. It neither reproduces nor explains
  the hardware lockup, and does not establish that valid requests cannot trigger
  a firmware defect. Issue #25 remains open.
- REST is not a device-side atomic compare-and-set transaction. Another client,
  the physical menu, or firmware may change values after the read. Core's local
  session gate cannot exclude those actors or make a POST atomically reversible.
- Unknown fields in a known LED store fail closed. Future renamed categories,
  cross-category dependencies, and indirect power selectors are not inferred to
  be LED modes. Broader hardware capability mapping remains Issue #24.
- Existing unrelated configuration writes remain available when fresh metadata
  validates them. Save to Flash remains its separate existing operation, persisting
  the running configuration including external changes; it does not use this
  per-edit dependency validator.
- Controller tests use inert GTK widgets. No real GTK rendering, physical C64U,
  package, hosted CI, or cross-platform acceptance is claimed.
- The earlier `issue25-led-safeguard` blanket-refusal checkout and its evidence
  remain untouched. This candidate is an independent checkout from the published
  baseline, not an integration or replacement of that workspace.

## Offline reproduction

From this checkout, run the focused suite:

```sh
PYTHONPATH=tests python3 -m unittest test_configuration_dependencies
```

Its fixtures reject Python socket connect/connect_ex/sendto/create_connection,
use injected synthetic transports, temporary preferences/history and inert GTK
widgets. The headless subprocess only imports Core/policy and checks that GI is
absent. The affected regression run also includes `test_configuration`,
`test_dependencies`, `test_backups`, `test_settings_safety`, `test_native_files`,
`test_core`, `test_api`, `test_c64_ai_launch`, `test_scheduler`, `test_recovery`,
and `test_ci_runner`, with the same socket guard installed around the full run.

CI registers the two new classes (20 Core tests, 10 UI tests); the source audit
checks inventory, not execution of all CI selections. Tests cover all category
modes and transitions, active/inactive field rules, both field/category orders,
valid mixed transitions, stale unedited controllers, malformed/unknown metadata,
case bypass, direct Core and public raw API, zero REST/history writes on refusal,
history on admitted dispatch, Restore/actual Undo/native previews, and existing
DHCP dependency semantics. See CURRENT-STATE for final test/review results.

Integration requires separate user approval after reviewing the exact diff,
source/target identities, ancestry, primary dirty files, and independent review
result. No staging, committing, pushing, publication, issue-state changes, or
physical acceptance are authorized by this implementation checkpoint.
