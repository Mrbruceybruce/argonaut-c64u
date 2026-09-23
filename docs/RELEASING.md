# Build and release guidance

Stable downloads are on the [Releases page](https://github.com/Mrbruceybruce/argonaut-c64u/releases).
The current published baseline is [1.8](../packaging/RELEASE-1.8.md).
Historical test/RC Releases were intentionally removed during repository cleanup;
their tags and retained Actions evidence remain. Do not recreate those downloads.

## Remaining workflows

| Workflow | Purpose and current behavior |
| --- | --- |
| `test-lab.yml` | Regression checks on pushes and pull requests targeting `development`, plus manual dispatch. Runs offline Test Lab and unit tests; retains a report. |
| `development-packages.yml` | Builds Debian, Windows, and both Mac architectures from one resolved `development` commit. Still labels packages **1.8-replay.3**. Publishing is opt-in and defaults off. |
| `stable-1.8.yml` | Stable 1.8 packaging baseline for Debian, Windows, and both Mac architectures, with packaged self-tests and checksum generation for publishing. Builds one resolved `development` commit, regardless of the dispatch branch. Publishing is opt-in and defaults off. |

Workflow files are under `.github/workflows/`. Preserve these build and test
recipes while preparing the next platform gate. Neither packaging workflow is
configured for 1.9. Selecting a different dispatch branch does not change their
hard-coded `development` source selection. Keep `publish` **false** when using
the existing recipes for build checks: enabling it targets the existing v1.8
release or the removed v1.8-replay.3 test release.

## Preparing the Stable 1.9 platform gate

Before a 1.9 candidate is dispatched, review and explicitly configure its version,
source commit selection, expected package names, release notes, signing, and
publication target. That work is separate from this housekeeping pass. Record
the exact source commit used by every platform and confirm the package build
identity matches it. Do not label an arbitrary current checkout as an older
stable release merely because a builder has an old default version.

Use the retained regression and packaging checks, then record physical acceptance
on Debian, Windows, Apple Silicon, and Intel Mac. Hosted checks alone do not
establish physical acceptance. The historical replay checklist in
[DEVELOPMENT-TEST.md](DEVELOPMENT-TEST.md) is reference material, not a 1.9 gate.
Review the resulting packages and checksums before an explicitly approved
publication. No 1.9 signing or publication is configured by this cleanup.

For local builds, pass the intended version explicitly to
`packaging/build_deb.py --version VERSION` or
`packaging/build_metadata.py --version VERSION`. See the
[README](../README.md#build-and-test) and [macOS build guide](MACOS-BUILD.md).

## Retired manual recipes

The following workflows were removed from the current tree, with their history,
runs, artifacts, tags, and surviving release assets preserved:

- `publish-macos.yml`: fixed-run 0.1.2 publisher; the historical release exists.
- `publish-0.1.4.yml` and `finalize-0.1.4.yml`: fixed-run preparation/finalization
  for the already-published 0.1.4 release, including an obsolete latest-release update.
- `publish-intel-test.yml` and `publish-quit-test.yml`: fixed-source one-off test
  publishers that could recreate intentionally removed 0.1.4 test Releases.
- `macos-quit-test.yml`: fixed PR #3 source and in-job patches for the old Quit test.
- `macos.yml`, `macos-intel.yml`, and `windows.yml`: 0.1.4-only package recipes,
  superseded by the retained cross-platform workflows and packaged self-tests.
- `stable-1.5.yml` and `stable-1.6.yml`: fixed-version older stable/candidate
  recipes superseded by the 1.8 baseline. The 1.5 publisher runs unconditionally
  after its builds; 1.6 can publish an obsolete candidate version as stable.

Removing current workflow files does not erase copies in historical commits or
tags. Do not dispatch historical publishers. Versioned release notes and old
test records describe their original period, not current release instructions.
