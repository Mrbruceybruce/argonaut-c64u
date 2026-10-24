# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Explicit, one-shot GTK liveness evidence; never attempts recovery.

Only the main thread publishes phase/state. The watchdog never calls GTK or
acquires application/media locks. Stack records contain code locations only.
"""
from contextlib import contextmanager
from functools import wraps
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time

PHASES = frozenset(('idle', 'navigation', 'stream-start', 'stream-tick',
                    'stream-stop', 'stream-close', 'replay-toggle', 'record'))
STATE_KEYS = ('stream', 'audio', 'replay', 'recording', 'replay_exporting')
MAX_THREADS = 64
MAX_FRAMES = 48
MAX_BYTES = 65536
# Fixed module labels also work in frozen packages without source .py files.
CODE_FILES = frozenset(('gui.py', 'streams_tab.py', 'streaming.py',
                        'recording.py', 'replay_buffer.py', 'settings_tab.py',
                        'drives_tab.py', 'api.py', 'mainloop_diagnostics.py'))


def code_location(filename):
    parts = filename.replace('\\', '/').split('/')
    if len(parts) >= 2 and parts[-2] == 'c64u_browser' and parts[-1] in CODE_FILES:
        return parts[-1]
    return '<external>'


def observed(phase):
    """Instrument a GTK callback without changing its result or exceptions."""
    def decorate(function):
        @wraps(function)
        def call(owner, *args, **kwargs):
            app = getattr(owner, 'app', owner)
            monitor = getattr(app, 'mainloop_diagnostics', None)
            if monitor is None:
                return function(owner, *args, **kwargs)
            tab = getattr(app, 'streams_tab', None)
            state = {key: getattr(tab, attr, None) is not None for key, attr in
                     (('stream', 'session'), ('audio', 'output'),
                      ('recording', 'recorder'))}
            # Preserve report compatibility; Instant Replay is retired.
            state.update(replay=False, replay_exporting=False)
            with monitor.phase(phase, state):
                return function(owner, *args, **kwargs)
        return call
    return decorate


class Watchdog:
    def __init__(self, sink, build, *, clock=time.monotonic,
                 frames=sys._current_frames, thread_factory=threading.Thread):
        self.sink = sink
        self.build = build if isinstance(build, str) and re.fullmatch(r'[0-9a-f]{40}', build) else 'unknown'
        self.clock = clock
        self.frames = frames
        self.thread_factory = thread_factory
        self.main_thread = threading.get_ident()
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.last_beat = clock()
        self.current_phase = 'idle'
        self.state = {}
        self.reported = False
        self.worker = None
        self.source = None
        self.remove_source = None
        # Allowlisted application paths only. Never log arbitrary code filenames,
        # function names, source text, locals, thread names, or exception messages.

    def start(self, add_timeout, remove_source):
        self.remove_source = remove_source
        self.source = add_timeout(1000, self.heartbeat)
        self.worker = self.thread_factory(target=self._run,
                                         name='mainloop-watchdog', daemon=True)
        try:
            self.worker.start()
        except Exception:
            self.close()
            raise

    def heartbeat(self):
        with self.lock:
            if self.stopped.is_set():
                return False
            self.last_beat = self.clock()
        return True

    @contextmanager
    def phase(self, label, state):
        with self.lock:
            previous = self.current_phase, self.state
            self.current_phase = label if label in PHASES else 'idle'
            self.state = {key: state[key] for key in STATE_KEYS
                          if type(state.get(key)) is bool}
        try:
            yield
        finally:
            with self.lock:
                self.current_phase, self.state = previous

    def check(self):
        """One check, also usable with a fake clock in offline tests."""
        with self.lock:
            elapsed = self.clock() - self.last_beat
            if self.stopped.is_set() or self.reported or elapsed < 5:
                return False
            self.reported = True
            report = {'schema': 1, 'event': 'gtk-heartbeat-stall',
                      'timestamp': time.time(), 'build': self.build,
                      'missed_seconds': round(elapsed, 3),
                      'phase': self.current_phase, 'state_at_phase_entry': dict(self.state),
                      'main_thread': self.main_thread}
        try:
            report['threads'] = self._stacks()
            if not self.stopped.is_set():
                self.sink(report)
        except Exception:
            # Diagnostics must not affect application behavior; no exception prose.
            pass
        return True

    def _stacks(self):
        frames = self.frames()
        result = []
        try:
            ids = sorted(frames, key=lambda ident: (ident != self.main_thread, ident))
            for ident in ids[:MAX_THREADS]:
                frame = frames[ident]
                stack = []
                for _ in range(MAX_FRAMES):
                    if frame is None:
                        break
                    stack.append({'file': code_location(frame.f_code.co_filename),
                                  'line': frame.f_lineno})
                    frame = frame.f_back
                result.append({'thread': ident, 'stack': stack,
                               'frames_truncated': frame is not None})
            return {'items': result, 'threads_truncated': len(ids) > MAX_THREADS}
        finally:
            # Do not retain frames/locals after capture.
            frame = None
            frames.clear()

    def _run(self):
        while not self.stopped.wait(1):
            if self.check():
                return

    def close(self):
        self.stopped.set()
        if self.source is not None:
            source, self.source = self.source, None
            self.remove_source(source)
        worker = self.worker
        if worker is not None and worker.ident is not None and worker is not threading.current_thread():
            worker.join(timeout=0.2)


@contextmanager
def _report_directory(preferences_path):
    """Pin every path component before using it; never resolve symlinks."""
    if (not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY')
            or os.open not in os.supports_dir_fd
            or os.mkdir not in os.supports_dir_fd or not hasattr(os, 'fchmod')):
        raise OSError('Secure diagnostic directory operations unavailable')
    directory = Path(preferences_path).parent / 'diagnostics'
    if '..' in directory.parts:
        raise OSError('Parent traversal in diagnostic directory')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(directory.anchor or '.', flags)
    try:
        parts = directory.parts[1:] if directory.anchor else directory.parts
        for part in parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        os.fchmod(fd, 0o700)
        yield fd
    finally:
        os.close(fd)


def write_report(preferences_path, report):
    """One private, capped file, overwritten on the next diagnosed launch."""
    payload = json.dumps(report, separators=(',', ':')).encode('utf-8')
    while len(payload) > MAX_BYTES and report['threads']['items']:
        report['threads']['items'].pop()
        report['threads']['threads_truncated'] = True
        payload = json.dumps(report, separators=(',', ':')).encode('utf-8')
    if len(payload) > MAX_BYTES:
        return
    with _report_directory(preferences_path) as directory_fd:
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0)
        fd = os.open('mainloop-stall.json', flags, 0o600, dir_fd=directory_fd)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return
            os.fchmod(fd, 0o600)
            os.ftruncate(fd, 0)
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(payload)
        finally:
            os.close(fd)


def start_diagnostics(preferences, add_timeout, remove_source, *, environ=None):
    from .test_lab_access import enabled
    from .version import build_info
    environ = os.environ if environ is None else environ
    if not enabled(preferences) or environ.get('ARGONAUT_MAINLOOP_DIAGNOSTICS') != '1':
        return None
    monitor = None
    try:
        monitor = Watchdog(lambda report: write_report(preferences.path, report),
                           build_info()['build'])
        monitor.start(add_timeout, remove_source)
        return monitor
    except Exception:
        if monitor is not None:
            monitor.close()
        return None
