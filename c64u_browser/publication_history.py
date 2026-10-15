# SPDX-License-Identifier: GPL-3.0-or-later
"""Read the pinned staging chain and later read-only observations; never resume."""
import json
import os
import stat
from pathlib import Path
from .publication_model import require, digest, canonical, TRANSACTION
from .publication_history_pins import PINS
from .import_snapshots import open_directory
from .import_journal import decode
from .import_execution import initial_journal, validate_successor


def load_reference(root):
    root = Path(root)
    require(root.is_absolute() and root.resolve() == root, 'Unaliased historical root required.')
    records = {}; previous = None
    for name, (size, expected) in sorted(PINS.items()):
        path = root / name
        parent = open_directory(path.parent)
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, 'rb') as f:
                info = os.fstat(f.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == size,
                        'Historical file type/length changed.')
                data = f.read(size+1)
                require(len(data) == size and digest(data) == expected, 'Historical pin mismatch.')
        finally: os.close(parent)
        records[name] = data
        if '.execution-' in name:
            current = decode(data)
            require(current.transaction.id == TRANSACTION, 'Historical transaction mismatch.')
            if previous is None: require(current == initial_journal(current.transaction), 'Initial staging checkpoint changed.')
            else: validate_successor(previous,current)
            previous = current
    require(previous is not None and previous.state == 'verified-staged', 'Verified historical staging chain required.')
    prefix = 'PA-4.15-resumed-readonly/physical/observations/'
    old = bytes.fromhex(json.loads(records[prefix+'0009-manifest.json'])['value']['bytes_hex'])
    record = bytes.fromhex(json.loads(records[prefix+'0010-transaction-record.json'])['value']['bytes_hex'])
    return old, record, digest(canonical(PINS))
