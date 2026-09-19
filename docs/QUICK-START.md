# Argonaut quick-start guide

Argonaut controls and manages a C64 Ultimate from your computer. It provides
file transfers, settings and favorites, ROM selection, configuration backups,
and live screen preview with audio.

This guide covers Argonaut 1.5 on Debian, Windows, and Apple Silicon or Intel Mac. Available settings and actions depend on the connected C64U firmware.

## 1. Install Argonaut

Choose the package for your computer from the unified 1.5 release.

| Computer | Download | Install |
| --- | --- | --- |
| Debian 13 | [Debian 1.5](https://github.com/Mrbruceybruce/argonaut-c64u/releases/tag/v1.5) | Download the `.deb` and run the command below. |
| Windows 10/11, 64-bit | [Windows 1.5](https://github.com/Mrbruceybruce/argonaut-c64u/releases/tag/v1.5) | Run `Setup.exe`, then launch Argonaut from the Start menu. |
| Apple Silicon or Intel Mac, macOS 15 or newer | [Mac 1.5](https://github.com/Mrbruceybruce/argonaut-c64u/releases/tag/v1.5) | Open the DMG and drag Argonaut into Applications. Launch it from Applications. |

On Debian, open a terminal in the folder containing the downloaded package:

```sh
sudo apt install ./argonaut-c64u_1.5_all.deb
```

Windows and Mac packages include Python, GTK, and the media libraries.
Windows packages are unsigned. The Mac package is ad-hoc signed and has not
been Apple-notarized; the first launch may require the per-app **Open Anyway**
option in **System Settings → Privacy & Security**.

### Windows portable version

Extract the Portable ZIP into a writable folder, including a thumb-drive folder.
Keep `Argonaut.exe`, `_internal`, and `portable.flag` together. Launch the EXE.
Profiles and preferences travel in the adjacent `Data` folder. Passwords last
only for the current session. Keep `Data` when updating, and exit Argonaut
before ejecting the thumb drive. Reselect screenshot or recording destinations
if its drive letter changes.

Choose **Preferences → About** to see the running version and build identifier.

## 2. Prepare and connect your C64U

1. Connect your computer and C64U to the same reachable local network.
2. Enable the C64U's **REST** and **FTP** services in its network/service settings.
3. Note the C64U's current IP address. Use wired Ethernet on the C64U for preview.
4. Launch Argonaut and open **Preferences → Device details**.
5. Choose **New profile**, enter a descriptive name and the IP address, and check
   the REST and FTP ports. Defaults are **80** and **21**; use your device's values
   if you changed them.
6. Enter the network password if your C64U requires one. Choose the password-store
   checkbox if you want to save it and a native credential store is available.
7. Choose **Test connection**, then **Save profile** and **Connect**.

**New profile** starts a new form; **Save profile** saves it. Give each machine
and network interface an identifiable profile name, such as “Desk C64U Ethernet.”

You can also try **Scan again** or **Scan subnet**. Manual IP entry is available
on every platform. Subnet discovery works on Debian, Windows, and Mac. MAC-address fallback is
currently Linux-only.

### Keep profiles pointing to the right machine

A DHCP address can change. Router DHCP reservations help keep it stable.
Ethernet and Wi-Fi are separate interfaces and can have separate addresses and
MAC addresses; reserve each interface you use and keep its profile up to date.
After changing an address, test the profile and verify the connected device
before making changes. Argonaut does not automatically follow a changed IP.

## 3. Browse and transfer files

Open **Files**. The left pane contains local files; the right pane contains
files on the connected C64U's supported USB/SD storage.

The toolbar order is **Home, Back, Forward, Refresh, Copy, Paste, New folder**.
Hover over an icon to see its name. Drive buttons select available storage.
Double-click a folder to open it, or use the path field to navigate.

To copy files or a folder:

1. Select the source items in either pane.
2. Choose **Copy** in that pane or its right-click menu.
3. Open the destination folder in the appropriate pane.
4. Choose **Paste** there and wait for the result.

Copy/Paste uses Argonaut's own selection. If names already exist, review the
conflict dialog. **Replace** overwrites matching regular files; existing folders
merge. Folder/file conflicts and copies onto themselves are skipped.

Use Ctrl-click to select separate items or Shift-click to select a range.
Right-click a selected item to act on the selection. **Delete…**, **Delete
selected…**, or the Delete key opens a confirmation with the deletion preview.
Deletion is permanent and can include folder contents.

**Cancel transfer** stops an active transfer. Completed files may remain.
If an upload is interrupted, read the result and use **Delete partial upload…**
when available before retrying. A replacement error may identify staging or
backup paths; inspect those paths before retrying.

After inserting or moving a thumb drive, use **Refresh** to discover it.
Use your computer's normal eject/unmount controls for local removable media.

### Create and edit a D64 disk image

Open the local folder where the image should be saved and choose **New D64
disk…**. Enter a local filename, a C64 disk name of up to 16 characters, and an
exactly two-character disk ID. Argonaut creates a standard blank 35-track D64,
validates it, and opens its flat Commodore directory with 664 blocks free.

In a standard D64 directory window, you can stage filename changes, scratch
PRG, SEQ, USR, or structurally valid REL files, or add local PRG, SEQ, and USR
files. Choose the save action to publish the complete edited image under a new
local filename. Argonaut does not rewrite the source image or replace an
existing destination. Standard D71
images use the same staged workflow and a new `.d71` destination. Standard D81
images use a new `.d81` destination and protect CBM partition allocations from
file removal or reuse.

## 4. Change settings and use Favorites

Open **Ultimate Menu**. Use the section list or **Search settings…** to find an item.
Choose **Reload from C64U** when you need fresh device values.

1. Change the settings you want. Edits are staged locally.
2. Choose **Review & Apply…** and review the changes before confirming.
3. Use **Save to Flash…** if you want the running configuration retained after
   power off.

**Discard edits** removes staged edits. Applying settings and saving to Flash
are separate operations. Some hardware changes require a C64 reboot to take effect.

Read-only information, including the C64U Model, cannot be changed in Argonaut.
Other controls depend on the current configuration: static network fields are
inactive when DHCP is enabled, and LED fields depend on the selected mode.
Changing a controlling setting can discard staged edits to newly inactive fields.

Click **☆** beside a setting to add it to Favorites; **★** removes it.
Enable **Favorites** to filter the list. Favorites are saved on your computer.

## 5. Back up settings and manage Flash files

Before changing a configuration you want to keep, use **Export backup…** in
Settings. Apply or discard staged edits first.

**Restore backup…** shows compatible differences. Select the changes you want,
choose **Stage selected changes**, then use **Review & Apply…**. Restore does not
save to Flash automatically. **Undo last apply…** also opens a preview; review
and select what to restore before applying it.

Settings backups omit passwords, read-only information, and C64U Model. They do
not include ROM or media file contents. Referenced files must already be installed.

### ROMs and native C64U configuration files

Open **Flash files…** from Settings and choose the appropriate Flash folder.

- **Upload file…** copies a file from your computer into that folder.
- **Copy selected drive file…** copies the single file selected on the C64U side
  of Files into Flash. Select the file before opening this dialog.
- **Save a copy…** downloads the selected Flash file to your computer.
- **Preview config…** reviews compatible settings from a selected native `.cfg`
  file in the configs folder, ready to stage and apply.

The device menu calls this storage “Flash memory”; Argonaut accesses it through
paths such as `/Flash/roms` and `/Flash/configs`. Uploading a file does not activate
it, and this dialog does not replace existing Flash files.

After installing a compatible ROM, reload Settings and select it for the correct
hardware component, then review and apply. The ROM folder can contain Kernal,
BASIC, character, and drive ROMs; choose a file appropriate to the setting.
Reboot the C64 when needed. Argonaut does not include ROM images.

## 6. Preview, screenshots, and recordings

1. Connect the C64U through wired Ethernet.
2. Open **Streams**.
3. Enable **Play audio on this computer** if wanted, then choose **Start preview**.
4. Once video appears, choose **Save screenshot…** for a PNG or **Start recording…**
   for a WebM recording. Enable audio before starting preview to include sound.
5. Stop recording and preview when finished.

Screenshot and recording dialogs remember their chosen folders when those
folders remain available. Starting preview can replace existing C64U video/debug
and audio streams.

## 7. If something does not work

| Symptom | Check |
| --- | --- |
| Cannot connect | Current IP, REST/FTP services, ports, password, and network reachability. In a VM, bridged networking was used for testing. |
| Connected, but no preview | Wired Ethernet on the C64U, the correct interface/profile, and incoming UDP **11000–11001** on your computer. Argonaut does not change firewall rules. |
| Video works but audio does not | Stop preview, check the audio checkbox and computer output device, then restart preview. |
| Device rebooted or Ethernet was unplugged | Allow time for reconnection at the same address. Choose Start preview again after reconnecting. Disconnect stops automatic retries. |
| Settings will not reload | Apply or discard staged edits, then reload. |
| New USB drive is missing | Use Refresh and select its drive button. |
| Transfer stopped | Read the completed/unfinished list and any partial-file information before retrying. |

A freeze was reported while restoring settings that included **SuperCPU Detect**.
The cause remains unresolved. Avoid changing that setting during routine tests;
Undo is not a guarantee that hardware changes are harmless.

To report a problem, [open a GitHub issue](https://github.com/Mrbruceybruce/argonaut-c64u/issues).
Include your operating system, Argonaut package version, C64U firmware version,
steps to reproduce, and the error text. Remove passwords and any private details
from screenshots or attachments.
