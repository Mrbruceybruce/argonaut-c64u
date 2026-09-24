# Running and building on macOS

The published 1.8 release has separate Apple Silicon and Intel packages for
macOS 15 or newer. Hosted build checks do not replace physical Mac acceptance
for the next release. Earlier macOS versions are not validated.

## Run from source

Install Homebrew and Apple's Command Line Tools first (see https://brew.sh).
Use a native terminal and native Homebrew for your processor. From the repository root:

```sh
brew install python@3.13 pygobject3 gtk4 gstreamer adwaita-icon-theme
"$(brew --prefix python@3.13)/bin/python3.13" -m venv --system-site-packages .venv
.venv/bin/python -m pip install keyring
.venv/bin/python -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Gst', '1.0'); from gi.repository import Gtk, Gst"
.venv/bin/python -m c64u_browser.gui
```

Use that Python interpreter throughout: a different Python may not find Homebrew's
PyGObject (`gi`). Homebrew availability changes; Intel installations may need to
compile dependencies, which can take considerable time. If installation fails,
report the failing command and its error rather than continuing.

## Build an application bundle

Build from the intended source revision and record its commit. The example below
labels the bundle 1.8; choose a version that matches your source and release plan.
See [build and release guidance](RELEASING.md) before preparing a candidate.

```sh
.venv/bin/python -m pip install pyinstaller
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python packaging/build_metadata.py --version 1.8
.venv/bin/python -m PyInstaller --noconfirm --clean packaging/macos/argonaut.spec
open dist/Argonaut.app
```

The spec selects the running Python's architecture: x86_64 on Intel, arm64 on Apple
Silicon. Python and all native dependencies must match. It is not a universal app.
PyInstaller bundles the runtime; recipients do not need Homebrew or Python.
The app is ad-hoc signed, not Developer ID signed or notarized.

The macOS jobs in `.github/workflows/stable-1.8.yml` and
`development-packages.yml` create DMG/ZIP packages for both architectures and
check relocated packaged startup and signatures. Both resolve source from
`development`, regardless of the dispatch branch, and retain their existing
1.8 / 1.8-replay.3 versions. Keep publishing off; these are not 1.9 workflows.
The separate 0.1.4 Mac builders and one-off publishers have been retired.
Passing unit tests alone does not demonstrate that the graphical app launches.

## Intel tester checklist

Record Mac model, macOS version, and the build shown in About. Test launch first,
then connect to the C64U, upload/download a disposable file, preview video/audio,
and restart to check saved profiles. C64U preview requires Ethernet and incoming
UDP ports 11000–11001 on the Mac. Report exact errors and the last successful step.
