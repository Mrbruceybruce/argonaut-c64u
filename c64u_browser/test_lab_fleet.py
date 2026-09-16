# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Opt-in read-only Test Lab pass over bound Development connection profiles."""
import argparse
import io
import json
import sys

from .api import BrowserError, safe_argument
from .platform_support import config_base
from .profiles import Preferences
from .test_lab_cli import MAX_PASSWORD_LENGTH, main as run_profile
from .test_lab_history import profile_scope_key


def main(argv=None, stdin=None, stdout=None, stderr=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = argparse.ArgumentParser(description='Check every bound Argonaut Development connection.')
    parser.add_argument('--timeout', type=int, default=10,
                        help='Hardware network timeout in seconds (1-30).')
    parser.add_argument('--password-stdin', action='store_true',
                        help='Read one password line for this run only.')
    parser.add_argument('--explain-failures', action='store_true')
    parser.add_argument('--ai-provider', choices=('ollama', 'openai'))
    parser.add_argument('--ai-model')
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 30:
        parser.error('--timeout must be between 1 and 30 seconds')
    try:
        password = (stdin.readline(MAX_PASSWORD_LENGTH + 2).rstrip('\r\n')
                    if args.password_stdin else '')
        if len(password) > MAX_PASSWORD_LENGTH:
            raise BrowserError('Password input was too long.')
        safe_argument(password)
        preferences = Preferences(config_base() / 'argonaut-development' / 'config.json').load()
    except (BrowserError, OSError, ValueError) as exc:
        print('Test Lab fleet could not start: ' + str(exc), file=stderr)
        return 3

    profiles = sorted((profile for profile in preferences.profiles
                       if profile.device_id or profile.device_mac),
                      key=lambda profile: profile_scope_key(profile.id))
    results = []
    failed_setup = False
    for profile in profiles:
        command = ['--suite', 'hardware', '--profile-id', profile.id,
                   '--timeout', str(args.timeout)]
        if args.password_stdin:
            command.append('--password-stdin')
        if args.explain_failures:
            command.append('--explain-failures')
        if args.ai_provider:
            command.extend(['--ai-provider', args.ai_provider])
        if args.ai_model:
            command.extend(['--ai-model', args.ai_model])
        buffer = io.StringIO()
        code = run_profile(command, stdin=io.StringIO(password + '\n'),
                           stdout=buffer, stderr=stderr)
        try:
            report = json.loads(buffer.getvalue()) if buffer.getvalue() else None
        except ValueError:
            report = None
        results.append({'key': profile_scope_key(profile.id)[:16],
                        'exit_code': code, 'result': report})
        if code == 3 or report is None:
            failed_setup = True
            break

    statuses = [item['result']['status'] for item in results if item['result']]
    overall = ('error' if failed_setup else
               'fail' if 'fail' in statuses else
               'skip' if not statuses or set(statuses) == {'skip'} else 'pass')
    stdout.write(json.dumps({'schema': 1, 'suite': 'hardware_profiles',
                             'status': overall, 'profiles': results}, sort_keys=True) + '\n')
    return {'pass': 0, 'fail': 1, 'skip': 2, 'error': 3}[overall]


if __name__ == '__main__':
    raise SystemExit(main())
