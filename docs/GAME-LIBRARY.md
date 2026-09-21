# Game Library Core contract

The Game Library MVP supports referenced D64 and CRT files on the Argonaut Core
host or on one identified C64U removable volume. Adding a catalog entry does not
move, copy, upload, mount, launch or delete the referenced file.

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

## Physical acceptance procedure

Physical acceptance begins after the GTK Game Library client exists. Use a
catalog containing distinct, known-working examples and retain the source files
unchanged during each reviewed launch.

1. Launch a Core-host CRT and confirm the expected cartridge starts.
2. Launch a C64U-resident CRT and confirm the expected cartridge starts.
3. Press Reset and confirm the temporary cartridge starts again.
4. Reboot and confirm the permanently configured cartridge returns, if present.
5. Launch a second CRT and confirm it replaces the first temporary cartridge.
6. Launch Core-host and C64U-resident D64 games and confirm both reach their
   expected startup behavior.
7. Confirm a malformed/truncated CRT is rejected before a command is sent.
8. Try a structurally valid cartridge type whose firmware support is uncertain;
   confirm Argonaut presents the warning and reports the device response without
   claiming playable success.
9. Create a preview, reconnect or switch C64Us, and confirm execution is refused.
10. For a C64U-resident source, create a preview, swap or alter the removable
    volume, and confirm execution is refused.
11. Cancel before command transmission and confirm nothing starts. Request
    cancellation after transmission and confirm Argonaut does not falsely label
    the accepted/uncertain operation as safely cancelled.

Record the Development build identity, C64U firmware/API version, physical
device identity, source scope and observed outcome for each case.
