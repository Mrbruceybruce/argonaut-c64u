# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Analyze a saved Test Lab report without rerunning checks or contacting a C64U."""
import argparse
import json
from pathlib import Path
import sys

from .ai_analysis import analyze_failures
from .ai_gateway import AIGateway, GatewayConfig, GatewayError
from .test_lab_history import validate_report


MAX_REPORT_BYTES = 1024 * 1024


def load_report(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError('Saved Test Lab report is too large')
    return validate_report(json.loads(raw.decode('utf-8')))


def main(argv=None, stdout=None, stderr=None):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = argparse.ArgumentParser(
        description='Explain a saved Test Lab failure without rerunning checks.')
    parser.add_argument('--report', required=True,
                        help='Path to a saved or exported Test Lab JSON report.')
    parser.add_argument('--ai-provider', choices=('ollama', 'openai'))
    parser.add_argument('--ai-model')
    args = parser.parse_args(argv)
    try:
        report = load_report(args.report)
    except (OSError, ValueError, UnicodeError, TypeError):
        print('Saved Test Lab report could not be read or validated.', file=stderr)
        return 3
    try:
        if report['status'] != 'fail':
            analysis = analyze_failures(report, lambda _: None)
        else:
            if not args.ai_provider or not args.ai_model:
                raise GatewayError('configuration', 'AI provider and model are required.')
            gateway = AIGateway(GatewayConfig(args.ai_provider, args.ai_model))
            analysis = analyze_failures(report, gateway)
    except GatewayError as exc:
        analysis = {'schema': 1, 'status': 'error', 'error_kind': exc.kind,
                    'diagnosis': None}
    except (ValueError, TypeError):
        analysis = {'schema': 1, 'status': 'error', 'error_kind': 'analysis',
                    'diagnosis': None}
    print(json.dumps({'schema': 1, 'report_status': report['status'],
                      'analysis': analysis}, sort_keys=True), file=stdout)
    return {'pass': 0, 'fail': 1, 'skip': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
