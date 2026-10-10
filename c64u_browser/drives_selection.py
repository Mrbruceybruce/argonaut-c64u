# SPDX-License-Identifier: GPL-3.0-or-later
"""Drive source references; selection never authorizes execution by itself."""
import posixpath
from .api import BrowserError
from .picker_model import PickerSelection, DRIVES
from .storage import require_file_operation, storage_root


def validate_selection(selection, session):
    if (not isinstance(selection, PickerSelection) or selection.scope != 'c64u'
            or selection.category != DRIVES.category or selection.kind != 'file'
            or selection.filename != posixpath.basename(selection.path)
            or not DRIVES.matches(selection.filename)):
        raise BrowserError('Choose a C64U D64, G64, D71, G71 or D81 image.')
    selection.validate_session(session)
    require_file_operation(selection.path)
    if selection.storage_root != storage_root(selection.path):
        raise BrowserError('Storage root changed. Select the disk image again.')
    return selection


def remote_selection(path, session):
    """Capture an explicit manual path or Files shortcut, never a live widget."""
    selection = PickerSelection('c64u', path, posixpath.basename(path),
        storage_root(path), session.device_id, session.session_id, DRIVES.category, 'file')
    return validate_selection(selection, session)
