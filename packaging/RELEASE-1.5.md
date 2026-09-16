# Argonaut 1.5

Stable release promoted from dev.3 after user testing on Debian, Windows portable, Apple Silicon, and Intel Mac. All reported testing is complete.

- Preferences now contains General, scrollable Device details, and About. Close handles unsaved edits with Save, Discard, or Keep editing.
- Device discovery retries its broadcast, verifies saved addresses, and filters unrelated password-protected web servers. The reported scan problem was resolved in testing.
- Preview scaling uses minus/plus buttons and a percentage label, with 100-300% limits and scrolling for larger previews.
- Enter sends text to the C64 BASIC prompt. Mount & Run starts a selected D64 using DMA network service.
- Saved preferences include capture folders, preview defaults, and remembered file locations. Serial number and shipping-box model are saved per profile; the firmware model remains read-only.
- Mac Quit and Cmd-Q support are included. About consistently identifies the version and build.

Downloads: Debian .deb; Windows Setup.exe or Portable.zip; macOS Apple Silicon or Intel DMG/ZIP. Mac packages require macOS 15 or newer. Windows packages are unsigned; Mac apps are ad-hoc signed, not Apple-notarized.

This is version 1.5, following 0.1.4. Stable and development settings remain separate. Existing stable profiles are preserved on upgrade. To reuse development settings, close both applications and copy config.json from the argonaut-development folder to argonaut, backing up the stable file first. In Windows portable packages these folders are inside Data; on Debian they are under ~/.config; on Mac under ~/Library/Application Support. Development session passwords must be entered again.

Known limitation: Windows multiple-instance behavior remains under review. Avoid simultaneous operations from multiple clients against the same C64U.

Please report issues with the platform and version/build shown in Preferences > About. Updated screenshots will follow.
