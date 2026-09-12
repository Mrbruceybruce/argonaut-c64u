# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Successful folder visits, with independent back/forward cursors."""
class History:
    def __init__(self, initial):
        self.paths = [str(initial)]
        self.index = 0

    def target(self, offset):
        index = self.index + offset
        return self.paths[index] if 0 <= index < len(self.paths) else None

    def visit(self, path, offset=None):
        path = str(path)
        if offset is not None:
            if self.target(offset) != path:
                raise ValueError('History changed during navigation')
            self.index += offset
        elif path != self.paths[self.index]:
            self.paths[self.index + 1:] = [path]
            self.index += 1
