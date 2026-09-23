> Historical early Windows release record. Validation and platform limitations
> below describe that release, not current support. The old 0.1.4 builder has
> been retired; see [release guidance](../../docs/RELEASING.md).

Windows downloads for Argonaut, licensed under GPL-3.0-or-later.

- **Setup.exe**: per-user installation, Start-menu shortcut, optional desktop shortcut, and Windows uninstall support. Profiles use `%APPDATA%\argonaut`; passwords use Windows Credential Manager. Uninstall preserves profiles and saved credentials.
- **Portable.zip**: extract the entire ZIP into a writable folder or thumb drive and run `Argonaut.exe`. Keep `portable.flag` and `_internal` beside it. Settings travel in `Data\argonaut`; passwords are session-only. Preserve `Data` when updating.

Both include Python, GTK and the media libraries. No separate runtime installation is needed. Windows 10/11 x64 is the test target. These downloads are unsigned.

The earlier Windows test build was verified by the user in a VM: launch, connection, file transfers, preview video/audio and profile persistence. This build adds automated tests for portable preferences, packaged startup, installation, shortcuts and uninstall. Real-device testing of the new installer and portable mode is still welcome.

For a VM, use bridged networking and connect by LAN IP. Preview requires Ethernet on the C64U and inbound UDP 11000–11001 on Windows. Firewall rules are not changed automatically.

Known limitations: subnet suggestions and MAC fallback remain Linux-only; use manual IP/subnet entry and the C64U Default unique ID. Screenshot/recording destinations are absolute paths and may need reselecting after a drive-letter change. Refresh rescans local drives. The previously reported SuperCPU Detect/Undo freeze remains unresolved; avoid changing that hardware setting during normal use.

Source and SHA256 checksums accompany the downloads. The Debian 0.1.0 package remains available in the earlier release.
