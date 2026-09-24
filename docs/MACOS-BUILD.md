# Running and building on macOS

The currently published 1.8 release has separate Apple Silicon and Intel
packages for macOS 15 or newer. Stable 1.9 qualification targets the same two
native architectures. Hosted build checks do not replace physical Mac
acceptance. Earlier macOS versions are not validated.

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

## Build a Stable 1.9 application bundle

Build from the exact release commit using the native Python and Homebrew for the
target architecture. See [build and release guidance](RELEASING.md) before
preparing a qualification candidate.

```sh
.venv/bin/python -m pip install pyinstaller
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python packaging/build_metadata.py --release --version 1.9
.venv/bin/python -m PyInstaller --noconfirm --clean packaging/macos/argonaut.spec
open dist/Argonaut.app
```

The spec selects the running Python's architecture: x86_64 on Intel, arm64 on Apple
Silicon. Python and all native dependencies must match. It is not a universal app.
PyInstaller bundles the runtime; recipients do not need Homebrew or Python.

The macOS matrix in `.github/workflows/stable-1.9.yml` creates private DMG/ZIP
qualification packages for both architectures from one required commit. It
verifies the relocated app, final ZIP and final DMG and records build
dependencies. The app is ad-hoc signed, not Developer ID signed or notarized.
The workflow does not publish, notarize, staple, or use Developer ID credentials.
Passing automated package tests does not demonstrate physical C64U acceptance.

The older `stable-1.8.yml` and `development-packages.yml` retain their historical
or Development roles. The separate 0.1.4 Mac builders and one-off publishers
have been retired and are not current instructions.

## Intel tester checklist

Record Mac model, macOS version, and the build shown in About. Test launch first,
then connect to the C64U, upload/download a disposable file, preview video/audio,
and restart to check saved profiles. C64U preview requires Ethernet and incoming
UDP ports 11000–11001 on the Mac. Report exact errors and the last successful step.
