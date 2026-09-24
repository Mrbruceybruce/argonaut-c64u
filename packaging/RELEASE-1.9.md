# Argonaut 1.9

Argonaut 1.9 establishes the server-first Core boundary and adds USB/SD Backup
and Restore, the D64/CRT Game Library with reviewed Bulk Import, and SID
Jukebox. These features were implemented and physically accepted on Linux
before the consolidated desktop platform gate.

## Highlights

- Core-owned device sessions, scheduling, jobs, transfers, structured progress,
  cancellation, and confirmation-plan safety.
- Reviewed USB/SD backup and restore with complete manifests, staged uploads,
  atomic local publication, and conservative removable-volume verification.
- D64/CRT Game Library with favorites, notes, artwork references, source
  validation, Relink, reviewed launch, and bounded local/C64U Bulk Import.
- SID Jukebox with local and C64U sources, playlists, subtunes, multi-SID
  requirements, manual Previous/Next, and non-repeating Shuffle.
- Octet-preserving C64U filename identity for full-volume Game Launch and
  USB/SD safety checks.
- Test Lab, local/cloud failure analysis, unattended checks, disk-image tools,
  recording, and instant replay from earlier releases remain available.

Structural D64/CRT validation establishes image structure and content identity;
it does not prove that software boots or is playable. SID duration remains
unknown, so Stable 1.9 uses manual Next and does not guess or detect silence.

## Downloads and platform trust

The Windows Setup and Portable packages are intentionally **unsigned**. Windows
may show a reputation or publisher warning. Confirm that the file came from the
official Argonaut release and matches `SHA256SUMS` before choosing the normal
per-file option to continue.

The macOS Apple Silicon and Intel applications are ad-hoc signed and are **not
notarized**. After verifying the download checksum, move Argonaut to
Applications and try opening it normally. If macOS blocks it, use the per-app
**Open Anyway** control in **System Settings → Privacy & Security**. Do not
disable Gatekeeper globally.

Debian is distributed as a direct `.deb` download. Install it from its download
folder with:

```sh
sudo apt install ./argonaut-c64u_1.9_all.deb
```

Windows Authenticode and Apple Developer ID signing/notarization are deferred.
No signing certificate, Apple membership, or external signing service is needed
to build or qualify 1.9.

## Known constraints

- C64U preview and media workflows require Ethernet and local UDP access.
- The reported SuperCPU Detect/Undo freeze remains unresolved; avoid changing
  that setting during routine use.
- Physical platform qualification is recorded separately from automated package
  checks. Packaged self-tests do not replace real C64U media testing.

Argonaut is GPL-3.0-or-later. No Commodore ROMs or C64U firmware are included.
