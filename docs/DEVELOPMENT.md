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

### Hosted qualification exception — October 2026

P4-2 infrastructure is implemented and administratively accepted
with one unresolved GTK regression. Hosted GitHub Actions run
[39543869234](https://github.com/Mrbruceybruce/argonaut-c64u/actions/runs/39543869234)
at commit `7701e215951311579b3afbd3dd7bb8d00c826626`
completed six of seven jobs successfully.

Docker network isolation, nonroot execution, GTK initialization,
private D-Bus authentication, and independent container cleanup
were demonstrated. The GTK regression job executed 27 tests:
26 passed and one failed, with zero errors and zero skips.

The remaining failure is
`test_device_details_compact.GeometryAndKeyboard.test_narrow_controls_reachable_by_vertical_scroll`.
The requested dialog size was 520 × 480 pixels; the expected
maximum height was 500 pixels, but GTK allocated 578 pixels.
The failure occurred before subsequent scrolling and keyboard
reachability assertions could execute.

The investigation is deferred under
[Issue #18](https://github.com/Mrbruceybruce/argonaut-c64u/issues/18),
with [Issue #21](https://github.com/Mrbruceybruce/argonaut-c64u/issues/21)
referenced for the Game Library Settings component.

The workflow conclusion remains **FAILURE**. This administrative
deferral does not establish full hosted CI qualification, satisfy
the seven-job acceptance requirement, or authorize release
acceptance. Preserve the existing test, its 500-pixel assertion,
failure reporting, and diagnostic evidence.



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

The local `--isolation namespace` backend (the default) creates an unprivileged user/network namespace with the current
user mapped. `--keep-caps` retains capabilities only inside that new user namespace
long enough to enable loopback. Before Python runs, `setpriv` drops all capability
sets and enables no-new-privileges. Runtime verification requires a changed network
namespace, non-root UID, zero capabilities, only an active loopback interface,
loopback-only routes, and a successful local TCP exchange. No external probe is
sent. Native libraries and subprocesses inherit the network namespace. Each suite
uses a clean environment and temporary HOME/XDG directories, with no user profiles
or credentials. Xvfb disables TCP listening.

**Isolation is a hard gate:** failed Docker launch or isolation evidence on the actual
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


### Explicit Docker backend for hosted CI

The seven hosted job entries explicitly select `--isolation docker`; local runs
retain `--isolation namespace`. Neither backend falls back to the other.
**Hosted Docker compatibility remains unverified until an authorized hosted run
passes all seven entries.** Synthetic local contracts do not establish runtime
compatibility. Publication and dispatch are separate approvals.

`tests/ci/Dockerfile` installs dependencies on Ubuntu 24.04 only. The workflow
pulls the base, records its repository digest, substitutes that immutable digest
into the Dockerfile, and builds with the Dockerfile on stdin and no source context.
No application source is copied or executed during the build. `base-image.json`,
`built-image.json`, `image.json`, build logs and the image's full `dpkg-query -W`
inventory (`container-results/dependencies.txt`) record exact inputs and installed
versions. Versions are recorded rather than apt-pinned; a later build may differ.
The runner resolves the built tag to its immutable image ID before creating a
container. Host kernel, hosted image identifiers, Docker client/server versions
and daemon security configuration are retained in `environment.txt`.

For a Docker-equipped local host, build and run explicitly:

```sh
docker build --tag argonaut-ci:local - < tests/ci/Dockerfile
/usr/bin/python3 tests/run_ci_tests.py --isolation docker --suite python-unit --output ci-results/docker-unit
```

The launcher snapshots current **tracked regular files** into a temporary directory;
no `.git`, untracked fixtures, host profiles or credentials are included. Symlinks
and nonregular entries fail closed. Tracked edits are included so review builds
exercise the working tree. Commit the new Dockerfile only under separate publication
authorization; it is build input, not required in the mounted runtime snapshot.
Source is mounted read-only at `/source`; a fresh `container-results` directory is
mounted writable at `/results`. The container root is read-only with writable
private `/tmp` and Docker's private shared memory. No Docker socket, host devices,
host D-Bus, display sockets or credentials are mounted or passed in the environment.
The trusted host launcher and Docker daemon remain outside the test boundary.

The launcher generates minimal container-local `/etc/passwd` and `/etc/group`
files for the actual nonzero host UID/GID and mounts them read-only separately
from the tracked source snapshot. They contain only root and the `argonaut-ci`
runtime identity, with no login shell; no host account database is read or mounted.
IDs must be integers from 1 through 4294967294. This avoids missing-UID failures
in the private D-Bus daemon without image-specific UID assumptions or root startup.
Before preflight, `identity.json` records validated numeric and named passwd/group
lookups. GTK preflight also checks account resolution and asks the private session
bus to confirm its connection's Unix UID; failure blocks the suite. Docker runtime
and hosted acceptance of this correction remain unverified locally.

Creation requires `--network none`, the nonzero host UID/GID, `--cap-drop ALL`,
`--security-opt no-new-privileges=true` and `--init`. Default Docker seccomp and
AppArmor policies remain in place; no unconfined/privileged options are supplied.
Before application imports, the internal runner checks the actual host network
namespace differs, real/effective UID/GID match, all five capability sets are zero,
and NoNewPrivs is set. It inspects IPv4 and IPv6 addresses and every route table,
rejecting external destinations even via `lo`. Only `127.0.0.0/8` and `::1/128`
routes are allowed; an IPv6 loopback address is not required. Kernel route lookups
to documentation addresses must report unreachable without emitting packets.
A fresh Python child must inherit the same namespace, identity and restrictions.
Only the loopback TCP exchange sends traffic. `network.json` records this evidence.
GTK retains private Xvfb (`-nolisten tcp`), private D-Bus sessions and temporary
HOME/XDG directories; media retains real VP8/Vorbis/WebM preflight and tests.

A UUID container name is recorded before creation; the daemon ID is retained after
creation. Results live on the host, so partial JSON reports and logs survive removal.
On success, failure, timeout or TERM/INT, `finally` attempts a graceful ten-second
stop, force-removes the container, and positively verifies absence using a successful
daemon listing. Repeated TERM/INT cannot interrupt that cleanup. Any cleanup error
fails the suite, even if tests passed. `cleanup.json` and `docker-control.log` retain
evidence. An independent workflow `always()` step queries the unique job/attempt
label, stops/removes leftovers and verifies absence; its failures fail the job.
Artifact upload still runs afterward. Runner loss or forced cancellation can prevent
cleanup or upload; there is no claim that `always()` survives destruction of the host.

Review acceptance requires synthetic contracts in normal and optimized modes,
source inventory, and then separately authorized container/hosted validation:
all expected counts, zero skips/errors/failures, GTK/media preflight, network and
child evidence, retained partial reports, and verified removal after success,
failure, timeout and interruption. Privileged containers, host networking, socket
mounts, application-code edits or weaker isolation require stopping for approval.

Creation is marked pending on disk before the Docker command is attempted. Only a
validated container ID recorded on disk clears that marker. On interrupted,
timed-out or otherwise unconfirmed creation, cleanup polls the unique name ten
times with one-second delays and force-removes late arrivals, then performs the
normal stop/remove/absence checks. It still reports `creation_unresolved: true`
and fails: no finite observation window proves daemon-side creation cannot finish
later. The independent `always()` cleanup similarly retries the job label when
the pending marker remains, preserves that uncertainty, and fails the job.
Each Docker control command is flushed to the log before execution; timeout and
interruption retain captured stdout/stderr after killing and reaping the client.

Local signal tests deliver real SIGTERM and SIGINT through shell/Python supervisor
and child process chains, including repeated signals during cleanup. These prove
local process cleanup only. Synthetic Docker clients and mocked daemon responses
do not establish real Docker create/start/stop cancellation semantics or GitHub
runner cancellation grace periods. Real container and all seven hosted acceptance
runs remain unverified; SIGKILL, host loss and cancellation deadlines can prevent
cleanup and artifact retention.

## Linux package verification (P4-4)

`.github/workflows/linux-verification.yml` adds two independent hosted Ubuntu
24.04 jobs: `linux-build`, then `linux-package-smoke` on successful artifact
verification. Only explicit `workflow_dispatch` starts this workflow; pushes and
pull requests cannot start it. Dispatch requires separate execution approval and
uses the actual checkout SHA.
Neither job publishes a release. Existing P4-2 executions, P4-3 Markdown checks,
and the unresolved GTK geometry exception above remain unchanged.

The bounded contract in `tools/linux/contract.json` fixes Development version
`1.10~dev2` (`1.10-dev2`), the exact payload inventory, Debian control fields,
and the complete installed self-test ID set. Payload or test-ID changes require
reviewing this contract. The runner uses `git archive` of the verified HEAD,
rejects tracked changes, links and submodules, and excludes untracked fixtures
and Git metadata. It supplies the full source SHA and positive commit epoch to
the existing `packaging/build_deb.py`; it never stamps the checkout. Final archive
contents must match that builder's staging output byte for byte, alongside the
independent inventory, control, metadata, path, ownership, mode and epoch checks.
No maintainer scripts, links, extra control files or unresolved unit placeholders
are accepted. Build evidence is embedded; every payload hash is retained.

Dependency-only images are acquired before isolation, using a recorded Ubuntu
base digest. Separate build and runtime targets record installed apt versions.
Build code runs nonroot with no network, read-only source/root, no capabilities,
no-new-privileges, two CPUs, 2 GiB memory, 256 processes and a 512 MiB temporary
filesystem. Only evidence/output is writable outside temporary storage. The
runtime has no application source mount, host sockets or passed-through devices.
Root is confined to disposable install/reinstall/removal containers with narrowly
limited filesystem capabilities. Services and timers are never enabled or started.

The smoke job downloads only the verified package, verification manifest and
checksum file. The build job passes the manifest SHA-256 separately as a job
output; the smoke job verifies it, the source SHA, package checksum and complete
archive before installation. It installs and reinstalls those exact bytes,
checks installed hashes/identity, then runs the installed launcher with private
HOME/XDG directories, Xvfb without TCP, and a private D-Bus session. GTK, Secret,
GStreamer and GstPbutils preflight checks use only the runtime dependency closure;
`gir1.2-gst-plugins-base-1.0` is declared in shared Stable/Development Depends,
the runtime image and the exact contract. Runtime image build arguments map the
host UID/GID to the container runtime account, reusing an existing group ID and
replacing an existing user at that UID. Preflight checks numeric and named account
resolution and the private bus connection authenticated UID before GTK testing.
Identity, D-Bus, typelib, GTK and factory results/errors are persisted incrementally.
Missing dependencies fail instead of silently expanding that closure. Preflight
and the existing `--self-test` share a 180-second deadline. Every expected ID must
appear exactly once and pass. Removal runs after a smoke failure only when daemon
container termination is verified, and checks
payload removal and retention of a synthetic Development configuration marker.
This is not a real-user upgrade or configuration migration test.

The host supervisor bounds commands, records container names before creation,
kills timed-out child process groups, then bounds daemon stop/kill and inspects
container state before proceeding. Unverified termination skips removal testing;
termination errors and final state are retained. Global cleanup removes all
job-labelled containers and reports cleanup errors.
An independent `always()` cleanup repeats the absence check. Pending creation,
OOM, nonzero exit, timeout, malformed/missing reports and cleanup failures fail
closed. Evidence includes stage status, logs, container state, cleanup history,
source SHA/epoch, base/built/installed image identities, dependency inventories,
GTK/media versions and factories, the verified package and SHA-256 records.
Artifacts are retained for 14 days, including available failure evidence. Runner
loss or cancellation can still prevent final cleanup or artifact upload.

Static/synthetic validation requires no Docker, packages, GUI or device access:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_debian_packaging.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/linux -p test_verify.py
PYTHONDONTWRITEBYTECODE=1 python3 -O -m unittest discover -s tools/linux -p test_verify.py
```

Actual image/package builds, installations and hosted execution need separate
approval. After approval, use a committed candidate in a disposable checkout and
a fresh output directory; `python3 tools/linux/run.py --help` lists the bounded
build/smoke/cleanup interfaces. Internal child phases are not isolation entry
points. Local unstaged implementation files are intentionally absent from a Git
archive and do not establish candidate qualification.

Implementation and synthetic passes are not hosted acceptance. Both jobs must
pass on the exact candidate, including artifact transfer, isolation and cleanup;
failure/timeout/interruption paths also need hosted qualification. Ubuntu success
does not qualify Debian 13, physical C64U hardware, streaming, Windows/macOS or
release acceptance, and cannot close the documented GTK geometry failure.
