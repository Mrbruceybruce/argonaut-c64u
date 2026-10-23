# Opt-in GTK stall evidence (Issue #23 / RM-015)

This diagnostic gathers evidence; it does not fix or recover a hang. Issue #18
geometry work and the migration board audit are separate.

## Enable for an approved diagnostic session

Developer Mode access is required (the Development launcher, or the existing
Developer Mode preference in the stable application). Additionally set
`ARGONAUT_MAINLOOP_DIAGNOSTICS=1` when launching a fresh process. Without both
conditions no heartbeat, watchdog worker or diagnostic file is created. Preference
changes take effect after restart, as with existing Developer Mode access.

For a source checkout, set `ARGONAUT_DEV_BUILD` to the full 40-character commit
hash when using the Development launcher. Packaged applications use their embedded
build identity. Unavailable or invalid identities are recorded as `unknown`.

The GTK heartbeat runs every second. A separate daemon watchdog checks once a
second and attempts one report after a heartbeat is at least five seconds old.
Navigation and stream start/tick/stop/close, recording and replay-toggle callbacks
publish their phase. The stream/audio/replay/recording/export flags are snapshots
at callback entry, not live queries from the watchdog. They indicate object
presence, not pipeline health. Nested callbacks restore both the outer phase and its state snapshot on return.

The report is `diagnostics/mainloop-stall.json` next to the active preferences
file. It is created only after a stall, capped at 64 KiB, and overwritten by the
next diagnosed launch. There are no rotated reports or repeated dumps. Review and
copy evidence before another diagnostic session. On POSIX the directory is 0700
and the file 0600; Windows access follows the user's profile permissions.

Reports contain a timestamp, validated build hash, phase, boolean state flags,
numeric thread identities, and stack code locations. They exclude locals, function
names, source lines, arbitrary filenames, thread names, exception messages,
credentials, device addresses and media/user content. Only a fixed list of relevant
application module names is emitted; other frames use `<external>` and a line
number. Python stacks are newest-frame-first, capped at 48 frames per thread and
64 threads (GTK/main thread first). Truncation is explicit, including any additional
threads removed to meet the byte cap. Frozen builds do not need source files for
these module labels.

Shutdown removes the heartbeat and signals the worker to stop, waiting at most
0.2 seconds. No application/media lock is taken by the watchdog, and it never
calls GTK, performs recovery, sends signals, kills a thread or changes a pipeline.
If report I/O itself blocks, the worker remains a daemon and cannot delay process
exit. Report failures are best effort and do not propagate into application work.

## Limits and next gate

Offline tests exercise the actual navigation and stream tick callback methods
with fake devices/media and a controlled clock. They verify healthy heartbeats,
audio/navigation stalls, bounded sanitized stacks, opt-in, file retention and
worker cleanup. This does not reproduce or resolve the physical-device hang.

A Python watchdog cannot run while native code holds the GIL indefinitely. Python
frames may identify only the application call into a native library. Native-stack
capture requires a separately approved procedure. Five-second pauses (including
system suspension or debugger pauses) can produce a report; a report is evidence
to investigate, not proof of a deadlock.

Physical C64U streaming/navigation and clean-shutdown testing require separate
approval. Root-cause selection and correction follow captured evidence. Repeated
navigation and an independent retest after replay removal remain acceptance gates.
Remove the environment flag and restart to disable this diagnostic.
