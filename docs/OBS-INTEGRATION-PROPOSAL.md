# Proposal: clean C64 capture for OBS

Status: proposed, not implemented. Companion to the [roadmap](ROADMAP.md).
Reviewed baseline: Argonaut 1.5 / `main` at `5d1b270`, 2026-09-13.

## Outcome and scope

Add **Open capture window** to Streams. It opens a separate, stable-titled
**Argonaut — C64 Capture** window whose content is only the C64 picture and
letterboxing. OBS captures that window while Bruce continues using Argonaut's
controls elsewhere. Existing **Start recording**, WebM audio/video, PNG screenshots,
recording folders and Stop behavior remain available without OBS installed.

Do not build an OBS plugin, virtual camera, browser server, RTMP output, microphone
mixer or replay buffer in this increment. OBS supplies scene composition, mic,
webcam and eventual broadcast controls. No additional network endpoint or C64U
API command is required by the proposed clean view.

## Baseline and the reason for a small preparatory change

`StreamSession` already owns remote stream commands and one UDP `Receiver`.
`StreamsTab.tick()` currently drains receiver data every 33 ms, converts pixels,
updates the picture, and feeds both the existing recorder and local audio.
`Receiver.take()` consumes samples and clears the latest frame. A second caller
would steal data from recording/audio: **the capture window must never call take()**.

The latest-frame slot bounds latency but discards intermediate display frames.
Received FPS is not recorded FPS. The existing writer declares 30 fps, timestamps
video at feed time, advances audio using nominal 48 kHz samples, and re-anchors
after large gaps. `AudioOutput` uses `sync=false` and has its own dropping policy.
The two UDP streams have no shared capture timestamp in the documented packet
headers, so exact source synchronization cannot be claimed from packet reception alone.

The [upstream stream specification](https://1541u-documentation.readthedocs.io/en/latest/data_streams.html#available-streams)
describes a cropped raster of 384×272 (PAL) or 384×240 (NTSC), sequence-numbered
192-sample stereo audio packets, and clocks approximately 47,983 / 47,940 Hz.
Argonaut currently treats audio as 48,000 Hz. Confirm those clocks on the target
firmware before choosing a correction. Treat arrival jitter, nominal-clock error,
queue drops and output-device latency as separate causes of sync error.

## Proposed architecture

```text
C64U -- existing REST start/stop + UDP --> StreamSession / Receiver
                                              |
                                 one bounded media dispatcher
                                   /          |          \
                     latest display frame   Recorder    AudioOutput
                          /       \          WebM       computer audio
                Streams picture   Capture window            |
                                      |                     |
                                      +---- OS capture -----+--> OBS
```

Keep the existing control/transfer worker separate from continuous media work.
A media worker drains the receiver, assigns media timing and converts a frame
once. It publishes immutable frame data into bounded consumer queues. The GTK
thread creates/reuses display textures and updates widgets; it performs no network
waits, encoding, heavy pixel conversion or file writing. GStreamer initialization,
feed/error processing and shutdown belong to the media owner rather than UI callbacks.

Suggested small module boundaries (names provisional):

| Responsibility | Existing base / proposed placement |
| --- | --- |
| REST and UDP lifecycle, peer filtering | `api.py`, `streaming.py`; retain supported calls |
| Timing, queues, consumer ownership | Small `media_session.py`, independent of GTK |
| Counters and safe report | Pure `stream_diagnostics.py` snapshot/formatter |
| Display geometry and frame presentation | Pure `video_geometry.py` + GTK video widget |
| Capture window | `capture_window.py`, no sockets or encoder |
| Recording | Extend `recording.py` behind its existing user-visible contract |
| Start/Stop/settings UI | `streams_tab.py`, observes state and requests actions |

Use one session generation to reject old frames/callbacks after device switching.
Latest-only display queues may drop frames; recorder input must have its own bounded
queue and explicit overflow policy. Audio queue eviction must be counted, not silent.
Provisional budgets: latest display frame per view, at most four raw recording
frames and 250 ms queued audio, with bounded encoder queues too. Measure and tune
these on all packages. A slow capture window must not block reception or corrupt
recording. Failure stops the affected consumer with an explanation; finalize what
can be saved. Do not hide errors to keep a green status label.

Do not combine a clock-policy rewrite with the first window change. Characterize
the current writer first, separate its handoff from GTK while retaining its output
policy, then address measured timing defects in a focused follow-up before declaring
OBS support complete. Keep 30 fps recording support; full 50/60 Hz recording is a
separate qualified improvement, not an implicit promise of this window feature.

## Capture-window behavior

- Open/focus one capture window; no automatic stream start, device reconfiguration,
  recording or broadcasting. If stopped, show a black canvas and explain how to
  Start preview in the main window. No diagnostic overlays inside the canvas.
- Give the window a stable title without device name, address or FPS. Keep menus,
  buttons, selection borders, tooltips and notifications out of the captured client
  area. OS decorations can be excluded using OBS client-area capture or cropped
  as documented per platform. Test this rather than assuming every compositor agrees.
- Put fit/integer-scale/aspect choices beside the Open capture window control in
  Streams, not over the picture. Keep existing in-tab scale preferences intact.
  Resize the capture window with letterboxing, never stretch to arbitrary bounds.
  It need not enlarge Argonaut's main window or add scrollbars to the capture canvas.
- Closing the capture window detaches that view only; recording and preview continue.
  Stop preview retains current recording-finalization semantics and blanks both views.
  Switching device blanks immediately. When signal becomes stale (proposed 2 seconds),
  blank the capture canvas and show the explanation in Streams, so old gameplay
  is not silently presented as live. Retain the existing eight-second session timeout
  unless a separately tested change justifies adjusting it.
- Closing the application uses the current guarded Quit path and waits asynchronously
  for bounded recorder finalization/stream cleanup. Cover an open capture window
  and a recording in progress; do not introduce orphan windows or new implicit retries.
- Keep the capture window visible while OBS captures; verify obscured/minimized,
  other-tab and main-window-minimized behavior on each OS. Document compositor limits
  rather than claiming hidden windows always keep rendering.

## Aspect ratio and crisp scaling

Raster dimensions are not a complete physical pixel-aspect specification. Preserve
all streamed border pixels by default; do not label a blind stretch of the cropped
raster to 4:3 as “correct.” Start with explicitly named **Native pixels** (unchanged
raster ratio) plus a planned **Display aspect** mode whose PAL/NTSC geometry is
verified against authoritative firmware rendering and a physical reference.
If evidence is insufficient, label Display aspect experimental or defer its release;
do not silently guess pixel ratios from frame height. A 4:3 canvas can letterbox
native output but is not itself proof of correct C64 geometry.

Offer integer 1×/2×/3× sizes and Fit with aspect-preserving letterboxing. Integer
native-pixel scaling gives uniform pixel blocks; corrected pixel aspect or fractional
HiDPI scaling can require uneven sample widths. Document that tradeoff and test
checkerboards, circles and border markers at 100%, 150% and 200% desktop scale.
PNG capture and normal recording stay at source resolution; changing the clean
view's geometry must not resize or distort the recorded source frames.

Use explicit nearest-neighbor filtering, not a bigger `Gtk.Picture` alone.
[GTK's append_scaled_texture](https://docs.gtk.org/gtk4/method.Snapshot.append_scaled_texture.html)
provides filter control starting in GTK 4.10, while README permits GTK 4.8.
Feature-detect it; validate a GTK-4.8 nearest-neighbor fallback using already shipped
rendering facilities, or separately propose a minimum-version change. Do not add
Pillow or another runtime dependency solely for this without package review.
Renderer/HiDPI results on Windows and macOS are release gates.

## OBS setup guide to deliver with the feature

These are proposed instructions based on OBS documentation, not a claim that the
new window has been tested. Capture the existing app as a temporary manual workaround;
the named clean capture window will exist only after implementation.

1. Connect Argonaut to the wired C64U profile. Enable audio **before** Start preview
   when sound is wanted; the current checkbox controls audio reception as well as
   monitoring. Start preview, then open the capture window. Do not change C64U
   destinations manually to point at OBS; Argonaut remains the receiver.
2. Add the appropriate OBS source and select **Argonaut — C64 Capture**. Exclude
   cursor and decorations where available. Fit while retaining aspect; avoid Stretch.
   Keep the selected window available and check the OBS picture after resizing.
3. Capture Argonaut's computer audio using one path below. Watch its meter, then
   make a short recording to confirm it contains sound. Avoid adding the same
   output both globally and per-scene, which duplicates sound.
4. Add the microphone as a separate audio input and webcam as a Video Capture
   source. Use headphones while testing to avoid acoustic feedback. Position webcam
   in OBS. Neither input is added to Argonaut's existing WebM recording in this scope.
5. First use OBS **Start Recording**, not Go Live. Play back the file and check
   video, sound, mic, webcam and sync. Argonaut's recording can run simultaneously;
   it still contains the C64 feed rather than the OBS scene composition.

| Platform | Picture | C64 audio and portability checks |
| --- | --- | --- |
| Debian / GNOME Wayland | OBS PipeWire capture through the desktop portal; select the capture window if offered | Select the appropriate output monitor in OBS's PulseAudio-compatible capture. Availability depends on installed OBS/backend; verify meter and device. An output monitor may include other computer sounds. Do not automatically reconfigure PipeWire/PulseAudio. |
| Linux X11 | Window Capture (Xcomposite) | Same explicit output-monitor selection and isolation caveat; confirm compositor behavior. |
| Windows 10/11 | Window Capture, preferably client area | OBS application-audio capture for Argonaut; supported Window Capture audio is another option. If the GStreamer sink cannot be isolated, document an explicitly chosen output capture fallback and its scope. |
| macOS 15+, Apple Silicon / Intel | macOS Screen Capture in Window mode | Use captured application audio, or a separate macOS Audio Capture source selecting Argonaut. Test the actual packaged GStreamer output; avoid two simultaneous captures of the same sound. Grant Screen Recording, mic/camera permissions through macOS when needed. |

These choices follow OBS's [window capture](https://obsproject.com/kb/window-capture-sources),
[Windows application audio](https://obsproject.com/kb/application-audio-capture-guide),
[Mac screen capture](https://obsproject.com/kb/macos-screen-capture-source),
[Mac audio](https://obsproject.com/kb/macos-desktop-audio-capture-guide),
[audio sources](https://obsproject.com/kb/audio-sources) and
[Mac permissions](https://obsproject.com/kb/macos-permissions-guide) documentation,
checked 2026-09-13. OBS controls vary by version/backend; list tested versions in
the eventual user guide. No new audio driver or virtual cable is an initial requirement.

## Synchronization and recording qualification

Create an original, small C64 test program that produces a repeated visible flash
and click from a known common trigger. Running it requires Bruce's agreement because
it replaces the current C64 program. Compare both an OBS recording and Argonaut WebM
at the beginning and end of a 30-minute run, with intermediate markers. Inspect frame
transitions and audio peaks, not just listening impression. Record constant offset,
change in offset, dropped media, output sample rate and CPU/memory behavior.

Proposed acceptance target: absolute A/V offset at most 80 ms after an explicitly
recorded OBS sync adjustment, drift no more than 40 ms across 30 minutes, and no
unexplained audio discontinuities on a healthy wired link. These are targets, not
measurements. Measure Argonaut's WebM separately without relying on an OBS adjustment.
If either fails, investigate timing/resampling before declaring the feature ready.
Do not assume nominal 48 kHz resampling corrects a mistimestamped source clock.

Test PAL and NTSC when available, using only approved device-setting changes.
Timestamp monotonicity, actual file duration, audio sample count and playable output
must agree within stated tolerance. Exercise loss/reordering and UI stalls in
synthetic tests. Distinguish source/network loss, view frame skipping, deliberate
recording frame-rate conversion, encoder overload and OBS rendering/encoding drops.
A static offset can be calibrated; growing drift requires a timing fix.

## Small PR sequence and acceptance

| PR | Deliverable | Automated checks | Bruce / hardware checks |
| --- | --- | --- | --- |
| A — baseline | Synthetic timestamped frame/audio fixtures; record current behavior; pure stats snapshots | Existing stream/lifecycle tests; real GStreamer WebM encode/decode with and without audio, mode change, EOS/error/quit and destination collisions; planted-secret report tests | Short known-good current WebM on each available platform; no settings changes |
| B — shared media delivery | One bounded dispatcher; UI only renders state; preserve writer contract | No duplicate socket/start calls; independent consumers; queue overflow, cancellation, stale generation, UI stall; compare output timing with A | Preview and recording together, tab switching, stop/reconnect; report responsiveness |
| C — clean view | Stable-titled canvas, explicit scale/aspect policy, guide draft | Geometry and raster tests; mocked window lifecycle; GTK smoke tests where runtime exists; no remote actions when opening/closing view | OBS window/audio capture on Debian, Windows, both Macs; HiDPI, decorations, resize, mic/webcam, capture-window close during recording |
| D — qualification | Measured sync fixes only if needed; final guide and test matrix | Timestamp/gap regression cases; packaged codec tests; long synthetic bounded-resource run | 30-minute flash/click comparison with simultaneous OBS + Argonaut recording; approved PAL/NTSC and cable interruption; inspect saved files |

No broader roadmap implementation is bundled into these PRs. For PR A, start with
`tests/test_streaming.py`, `tests/test_app_lifecycle.py`, new recorder integration
fixtures and a pure diagnostics model; defer the UI feature until that baseline
exists. Tests needing GTK/GStreamer must run on equipped jobs, with skipped tests
reported explicitly. CI codec discovery alone does not prove file playback or sync.

Keep file-chooser overwrite confirmation and add changed-destination revalidation
where the media tests expose a gap; never silently replace a file created after
review. Failed finalization must preserve a clearly identified partial recording
and never report success. Maintain all existing recording controls throughout.

## Initial review results and next decision

Completed now: code/README/recent-history inspection, primary-documentation review,
feature inventory, dependency order, architecture and test proposal. No application
code changed; no C64U, firewall, networking, OBS scene, recording or broadcast was
started. No new automated feature test or hardware test was run in this documentation pass.

Recommended next action: implement **PR A only**, then review its measured results
with Bruce before PR B. Bruce has no immediate hardware action for this roadmap.
Later checks require the current device/firmware identity, a wired connection, the
platforms available for OBS testing, and approval before replacing a running C64
program or changing its video mode.
