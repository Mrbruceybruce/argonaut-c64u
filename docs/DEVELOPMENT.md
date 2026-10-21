# Local development

Argonaut follows the [server-first development policy](SERVER-FIRST.md):
Argonaut Core is the product, and every user interface is a client. This file
covers local checkout and release practices; architectural ownership and
boundaries are defined in that policy.

Use `./run-development` from this checkout on Debian. The launcher uses system
Python and the GTK/media dependencies already installed with stable Argonaut.

Development has its own application ID and window title. About shows 1.10-dev
and the checkout commit (with -modified when changes exist). It stores preferences
in ~/.config/argonaut-development/config.json (or XDG_CONFIG_HOME), with separate
configuration history. Passwords are session-only; stable keyring entries are not
accessed. Profiles start empty; no stable settings are copied automatically.

Keep work on the development branch. Commit tested changes here; push/release
when ready. The argonaut-windows directory is legacy staging, not the active
checkout. The retained shared packaging workflow is historical; do not use or dispatch it
as the current 1.10 packaging procedure.

Development is currently Linux-first. Complete implementation and hardware
validation on Linux, where the C64Us and local AI services are available. Build
and physically test Windows plus both Mac architectures at major-release
boundaries. Portable code and platform tests remain required throughout;
repeated desktop packaging is deferred until a major release is ready for
consolidated regression testing.

Stable 1.9 is published and immutable. Current development follows the 1.10
roadmap in [CURRENT-STATE.md](CURRENT-STATE.md) and [ARGONAUT-ROADMAP.md](ARGONAUT-ROADMAP.md).
The next local Debian Development package is `1.10~dev2`, displaying `1.10-dev2`.
Use the [authoritative local build procedure](RELEASING.md#local-debian-development-build)
only at its separately approved package acceptance gate. Public Stable 1.10 and
cross-platform packaging/qualification remain future work. Shared source Development
identity is now `1.10-dev` on all platforms; Windows/macOS packaging is unchanged.

This separates app settings, not the connected C64U hardware or files: operations
in either app still affect the selected real device. Mount & Run and Send Text have passed initial hardware testing; the
historical replay acceptance checklist is in [DEVELOPMENT-TEST.md](DEVELOPMENT-TEST.md).
It is historical evidence, not current package acceptance guidance. See
[build and release guidance](RELEASING.md) for current channel boundaries.

The Debian development package also includes the per-user C64 AI bridge
launcher and service unit. Test Lab can create its private pairing, start or
restart the service, and generate the matching C64 program without `petcat`.
Ollama and firewall configuration remain separate, visible prerequisites.

## Bounded offline CI (P4-2)

`.github/workflows/test-lab.yml` retains pushes and pull requests targeting
`development` and manual dispatch. It runs only on GitHub-hosted `ubuntu-24.04`;
there is no publishing, hardware input, live Test Lab, device discovery, local AI
service, physical C64U, or self-hosted execution. Packaging workflows are separate.

`tests/ci_suites.json` is the reviewed execution allowlist. Each selector names a
single unittest class, its expected test count, audit rationale and timeout. The
runner never discovers tests for execution. Source-only inventory checks reject
missing/duplicate selectors, changed counts, and new/unaccounted test modules,
classes in selected modules, or standalone GTK scripts. Expanding coverage requires
reviewing imports, fixtures, transport calls, subprocesses and budgets, then editing
the manifest. Both synchronous and async test methods are counted.
Conditional/nested test classes or methods and duplicate definitions fail inventory audit. Direct
TestCase subclasses without local methods also require accounting; static counts
do not expand inherited methods or discover dynamically generated tests.
Helper-only classes are not selectors. Deferred modules, classes and
all 26 standalone GTK scripts have explicit reasons in the manifest and are copied
to every `coverage.json`. Deferred counts are static source method counts, not a
claim that those tests have been loaded or qualified.

The initial selection covers SID/settings/jobs/version, mocked media and streaming,
parser and mocked hardware checks; tracked VICE D64/D71/D81 read/edit regressions;
import planning/transaction/policy/execution; and loopback FTP reads/uploads/
replacements. `test_media.MediaTests` is mocked REST, while
`test_replay_buffer.ReplayBufferTests` really encodes and exports WebM. Native GTK
covers Device Details and compatibility presentation. `PreferencesUI` is used as
a fixture by selected GTK tests; its own test suite remains deferred. Runner
contract tests use synthetic children to check failures, skips, zero tests,
selector errors, timeout tracebacks, partial reports and descendant cleanup.

| Job | Suite execution budget | Job limit | Modes |
| --- | ---: | ---: | --- |
| offline-checks | 120 seconds | 10 minutes | normal |
| python-unit | 300 seconds | 15 minutes per entry | normal / optimized |
| python-regression | 600 seconds | 20 minutes per entry | normal / optimized |
| media-regression | 180 seconds | 12 minutes | normal |
| gtk-regression | 300 seconds | 15 minutes | normal |

The Python matrices use `fail-fast: false`. Every class gets a fresh child process
and process group: 120 seconds by default, 180 for media/GTK, capped by the remaining
suite budget (including preflight). GTK remains unoptimized because its input
fixtures contain ordinary assertions. Each GTK class and its preflight also get
a private Xvfb display and D-Bus session. Timeouts request Python tracebacks only
from group members with a registered SIGUSR1 handler, then send TERM and KILL to the entire class group; surviving
descendants are cleaned up on successful exit too. Supervisors adopt orphaned
descendants and reap the terminated group. The outer timeout sends TERM to the
namespace supervisor, whose interruption handler cleans its active nested group;
it allows five seconds for that cleanup before escalating. Repeated TERM/INT
signals cannot interrupt cleanup. Children must not detach into new sessions. The outer
namespace launcher has a further 45-second setup/cleanup allowance. Job limits
leave time for apt setup and artifact upload; cancellation or runner loss may
still prevent diagnostics from uploading.

Install dependencies before isolation, using system Python for apt GI bindings:

```sh
sudo apt-get update
sudo apt-get install -y python3-gi gir1.2-gtk-4.0 gir1.2-secret-1 \
  gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-tools iproute2 util-linux \
  xvfb xauth dbus-x11 libxtst6 fonts-dejavu-core
```

From a disposable checkout containing tracked files only, use:

```sh
/usr/bin/python3 tests/run_ci_tests.py --audit --output ci-results/audit
/usr/bin/python3 tests/run_ci_tests.py --suite offline-checks --output ci-results/offline
/usr/bin/python3 tests/run_ci_tests.py --suite python-unit --output ci-results/unit
/usr/bin/python3 tests/run_ci_tests.py --suite python-unit --optimized --output ci-results/unit-O
/usr/bin/python3 tests/run_ci_tests.py --suite python-regression --output ci-results/regression
/usr/bin/python3 tests/run_ci_tests.py --suite python-regression --optimized --output ci-results/regression-O
/usr/bin/python3 tests/run_ci_tests.py --suite media-regression --output ci-results/media
/usr/bin/python3 tests/run_ci_tests.py --suite gtk-regression --output ci-results/gtk
```

Use a fresh output directory for each validation. `--audit` only reads source.
Internal child/preflight switches are implementation interfaces, not substitutes
for the isolated suite entry points above. To validate only the synthetic runner
contracts without application or network activity:

```sh
PYTHONPATH=tests /usr/bin/python3 -m unittest test_ci_runner.RunnerTests
PYTHONPATH=tests /usr/bin/python3 -O -m unittest test_ci_runner.RunnerTests
```

The suite launcher creates an unprivileged user/network namespace with the current
user mapped. `--keep-caps` retains capabilities only inside that new user namespace
long enough to enable loopback. Before Python runs, `setpriv` drops all capability
sets and enables no-new-privileges. Runtime verification requires a changed network
namespace, non-root UID, zero capabilities, only an active loopback interface,
loopback-only routes, and a successful local TCP exchange. No external probe is
sent. Native libraries and subprocesses inherit the network namespace. Each suite
uses a clean environment and temporary HOME/XDG directories, with no user profiles
or credentials. Xvfb disables TCP listening.

**Isolation is a hard gate:** namespace or capability restrictions on the actual
GitHub-hosted image must fail the job before application tests run. Do not add
`sudo unshare`, privileged containers, host-network execution, or disable AppArmor/
sysctl restrictions as a fallback. Any such alternative requires separate review.
A local pass does not establish hosted compatibility; retain the first hosted
run's `network.json` and environment evidence after manual publication. Ubuntu's
[AppArmor policy](https://documentation.ubuntu.com/security/security-features/privilege-restriction/apparmor/)
can restrict unprivileged namespaces.

Media preflight checks GI/GstPbutils and the actual VP8/Vorbis, WebM and splitmux
factories. GTK preflight requires a working display, private session bus and XTest
library. Missing dependencies fail instead of skipping. Success requires every
selected class to finish with its expected nonzero test count, zero skips/errors/
failures and no expected failures; offline Test Lab also requires every check to
pass with exactly the identities enumerated in `offline_checks` (17 initially).
Missing, duplicate and unexpected definitions or returned identities fail. The CI
adapter uses the existing Test Lab per-check executor under the simulation origin,
writes an incomplete report before importing checks, and atomically persists each
start and result. A later hang retains completed results and the active check ID.
Environment versions, namespace evidence, verbose logs, incremental test
IDs/outcomes/tracebacks, class durations and partial JSON summaries are retained.
Workflow artifacts upload with `if: always()`, unique job/mode/attempt names and
14-day retention. The initial manifest is deliberately partial coverage, not
full-suite or physical-hardware acceptance.
