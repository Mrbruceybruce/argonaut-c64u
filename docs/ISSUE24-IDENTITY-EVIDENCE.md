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

## Two distinct Argonaut contracts

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
