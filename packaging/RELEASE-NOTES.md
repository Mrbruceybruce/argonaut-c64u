# Argonaut 0.1.0 — Debian 13

First Debian package. Launch Argonaut from the application menu or run `argonaut`.
Existing preferences, connection profiles and recovery data remain in the user's XDG configuration directory. Passwords remain in Secret Service. Removing the package does not delete user data.

Validated by the user: file operations, removable drive selection, ROM selection, preview, favorites, reconnect, Flash configuration upload/preview, and Undo of an audio-volume change.

Known unresolved issue: the C64U froze following an Undo attempt involving SuperCPU Detect and audio volume. The cause is unconfirmed. Avoid changing SuperCPU Detect during normal use; audio-volume Undo subsequently passed. Recovery after that incident was delayed.

Network and firewall settings are not modified by installation. Streaming still needs Ethernet and the existing UDP firewall permissions. Use the OS to safely remove local media.

Argonaut is licensed under GPL-3.0-or-later. No C64 firmware or ROM images are included.
