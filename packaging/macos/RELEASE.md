> Historical 0.1.2 release record, including its fixed build run and platform
> limitations at that time. The one-off publisher has been retired. For current
> packages and procedures, see [release guidance](../../docs/RELEASING.md).

Argonaut for Apple Silicon Macs running macOS 15 or newer.

- **DMG**: open it and drag Argonaut into Applications.
- **ZIP**: extract it and move Argonaut.app from mac-package into Applications.

Python, GTK, and the media runtime are included. Profiles use `~/Library/Application Support/argonaut`; saved passwords use macOS Keychain when access is allowed.

The user verified launch, C64U connection, file upload/download, preview video/audio, and profile persistence on an Apple Silicon Mac. Automated unit tests, relocated app startup, and ad-hoc signature verification also passed.

These are the exact packages from successful build 34720749109, renamed for release without rebuilding. Their enclosed README still calls them test builds. They are ad-hoc signed, not Apple Developer ID signed or notarized. macOS may require the per-app **Open Anyway** option in Privacy & Security on first launch. Do not disable Gatekeeper globally.

Preview requires Ethernet on the C64U and inbound UDP 11000–11001 on the Mac. Connect by IP; automatic subnet suggestions and MAC fallback remain Linux-only. The previously reported SuperCPU Detect/Undo freeze remains unresolved.

GPL-3.0-or-later. Source and SHA256 checksums accompany the downloads. Debian and Windows packages remain available in the earlier releases.
