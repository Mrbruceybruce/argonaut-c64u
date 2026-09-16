#!/usr/bin/env python3
"""Render user-level Linux units for independent read-only Test Lab runs."""
import argparse
from pathlib import Path
import sys


UNIT_NAME = 'argonaut-test-lab-fleet'


def _unit_path(path):
    value = str(Path(path).resolve())
    if not Path(value).is_absolute() or any(char in value for char in '\r\n\x00'):
        raise ValueError('Invalid unit path')
    return value


def render(source, python, config):
    source, python, config = map(_unit_path, (source, python, config))
    if ' ' in python:
        raise ValueError('Python executable path cannot contain spaces')
    service = f'''[Unit]
Description=Argonaut read-only Test Lab checks for Development C64Us
ConditionPathExists={config}

[Service]
Type=oneshot
WorkingDirectory={source}
ExecStart={python} -m c64u_browser.test_lab_alert
TimeoutStartSec=5min
SuccessExitStatus=2
'''
    timer = f'''[Unit]
Description=Run Argonaut read-only C64U checks every 30 minutes

[Timer]
OnActiveSec=5min
OnUnitActiveSec=30min
Unit={UNIT_NAME}.service

[Install]
WantedBy=timers.target
'''
    return service, timer


def main(argv=None):
    parser = argparse.ArgumentParser(description='Render Argonaut user timer files for review.')
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--config', type=Path,
                        default=Path.home() / '.config/argonaut-development/config.json')
    args = parser.parse_args(argv)
    service, timer = render(args.source, args.python, args.config)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / f'{UNIT_NAME}.service').write_text(service)
    (args.output_dir / f'{UNIT_NAME}.timer').write_text(timer)
    print('Rendered', UNIT_NAME, 'service and timer in', args.output_dir)


if __name__ == '__main__':
    main()
