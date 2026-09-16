# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Opt-in local diagnoses for already saved unattended fleet failures."""
from dataclasses import dataclass
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import tempfile

from .ai_analysis import analyze_failures, failure_evidence
from .ai_gateway import AIGateway, GatewayConfig, GatewayError
from .test_lab_history import profile_scope_key, validate_report


CONFIG_NAME = 'local-ai.json'
CACHE_NAME = 'latest-local-ai.json'
PROFILE_KEY = re.compile(r'[0-9a-f]{16}\Z')
FINGERPRINT = re.compile(r'[0-9a-f]{64}\Z')
MAX_PROFILES = 4


@dataclass(frozen=True)
class Diagnosis:
    fingerprint: str
    records: tuple
    notified: bool


def _write_private(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.local-ai-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_local_config(path, model=None):
    """A missing model disables unattended analysis; cloud is never accepted."""
    if model is None:
        value = {'schema': 1, 'enabled': False}
    else:
        config = GatewayConfig('ollama', model)
        value = {'schema': 1, 'enabled': True,
                 'provider': config.provider, 'model': config.model}
    _write_private(path, value)


def load_local_config(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    if not isinstance(value, dict) or value.get('schema') != 1:
        raise ValueError('Invalid local AI setting')
    if value.get('enabled') is False:
        return None
    if value.get('enabled') is not True or value.get('provider') != 'ollama':
        raise ValueError('Invalid local AI setting')
    return GatewayConfig('ollama', value.get('model'))


def _saved_failures(output):
    fleet = json.loads(output)
    if not isinstance(fleet, dict) or fleet.get('schema') != 1:
        raise ValueError('Invalid fleet result')
    selected = []
    for profile in fleet.get('profiles', []):
        if not isinstance(profile, dict) or profile.get('exit_code') != 1:
            continue
        key = profile.get('key')
        report = profile.get('result')
        if not isinstance(key, str) or not PROFILE_KEY.fullmatch(key):
            raise ValueError('Invalid fleet profile key')
        if not isinstance(report, dict) or report.get('history_saved') is not True:
            continue
        validate_report(report)
        if report['status'] == 'fail':
            selected.append((key, report))
    if len(selected) > MAX_PROFILES:
        raise ValueError('Too many failed profiles for local AI analysis')
    return selected


def _fingerprint(selected, config):
    evidence = [(key, failure_evidence(report)) for key, report in selected]
    body = json.dumps({'model': config.model, 'evidence': evidence},
                      sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(body).hexdigest()


def _report_fingerprint(report):
    body = json.dumps(failure_evidence(report), sort_keys=True,
                      separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(body).hexdigest()


def read_cache(path, fingerprint):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        records = value['records']
        if (value.get('schema') != 1 or value.get('fingerprint') != fingerprint or
                not FINGERPRINT.fullmatch(fingerprint) or
                type(value.get('notified')) is not bool or
                not isinstance(records, list) or not records or
                len(records) > MAX_PROFILES):
            return None
        for record in records:
            if (not isinstance(record, dict) or
                    not isinstance(record.get('key'), str) or
                    not PROFILE_KEY.fullmatch(record['key']) or
                    not isinstance(record.get('evidence_sha'), str) or
                    not FINGERPRINT.fullmatch(record['evidence_sha']) or
                    not isinstance(record.get('diagnosis'), str) or
                    not record['diagnosis'] or len(record['diagnosis']) > 8000):
                return None
        return Diagnosis(fingerprint, tuple(records), value['notified'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _save_cache(path, diagnosis):
    _write_private(path, {'schema': 1, 'fingerprint': diagnosis.fingerprint,
                          'records': list(diagnosis.records),
                          'notified': diagnosis.notified})


def mark_notified(path, diagnosis):
    current = read_cache(path, diagnosis.fingerprint)
    if current is not None and not current.notified:
        _save_cache(path, Diagnosis(current.fingerprint, current.records, True))


def saved_diagnosis(path, profile_id, report):
    """Show a cached diagnosis only for this bound profile and failure evidence."""
    validate_report(report)
    if report['status'] != 'fail':
        return None
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        fingerprint = value['fingerprint']
    except (OSError, ValueError, KeyError, TypeError):
        return None
    cached = read_cache(path, fingerprint)
    if cached is None:
        return None
    key = profile_scope_key(profile_id)[:16]
    evidence_sha = _report_fingerprint(report)
    for record in cached.records:
        if record['key'] == key and record['evidence_sha'] == evidence_sha:
            return record['diagnosis']
    return None


def diagnose_saved_fleet(output, config_path, cache_path,
                         gateway_factory=None):
    """Reuse replay analysis after history save; never affect fleet exit status."""
    config = load_local_config(config_path)
    if config is None:
        return None
    selected = _saved_failures(output)
    if not selected:
        return None
    fingerprint = _fingerprint(selected, config)
    cached = read_cache(cache_path, fingerprint)
    if cached is not None:
        return cached
    gateway = (gateway_factory or AIGateway)(config)
    records = []
    for key, report in selected:
        result = analyze_failures(report, gateway)
        if result['status'] != 'analyzed':
            raise GatewayError('response', 'Local AI returned no diagnosis.')
        records.append({'key': key, 'evidence_sha': _report_fingerprint(report),
                        'diagnosis': result['diagnosis']})
    diagnosis = Diagnosis(fingerprint, tuple(records), False)
    _save_cache(cache_path, diagnosis)
    return diagnosis


def alert_excerpt(diagnosis):
    """One short local desktop preview; full bounded text stays private."""
    text = ' '.join(diagnosis.records[0]['diagnosis'].split())
    if len(text) > 280:
        text = text[:277] + '…'
    if len(diagnosis.records) > 1:
        text += f' ({len(diagnosis.records)} C64Us analyzed)'
    return escape(text, quote=False)
