# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit bound-profile CLI reads through the Core application boundary."""
from dataclasses import asdict
import json
import signal
import sys

from .api import BrowserError, safe_argument
from .core import ArgonautCore
from .fresh_folder_cli import resolve_profile, private_password, drain
from .transfers import remote_file


def run(args):
    core = None
    active = [None]
    cancelled = [False]
    prior_handler = None
    phase = 'profile'
    result = None
    code = 1
    error = None
    category = None

    def interrupt(signum, frame):
        cancelled[0] = True
        if phase == 'credential':raise KeyboardInterrupt()
        if active[0] is not None:active[0].request_cancel()

    def check():
        if cancelled[0]:raise KeyboardInterrupt()

    def progress(count):
        print(f'\rTransferred {count:,} bytes', end='', file=sys.stderr, flush=True)

    try:
        safe_argument(args.path)
        if args.command == 'ls' and not args.path.startswith('/'):
            raise BrowserError('Absolute directory required.')
        if args.command == 'get':remote_file(args.path)
        prior_handler = signal.signal(signal.SIGINT, interrupt)
        core = ArgonautCore().load()
        profile = resolve_profile(core, args.profile_id)
        phase = 'credential'
        entered = private_password() if args.password else ''
        check()
        phase = 'connection'
        core.connect(profile, entered_password=entered, require_bound=True,
                     bind_identity=False, persist=False, remember=False, initial_browse=False)
        entered = ''
        check()
        phase = 'read'
        active[0] = (core.list_directory(args.path) if args.command == 'ls' else
                     core.download(args.path, args.destination, progress))
        snapshot = drain(active[0], cancelled)
        if snapshot.state == 'succeeded':
            if args.command == 'ls':
                path, entries = snapshot.result
                result = dict(path=path, entries=[asdict(entry) for entry in entries])
            else:
                result = snapshot.result
            code = 0
        elif snapshot.state == 'cancelled':
            code = 130
            error = 'Read cancelled; inspect the local destination before retrying.'
        else:
            category = snapshot.error.code if snapshot.error else 'read'
            raise BrowserError() from None
    except (KeyboardInterrupt, EOFError):
        code = 130
        error = 'Read cancelled; inspect the local destination before retrying.'
    except Exception as exc:
        category = getattr(exc, 'code', None) or getattr(exc, 'kind', None) or category or phase
        category = category if category in ('identity', 'session', 'authentication', 'network', 'host', 'profile', 'credential', 'connection', 'read', 'filesystem') else phase
        error = 'Read failed (' + category + ').'
    finally:
        if active[0] is not None and active[0].snapshot().state not in ('succeeded', 'failed', 'cancelled'):
            cancelled[0] = True
            drain(active[0], cancelled)
        if core is not None:
            try:core.close()
            except Exception:
                error = 'Read cleanup failed; inspect the local destination before retrying.'
                code = 1
        if prior_handler is not None:signal.signal(signal.SIGINT, prior_handler)
    if args.command == 'get' and active[0] is not None:print(file=sys.stderr)
    if error:print(error, file=sys.stderr)
    if code == 0:print(json.dumps(result, indent=2))
    return code
