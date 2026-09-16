# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Opt-in, session-only headless monitor for read-only C64U checks."""
import argparse
import io
import json
import sys
import time

from .test_lab_cli import main as run_once
from .test_lab_fleet import main as run_fleet


def monitor(interval_seconds, max_runs, run, stdout, sleeper=time.sleep):
    """Run sequentially; wait after completion, so missed intervals never catch up."""
    aggregate = 0
    number = 0
    while max_runs == 0 or number < max_runs:
        code, result = run()
        if result is None:
            return 3
        number += 1
        stdout.write(json.dumps({'schema': 1, 'run': number,
                                 'exit_code': code, 'result': result}, sort_keys=True) + '\n')
        stdout.flush()
        if code == 3:
            return 3
        if code == 1:
            aggregate = 1
        elif code == 2 and aggregate == 0:
            aggregate = 2
        if max_runs and number >= max_runs:
            break
        sleeper(interval_seconds)
    return aggregate


def main(argv=None, stdin=None, stdout=None, stderr=None, sleeper=time.sleep):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = argparse.ArgumentParser(description='Repeat read-only Argonaut C64U checks without the GUI.')
    parser.add_argument('--interval-minutes', type=int, default=30,
                        help='Minutes after each completed run before the next (5-1440).')
    parser.add_argument('--runs', type=int, default=0,
                        help='Stop after this many runs; 0 continues until interrupted.')
    parser.add_argument('--timeout', type=int, default=10,
                        help='Hardware network timeout in seconds (1-30).')
    parser.add_argument('--device-id',
                        help='Monitor the Development profile bound to this C64U ID.')
    parser.add_argument('--all-profiles', action='store_true',
                        help='Check every identity-bound Development connection each interval.')
    parser.add_argument('--password-stdin', action='store_true',
                        help='Read one password line once and reuse it in this process only.')
    parser.add_argument('--explain-failures', action='store_true')
    parser.add_argument('--ai-provider', choices=('ollama', 'openai'))
    parser.add_argument('--ai-model')
    args = parser.parse_args(argv)
    if args.all_profiles and args.device_id is not None:
        parser.error('--all-profiles and --device-id cannot be combined')
    if not 5 <= args.interval_minutes <= 1440:
        parser.error('--interval-minutes must be between 5 and 1440')
    if args.runs < 0:
        parser.error('--runs must be zero or greater')
    if not 1 <= args.timeout <= 30:
        parser.error('--timeout must be between 1 and 30 seconds')
    password = stdin.readline(1026) if args.password_stdin else ''
    command = ['--timeout', str(args.timeout)]
    if not args.all_profiles:
        command[:0] = ['--suite', 'hardware']
    if args.device_id is not None:
        command.extend(['--device-id', args.device_id])
    if args.password_stdin:
        command.append('--password-stdin')
    if args.explain_failures:
        command.append('--explain-failures')
    if args.ai_provider:
        command.extend(['--ai-provider', args.ai_provider])
    if args.ai_model:
        command.extend(['--ai-model', args.ai_model])

    def run():
        buffer = io.StringIO()
        runner = run_fleet if args.all_profiles else run_once
        code = runner(command, stdin=io.StringIO(password), stdout=buffer, stderr=stderr)
        content = buffer.getvalue()
        return code, json.loads(content) if content else None

    try:
        return monitor(args.interval_minutes * 60, args.runs, run, stdout, sleeper)
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
