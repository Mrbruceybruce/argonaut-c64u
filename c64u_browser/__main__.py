# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
import argparse
from dataclasses import asdict
import getpass
import json
import posixpath
import sys
from .api import UltimateClient, BrowserError
from .transfers import download, upload_new_folder


def display(path, entries):
    print(json.dumps(path, ensure_ascii=True))
    for index, entry in enumerate(entries, 1):
        print(f'{index:4} {entry.kind:8} {str(entry.size or 0):>10}  {json.dumps(entry.name, ensure_ascii=True)}')


def main():
    parser = argparse.ArgumentParser(description='C64 Ultimate browser and conservative file transfers')
    parser.add_argument('--host', required=True, help='C64U IPv4 address or hostname')
    parser.add_argument('--password', action='store_true', help='Prompt privately for network password')
    parser.add_argument('--port', type=int, default=21)
    parser.add_argument('--timeout', type=float, default=10)
    parser.add_argument('--encoding', choices=['utf-8', 'latin-1'], default='utf-8')
    parser.add_argument('command', choices=['info', 'ls', 'browse', 'get', 'put-new'])
    parser.add_argument('path', nargs='?', default='/')
    parser.add_argument('destination', nargs='?')
    args = parser.parse_args()
    if args.command in ('get', 'put-new') and args.destination is None:
        parser.error('Transfers require source and destination arguments')
    if args.timeout <= 0 or not 1 <= args.port <= 65535:
        parser.error('Timeout must be positive and port must be 1–65535')
    try:
        client = UltimateClient(args.host, getpass.getpass('Network password: ') if args.password else '', args.port, args.timeout, args.encoding)
        if args.command in ('get', 'put-new'):
            def progress(count):
                print(f'\rTransferred {count:,} bytes', end='', file=sys.stderr, flush=True)
            if args.command == 'get':
                result = download(client, args.path, args.destination, progress)
            else:
                result = upload_new_folder(client, args.path, args.destination, progress)
            print(file=sys.stderr)
            print(json.dumps(result, indent=2))
            return 0
        if args.command == 'info':
            print(json.dumps(client.info(), indent=2))
            return 0
        path, entries = client.list_directory(args.path)
        if args.command == 'ls':
            print(json.dumps({'path': path, 'entries': [asdict(e) for e in entries]}, indent=2))
            return 0
        while True:
            display(path, entries)
            choice = input('Directory number, /absolute/path, .., r to refresh, q to quit: ')
            if choice == 'q':
                return 0
            target = path
            if choice == '..':
                target = posixpath.dirname(path.rstrip('/')) or '/'
            elif choice.startswith('/'):
                target = choice
            elif choice.isdecimal() and 1 <= int(choice) <= len(entries):
                entry = entries[int(choice)-1]
                if entry.kind != 'dir':
                    print('Select a directory.')
                    continue
                target = posixpath.join(path, entry.name)
            elif choice != 'r':
                print('Unknown selection.')
                continue
            try:
                path, entries = client.list_directory(target)
            except BrowserError as exc:
                print(str(exc), file=sys.stderr)
    except BrowserError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130

if __name__ == '__main__':
    sys.exit(main())
