# Argonaut 0.1.4-dev.2 — Development testing

This pass fixes Windows/macOS local network enumeration for discovery and adds:

- Preferences tabs: General, Connections, and Device details.
- Editable Serial number and Box model (the model checked on the shipping box), saved per connection profile. Existing Case edition text is preserved as Box model.
- C64U Model is read-only. Select the profile, then use Read model from C64U.
- Preview scale: 100–300% in 25% steps, with minus/plus buttons and a read-only value.
- General preferences save the default scale; Streams scale changes are session-only.
- Preview scrollbars appear when needed, without resizing the application window.
- Append Return is checked by default. Sending text with it checked executes the line.
- Preference checkboxes no longer toggle when clicking far beyond their labels.

Windows: extract the portable ZIP to a writable folder and run Argonaut.exe.
Mac: open the DMG and copy Argonaut Development.app to Applications, or extract
the ZIP. Apple Silicon and Intel packages require macOS 15 or newer. The Mac app
is ad-hoc signed, not notarized. If blocked, use System Settings → Privacy &
Security → Open Anyway.

Profiles and preferences remain separate from stable Argonaut. To retain Windows
development profiles, copy the existing Data folder into the newly extracted
portable folder. Mac uses the existing development preferences. Passwords remain
session-only. About displays 0.1.4-dev and the source build identifier.

## Test checklist

1. Open Preferences → Connections. Test Scan again and Scan subnet on your LAN;
   select a device, test the connection, and connect. Manual IP entry remains available.
2. Switch profiles and check Serial number and Box model. Save profile details,
   close/reopen, and confirm each machine retains its own values. Read C64U Model.
3. In General, click to the right of checkbox labels; they should not toggle.
4. Save a preview default such as 175%. Restart and confirm it persists.
5. On Streams, test minus/plus from 100% to 300%. The window should stay the same
   size and display scrollbars as needed. Restart; scale should return to the saved default.
6. Confirm Append Return starts checked. At BASIC READY, send PRINT "HELLO".
7. Check capture folders, screenshot/recording, Mount & Run, and Quit as a regression check.

Mount & Run requires DMA network service and runs a temporary D64 copy in Drive A.
Operations affect the connected real C64U and its files. Report platform and About
build with any failure. This prerelease does not replace the stable release.
