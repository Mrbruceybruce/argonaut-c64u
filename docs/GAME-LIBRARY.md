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
acceptance is complete; cross-platform acceptance remains open.
