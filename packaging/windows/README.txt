Argonaut 1.5 — Windows x64

PORTABLE ZIP
Extract the entire ZIP into a writable folder on your thumb drive.
Open Argonaut.exe. Keep _internal and portable.flag beside the executable.
Stable profiles, favorites and recovery data stay in Data\argonaut. Development
builds use Data\argonaut-development and keep passwords session-only, separate
from the stable app and the host credential store.
Exit Argonaut before safely removing the drive. Keep portable.flag when upgrading;
replace the application files but preserve your Data folder.
Saved screenshot/recording locations are absolute paths; choose a new destination
if a drive letter changes or you move to another PC.

INSTALLER
Run the Setup EXE. Installation is per-user; administrator rights are not required.
The installer adds a Start-menu shortcut and optional desktop shortcut.
Uninstall through Windows Settings > Apps. Profiles remain in %APPDATA%\argonaut,
and saved passwords remain in Windows Credential Manager. Uninstall preserves them.

No Python or MSYS2 installation is needed. Windows 10/11 x64 is the initial target.
These builds are unsigned. In a VM use bridged networking and connect by LAN IP.
Preview needs Ethernet on the C64U and inbound UDP 11000–11001 on the Windows PC.
Neither package changes firewall rules. Allow only your trusted private network.

Automatic subnet suggestions work on Windows. Enter the C64U address manually if
discovery is blocked by the VM or firewall, and use the C64U Default unique ID.
Linux background-service controls in Development's Test Lab report unavailable on
Windows; the package self-test and normal Test Lab checks remain available.
The SuperCPU Detect freeze documented in the Debian release remains unresolved.

Argonaut: GPL-3.0-or-later, copyright 2026 Bruce Marcus. See LICENSE and COPYRIGHT.
Runtime libraries retain their own licenses under _internal/third-party-licenses.
MSYS2-PACKAGES.txt records build dependency versions; upstream source packages:
https://mirror.msys2.org/mingw/sources/
