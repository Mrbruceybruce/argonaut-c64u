# Argonaut 0.1.4-dev.1 — Development testing

These packages include Preferences with folder browsing, Mount & Run for Drive A
(D64), DMA text input, preview scaling (50–200%), the revised Streams layout,
and the macOS Quit fix. This is a prerelease for testing.

Windows: extract the portable ZIP to a writable folder and run Argonaut.exe.
Mac: open the DMG and copy Argonaut Development.app to Applications, or extract
the ZIP. Apple Silicon and Intel packages are provided for macOS 15 or newer.
The Mac app is ad-hoc signed, not notarized; use System Settings → Privacy &
Security → Open Anyway if macOS blocks the downloaded app.

The window identifies itself as Argonaut Development; About shows 0.1.4-dev
and the source commit. Preferences and profiles are separate from stable Argonaut.
Windows portable preferences live in Data/argonaut-development beside the app;
Mac preferences use the argonaut-development configuration folder. Create a
connection profile for testing. Passwords are session-only. Existing local
development settings can be reused; stable settings are not imported.

Test Preferences persistence after quitting/reopening, Screenshot and Recording
folder browsing, preview scale and audio, DMA Send text at BASIC, Mount & Run
with a test D64, and Quit (including Cmd-Q on Mac). Remember last-used file folders
controls file browser locations only; capture folders remember their own last use.
Mount & Run requires DMA network service and runs a temporary disk copy in Drive A.
Operations still affect the connected real C64U and its files.

Keep the stable release for everyday use. Report the platform and About build
when reporting a problem. No installer is needed for this Windows test package.
