# Argonaut 1.6

> Historical 1.6 candidate-era notes. No stable v1.6 Release is published; the
> RC Releases were removed during cleanup and the superseded 1.6 workflow retired.
> See [release guidance](../docs/RELEASING.md); these are not 1.9 release notes.

Argonaut 1.6 adds an optional Developer Mode and Test Lab while preserving the
ordinary stable experience. Developer Mode is off by default. Enable **Developer
Mode and Test Lab after restart** in Preferences, then restart Argonaut to show
the Test Lab tab. Enabling it does not start background work or change a C64
Ultimate.

Developer Mode provides:

- structured, privacy-filtered logs for C64 Ultimate REST and FTP operations;
- deterministic offline, connected-device, regression, fleet, and installed
  package checks whose pass/fail results are decided by ordinary code;
- private saved result history, comparisons, JSON export, and change tracking;
- a separate AI explanation layer for failed checks, using local Ollama or an
  explicitly configured OpenAI API key, without allowing AI to alter verdicts;
- optional Linux background checks, local AI diagnoses, and change-only desktop
  alerts;
- an optional paired PETSCII C64 client and authenticated local AI bridge for
  Ollama, including deterministic scheduled end-to-end bridge checks.

The Test Lab performs read-only C64U checks unless a control clearly describes
an installation or pairing action. Its simulation controls do not contact the
C64U and do not save false failures as device history. Background services are
independent and opt-in. Disabling Developer Mode stops stable Linux automation
after restart while retaining private reports and settings for later use.

Stable and Development profiles, reports, bridge credentials, and Linux service
identities are separate. Existing stable profiles remain in place during an
upgrade. The normal Files, Settings, Drives, Machine, SID/Media, and Streams
features remain available with Developer Mode disabled.

The main window now provides **Quick Connect** for the last-used device profile
while retaining the normal device-identity check. General preferences save
automatically and provide **Undo**, **Restore defaults…**, and a single **Close**
button. Device profile edits keep one explicit **Save device profile** action and
an unfinished-edit confirmation when Preferences closes.

Downloads include a Debian package, Windows Setup and Portable packages, and
Apple Silicon and Intel macOS packages. Mac packages require macOS 15 or newer.
Windows packages are unsigned; Mac apps are ad-hoc signed and are not notarized
by Apple. Local AI features require a separately installed model service such as
Ollama. The C64 bridge may require a local firewall rule and explicit pairing.

Known limitation: the previously reported C64U freeze involving an Undo of the
SuperCPU Detect setting remains unresolved. Avoid changing SuperCPU Detect in
normal use. Windows multiple-instance behavior also remains under review; avoid
simultaneous operations from multiple clients against the same C64U.

Please report issues with the platform and version/build shown in Preferences >
About. Include an exported Test Lab report when it is relevant; exported reports
exclude saved passwords and AI API keys.
