# Local development

Use `./run-development` from this checkout on Debian. The launcher uses system
Python and the GTK/media dependencies already installed with stable Argonaut.

Development has its own application ID and window title. About shows 1.5-dev
and the checkout commit (with -modified when changes exist). It stores preferences
in ~/.config/argonaut-development/config.json (or XDG_CONFIG_HOME), with separate
configuration history. Passwords are session-only; stable keyring entries are not
accessed. Profiles start empty; no stable settings are copied automatically.

Keep work on the development branch. Commit tested changes here; push/release
when ready. The argonaut-windows directory is legacy staging, not the active
checkout. GitHub Actions still builds Windows and Mac packages.

This separates app settings, not the connected C64U hardware or files: operations
in either app still affect the selected real device. Mount & Run and Send Text have passed initial hardware testing; the
current prerelease checklist is in DEVELOPMENT-TEST.md.

The Debian development package also includes the per-user C64 AI bridge
launcher and service unit. Test Lab can create its private pairing, start or
restart the service, and generate the matching C64 program without `petcat`.
Ollama and firewall configuration remain separate, visible prerequisites.
