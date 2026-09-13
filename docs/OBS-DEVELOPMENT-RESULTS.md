# OBS development results

2026-09-13. Local branch: `feature/obs-capture`. This is a development increment,
not a stable release or a claim of cross-platform OBS qualification.

## Delivered

- A separate **Argonaut — C64 Capture** window shares the existing stream. No
  application controls appear in its canvas; native raster aspect, nearest-neighbor
  scaling, optional integer enlargement and black letterboxing are provided.
- A media worker owns frame conversion, audio monitoring and recorder input.
  GTK consumes only the latest display frame, so a slow view does not directly
  stall recording. Queues remain bounded. Both views blank after stale video.
- Existing PNG capture and WebM VP8/Vorbis recording remain available. Recording
  creation/finalization runs off GTK; quitting waits asynchronously for stream and
  writer cleanup. Recording replacement needs explicit confirmation and a target
  identity recheck. A newly appearing destination is not overwritten.
- Copyable diagnostics distinguish received traffic, incomplete frames, estimated
  audio gaps, receiver/display queue drops and submitted recording frames. Reports
  omit credentials, keys, raw errors, device identifiers and paths. IP addresses
  are opt-in. Diagnostics do not send commands or change network settings.
- GTK 4.8 has a Cairo nearest-neighbor fallback. The Debian package explicitly
  depends on `python3-gi-cairo`; newer GTK uses scaled textures directly.
- The [OBS guide](OBS-GUIDE.md) covers capture sources, C64 audio, mic/webcam,
  duplicate audio avoidance and simultaneous Argonaut/OBS recording.

## Automated and local visual verification

On Debian, Python 3.13, GTK 4.18 and GStreamer 1.26.2:

- Regular suite: **186 tests discovered, 177 passed, 9 opt-in display tests skipped**.
- Separate display run: **all 9 passed**, including existing Preferences tests and
  the four new capture/diagnostics tests. GTK emitted deprecation warnings, no failures.
- Real GStreamer tests wrote and decoded WebM with and without audio, checked
  monotonic timestamps, overwrite protection and video-mode change finalization.
- An accelerated 30-minute nominal-clock test checked timestamp generation; gap
  re-anchoring and encoder backlog failures were exercised. This is not a real
  30-minute recording and does not establish actual C64U audio/video sync.
- Worker tests verified continued recorder input while GTK did not drain display
  frames, independent recording stop and cancellation before writer creation. A lifecycle test checks deferred quit without duplicate timers.
- Synthetic GTK rendering was visually inspected: a 384x240 checkerboard rendered
  as a crisp 768x480 image centered within a 900x700 black canvas. Both the normal
  rendering path and forced Cairo fallback passed display checks.

No real C64U commands, firmware changes, firewall changes or system network changes
were used for this verification. Stable Argonaut and the installed development
application were not replaced. No GitHub release was published.

## Remaining limitations and hardware checks

1. **OBS and actual C64U A/V sync are unverified.** Test sound, clean window capture
   and simultaneous WebM/OBS recording first on Debian, then Windows and macOS.
2. The existing nominal 48 kHz / 30 fps recorder policy remains. Physical source
   clock correction, full-rate 50/60 fps recording and calibrated PAL/NTSC pixel
   aspect are not claimed. Received FPS can exceed recorded FPS.
3. The eight-second no-complete-video timeout remains. Audio gaps are estimates;
   exact video packet loss, sink drops and compositor presentation are not measured.
4. OS capture decorations, minimized-window behavior, Wayland portal choices,
   fractional desktop scaling and audio routing need platform-specific checks.
5. The recorder has its existing ten-second EOS wait. Media cleanup happens off
   GTK; a lower-level driver teardown stall is not covered by that EOS timeout.
6. Destination identity is checked before explicitly approved replacement, but
   another process changing an existing destination in the final check/replace
   interval is not protected by an OS-wide file lock.

Bruce's first check: Start preview with audio, open the capture window, select it
in OBS, make a short recording in both applications, and replay both. Then use the
fillable OBS checklist for longer sync and lifecycle tests. Network interruption
or a flash/click test program should be agreed separately before changing the
running C64 session. Do not promote this increment before those checks pass.

The other roadmap features remain planned, not implemented by this increment.
