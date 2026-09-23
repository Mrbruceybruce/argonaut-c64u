# Game Library Core contract

The Game Library MVP supports referenced D64 and CRT files on the Argonaut Core
host or on one identified C64U removable volume. Adding a catalog entry does not
move, copy, upload, mount, launch or delete the referenced file.

## GTK client workflow

The **Game Library** tab is a thin client of the two Core services. It lists the
title, D64/CRT format, favorite marker, validation state and explicit source.
Search covers titles, notes and source paths; **Favorites only** narrows the same
Core query. Missing, changed and unavailable entries remain visible.

**Add local files…** records references selected from the Core host. **Add
selected C64U file** records the single D64 or CRT selected in the C64U pane of
Files, including its physical device, volume and path identity. Neither action
copies or launches the game. Details allow title, favorite, notes and a reference
to existing Core-host PNG, JPEG or WebP artwork. Removing an entry never deletes
the game or artwork file.

After a local batch, GTK reports Core's actual result counts. It distinguishes
new records, an already-cataloged matching source, identical content represented
by another record, changed content at a cataloged source, and rejected files. A
submitted path is never described as added merely because validation completed.

**Validate** refreshes source state. **Locate/Relink…** uses a local chooser for
Core-host sources and the selected C64U file for C64U sources. A different hash
is shown explicitly and requires **Accept different content** before Core changes
the catalog identity.

**Review & Launch…** first runs Core preparation, then presents its source,
target, mechanism, reset/interruption flags and warnings. Only an approved Core
plan can be executed. The final message says **Command accepted** rather than
claiming successful gameplay. Missing, changed and unavailable entries cannot be
launched until their source state is resolved.

## Reviewed launch

Launching is a consequential Core operation. A client first requests a launch
preview. The preview identifies the game, source, target physical C64U, launch
mechanism, expected reset/program interruption and warnings. It expires after
five minutes and can be used only once.

Execution revalidates the immutable catalog record, source, SHA-256 digest,
physical device, connection session and, for a C64U source, removable-volume
identity. Core checks cancellation immediately before the runner or DMA command.
It never retries a failed or uncertain launch automatically.

Removable-volume identity is a complete bounded tree fingerprint. Its internal
identity listing preserves each FTP filename as its exact octets, including
names that are not valid UTF-8, and sorts those octets deterministically. The
fingerprint uses a versioned, length-delimited encoding of raw path components,
entry type and reported size. Raw names remain inside Core; normal Files views
continue using display text. A raw filename, hierarchy, type or size change
therefore changes the digest without requiring lossy filename decoding.

`storage-changed` means two complete verified fingerprints differ.
`storage-unverifiable` means Core could not complete the required full-volume
verification; the client asks the user to keep the volume available and review
again. Neither result sends a launch command. Long verification reports
structured directory and entry counts while it remains on the Core scheduler,
so GTK can show progress without parsing error or status prose.

The four launch routes are:

| Source | Format | Core mechanism |
| --- | --- | --- |
| Core host | CRT | Attached `POST /v1/runners:run_crt` |
| C64U | CRT | Existing-file `PUT /v1/runners:run_crt` |
| Core host | D64 | Authenticated DMA `RUN_IMG` using validated bytes |
| C64U | D64 | Authenticated DMA `RUN_IMG` using validated bytes |

`command-accepted` means the C64U accepted or processed the consequential
command. It does not mean Argonaut proved that the game reached a playable
screen. A lost response after command transmission is reported as
`launch-outcome-unknown`; the operation is not retried.

## Temporary CRT behavior

Launching a CRT activates a temporary cartridge and resets the C64. Reset starts
that temporary cartridge again. Reboot returns to the permanently configured
cartridge, if any. Launching another CRT replaces the active temporary cartridge.
The documented C64U API has no detach operation, so Core does not invent one.

## Linux physical acceptance

Linux physical acceptance passed on 2026-09-20 with Development candidate
`1.9-game-library.1+gtk-ac.2` and the beige
`C64-Ultimate-7F01C9`. Core-host D64 and CRT files were added without being
moved. Search, favorite filtering, title and notes editing, restart persistence,
missing-source validation, disabled launch for missing entries, matching-content
Relink, and explicitly reviewed different-content Relink all passed. A malformed
truncated CRT was rejected during validation before launch.

All four launch routes reached a physical startup screen:

| Source | Format and test | Physical result |
| --- | --- | --- |
| C64U | `Amaurote.d64` | Reset, disk activity and startup screen; command accepted |
| Core host | `C64Robots v1.3.d64` | DMA `RUN_IMG`, reset, disk activity and startup screen; command accepted |
| Core host | `Prince of Persia (POP).crt` | Attached CRT reset and startup; command accepted |
| C64U | `Bomberland.crt` | Resident CRT runner reset and startup; command accepted |

With the temporary Prince of Persia cartridge active, Reset restarted it and a
C64U Reboot removed it. Because no permanent cartridge was configured, the C64U
returned to BASIC. This matches the review dialog's Reset/Reboot explanation.

Acceptance initially found that one transient `/v1/info` health timeout caused
GTK recovery to replace the Core session, making a valid preview stale. Core
correctly rejected that preview before reset, DMA or a runner call. Recovery now
confirms a retryable health failure before discarding the session. Physical
retesting verified a normal launch retains its session, while a real Ethernet
disconnect shows **Confirming connection…**, transitions offline after the
confirmation fails, reconnects with a new session, and rejects the old preview
without any launch activity.

Automated coverage retains the remaining destructive-boundary cases, including
source or catalog changes after preview, storage/device/session changes,
cancellation, malformed structures and uncertain command outcomes. Linux
acceptance is complete at
`b66faa5da9119417fb7e38b695122c7d39403b54`; cross-platform acceptance remains
open for the consolidated Stable 1.9 gate. Artwork association and presentation
have automated coverage, but artwork selection/display was not explicitly
recorded in the Linux physical-acceptance results. This is an acceptance-record
gap and does not reopen the completed Game Library implementation.

## Stable 1.9 enhancement: Bulk Import Linux-complete

Game Library Bulk Import follows SID Jukebox Linux acceptance and precedes the
consolidated Stable 1.9 platform gate. Its Core and thin GTK implementation and
Linux physical acceptance are complete. The
existing **Add local files…** multi-file workflow remains available. The
enhancement adds:

- **Scan local folder…**, with an optional bounded recursive scan;
- adding multiple selected supported files from the C64U Files view where
  practical; and
- **Scan C64U folder…**, with an optional bounded recursive scan.

Scanning is limited to the Game Library's current D64 and CRT formats. Core owns
traversal, validation, hashing, duplicate/content-identity decisions,
cancellation, and the resulting serializable review. GTK chooses the source and
options, presents progress and review, and submits the approved Core operation.

Sources remain references. A scan or approved import never copies, moves,
uploads, mounts, launches, deletes, or otherwise modifies game files. Before
catalog changes are committed, Core provides a review that distinguishes new
records, already-cataloged sources, duplicate content, changed existing sources
where relevant, invalid/inaccessible supported images, and unsupported files.
Unsupported files such as ZIP or TXT are counted and filtered separately; they
are not presented as corrupt or inaccessible game images. One invalid candidate
does not unnecessarily abort the rest of the scan.

Recursive traversal enforces defensive ceilings of 10,000 directories, 100,000
total entries, 50,000 D64/CRT candidates, depth 32 and 32 cumulative GiB. These
are runaway-traversal safeguards, not normal Game Library capacity limits. They
remain Core constructor limits for deterministic testing and are not ordinary
GTK preferences. Hidden entries are excluded by default and Core-host symlinks
are never followed. Exceeding any bound aborts the scan with the available
diagnostic counts rather than silently truncating the review. C64U scans use one
sequential reader and remain tied to physical-device, volume and
connection-session state.
Review plans are process-local, one-use, retained for 30 minutes, and bounded to
eight plans. Reviewed catalog admission rereads approved sources and requires
their exact reviewed content identities without recursively fingerprinting the
volume. C64U admission binds the exact device, connection session, volume and
path, performs a bounded complete read, validates the image structure, and
requires the reviewed SHA-256. Candidate-level read or validation failures are
reported while other safe candidates continue. Device/session failures and
other batch-level safety failures abort before publication.

The first large real-world C64U physical scan reached the original
2,000-candidate ceiling and aborted safely. The measured collection contained
5,498 files, 3,159 D64/CRT candidates, 33 directories and 527.1 MiB of candidate
content. This is a realistic enthusiast collection rather than a pathological
tree, so the defensive defaults were raised while retaining every traversal
bound and the same fail-safe abort behavior.

Bulk Import validates supported format, bounded readable content, D64/CRT
structure and SHA-256 identity, then classifies catalog and duplicate state.
Structural validity does not prove that a game boots or works, that a release
contains every required disk side or companion file, or that C64U firmware
supports a structurally valid CRT hardware type. The internal `new-valid`
classification is presented to users as **New game image**; it is not a claim
that the software has been tested or verified playable.

GTK offers **Scan local folder…**, **Scan C64U folder…**, and reviewed batch
handling for multiple selected C64U D64/CRT files. One scrolling review shows
totals and per-candidate classifications. All structurally valid new game images
begin selected; the user can select all new, select none, change individual checkboxes, and
filter the presentation without losing the approved set. Execution refreshes
the Game Library once and summarizes additions, reclassifications and failures.
Execution independently rereads and revalidates the selected subset. Core
publishes all created records with one atomic catalog write and restores the
previous in-memory catalog if persistence fails. GTK does not enumerate, hash,
classify or modify catalog records itself.

### Linux physical acceptance

Linux physical acceptance passed on 2026-09-23. Local non-recursive and
recursive scans, C64U non-recursive and recursive scans, classification filters,
Select all new, Select none, individual exclusions, dynamic **Import N games**,
approved-subset import, cancellation without catalog mutation, and stale-plan
rejection after disconnect/reconnect all passed. The original 2,000-candidate
limit was physically reached and aborted safely before the defensive defaults
were revised for realistic collections.

The source collection used for acceptance contained 5,498 files, including
3,159 D64/CRT files in 33 directories and approximately 527.1 MiB of D64/CRT
content. The final physical C64U scan reviewed:

- 4,797 entries;
- 2,743 D64/CRT candidates;
- 2,606 new game images;
- 10 duplicates;
- 0 changed images;
- 128 invalid or inaccessible items; and
- 2,022 unsupported items.

Unsupported ZIP and other files remained distinct from invalid or inaccessible
supported images. Archive contents were not imported. The approved execution
added 2,606 games with 0 skipped/reclassified and 0 failed, producing a
2,616-record Development catalog. The catalog persisted across restart, and
large-library scrolling and filtering passed.

Physical use of the 2,616-record catalog also accepted the 300 ms GTK search
debounce. Rapid typing replaces the one pending callback and produces one final
refresh. Enter, clearing the field, and changing **Favorites only** refresh
immediately; immediate actions cancel the pending callback, and tab teardown
neutralizes it so stale work cannot overwrite newer client state. This is a
Game Library presentation optimization and does not change SID Jukebox search.

A Bulk-Imported C64U D64 completed reviewed Game Launch and loaded successfully.
The same physical acceptance volume exposed two raw filenames containing byte
`0x84`:

```text
Schatzj\x84ger [Side 1] [Ariolasoft] [TWG].d64
Schatzj\x84ger [Side 2] [Ariolasoft] [TWG].d64
```

The original UTF-8-only full-volume traversal could not verify that volume. The
corrected internal identity path preserves filename octets reversibly, sorts by
exact raw bytes, and hashes length-delimited raw path components, entry type and
reported size. It does not interpret `0x84` as a particular character. Repeated
fingerprints of unchanged `/USB1` were deterministic, and reviewed Game Launch
from the unchanged volume passed. Structured directory/entry progress kept GTK
responsive during the corrected long verification, and final GNOME physical
use did not reproduce the Force Quit loop.

Bulk Import catalog admission uses authorized-content identity and does not need
a recursive volume fingerprint. Game Launch retains conservative full-volume
before/after verification and now distinguishes a verified differing digest
(`storage-changed`) from an incomplete verification (`storage-unverifiable`).
USB Backup/Restore retains its conservative full-volume safeguards and uses the
same octet-preserving identity correction. Bulk Import did not weaken either
consequential safety contract.

### Completed Linux Bulk Import acceptance checklist

- [x] Scan a local folder without subfolders and verify review totals.
- [x] Scan a local folder with **Include subfolders** and verify hidden entries
  and symlinks are excluded.
- [x] Verify new, already cataloged, duplicate, changed, invalid and unsupported
  classifications with Select all new, Select none, individual selection and
  filters.
- [x] Import a selected local subset and verify deselected files remain absent.
- [x] Select multiple C64U D64/CRT files and complete one reviewed batch import.
- [x] Scan a C64U folder without and with subfolders; verify the UI stays
  responsive and progress changes during enumeration and validation.
- [x] Cancel one scan during discovery/validation and verify no catalog change.
- [x] Automated: cancel one execution before publication and verify no partial
  batch.
- [x] Reconnect the C64U after review and verify execution requires
  a fresh scan and does not rescan automatically.
- [x] Automated: change or remove a reviewed source before execution and verify
  the structured final summary without substitution.
- [x] Verify one final library refresh, preserved search/favorites behavior and
  acceptable responsiveness after importing a large batch.
- [x] Restart Development and verify imported records persist while Stable
  remains isolated.

Deferred work includes ZIP/7z archive sources, additional Game Library image
formats, a Tested/Playable user state, and Game Launch fingerprint-performance
optimization. Structural validation remains a statement about image structure
and content identity, never proof that a game boots or is playable. Tape and
Datasette support remain a post-1.9 investigation. This enhancement adds no
metadata scraping, managed storage, automatic source modification, or weakening
of Game Launch and USB Backup/Restore safety.
