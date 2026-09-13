Argonaut 0.1.4 brings the same tested application version to Debian, Windows, and Apple Silicon Mac.

## Downloads

- **Debian 13:** `argonaut-c64u_0.1.4_all.deb`
- **Windows 10/11 x64:** `Setup.exe` for installation, or `Portable.zip` for a writable folder/thumb drive.
- **Apple Silicon Mac, macOS 15+:** open the DMG and drag Argonaut into Applications, or extract the app ZIP.

## Changes

- New application icon on all three platforms.
- About button beside Connections, with the supplied artwork, selectable version and source-build identifier, copyright, GPL license, and project/guide links.
- Fix for Connections remaining on Working after its background worker shut down (#2): repeated activation presents the existing window, closing the main window exits the app, and task-submission errors restore the controls.

All three packages were tested by the user. Automated tests and packaged About/startup checks passed; Windows installation/uninstallation and portable settings checks, Mac signature/relocation checks, and Debian extracted-package checks also passed. These release downloads preserve the tested binaries. Some enclosed instructions still call the Mac package a test build.

Close Argonaut before upgrading. Existing profiles and preferences are preserved. For the Windows portable edition, preserve its Data folder and keep portable.flag beside the EXE; passwords are session-only.

Windows downloads are unsigned. The Mac app is ad-hoc signed and not Apple-notarized; macOS may require the per-app Open Anyway option in Privacy & Security. Preview requires wired Ethernet on the C64U and incoming UDP 11000–11001 on the computer. Automatic subnet suggestions and MAC fallback remain Linux-only.

The separate SuperCPU Detect/Undo hardware freeze remains unresolved (#1).

GPL-3.0-or-later. Source and SHA256 checksums accompany the downloads. See the [quick-start guide](https://github.com/Mrbruceybruce/argonaut-c64u/blob/main/docs/QUICK-START.md).
