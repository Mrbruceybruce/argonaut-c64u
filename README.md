# Argonaut

A GTK desktop application for controlling and managing a Commodore 64 Ultimate.

Features include connection profiles, local and C64U USB/SD file management,
settings and favorites, ROM selection, configuration backups and Undo,
live screen preview, screenshots, and WebM recordings.

## Debian 13 installation

Download the Debian package from [Releases](https://github.com/Mrbruceybruce/argonaut-c64u/releases/latest) and install it with:

```sh
sudo apt install ./argonaut-c64u_0.1.0_all.deb
```

Launch **Argonaut** from the application menu, or run `argonaut`.
Enable the C64U REST and FTP services, then add its address in **Connections**.
Preview requires Ethernet and inbound UDP ports 11000–11001 from the C64U;
configure any firewall to allow only the intended device or trusted LAN.
Installation does not change firewall rules or device settings.

Profiles and preferences use `$XDG_CONFIG_HOME/argonaut` (normally
`~/.config/argonaut`). Saved passwords use the desktop Secret Service.
Removing or upgrading the package preserves user preferences.

## Run from source

Install Python 3.11+, PyGObject, GTK 4.8+, libsecret introspection,
GStreamer introspection and base/good plugins, iproute2 and Adwaita icons.
The complete Debian dependency list is in `packaging/build_deb.py`.
Run `python3 -m c64u_browser.gui` in a graphical desktop session.

## Build and test

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 packaging/build_deb.py --output dist
```

See `packaging/RELEASE-NOTES.md` for validation and known limitations.
The SuperCPU Detect freeze reported during an Undo test remains unresolved.
Other firmware versions may expose different capabilities.

## License

Copyright (C) 2026 Bruce Marcus. Licensed under **GPL-3.0-or-later**.
See [LICENSE](LICENSE) and [COPYRIGHT](COPYRIGHT). No firmware, ROMs,
third-party disk images, credentials, or device scan results are included.
