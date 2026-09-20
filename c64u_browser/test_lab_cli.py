# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Headless offline or opt-in read-only hardware Test Lab execution."""
import argparse
import json
import sys

from . import development
from .ai_analysis import analyze_failures
from .ai_gateway import AIGateway, GatewayConfig, GatewayError
from .api import BrowserError, safe_argument
from .hardware_checks import run_hardware_checks
from .platform_support import config_base
from .profiles import Preferences
from .test_lab import run_default_checks
from .test_lab_probe import run_diagnosis_probe
from .test_lab_history import run_with_history


MAX_PASSWORD_LENGTH = 1024


def profile_for_device(preferences, device_id=None):
    """Resolve only an identity-bound Development profile; never a raw host."""
    if device_id is None:
        return preferences.selected()
    if not device_id or len(device_id) > 120:
        raise BrowserError('Enter a valid saved C64U device ID.')
    safe_argument(device_id)
    matches = [profile for profile in preferences.profiles
               if profile.device_id and profile.device_id.casefold() == device_id.casefold()]
    if len(matches) != 1:
        raise BrowserError('Exactly one Argonaut Development profile must match that device ID.')
    return matches[0]


def profile_for_id(preferences, profile_id):
    if not profile_id or len(profile_id) > 120:
        raise BrowserError('Enter a valid saved Development profile ID.')
    safe_argument(profile_id)
    matches = [profile for profile in preferences.profiles if profile.id == profile_id]
    if len(matches) != 1:
        raise BrowserError('Exactly one Argonaut Development profile must match that profile ID.')
    return matches[0]


def main(argv=None, stdin=None, stdout=None, stderr=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = argparse.ArgumentParser(description='Run deterministic Argonaut Test Lab checks.')
    parser.add_argument('--suite', choices=('offline', 'hardware', 'diagnosis_probe'),
                        default='offline')
    parser.add_argument('--password-stdin', action='store_true',
                        help='Read one C64U password line from standard input (hardware only).')
    parser.add_argument('--timeout', type=int, default=10,
                        help='Hardware network timeout in seconds (1-30).')
    parser.add_argument('--device-id',
                        help='Use the Development profile bound to this C64U ID instead of the selected profile.')
    parser.add_argument('--profile-id',
                        help='Use this exact Development connection profile (for fleet automation).')
    parser.add_argument('--explain-failures', action='store_true',
                        help='Ask an AI model to explain failed checks; verdicts and exit code are unchanged.')
    parser.add_argument('--ai-provider', choices=('ollama', 'openai'),
                        help='AI service for --explain-failures (local Ollama or OpenAI cloud).')
    parser.add_argument('--ai-model',
                        help='Model name for --explain-failures.')
    args = parser.parse_args(argv)
    if args.device_id is not None and args.profile_id is not None:
        parser.error('--device-id and --profile-id cannot be combined')
    if args.suite != 'hardware':
        if args.password_stdin or args.device_id is not None or args.profile_id is not None:
            parser.error('Hardware connection options require --suite hardware')
        report = (run_diagnosis_probe() if args.suite == 'diagnosis_probe'
                  else run_default_checks())
        result = {'report': report, 'comparison': None, 'saved': False}
    else:
        if not 1 <= args.timeout <= 30:
            parser.error('--timeout must be between 1 and 30 seconds')
        try:
            password = stdin.readline(MAX_PASSWORD_LENGTH + 2).rstrip('\r\n') if args.password_stdin else ''
            if len(password) > MAX_PASSWORD_LENGTH:
                raise BrowserError('Password input was too long.')
            safe_argument(password)
            path = config_base() / development.config_name() / 'config.json'
            preferences = Preferences(path).load()
            profile = (profile_for_id(preferences, args.profile_id)
                       if args.profile_id is not None else
                       profile_for_device(preferences, args.device_id))
            client = profile.client(password) if profile else None
            if client is not None:
                client.timeout = args.timeout
            result = run_with_history(preferences.path,
                lambda: run_hardware_checks(client, profile),
                profile_id=profile.id if profile else None)
        except (BrowserError, OSError, ValueError) as exc:
            print('Test Lab could not start: ' + str(exc), file=stderr)
            return 3
    output = dict(result['report'])
    if args.suite == 'hardware':
        output['comparison'] = result['comparison']
        output['history_saved'] = result['saved']
    if args.explain_failures:
        try:
            if output['status'] != 'fail':
                output['analysis'] = analyze_failures(result['report'], lambda _: None)
            else:
                if not args.ai_provider or not args.ai_model:
                    raise GatewayError('configuration', 'AI provider and model are required.')
                gateway = AIGateway(GatewayConfig(args.ai_provider, args.ai_model))
                output['analysis'] = analyze_failures(result['report'], gateway)
        except GatewayError as exc:
            output['analysis'] = {'schema': 1, 'status': 'error',
                                  'error_kind': exc.kind, 'diagnosis': None}
        except (ValueError, TypeError):
            output['analysis'] = {'schema': 1, 'status': 'error',
                                  'error_kind': 'analysis', 'diagnosis': None}
    print(json.dumps(output, sort_keys=True), file=stdout)
    if args.suite == 'hardware' and not result['saved']:
        return 3
    return {'pass': 0, 'fail': 1, 'skip': 2}[output['status']]


if __name__ == '__main__':
    raise SystemExit(main())
