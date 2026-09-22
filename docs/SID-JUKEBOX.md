# SID Jukebox

SID Jukebox is a Core-owned catalog, playlist and reviewed-playback capability.
GTK presents the Library, active Playlist and Now Playing state, while Core owns
source validation, parsing, playlist navigation, device/session binding,
cancellation and playback submission.

## C64U-resident SID safety

SID playback uses **authorized-content identity**. For a SID referenced on C64U
USB/SD storage, Core binds the operation to the exact physical C64U identity,
connection session, volume root and cataloged path. Core completely reads the
bounded SID, checks its SHA-256 against the cataloged content, parses those
fresh bytes, validates the selected subtune and rechecks catalog/playlist and
device/session state. Core then sends that same validated byte buffer as a
temporary attachment to the C64U SID runner.

The playback request never validates bytes and then asks the firmware to reopen
the resident path. An authorized Previous or Next transition performs one
complete SID source read, no recursive volume listings and one attached
playback request. Initial reviewed Play reads once for the preview and rereads
independently before execution.

This policy proves the identity of the consequential SID content; it does not
prove the identity of the physical removable medium. A replacement medium is
accepted when the expected device/session/volume/path supplies byte-identical
SID content. This is intentional: SID playback is non-destructive, and the
submitted bytes and subtune are the complete source-dependent inputs to the
operation. Missing, malformed, truncated, unstable or changed content is
rejected before a playback request.

USB Backup/Restore, Game Library launch and destructive file operations do not
inherit this policy. They retain their existing removable-media safeguards
until each operation receives its own consequence-specific review.

## Result semantics

Cancellation remains cooperative through validation and at the final point
before submission. Once submission begins, a lost response is reported as an
unknown playback outcome and is never retried automatically. A successful
response means **Command accepted**; Argonaut does not claim that audible
playback was verified.

## Linux physical acceptance

SID Jukebox Linux physical acceptance passed on 2026-09-21. Testing confirmed:

- Core-host SID playback passed and was audibly verified.
- C64U-resident SID playback passed and was audibly verified.
- Real PSID metadata parsing passed.
- Real 3SID metadata, address and requested-model reporting passed.
- Explicit subtune selection and playback passed.
- Playlist persistence, multi-selection, removal and reordering passed.
- Playlist editing selection remained independent from the Core playback
  cursor and its single current-item indicator.
- Previous/Next, playlist boundaries and non-repeating Shuffle passed.
- Shuffle Previous/forward history passed.
- Disabling Shuffle retained the actual Core current item and resumed ordered
  navigation from that item's playlist position.
- Reconnection invalidated playlist authorization.
- A reviewed Play made stale by disconnect/reconnect was rejected before
  playback.
- C64U-resident authorized-content validation and attached playback passed.
- The UI preserved **Command accepted — audible playback not verified** rather
  than claiming that Argonaut had verified the sound output.

On the tested physical C64U, a resident SID transition improved from
approximately 44 seconds with recursive full-volume scanning to approximately
1.5 seconds with exact-content validation. This is an observed acceptance result,
not a wall-clock guarantee; source size, storage and network conditions vary.

USB Backup/Restore still uses its stronger full-volume removable-media
protection. Its destructive restore consequences require physical-media safety
that SID playback does not. Game Library launch behavior was not changed by the
SID policy or this acceptance work.

## Duration policy and deferred work

Stable 1.9 uses manual Next. The C64U's apparent five-minute SID timer is not
accepted as trustworthy tune-duration metadata. Physical testing found that
SpaceFight subtune 2 produced roughly 30 seconds of meaningful audio followed
by silence while playback continued. Astrolabe could become silent briefly and
then loop or restart. Those behaviors make a firmware timer or a simple period
of silence unsafe as an automatic transition signal.

Song-length database support, silence detection and automatic advancement are
deferred. Any later automatic advance requires trustworthy duration evidence,
must begin as an opt-in feature, and must preserve manual navigation when a
duration is unknown. SID socket/model/address reconfiguration also remains
deferred; current multi-SID information is descriptive and Argonaut does not
automatically change the C64U's SID configuration.
