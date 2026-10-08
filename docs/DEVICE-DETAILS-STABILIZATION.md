# Device Details stabilization — implementation review

Status: **APPROVE COMMIT/PUSH — NOT EXECUTED**, 7 October 2026. Compact
re-review and bounded physical Development acceptance passed. No staging, commit,
push, package, release or next-roadmap work. Streaming P0 remains
**OPEN / intermittent / instrumented**; no streaming implementation changed.
The earlier implementation/review sections below retain their historical results;
the final acceptance section supersedes their pending gates and no-contact limits.

## Authority and starting changes

Repository: `/home/bruce/Documents/ChatGPT/Local Projects/argonaut-network-slice2`.
HEAD and local `origin/development` both
`17ad4e2bb7acd441560a3160fbcc224d13d30536`; parent R6
`f9457acd3bcef4269d9d98e95ef3c6dc33f90ff1`; subject
`Close FTP ownership compatibility paths`; divergence `0 0`. Detached HEAD is
unchanged. No fetch, branch creation or worktree creation.

Initial index empty. Starting dirt was exactly CURRENT-STATE +17 lines and the
new 375-line ARGONAUT-ROADMAP (392 additions). Both were read first and preserved.
Only narrow current-status additions and two investigation-table status updates
were made to the roadmap; historical decisions remain intact.

The initial read-only pass stopped over Windows metadata-only credential checks.
The user subsequently explicitly approved `CredReadW` followed by immediate
`CredFree`, with no blob dereference/materialization and only a boolean returned.
That clarified exception is implemented and tested; no other stop gate arose.

## Credential behavior matrix

| Operation/state | Before | Implemented |
| --- | --- | --- |
| Test with typed password | Authenticate, no persistence | Unchanged; no implicit save |
| Connect, Remember either way | Profile save; could persist a typed password when checked | Authenticate/connect and retain profile update, but never set or delete stored credentials; checked state is ignored by Core Connect |
| Save Profile, Remember ON, typed | Store entered credential without authentication | Save profile, then store/update the real typed password; no implicit authentication; offline/unverified edits remain intentional |
| Save Profile, Remember ON, blank | Preserve stored password | Unchanged; no mask, placeholder or session fallback is written as a password |
| Save Profile, Remember OFF | Preserve previously stored password | Save profile and delete persistent credential for the resulting exact profile ID; keep any current-process session password |
| Forget Password | Delete stored credential and Core session fallback; retain active connection/profile | Preserve that contract and immediately clear entry, saved indication and Remember state |
| Saved credential display | Blank entry, unchecked storage control | Exact ID/host/both ports checked through boolean existence API; fixed eight-bullet placeholder plus saved-state label; initially checked iff a stored credential exists |
| Typing / clearing replacement | Entered → session → stored resolution | Unchanged resolution; real typed text replaces indication, clearing returns to saved indication when present; placeholder is never entry content |
| Profile selection / successful dialog Connect | Clear entry and uncheck storage | Clear entry, then asynchronously reconstruct saved indication and Remember state |
| Development / Portable | Both session-only, misleading Portable label | Distinct exact mode text, hidden and disabled Remember/Forget controls; no native persistence access |
| Final Core close | Retained session dictionary not explicitly cleared | Clear dictionary in a finally block, including teardown failure; ordinary disconnect/reconnect retention unchanged |
| HTTP rejection | Safe visible HTTP 403 | Preserved |
| Connect status | Connected/Profile saved emphasis | Connected/authenticated first; profile update secondary, explicitly password storage unchanged |

Credential controls remain near Password; no broader profile-button relocation.
The old storage checkbox is replaced by `Remember password`; session modes use
`Development mode — passwords are session-only.` or
`Portable mode — passwords are session-only.` No Save Password button was added.

Existence checks are asynchronous and stale selection results are discarded.
Save Profile waits while the initial check is pending, preventing accidental
unchecked deletion during loading. Saved-state initialization does not itself
make the profile dirty. A canceled Preferences close keeps callbacks alive.

Rename retains profile ID. Host/port edits retain the existing new-ID behavior;
old credentials are not migrated or deleted. Ethernet/Wi-Fi profile identities
remain separate. Resolution still requires exact saved endpoint binding.

### Persistence failure boundary

Profile file and native credential store are independent resources, not an atomic
cross-store transaction. Profile writing occurs first: file failure leaves the
credential store untouched. A subsequent store failure reports **Profile saved,
but the password storage change failed**, never a successful password save.
The UI retains the typed edit and binds retry to the already saved profile ID.
No rollback that reads an old secret, silent migration or secret-bearing error
payload was added. After an unchecked save with no typed text, an already retained
session credential can still authenticate; Forget or final Core close clears it.

### Native existence privacy

- Linux: libsecret metadata search with `SearchFlags.NONE`; no unlock/load-secret
  flags or password lookup. [libsecret flags](https://gnome.pages.gitlab.gnome.org/libsecret/flags.SearchFlags.html).
- macOS: existing service/account matched using `SecKeychainFindGenericPassword`,
  with all password-length/data/item output pointers NULL. Apple's implementation
  reads password data only when length or data is requested.
  [Apple Security source](https://github.com/apple-oss-distributions/Security/blob/main/OSX/libsecurity_keychain/lib/SecKeychain.cpp).
- Windows: approved `CredReadW` opaque-buffer check; true on success, false only
  for not-found, sanitized error otherwise; `CredFree` in finally. No `.contents`,
  blob access, `string_at` or decoding in exists. Only boolean crosses the backend.
  [Win32 API](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credreadw).

## Discovery trace and implemented UI

Old Scan again invokes Core normal discovery: nonce-checked Ultimate Ident UDP
broadcasts to port 64 with replies on 64640; saved-profile addresses; Avahi mDNS;
direct mDNS queries; SSDP; then credential-free REST verification with eight
workers. The same mechanism is now labeled **Discover**, with indeterminate
progress. It does not automatically run a subnet scan. Results remain batched
for this normal mechanism; no broader callback redesign was introduced.

Explicit **Scan Subnet** uses the existing local IPv4 host enumeration, TCP port
80 probe (0.25-second connect timeout), then credential-free REST verification
(existing two-second client timeout), with eight workers. Progress now counts
completed probes, including failures, and candidates are delivered incrementally.
The callbacks return through GLib to GTK; network work remains on worker threads.
No existing cancellation seam was present; no cancellation framework was added.

Normal discovery merges address/HTTP-port keys; results from distinct Ethernet
and Wi-Fi addresses stay separate even with one physical identity. Incremental
UI rows also merge by address/HTTP port. Completion says
`Search complete — N network connections found`, not physical device count.

Validation uses `ipaddress`, requires explicit IPv4 prefix notation and normalizes
host input: `192.168.68.42/24` becomes `192.168.68.0/24` at scan initiation.
Blank/incomplete/invalid CIDR, IPv6, public ranges, oversized ranges and networks
outside connected local interfaces disable Scan Subnet and display nonmodal
feedback. Core and scanner revalidate before any probes. There is no network
access on an invalid UI request.

The existing private-network check, connected-interface containment, maximum
1,024 addresses (/22 or smaller network), eight-worker limit and `hosts()` policy
are preserved. `/0` and `/21` are rejected. `/24` has 256 total addresses but
254 probes; `/31` and `/32` retain Python's two-/one-host policy. Progress uses
actual completed/total probes and reaches 100% on successful completion.

Existing reliable network enumeration and preferred-subnet selection are reused
asynchronously, initially and after normal discovery, only when the field is
empty. User edits are never silently replaced. Network changes are checked again
at execution, so stale cached UI eligibility cannot authorize an out-of-scope scan.

Existing limitation retained: credential-free REST rejection can discard a subnet
candidate without an Ident advertisement. Normal Ident discovery can retain a
password-required advertisement as unverified. No authentication or broader probe
policy was added to discovery.

## Validation and accounting

Final results:

- Focused credential/Core/profile/discovery/platform/UI family: **107 passed**.
- Full normal suite: **1,225 run = 1,189 passed + 36 existing display skips**.
- Full optimized suite: **1,225 run = 1,189 passed + 36 existing display skips**.
- Offline Test Lab: **17/17 checks passed**, all simulation.
- Real GTK construction/state smoke: Installed, Development and Portable passed,
  with synthetic profiles, mocked stores/discovery and unshown windows. Exact
  labels, eligibility, fixed placeholder and session control visibility checked.
- Syntax, tracked/untracked whitespace, existence-method privacy and scope checks
  passed. No old named test method was removed or renamed; no new skip was added.

There are **38 new tests** in test_device_details.py. Existing modules discover
1,187 tests at this checkout; the historical closure document reports 1,177.
The current total is 1,187 + 38, not an assumed 1,177 baseline. Two existing macOS
fixtures now mock the metadata existence seam rather than secret lookup.

Focused command:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python3 -m unittest test_device_details test_core test_connections test_package_credential_channel test_app_lifecycle test_platform_support test_local_networks test_network_identity test_macos_support test_development
```

Full commands used `PYTHONDONTWRITEBYTECODE=1` and a temporary audit-hook guard on
PYTHONPATH to permit loopback fixtures and block external DNS/non-loopback socket
connect/sendto. No guard change was made to repository code.

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -O -m unittest discover -s tests -p 'test_*.py'
python3 -m c64u_browser.test_lab --suite offline
```

Earlier iterations exposed a synthetic test result error, an incorrectly named
platform test module, two macOS fixtures needing the new seam, and a real GTK
PasswordEntry setter mismatch. These were corrected; later review added
partial-save retry and canceled-close regressions. Final suites run the corrected
code. No failures were hidden with skips or removed tests.

## Changed files and review limits

Production: connection_dialog.py, core.py, credentials.py, discovery.py,
macos_credentials.py, windows_credentials.py (all under c64u_browser/).
Tests: new tests/test_device_details.py; adjusted tests/test_macos_support.py.
Docs: narrow updates to CURRENT-STATE.md and the pending ARGONAUT-ROADMAP.md;
this implementation record. No streaming, header, Machine, Files, Drives,
Streams or Ultimate Menu redesign, profile/keyring migration, or packaging.

No native keyring secret was read, set or deleted during validation. Native calls
were simulated; Windows/macOS real-store acceptance is not claimed. No C64U was
contacted and no physical subnet scan was run. A small physical UX acceptance
and platform-native store check may be useful **after review and separate
approval**, but are not prerequisites for this deterministic review verdict.

No unresolved implementation blocker. Review limitations: non-atomic profile/
store resources as above, preserved credential-free discovery limitation, and
unperformed live native-store/device acceptance. **Stop for review.**


## Review correction — unknown credential state (7 October 2026)

The compact review found a publication blocker: a failed existence lookup cleared
pending state but left Remember unchecked. A later Save could therefore delete
an existing credential after the backend recovered, without a deliberate choice.
This correction supersedes the earlier no-unresolved-blocker statement; the
publication review gate remains pending, with no physical acceptance authorized
by this correction pass.

The dialog now explicitly tracks UNKNOWN / PRESENT / ABSENT. UNKNOWN is shown
with a disabled, indeterminate Remember checkbox and safe status text; it blocks
Save Profile before any profile or credential persistence. Typed password and
profile edits remain intact. Retry credential check performs only a new metadata
lookup. True restores PRESENT and checked Remember; false restores ABSENT and
unchecked Remember. The fixed eight-bullet placeholder appears only for PRESENT
with an empty entry. Neither retry outcome replays Save; the user must click Save
again. Explicit Forget retains its deletion semantics and establishes ABSENT on
success. Development/Portable remain session-only and bypass this persistence gate.

Correction files: c64u_browser/connection_dialog.py, tests/test_device_details.py,
this report, and docs/CURRENT-STATE.md. Existing roadmap content is unchanged.
Core, native credential backends (including Windows opaque-buffer existence),
Discover/Scan Subnet and streaming implementation are unchanged by the correction.

Verification: both new deterministic failure → blocked Save → retry regressions
passed, covering PRESENT and ABSENT. They assert zero profile-save/set/delete
calls while UNKNOWN regardless of checkbox value, retained edits, no replay,
and deliberate subsequent Save behavior. The focused command above now passes
**109 tests**; test_device_details.py now contains **40 tests** (38 prior + 2).
Existing mask, Windows opaque-buffer, session-mode, connection and partial-save
checks passed in that run. Privacy/syntax/whitespace and correction-scope checks
passed. No real credentials/keyrings or C64Us were accessed. Broad normal/optimized
and Offline Test Lab results above are retained historical evidence, not rerun
results for this correction. No staging, commit, push, packaging or publication.
Streaming P0 remains OPEN / intermittent / instrumented. **Stop for re-review.**


## Publication gate — re-review and bounded physical acceptance (7 October 2026)

The compact re-review independently confirmed the explicit UNKNOWN guard before
Save Profile submits persistence, regardless of checkbox value; retained edits;
authoritative PRESENT/ABSENT retry with no Save replay; deliberate Forget;
placeholder/input separation; Development/Portable isolation; Windows opaque-buffer
existence; Test/Connect nonpersistence; HTTP 403 visibility; and final Core session
clearing. Both new regressions assert zero profile-save/set/delete calls while
UNKNOWN, preserve edits and exercise both retry outcomes. All **109 focused tests
passed again**. No broad normal/optimized suite or Offline Test Lab rerun.

The installed Debian package still contains the baseline implementation. The user
explicitly authorized the current worktree's supported `./run-development` entry
point for this acceptance. The actual runtime imported this checkout, reported
application ID `org.local.Argonaut.Development`, window title `Argonaut Development`,
version `1.9-dev` and build `17ad4e2bb7ac-modified`, and used the existing
`~/.config/argonaut-development/config.json`. This is source-worktree qualification
under the installed package's Development isolation semantics, not qualification
of a rebuilt package. No package was built or replaced.

An external temporary observer drove real GTK dialog methods on the desktop and
read safe widget/progress state; passwords were entered locally by the user and
were never printed or written by the observer. This is automated, user-assisted
physical qualification, not an independent visual-layout sign-off or packet capture.
No production/test code was changed for acceptance.

| Check | Observed evidence |
| --- | --- |
| Development isolation | Exact `Development mode — passwords are session-only.` text; Remember and Forget hidden and disabled. Session credential backend selected; zero calls to its exists/get/set/delete methods across the observed checks, and no native keyring access. |
| Initial Beige connection | Existing profile at `192.168.68.70`; successful Connect and Test status identified `25EA78`, hostname `C64-Ultimate-7F01C9`, firmware `1.1.0s2`, API `0.1`. Beige also accepted credential-free discovery, so authentication rejection was qualified on Founder instead. |
| Founder typed-password Test | Existing bound profile at `192.168.68.69`; valid typed input produced Success for `25BE71`, hostname `C64-Ultimate-2B02C3`, firmware `1.1.0`, API `0.1`. No session password was retained by Test. |
| Founder Connect | Identity reverified through the normal Core path; successful connection retained one session password. Status was `Connected · Authenticated. Connection profile updated; password storage unchanged.` No credential persistence. |
| Wrong password, once | Founder Test displayed `Authentication failure: REST authentication failed (HTTP 403).` Preferences file hash unchanged; no credential-store calls. Valid typed input was restored and Test succeeded again before cleanup. |
| Restart / exit | Normal close cleared Core's session dictionary. A fresh Development process had an empty entry and zero session passwords; no credential-store calls. The final process then closed normally. |
| Discover, once | Button is `Discover`. Completion reported `2 network connections found`: verified Beige `.70:80`; Founder `.69:80` via Ultimate Ident, explicitly password-required / identity-unverified at discovery. Founder identity was subsequently authenticated above. |
| Invalid subnet | Blank, incomplete address and incomplete prefix kept Scan Subnet disabled; attempts started no scan. |
| Connected network / bounded scan | Host `br0` was `192.168.68.80/22`, connected network `192.168.68.0/22`. The authorized `192.168.68.0/24` is contained within it; entering that CIDR enabled Scan Subnet. Exactly one /24 scan ran. |
| Progress / results | Actual denominator was 254 hosts; sampled UI progress advanced from `1/254` through `251/254` to completed 100%. Completion reported `1 network connections found`, verified Beige `.70:80`. GTK observer ticks continued during both searches; maximum observed tick gap across the first process, including startup, was 0.908 seconds. |

Founder is omitted by the subnet scan because it rejects credential-free REST
verification and that scan has no Ident advertisement fallback. Normal Discover
retains its password-required advertisement. This is the already-reviewed discovery
limitation, not a claim that one physical C64U exists or that Founder is unreachable.
No extra scan, expanded range or device authentication-policy change was attempted.

The initial user-assisted device selection did not match the observed target; no
Founder success was inferred from that report. A normal restart explicitly selected
Founder, and the observer verified `.69` and authenticated identity `25BE71` before
accepting its credential checks. No secrets entered the evidence or repository.

Cleanup completed with no running acceptance GUI, scan or worker process. No
Save Profile/Delete Profile action, device configuration/storage/power mutation,
streaming investigation or next-roadmap work occurred. Connect retained its normal
Development profile update, and normal app closure retained ordinary preferences
behavior. Streaming remains **OPEN / intermittent / instrumented**.

Live installed native Secret Service/macOS/Windows credential-store persistence
remains untested by design and belongs to later packaging/release acceptance.
Deterministic backend evidence and this Development acceptance satisfy this gate.

Publication scope is six production files, two test files and three documentation
files. Include the previously pending roadmap consolidation as reviewed product
planning documentation, together with its narrow implemented-state updates; its
historical sections do not claim implementation of other roadmap items. One coherent
commit is recommended: `Stabilize Device Details credentials and discovery`.
The index remains empty; no commit/push/tag/package/release has been performed.
