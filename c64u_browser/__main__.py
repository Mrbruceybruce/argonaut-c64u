# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
import argparse
import getpass
import json
import itertools
import sys
from .api import UltimateClient, BrowserError


def main():
    recognized_put_new = False
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            if recognized_put_new:
                from .fresh_folder_cli import UsageError
                raise UsageError()
            super().error('Invalid syntax or unsupported option. Use --help for usage.')
    parser = Parser(description='C64 Ultimate browser and conservative file transfers')
    parser.add_argument('--host', help='C64U IPv4 address or hostname (info only)')
    parser.add_argument('--profile-id', action='append', help='Saved bound profile ID (required for ls/get; optional for put-new)')
    parser.add_argument('--password', action='store_true', help='Prompt privately for network password')
    parser.add_argument('--port', type=int, default=None, help='Legacy FTP port (info only)')
    parser.add_argument('--timeout', type=float, default=None, help='REST timeout (info only)')
    parser.add_argument('--encoding', choices=['utf-8', 'latin-1'], default=None, help='Legacy encoding (info only)')
    parser.add_argument('command', choices=['info', 'ls', 'get', 'put-new'])
    parser.add_argument('path', nargs='?', default='/')
    parser.add_argument('destination', nargs='?')
    # Locate the first positional using this parser's option grammar, before
    # type/choice validation can fail. All value-taking options consume one
    # argument; flags consume none. An option's value is never the command.
    tokens = iter(sys.argv[1:])
    while (token := next(tokens, None)) is not None:
        if token == '--':
            recognized_put_new = next(tokens, None) == 'put-new'
            break
        option = parser._parse_optional(token)
        if option is None:
            recognized_put_new = token == 'put-new'
            break
        # Recent Python versions return a list of candidates; older ones return
        # one tuple. Ambiguous options cannot establish a command position.
        if isinstance(option, list):
            if len(option) != 1:
                break
            option = option[0]
        action, explicit_value = option[0], option[-1]
        if action is not None and action.nargs != 0 and explicit_value is None:
            # A missing value followed by an option does not consume that option.
            # parse_args still owns all validation and reports the actual error.
            value = next(tokens, None)
            if value is not None and (value == '--' or parser._parse_optional(value) is not None):
                tokens = itertools.chain([value], tokens)
    try:
        args = parser.parse_args()
        if args.command == 'put-new':
            from .fresh_folder_cli import run
            if (args.destination is None or args.profile_id is not None and len(args.profile_id) != 1
                    or any(getattr(args, name) is not None for name in ('host', 'port', 'timeout', 'encoding'))):
                parser.error('Unsupported put-new options')
            return run(args)
    except Exception as exc:
        from .fresh_folder_cli import UsageError, usage_error
        if isinstance(exc, UsageError):return usage_error()
        raise
    if args.command in ('ls', 'get'):
        if (args.profile_id is None or len(args.profile_id) != 1
                or any(getattr(args, name) is not None for name in ('host', 'port', 'timeout', 'encoding'))
                or args.command == 'ls' and args.destination is not None
                or args.command == 'get' and args.destination is None):
            parser.error('Invalid read command authority or operands')
        from .headless_reads_cli import run
        return run(args)
    if args.host is None:parser.error('the following arguments are required: --host')
    if args.profile_id is not None:parser.error('--profile-id is not supported by info')
    args.port = 21 if args.port is None else args.port
    args.timeout = 10 if args.timeout is None else args.timeout
    args.encoding = 'utf-8' if args.encoding is None else args.encoding
    if args.timeout <= 0 or not 1 <= args.port <= 65535:
        parser.error('Timeout must be positive and port must be 1–65535')
    try:
        client = UltimateClient(args.host, getpass.getpass('Network password: ') if args.password else '', args.port, args.timeout, args.encoding)
        print(json.dumps(client.info(), indent=2))
        return 0
    except BrowserError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130

if __name__ == '__main__':
    sys.exit(main())
