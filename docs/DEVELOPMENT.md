# Local development

Use `./run-development` from this checkout on Debian. The launcher uses system
Python and the GTK/media dependencies already installed with stable Argonaut.

Development has its own application ID and window title. About shows 0.1.4-dev
and the checkout commit (with -modified when changes exist). It stores preferences
in ~/.config/argonaut-development/config.json (or XDG_CONFIG_HOME), with separate
configuration history. Passwords are session-only; stable keyring entries are not
accessed. Profiles start empty; no stable settings are copied automatically.

Keep work on the development branch. Commit tested changes here; push/release
when ready. The argonaut-windows directory is legacy staging, not the active
checkout. GitHub Actions still builds Windows and Mac packages.

This separates app settings, not the connected C64U hardware or files: operations
in either app still affect the selected real device. Mount & Run remains queued
in NEXT-PASS.md.
