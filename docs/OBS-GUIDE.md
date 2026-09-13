# Capture Argonaut with OBS

Development feature; not yet in the stable 1.5 download. Local synthetic tests
passed on Debian, but C64U A/V synchronization and platform-specific OBS capture
still require the checks below. Existing Argonaut WebM recording remains available.

## Picture

1. Connect to the C64U's wired Ethernet profile. In Streams, enable **Play audio on
   this computer** if sound is wanted, then choose **Start preview**.
2. Choose **Open capture window**. It displays only the C64 picture and black
   letterboxing. Opening this window by itself does not start or retarget streams.
3. In OBS add a window capture source and select **Argonaut — C64 Capture**:
   - **Debian/GNOME Wayland:** use the PipeWire/desktop-portal capture source and
     choose the window if the portal offers it. On X11, use Window Capture (Xcomposite).
   - **Windows:** use Window Capture and enable Client Area where offered.
   - **Mac:** use macOS Screen Capture in Window mode.
4. Exclude the cursor, title bar and window shadow where the capture source permits.
   If decorations remain, crop them in OBS. Keep the capture window available;
   minimized-window capture depends on the OS/compositor and still needs testing.
5. Resize using Fit while preserving aspect, not Stretch. **Integer scaling** in
   Argonaut uses whole-number native-pixel enlargement when the window is large
   enough; turn it off for nearest-neighbor Fit. Smaller windows fit the full image.

The canvas preserves the streamed **native raster aspect** (384×272 or 384×240),
including the streamed border. It does not claim calibrated CRT pixel aspect or
stretch the cropped raster to 4:3. Physical PAL/NTSC display-aspect correction is
not yet qualified. Fractional desktop scaling can affect apparent pixel uniformity.
View scaling never changes PNG or WebM source dimensions.

Closing the capture window does not stop preview or recording. Stop preview stops
recording and finalizes it. After two seconds without complete video the picture
blanks rather than showing stale gameplay; errors remain in the main Streams tab.
The original eight-second no-complete-video timeout is retained.

## C64 audio, microphone and webcam

The audio checkbox currently enables both reception and local playback. Enable it
before starting preview. OBS captures that playback, not a second C64U network stream.

- **Windows:** use Application Audio Capture for Argonaut, or Window Capture's
  Capture Audio option when supported. Confirm the meter moves. Some audio output
  backends may need an explicitly chosen output-device capture instead.
- **Mac:** use the screen-capture source's audio or a separate macOS Audio Capture
  source selecting Argonaut. Do not capture the same sound twice.
- **Debian:** choose the playback output's monitor through OBS's PulseAudio-compatible
  audio source. Available names depend on the sound setup. An output monitor can
  include other computer sounds; check that before sharing or broadcasting.

Add the mic as a separate audio input source and the webcam as a Video Capture
source in OBS. Grant the relevant screen/audio/camera permissions through the OS
if prompted. Use headphones to avoid feedback. Disable duplicate global/per-scene
capture of the same audio device. Argonaut does not install virtual audio cables,
change system sound routing, firewall rules or networking.

Make a short **OBS recording** first and listen to it. OBS mixes the C64, mic and
webcam; Argonaut's own WebM contains only the C64 picture and optional C64 audio.
You may use both recorders together. Neither OBS nor a capture window is required
for Argonaut's normal Start recording function. Recording replacement now requires
explicit confirmation and checks that the chosen destination has not changed.

## Diagnostics

Choose **Diagnostics…** in Streams. Reports distinguish complete frames, invalid
packets, incomplete video frames, estimated audio sequence gaps, queue drops and
frames submitted to recording. Received FPS is not recording FPS. Reports do not
claim that missing sequence numbers prove network loss or identify a firewall as
certainly responsible. Audio-monitor input drops exclude internal sink/compositor
loss that Argonaut cannot measure.

**Copy report** excludes passwords, stream keys, raw errors, device identifiers
and file paths. Network addresses are hidden unless **Include network addresses**
is checked. Opening diagnostics is read-only. For support, add the build shown in
Preferences → About and the OBS/OS versions separately.

No video: check the C64U's wired connection, computer destination address and
incoming UDP 11000–11001. REST working does not prove UDP can reach the computer.
Another stream client, a VM route or a port conflict can also prevent reception.
No audio: confirm reception was enabled and the chosen OBS audio source sees it.
Argonaut never changes firewall rules automatically.

## Tests still required on real hardware

Record the exact Argonaut build, firmware/API, platform, OBS version and video mode.
Test a short OBS clip with C64 sound/mic/webcam, then simultaneous OBS and Argonaut
WebM recording. Close/reopen the capture window during recording, change tabs,
resize at normal and HiDPI desktop scale, and inspect both saved files.

For sync, use a repeated flash/click test program only after agreeing to replace
the running C64 program. Measure A/V offset at the start and end of 30 minutes,
plus intermediate points. Proposed target: offset ≤80 ms and drift ≤40 ms; any OBS
sync adjustment must be recorded and does not fix Argonaut's separate WebM file.
The accelerated nominal-clock test is not evidence that the actual C64U clock meets
these targets. The existing nominal 48 kHz / 30 fps recording policy is preserved;
physical clock correction and full-rate 50/60 fps recording remain unqualified.

Only with explicit agreement: repeat in another video mode and unplug/reconnect
the cable. Confirm truthful stopped/partial messages, playable finalized recording,
and no automatic stream or recording restart. Do not change firmware/network/video
settings just to complete this checklist without Bruce's approval.

## Authoritative references

Capture choices follow OBS documentation checked 2026-09-13:
[Window capture](https://obsproject.com/kb/window-capture-sources),
[Windows application audio](https://obsproject.com/kb/application-audio-capture-guide),
[Mac screen capture](https://obsproject.com/kb/macos-screen-capture-source),
[Mac audio](https://obsproject.com/kb/macos-desktop-audio-capture-guide),
[audio sources](https://obsproject.com/kb/audio-sources), and
[Mac permissions](https://obsproject.com/kb/macos-permissions-guide).
Source/backend names vary by OBS version. Protocol evidence and implementation
limitations are recorded in the [OBS proposal](OBS-INTEGRATION-PROPOSAL.md).
