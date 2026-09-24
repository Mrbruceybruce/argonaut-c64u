# Local development

Argonaut follows the [server-first development policy](SERVER-FIRST.md):
Argonaut Core is the product, and every user interface is a client. This file
covers local checkout and release practices; architectural ownership and
boundaries are defined in that policy.

Use `./run-development` from this checkout on Debian. The launcher uses system
Python and the GTK/media dependencies already installed with stable Argonaut.

Development has its own application ID and window title. About shows 1.8-dev
and the checkout commit (with -modified when changes exist). It stores preferences
in ~/.config/argonaut-development/config.json (or XDG_CONFIG_HOME), with separate
configuration history. Passwords are session-only; stable keyring entries are not
accessed. Profiles start empty; no stable settings are copied automatically.

Keep work on the development branch. Commit tested changes here; push/release
when ready. The argonaut-windows directory is legacy staging, not the active
checkout. GitHub Actions still builds Windows and Mac packages.

Development is currently Linux-first. Complete implementation and hardware
validation on Linux, where the C64Us and local AI services are available. Build
and physically test Windows plus both Mac architectures at major-release
boundaries. Portable code and platform tests remain required throughout;
repeated desktop packaging is deferred until a major release is ready for
consolidated regression testing.

The current boundary is Stable 1.9. Feature implementation and Linux acceptance
are complete, and repository history has been reconciled. The unsigned private
qualification workflow is prepared; the consolidated platform gate is next and
has not yet been completed. The gate covers the server-first Core foundation,
USB/SD Backup & Restore, Game Library, SID Jukebox, and Bulk Import together. Cross-platform
qualification blocks Stable 1.9 publication; it does not require a separate
Windows/Mac physical cycle between those Linux-first feature sections. See the
authoritative sequence and retained implementation history in
[NEXT-PASS.md](NEXT-PASS.md).

This separates app settings, not the connected C64U hardware or files: operations
in either app still affect the selected real device. Mount & Run and Send Text have passed initial hardware testing; the
historical replay acceptance checklist is in [DEVELOPMENT-TEST.md](DEVELOPMENT-TEST.md).
It is not the 1.9 platform gate. See [build and release guidance](RELEASING.md)
for the unsigned qualification workflow and the remaining platform gate.

The Debian development package also includes the per-user C64 AI bridge
launcher and service unit. Test Lab can create its private pairing, start or
restart the service, and generate the matching C64 program without `petcat`.
Ollama and firewall configuration remain separate, visible prerequisites.
