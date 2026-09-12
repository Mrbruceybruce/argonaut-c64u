Argonaut macOS test build — Apple Silicon, macOS 15 or newer

Open the DMG and drag Argonaut into Applications, then launch it there.
The ZIP contains the same app. Do not run directly from the read-only DMG.
Python, GTK, and the media runtime are bundled.

This is an ad-hoc-signed test build, not Apple Developer ID signed or notarized.
macOS may block its first launch. Only for this trusted download, use the
per-app Open Anyway option in System Settings > Privacy & Security if offered.
Do not disable Gatekeeper globally.

Profiles: ~/Library/Application Support/argonaut
Saved passwords: macOS Keychain, when access is allowed.
Removing the app preserves profiles and credentials.

Enable REST and FTP on the C64U, and enter its IP in Connections.
Preview requires Ethernet on the C64U and incoming UDP 11000–11001 on the Mac.
Automatic subnet suggestions and MAC fallback currently remain Linux-only.

Testing needed on a physical Mac: launch, connect, upload/download, preview
video/audio, screenshot, profile and Keychain persistence, and removable drives.
The previously reported SuperCPU Detect/Undo freeze remains unresolved.

Argonaut copyright (C) 2026 Bruce Marcus, GPL-3.0-or-later.
Source: https://github.com/Mrbruceybruce/argonaut-c64u
Runtime package versions and source metadata are included in Homebrew-packages.json.
