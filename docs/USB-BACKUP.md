# USB/SD backup and restore

USB/SD backup and restore is an Argonaut Core capability. GTK selects paths,
presents Core previews, returns the user's confirmation choice, and observes the
Core job. It does not traverse media, compare files, construct manifests, or
perform transfers.

## Core contract

`UsbBackupService.prepare_backup()` accepts a C64U volume root, zero or more
selected paths inside that volume, and a new `core-host` backup-folder path. An
empty selection means all children of the volume. Its scheduled job returns a
serializable `BackupPreview` with item and byte totals, the bound device and
volume, the local destination, and the cost of verification. Execution requires
the returned plan ID.

`UsbBackupService.prepare_restore()` accepts an Argonaut backup folder on the
Core host and a current C64U volume root. Its scheduled job validates the
manifest and local bytes and returns a serializable `RestorePreview` containing
additions, replacements, unchanged paths, conflicts, and missing or invalid
backup data. `execute_restore()` consumes that plan and takes an explicit
`replace` decision. Extra destination files are never deleted.

Both operations use the Core scheduler, structured job progress, cooperative
cancellation, categorized failures, and structured partial results. Paths use
the existing `core-host` and `c64u` scopes. `client-upload` remains unsupported.

## Backup root preference

**Preferences → General → USB/SD backup root** stores an optional Core setting
for the parent folder that contains individual backups. It is a `core-host`
path on the machine running Argonaut Core, rather than a path owned by a future
remote client. Stable and Development store it in their separate configuration
files.

When the setting is blank, the native destination chooser keeps its normal
starting location. When it names an existing folder, **Back up USB/SD…** starts
the same Save chooser in that folder and retains the editable individual backup
directory name. Argonaut does not create the root, add another directory level,
or automatically choose a timestamp. An unavailable configured root stops the
workflow with a clear error and must be corrected or cleared in Preferences.
Changing the root does not move, rename, convert, or invalidate existing backup
directories.

## Backup format and verification

Each backup is a new folder containing the original volume-relative directory
layout and `.argonaut-usb-backup.json`. Manifest format version 1 records:

- source device identity, volume root and bounded volume fingerprint;
- selected volume-relative paths;
- empty directories;
- file paths, sizes and SHA-256 digests;
- incomplete or complete state, timestamps, and any stopping failure.

Planning reads every selected file once to bind the confirmation plan to its
content. Execution downloads each file, hashes the published local bytes, and
reads the remote source again. All three observations must agree. The manifest
is atomically updated after every completed file and remains explicitly
incomplete after interruption. Backups are limited to 10,000 entries and 64
levels. Names that cannot be represented safely across supported host platforms,
case collisions, links, insufficient space, and existing destination folders are
refused.

## Restore safety

Restore verifies every local file against the manifest before preview and again
before execution. It fingerprints the bounded C64U volume, binds the plan to the
physical device and connection session, compares destination content, and repeats
those checks after confirmation. A changed backup, C64U session, storage volume,
destination file, or local storage identity requires a fresh preview.

Additions use verified staged uploads. Replacements use the existing staged
replacement and changed-target checks. Conflicts are skipped and reported.
Choosing additions without replacement leaves every existing differing regular
file unchanged. No restore applies firmware or configuration, and no mode deletes
destination extras.

The C64U API does not expose a removable-media serial number. Argonaut therefore
uses a bounded recursive fingerprint of paths, entry kinds and sizes together
with the C64U device/session binding. Physical testing should still include USB
removal and replacement because two byte-for-byte-equivalent media cannot be
distinguished through the available interface.

## Physical acceptance

Linux physical USB/SD backup and restore acceptance passed on 2026-09-20. The
accepted scenarios covered:

- normal backup, including preservation of an empty folder and a zero-byte file;
- normal restore;
- replacement detection and explicit replacement authorization;
- preservation of unrelated destination files;
- restore cancellation, partial-upload reporting, and reviewed cleanup;
- backup cancellation and rejection of incomplete backups;
- stale connection/session rejection after preview; and
- physical USB media-swap rejection after preview.

Physical testing found that a cancelled restore reported its unfinished file
but did not enable cleanup for the staged remote upload. Commit
`b340fd3146b3920a65b5323b9af2701e948bf6eb` corrected the Core-to-GTK cleanup
handoff, bound cleanup to the originating device session, and was physically
retested successfully.

USB/SD Backup & Restore is complete and physically accepted on Linux. Its
Windows, Apple Silicon Mac, and Intel Mac qualification is pending as part of
the consolidated Stable 1.9 platform gate after SID Jukebox Linux acceptance
and the Game Library Bulk Import enhancement.
