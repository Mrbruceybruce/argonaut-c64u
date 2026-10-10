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
