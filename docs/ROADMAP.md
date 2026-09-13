# Argonaut feature roadmap

Status: proposed roadmap; the OBS development increment is now implemented locally.
See [implementation results](OBS-DEVELOPMENT-RESULTS.md) for its measured scope and
remaining qualification. The inventory below describes the original stable baseline.
Reviewed 2026-09-13 against stable **1.5**,
application release commit `857c8bac63a07fb9fab6ba81366065af1141f341`, and current
`main` at `5d1b270` (the subsequent screenshot update). No feature in this roadmap
is promised for a particular release. No device or system configuration was changed.

**Preserve existing recording.** The next feature should extend the current
receiver and WebM writer, not replace working recording with OBS. Start with the
[focused OBS proposal](OBS-INTEGRATION-PROPOSAL.md), one reviewed increment at a time.

## Evidence and existing behavior

The review covers [README](../README.md), [Quick Start](QUICK-START.md), recent
release/development changes, application modules, tests, and authoritative sources
linked below. Recent changes already added Mount & Run, BASIC text input, preview
scaling and scrolling, persistent capture folders, consolidated Preferences/About,
Mac Quit handling, discovery retries, and consistent package build identification.
These are the baseline, not new roadmap work.

| Requested feature | Status | Already present | Work still required |
| --- | --- | --- | --- |
| OBS integration | Partial foundation; dedicated integration new | Video/audio reception, screen preview, PNG capture, scaling, existing WebM recording | Clean capture window; explicit aspect/scaling policy; OBS instructions; measured sync and concurrent-recording qualification |
| Connection/stream diagnostics | Partial | Connection recovery/errors, received FPS, elapsed preview seconds, audio/video freshness, internal decoder counters | Expose meaningful counters, queue loss and interface/destination information; plain-language diagnosis; redacted copyable report |
| Replay buffer | New; writer reusable | Bounded recording inputs, VP8/Vorbis WebM encoding, asynchronous finalization | Rolling encoded history, duration/byte limits, save/export, active/available-duration state, cleanup |
| USB backup/restore | Partial file-copy foundation | Recursive copy, cancellation, conflict review, verified uploads, staged replacement, completed/skipped/unfinished report | Backup manifest/catalog, stronger download verification, scalable whole-volume planning, restore comparison and explicit decisions |
| Game library | New; selection/launch primitives reusable | File browsing, PNG screenshots, D64 Mount & Run, per-device profiles | Persistent file references, game favorites, notes, artwork association, search, launch shortcuts and missing-file handling |
| SID jukebox | Partial | Remote SID playback, default or explicit 1-based subtune, program-interruption confirmation | Playlists, shuffle, tune favorites, metadata/lengths, next/previous, carefully qualified auto-advance |
| Disk-image browser | New | Image mounting and D64 validation for Mount & Run | Read-only D64/D71/D81 directory parser and extraction; editing explicitly deferred |
| YouTube broadcasting | New; assessment deferred | Local media acquisition and recording | Decide whether direct computer encoding/transmission adds value beyond OBS; only then design credentials and explicit live controls |

### What the code actually guarantees

- [streaming.py](../c64u_browser/streaming.py) owns threaded UDP reception and
  stream start/stop. The decoder accepts 384×272 and 384×240 packed color-index
  frames, rejects malformed data, and uses a fixed palette. It does not reproduce
  arbitrary device palettes. Video has `invalid` and `incomplete` counters; audio
  has sequence-gap and invalid counters. These are not all exposed in the UI.
- [streams_tab.py](../c64u_browser/streams_tab.py) displays received FPS/time,
  stale-video/audio messages, and a 100–300% preview scale in 25% steps. It has
  scrollbars. Scaling changes widget size; an explicit nearest-neighbor filter
  and physical pixel-aspect correction are not implemented.
- [recording.py](../c64u_browser/recording.py) already writes WebM using VP8 and
  optional Vorbis audio. It stages output and finalizes asynchronously with an
  EOS timeout. A mode change stops that recording with an explanation. Keep PNG
  capture and remembered capture folders working too.
- A 33 ms GTK timer drains a single latest-frame slot and up to 24 audio packets;
  RGB conversion and recorder/audio feeding happen in that UI callback. GStreamer
  performs encoding asynchronously, but the media handoff is still UI-dependent.
  Received FPS can exceed the number of frames rendered or recorded. Writer caps
  declare 30 fps; video PTS use arrival-to-UI time, while audio uses nominal 48 kHz
  sample duration with gap re-anchoring. These are timing limitations to measure,
  not evidence that current recordings are unusable.
- [transfers.py](../c64u_browser/transfers.py) reads uploaded data back and compares
  SHA-256 before publication. Downloads check size before/after and hash received
  bytes, but do not independently hash the remote source or reread the local file.
  A digest of incoming bytes alone is not end-to-end backup verification.
- [folder_copy.py](../c64u_browser/folder_copy.py) limits a plan to 10,000 items / 64
  levels; it is not an unlimited volume-backup engine. Symbolic links are rejected.
  [replacement.py](../c64u_browser/replacement.py) rechecks targets and stages
  replacements. FTP cannot atomically exchange files; uncertain outcomes retain
  inspection instructions. Preserve these protections and honest failure reports.
- [backups.py](../c64u_browser/backups.py), configuration history and Flash config
  tools back up **settings**, not entire USB media. Do not label these as a USB backup.
- [media_tab.py](../c64u_browser/media_tab.py) confirms before SID playback takes
  over the C64 and reports the last accepted request, not live playback progress.
  Subtunes already exist. [profiles.py](../c64u_browser/profiles.py) stores setting
  favorites and profile notes, not game/tune favorites or game notes.
- [disk_run.py](../c64u_browser/disk_run.py) handles supported D64 sizes through DMA.
  Command acceptance does not prove a game loaded successfully. D71/D81 browsing
  must not imply D71/D81 Mount & Run support.

## Suggested implementation order and dependencies

Each row is a milestone, potentially several small PRs. Finish its automated
checks and applicable hardware gate before shipping or beginning its dependent
milestone. Independent file/library work need not wait for all media features.

| Order | Increment | Dependencies | Completion gate |
| --- | --- | --- | --- |
| 0 | Recording baseline and media characterization | Stable 1.5 | Reproducible synthetic media tests; document existing timing and shutdown behavior; retain working WebM output |
| 1 | Small diagnostics foundation | 0 | Thread-safe stats snapshots, separate received/rendered/recorded counts, redacted report and useful no-signal messages |
| 2 | OBS capture window and guide | 0–1 | Clean, crisp view; one shared receiver; capture on Debian/Windows/macOS; simultaneous WebM recording; sync measurements pass |
| 3 | Replay buffer | 2's media fan-out and timing gates | Bounded encoded storage, playable export, truthful retained duration, ordinary recording preserved |
| 4 | USB backup then restore | Existing transfer protections; independent of 2–3 | Verified manifest-backed backup first; then restore preview/confirmation, interruption and changed-target tests |
| 5 | Game library MVP | Existing profiles and D64 launch; optional backup links after 4 | Searchable references/favorites/notes/screenshots; no automatic file relocation; safe missing-device/file handling |
| 6 | SID jukebox | Existing SID/subtune support; optional shared library metadata from 5 | Manual playlist first, then evidence-based timing; takeover disclosure; no auto-retry after ambiguous play result |
| 7 | Disk-image directory and extraction | Existing transfer/extraction destination protections | D64 first, then D71/D81 fixture coverage; malformed-image bounds; never mount or alter source for browsing |
| 8 | Direct YouTube decision | 2 proven in real OBS use; 1 diagnostics and 3 timing lessons | Written go/no-go assessment before implementation; compare ongoing support burden with OBS |

### 1. Diagnostics scope

Show selected device, REST/FTP reachability when checked, destination computer
interface/address, UDP listener ports, age of last complete video/audio, and
recording state. Differentiate no packets, invalid packets and incomplete frames.
Expose audio sequence gaps as **estimated missing packets**: reordering/restarts
must not become enormous false loss counts. Video incomplete frames are not a
packet-loss count. Add wrap-aware video sequence tracking only with tests; report
unsupported/unmeasurable values as unavailable. Count receiver queue evictions,
latest-frame supersession, render skips and encoder backlog separately.

Use a typed, allowlisted diagnostic snapshot, not raw client objects, exception
payloads or HTTP dumps. Copy only after the user requests it. Exclude passwords,
X-Password/authorization headers, credential-store contents, stream keys, tokens,
URL query secrets and user file paths. Replace arbitrary exception strings with
safe error categories; test with planted secrets. Local addresses can help support,
but preview them and offer an anonymized copy; omit device IDs/MACs/serials by default.

Explain: “Connected to controls, but no video has arrived”; “The destination must
be this computer, not the C64U”; “This port is already in use”; “The C64U needs its
wired connection for this stream”; and “A firewall may be blocking incoming UDP.”
A timeout is not proof of a firewall problem. Read-only diagnosis must not start a
stream, scan broadly, change networking, or alter a device setting on its own.

### 3. Replay buffer scope

Default off; explicit Start/Stop buffering, a visible active indicator, default
30 seconds and a proposed 10–120 second range. Show actual available seconds while
warming up. Prototype encoded, keyframe-aligned fragments using existing GStreamer
codecs; do not retain 120 seconds of RGB frames or launch an unbounded list of writers.
Set explicit memory/queue and disk-byte ceilings as well as duration (initial disk
budget proposal: 256 MiB, to be benchmarked). Stop visibly on exhausted resources.

[GStreamer's splitmuxsink](https://gstreamer.freedesktop.org/documentation/multifile/splitmuxsink.html)
is a candidate, not a committed dependency: fragments split at keyframes and may
exceed nominal thresholds by a GOP. Prove WebM compatibility and export first.
Keep a hard supervisory budget and short GOP; pin fragments during export, account
for pinned/in-flight bytes, and bound concurrent exports. Remux with rebased PTS;
never concatenate WebM bytes. Report actual saved duration if keyframe granularity
makes an exact cutoff impractical. Delete only application-owned temporary fragments.

Reuse codec/timestamp/finalization logic where practical, but keep ordinary Start
recording independently usable. Validate simultaneous recording/buffering/export,
video-only, failure, quit, low disk space and long runs before enabling by default
(any default change would need a separate decision).

### 4. USB backup and restore scope

Back up selected folders or all children of a selected USB/SD volume into a new
local backup folder. Record relative paths, sizes, SHA-256, source identity/volume,
format version and completed/failed state in a manifest. Preserve empty folders
and zero-byte files. Local read-back verification is required; compare a second
remote read when no authoritative remote hash is available, with an explicit cost
in network traffic. Never claim a consistent snapshot of media being written by
another program; warn/report changed files and request a quiet source for full verification.

Replace the current all-in-memory plan ceiling only with bounded traversal and
checkpointing, or clearly refuse oversized jobs. Check space, case collisions,
reserved names and traversal/links on all platforms. A partial backup must remain
marked incomplete and reviewable; retries must validate source/target again.

Restore verifies the manifest and local bytes, binds to the chosen current device
and volume, and previews additions/replacements/unchanged/conflicting/missing
items and bytes. Require confirmation before replacement; use existing staged
replacement and revalidation. **Never delete extra destination files by default.**
Any later mirror/delete-extras option must be separately selected, list deletions,
and require explicit confirmation. No firmware/config apply is part of a USB restore.

### 5–7. Library, jukebox and disk images

Library records should reference a local path or device identity + volume/path,
not just an IP. A stable catalog key must survive profile edits without conflating
two devices. Adding an entry only stores metadata; screenshots are attached only
by user action. Offer Locate/Relink for missing files, retain notes, and disable
launch until validated. Reuse only currently supported launch routes; no background
uploads, mounting, or copying. Use a separate versioned metadata store with atomic
writes; evaluate JSON versus SQLite based on measured library size, not a new framework.

For SID, begin with manual next/previous, shuffle and favorites around existing
subtune control. The authoritative [runner reference](https://1541u-documentation.readthedocs.io/en/latest/api/api_calls.html#runners)
documents `sidplay` with `file`/optional `songnr` and song-length lookup, but does not
establish a remote playback-position or end-of-track callback. No such endpoint
was found in the reviewed client. Verify the target firmware's length-file format
and semantics before integration. Optional local length metadata or a user-entered
duration can drive an explicitly enabled approximate timer; unknown length means
manual Next. Explain whether advancing replaces a tune or changes its subtune.
Do not infer completion from silence. A playlist Start confirmation must explain
that it takes over the running program and authorize timed transitions for that
session. Disconnect/unknown outcomes stop scheduling; never auto-resume on reconnect.

Disk browsing downloads a remote image into a size-bounded temporary cache, or
opens a local image read-only, without mounting. Audit an existing parser's license,
maintenance, dependencies and supported variants before choosing it; otherwise
implement a small separately tested parser. D64, D71 and D81 need individual
geometry/directory-chain validation, PETSCII names, file types and corruption tests.
Bound sector walks and detect cycles/out-of-range links. Extraction uses explicit
selection/destination and safe filename mapping with collision/overwrite review.
State unsupported REL/error-table/extended image cases rather than corrupting output.
Disk-image editing is a separate later design and release gate.

### 8. YouTube assessment

First document broadcasting with OBS. Collect actual user friction before adding a
second encoder/transmitter. Direct support is justified only if a simple C64-only
workflow materially improves on OBS and remains supportable across all platforms.
A later proposal must choose maintained transport/encoder components and check
current official YouTube ingest requirements; no endpoint or key format is assumed here.
The computer performs encoding/transmission. Require preview, explicit Go Live/Stop,
Connecting/Live/Stopping/Failed states and visible destination. Never broadcast
at startup, reconnect, or after restoring preferences. Store keys using existing
platform credential abstractions (session-only if secure storage is unavailable),
mask entry, redact logs/reports, and avoid exposing keys in process arguments.

## Development rules and release gates

- Separate communication (`api`, receiver, transfers), media processing/timing,
  pure data models and GTK presentation. Networking, decoding/conversion, encoding,
  hashing, disk traversal and export run off the UI thread; GTK updates stay on it.
  Use bounded queues and explicit cancellation/session ownership, not one giant UI module.
- Do not change system networking/firewall rules or persistent C64U settings without
  asking Bruce. Stream Start/Stop remain explicit actions; opening a viewer alone
  must not silently retarget an existing C64U stream. Never enable DMA automatically.
- Preserve file overwrite review, changed-target checks, recording behavior and
  credential handling. Check capture save/replace races separately: the current
  recorder publishes with `os.replace`, so chooser confirmation alone is not a
  concurrent-file protection guarantee.
- Keep GNOME-friendly controls, keyboard access and dialogs. Evaluate dependencies
  against packaged Debian, Windows installer/portable, and Mac Apple Silicon/Intel.
  Do not raise the GTK minimum silently. Keep working configurations compatible.
- Use topic branches/PRs; main requires PRs. Do not build the whole roadmap at once.
  Each PR documents changes, automated results, remaining limits and required
  hardware checks. Publish development packages before stable promotion.
- Existing decoder/session, transfer, replacement and lifecycle tests are useful
  foundations. Runtime startup checks find required codec elements; they do not
  establish A/V synchronization or a successful recording export. Add meaningful
  recorder/media integration tests before modifying that path.
- Automated synthetic tests do not replace Bruce's real-C64U checks. Record exact
  app build, OS/architecture, GTK/GStreamer/OBS versions, firmware/API, video mode,
  wired address, result and measured limits. PAL/NTSC changes, mic/camera permission,
  unplug/reconnect and destructive restore tests need explicit hardware-test agreement.
  Never include real credentials or copyrighted game/ROM files as test fixtures.

## Sources and scope of confidence

[Ultimate REST reference](https://1541u-documentation.readthedocs.io/en/latest/api/api_calls.html)
and [Data Streams](https://1541u-documentation.readthedocs.io/en/latest/data_streams.html)
were checked on 2026-09-13 alongside Argonaut's implemented routes and tests.
Upstream documentation describes the broader Ultimate family and evolving firmware;
its 3.x numbering does not establish feature availability on Bruce's C64U 1.1.0.
Pin any future firmware-source evidence to a commit and test the specific target.
This review sent no commands to a C64U, performed no OBS capture, and makes no new
hardware, sync, backup or broadcasting success claim.
