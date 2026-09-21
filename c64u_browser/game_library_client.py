# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Presentation-only Game Library controller shared by GTK client tests."""
from .game_library import ArtworkReference, C64U, GameLibraryError, GameSource


MECHANISM_LABELS = {
    'rest-attached-crt': 'Send this local cartridge temporarily to the C64U',
    'rest-c64u-crt': 'Start the cartridge from C64U storage',
    'dma-run-img': 'Run the disk image through the C64U command interface',
}


ERROR_GUIDANCE = {
    'launch-outcome-unknown': (
        'Launch outcome unknown. The command may have reached the C64U. '
        'Inspect its screen before trying again.'),
    'malformed-image': 'Validation rejected the game image. Choose a structurally valid D64 or CRT.',
    'missing-source': 'The referenced game file is missing. Use Locate/Relink.',
    'source-changed': 'The referenced game changed. Validate it or use Locate/Relink.',
    'record-changed': 'The library entry changed. Review the operation again.',
    'device-unavailable': 'Connect to the game’s C64U and try again.',
    'device-changed': 'The active C64U changed. Review the operation again.',
    'session-changed': 'The C64U connection changed. Review the operation again.',
    'storage-changed': 'The C64U storage changed. Review the operation again.',
    'firmware-rejection': 'The C64U firmware rejected the launch command.',
    'authentication': 'C64U authentication failed. Check the saved network password.',
    'cancelled': 'The operation was cancelled before launch.',
}


def source_text(source):
    if source.scope == C64U:
        return f'C64U {source.device_id} · {source.path}'
    return 'This computer · ' + source.path


def mechanism_text(value):
    return MECHANISM_LABELS.get(value, 'Core-selected C64U launch method')


def client_error_text(error):
    if error is None:return 'The operation did not complete.'
    guidance = ERROR_GUIDANCE.get(error.code)
    return guidance or error.message


def add_results_text(results, failures=()):
    """Summarize Core AddResults without treating submissions as additions."""
    results = tuple(results)
    failures = tuple(failures)
    added = sum(bool(result.created) for result in results)
    same_source = sum(result.duplicate_kind == 'source' for result in results)
    duplicate_content = sum(result.duplicate_kind == 'content'
                            for result in results)
    changed_source = sum(result.duplicate_kind == 'source-changed'
                         for result in results)
    rejected = len(failures) + sum(
        not result.created and result.duplicate_kind not in (
            'source', 'content', 'source-changed') for result in results)

    messages = [
        (f'Added {added} new game record' + ('' if added == 1 else 's') + '.')
        if added else 'No new game records were added.'
    ]
    if same_source:
        messages.append(
            f'{same_source} file' + ('' if same_source == 1 else 's') +
            (' was' if same_source == 1 else ' were') +
            ' already cataloged from the same source with matching content.')
    if duplicate_content:
        messages.append(
            f'{duplicate_content} file' +
            ('' if duplicate_content == 1 else 's') +
            ' had' +
            ' duplicate content already represented by another catalog entry.')
    if changed_source:
        messages.append(
            f'{changed_source} cataloged source' +
            ('' if changed_source == 1 else 's') +
            ' had changed content and ' +
            ('was' if changed_source == 1 else 'were') +
            ' not added; use Validate or Locate/Relink.')
    if rejected:
        message = (f'{rejected} file' + ('' if rejected == 1 else 's') +
                   (' was' if rejected == 1 else ' were') + ' rejected.')
        if failures:
            message += (' Reason: ' if rejected == 1 else ' First reason: ') + failures[0]
        messages.append(message)
    return ' '.join(messages)


class GameLibraryClient:
    """Client state and direct forwarding to Core-owned services."""
    def __init__(self, library, launcher):
        self.library = library
        self.launcher = launcher
        self.query = ''
        self.favorites_only = False
        self.selected_id = None

    def records(self):
        return self.library.search(
            self.query, favorite=True if self.favorites_only else None)

    def select(self, record_id):
        self.selected_id = record_id
        return self.selected()

    def selected(self):
        if self.selected_id is None:return None
        try:return self.library.get(self.selected_id)
        except GameLibraryError as exc:
            if exc.code != 'not-found':raise
            self.selected_id = None
            return None

    def can_launch(self, connected):
        record = self.selected()
        return bool(connected and record
                    and record.state not in ('missing', 'changed', 'unavailable'))

    def add_core_host(self, path):
        return self.library.add(GameSource.core_host(path))

    def add_c64u(self, device_id, path):
        return self.library.add(GameSource.c64u(device_id, path))

    def remove(self):return self.library.remove(self.selected_id)
    def validate(self):return self.library.validate_source(self.selected_id)
    def edit_title(self, title):return self.library.edit_title(self.selected_id, title)
    def set_favorite(self, value):return self.library.set_favorite(self.selected_id, value)
    def set_notes(self, value):return self.library.set_notes(self.selected_id, value)

    def set_artwork(self, path):
        reference = ArtworkReference.core_host(path) if path else None
        return self.library.set_artwork(self.selected_id, reference)

    def prepare_relink_core_host(self, path):
        return self.library.prepare_relink(
            self.selected_id, GameSource.core_host(path))

    def prepare_relink_c64u(self, device_id, path):
        return self.library.prepare_relink(
            self.selected_id, GameSource.c64u(device_id, path))

    def execute_relink(self, plan_id, accept_changed=False):
        return self.library.execute_relink(
            plan_id, accept_changed=accept_changed)

    def prepare_launch(self):return self.launcher.prepare_launch(self.selected_id)
    def execute_launch(self, plan_id):return self.launcher.execute_launch(plan_id)
    def discard_launch(self, plan_id):return self.launcher.discard_plan(plan_id)
