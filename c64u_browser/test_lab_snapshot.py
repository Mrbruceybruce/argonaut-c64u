# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Private machine-readable snapshot of the latest visible Test Lab result."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile


def save_latest(path, action, deterministic, ai):
    """Atomically save the three labeled fields shown in Test Lab."""
    values = (action, deterministic, ai)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError('Test Lab snapshot fields must be nonempty text')
    data = {
        'schema': 1,
        'saved_at': datetime.now(timezone.utc).isoformat(),
        'action': action,
        'deterministic_result': deterministic,
        'ai_analysis': ai,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.latest-status-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return data
