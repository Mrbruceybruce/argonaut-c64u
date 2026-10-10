# Build and release guidance

Stable downloads are on the [Releases page](https://github.com/Mrbruceybruce/argonaut-c64u/releases).
The published Stable baseline is [1.9](../packaging/RELEASE-1.9.md); its tag and
release artifacts are immutable. Current development targets 1.10. No public
Stable 1.10 tag or release exists.

## Local Debian Development build

The following is the authoritative local build example, for the separately
approved B6 package acceptance after implementation review:

```sh
python3 packaging/build_deb.py --development --version '1.10~dev2' --output /tmp/argonaut-b6-dev2
```

This creates an `argonaut-c64u-development` package; it does not install or publish
it. Debian version ordering is `1.9 < 1.10~dev1 < 1.10~dev2 < 1.10`. Its application
menu/About version is `1.10-dev2`; source Development is `1.10-dev`. The packaged
build identity records the source commit, including `-modified` for pending changes.
Stable's version contract remains 1.9; `--development` does not itself select a
package version. Do not combine Development with Stable `--release` mode.

Development uses separate application, configuration and service identities,
session-only credentials, and no installed Stable keyring access. Notes deliberately
come from `packaging/RELEASE-DEVELOPMENT.md`; a missing file fails the build rather
than falling back to historical notes. The archive includes all normal application
modules and assets, including B4 SVG/attribution and B5 foreground/presenter modules.

At acceptance, inspect archive/control/desktop metadata, notes, modules and assets;
run the packaged self-test in an isolated Development context; then perform an
offline launch/About/status smoke check. Installation/upgrade needs separate approval.
Do not contact a C64U, start a stream, tag or publish. Public-release review of
Commodore branding remains pending. Streaming remains OPEN / intermittent /
instrumented; packaging acceptance does not qualify it.

The shared `development-packages.yml` still stamps `1.8-replay.3`, includes historical
notes, and has an optional publisher. It is **not** the current 1.10 procedure:
do not dispatch it for B6. Modernization is deferred to later release/automation
work, as are Windows/macOS packaging changes and 1.10 cross-platform qualification.

## Historical Stable 1.9 private qualification contract

The following records the qualification architecture used for the now-published
1.9 baseline. It is retained reference, not a new publication instruction.

Stable 1.9 uses `.github/workflows/stable-1.9.yml`. It builds all platforms from
one required full Git commit ID. The source job verifies that its checkout equals
that ID; every downstream job checks out the resolved ID, and
`build_metadata.py --release` rejects a metadata/checkout mismatch or dirty tree.

The workflow does not publish, tag, create a GitHub Release, or request signing
credentials. It produces private Actions artifacts for the consolidated platform
gate. For that process, final publication required separate approval after the exact
assembled bytes passed qualification. Rebuilding any payload
changes those bytes and requires renewed qualification.

`c64u_browser/release.py` is the authoritative Stable 1.9 contract:

- display, Debian, Windows product and macOS short version: `1.9`;
- Windows numeric file/product version: `1.9.0.0`;
- macOS bundle build version: `10900`;
- published tag: `v1.9`;
- notes: `packaging/RELEASE-1.9.md`;
- exact eight-payload allowlist used by final assembly.

Release-mode packaging fails rather than falling back to an older version,
unknown source fingerprint, mismatched SHA, dirty checkout, stale timestamp, or
missing 1.9 release notes. `SOURCE_DATE_EPOCH` is derived from the immutable
release commit.

### Unsigned qualification boundaries

Windows builds and verifies the PE version resource before PyInstaller. The
future Authenticode insertion point is after PE construction and verification
and before Setup and Portable containers are made. Stable 1.9 leaves this step
disabled and does not create a self-signed substitute. The final installer is
installed, self-tested, version-checked and uninstalled. The final Portable ZIP
is extracted and self-tested and must contain no generated `Data` directory.

Each native Mac build is explicitly ad-hoc signed after bundle creation. The
future Developer ID and notarization insertion point is that signing step,
before the ZIP and DMG are created. Stable 1.9 does not enable hardened runtime,
notarization or stapling. Both final containers are opened and their contained
apps are checked for architecture, versions, build identity, signature, and
external Homebrew/build-machine dependencies. Relocated startup runs with a
minimal environment.

Debian packages use the direct-download model. The build derives ownership and
timestamps deterministically, inspects final contents and permissions, installs
and reinstalls the package, runs the packaged GTK self-test, and removes it while
confirming user configuration is retained. The package is not signed and no APT
repository is created.

Each package embeds build evidence covering the runner/OS, Python, PyInstaller
where used, GTK/GLib/PyGObject, GStreamer, Inno Setup, Homebrew/MSYS2 packages,
and relevant container tools.

### Exact final assembly

The assembly job downloads the qualified platform outputs, creates
`argonaut-1.9-source.zip` directly from the same commit, and checks the exact set
of eight payloads. Only after that check succeeds does it write the authoritative
`SHA256SUMS`. Platform-local preliminary checksums are not release manifests.

Windows is intentionally unsigned. macOS is ad-hoc signed and not notarized.
The safe user instructions are in `packaging/RELEASE-1.9.md`; never advise users
to disable Gatekeeper globally.

## Other retained workflows

| Workflow | Purpose and current behavior |
| --- | --- |
| `test-lab.yml` | Regression checks on pushes and pull requests targeting `development`, plus manual dispatch. Runs offline Test Lab and unit tests; retains a report. |
| `development-packages.yml` | Builds Debian, Windows, and both Mac architectures from one resolved `development` commit. Historical `1.8-replay.3` recipe; deferred and not current 1.10 guidance. Do not dispatch for B6. |
| `stable-1.8.yml` | Historical Stable 1.8 packaging baseline. It is not a Stable 1.9 workflow. |

Selecting a different dispatch branch does not convert an older workflow into a
1.9 builder. Keep any legacy publishing input disabled; the 1.9 workflow has no
publication path.

The historical 1.9 gate required exact-artifact qualification and physical
acceptance on Debian, Windows, Apple Silicon and Intel Mac; hosted checks alone
did not establish physical acceptance. [DEVELOPMENT-TEST.md](DEVELOPMENT-TEST.md)
records the earlier replay test period and is not current 1.10 release guidance.

For current local Debian Development builds use the procedure above. Retained
Stable release-mode builders still require the exact clean source commit and
Stable 1.9 contract. The [macOS build guide](MACOS-BUILD.md) remains outside B6.

## Retired manual recipes

The following workflows were removed from the current tree, with their history,
runs, artifacts, tags, and surviving historical release assets preserved:

- `publish-macos.yml`: fixed-run 0.1.2 publisher.
- `publish-0.1.4.yml` and `finalize-0.1.4.yml`: fixed-run preparation/finalization
  for the already-published 0.1.4 release, including an obsolete latest-release update.
- `publish-intel-test.yml` and `publish-quit-test.yml`: fixed-source one-off test
  publishers that could recreate intentionally removed 0.1.4 test Releases.
- `macos-quit-test.yml`: fixed PR #3 source and in-job patches for the old Quit test.
- `macos.yml`, `macos-intel.yml`, and `windows.yml`: 0.1.4-only package recipes,
  superseded by the retained cross-platform workflows and packaged self-tests.
- `stable-1.5.yml` and `stable-1.6.yml`: fixed-version older stable/candidate
  recipes superseded by the 1.8 baseline. The 1.5 publisher ran unconditionally
  after its builds; 1.6 could publish an obsolete candidate version as stable.

Historical test/RC Releases were intentionally removed during repository cleanup;
their tags and retained Actions evidence remain. Do not recreate those downloads
or dispatch publishers from historical commits. Removing current workflow files
does not erase copies in historical commits or tags. Versioned release notes and
old test records describe their original period, not current release instructions.
