Argonaut — Windows x64 test build

Extract the entire ZIP into a folder, then open Argonaut.exe.
Keep the _internal folder beside the executable. No Python or MSYS2 installation is needed.

Windows 10/11 x64 is the initial test target. This build is unsigned.
Preferences: %APPDATA%\argonaut. Passwords: Windows Credential Manager.
Use a bridged network adapter in a VM. Connect to the C64U by its LAN address.
Screen preview requires Ethernet on the C64U and inbound UDP 11000–11001.
If Windows Firewall asks, allow access only on your trusted private network.

Initial limitations: automatic subnet suggestions and MAC fallback are Linux-only;
enter the device IP/subnet manually and use the C64U Default unique ID.
Click Refresh to rescan local drives after USB insertion/removal.
The SuperCPU Detect freeze documented in the Debian release remains unresolved.

Argonaut: GPL-3.0-or-later, copyright 2026 Bruce Marcus. See LICENSE/COPYRIGHT.
Runtime libraries retain their own licenses, included under _internal/third-party-licenses.
The build workflow records MSYS2 package versions for the runtime dependencies.
