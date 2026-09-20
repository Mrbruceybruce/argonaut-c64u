# Argonaut 1.8

Argonaut 1.8 brings the completed AI-aware testing foundation, authentic
Commodore disk-image tools, and opt-in instant replay into the stable app.
Existing stable profiles and preferences remain in place during an upgrade.

## Disk-image management

- Open, validate, and extract files from D64, D71, and D81 images using their
  authentic CBM geometry, BAM, directory, and sector-chain structures.
- Stage safe rename, removal, and PRG/SEQ/USR additions on standard images,
  validate the complete result, and save it under a new local filename without
  modifying the source.
- Remove D64 REL files together with their data and side sectors. New REL-file
  creation is not supported.
- Create an empty standard D64 locally or directly on supported C64 Ultimate
  firmware. Existing filenames are protected before and during publication.
- Prepare a C64U disk image for mounting from the Files context menu.
- Keep genuine D81 CBM partitions labeled and protected instead of presenting
  them as host folders.

## Streams and replay

Instant replay is disabled by default. When enabled in Preferences, Argonaut
keeps a bounded 30-second history of encoded VP8 video and optional Vorbis
audio while previewing. **Save recent 30 seconds…** exports a playable WebM
without stopping live preview or an ordinary recording. Temporary replay data
is removed after stop, failure, export, and quit.

Streams also accepts consecutive Return-to-send commands: a successful send
clears the field and keeps it ready for the next C64 command.

## Optional Developer Mode and Test Lab

Developer Mode remains off by default. Enabling **Developer Mode and Test Lab
after restart** reveals structured, deterministic offline and read-only C64U
checks, private result history, JSON export, regression comparisons, and an
optional failure-analysis layer. Ordinary code decides every test verdict; AI
text can explain a failure but cannot change pass or fail.

Local Ollama and explicitly configured OpenAI analysis are supported. Linux
also provides opt-in background health, end-to-end AI, and fleet checks. The
paired PETSCII C64 client uses a narrow authenticated local bridge. These
features start only when the user enables their individual controls.

## Files and preferences

- Local hidden files are hidden by default and can be shown in General
  preferences.
- The active Files pane is visibly identified while selections in the inactive
  pane remain readable.
- Successful copy and drag operations retain the source and destination
  selections.
- General preferences save automatically and provide **Undo**, **Restore
  defaults…**, and **Close**. Device profile edits retain an explicit save
  action and unfinished-edit confirmation.
- The C64U settings tab is now named **Ultimate Menu**.

## Packages and validation

Downloads include Debian, Windows Setup and Portable, Apple Silicon macOS, and
Intel macOS packages. The exact release commit is compiled and tested on every
platform. Debian is installed on a clean runner before its packaged GTK
self-test. Both Mac bundles are tested after relocation with a minimal runtime
environment. The Windows installer, uninstaller, and portable package are
tested independently. Apple Silicon, Windows, and Linux also completed physical
acceptance for this roadmap release; the native hosted Intel package tests
passed, with physical Intel testing deferred until a tester is available.

Mac packages require macOS 15 or newer. Windows packages are unsigned; Mac apps
are ad-hoc signed and are not notarized. Local AI features require a separately
installed service such as Ollama. The C64 bridge may require an explicit local
firewall rule and pairing.

The previously reported C64U freeze involving an Undo of **SuperCPU Detect**
remains unresolved. Argonaut labels this setting as a hardware compatibility
risk and requires a separate high-risk confirmation. Avoid changing it during
routine use.

Please report issues with the platform, version, and build shown in
**Preferences → About**. Exported Test Lab reports exclude saved passwords and
AI API keys.
