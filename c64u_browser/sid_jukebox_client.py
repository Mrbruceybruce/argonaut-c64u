# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Presentation-only client state for the Core-owned SID Jukebox."""
from .sid_jukebox import C64U, SidCatalogError, SidSource
from .sid_playback import PlaylistContext


MECHANISM_LABELS = {
    'rest-attached-sid': 'Send this local SID temporarily to the C64U',
    'rest-validated-c64u-sid': (
        'Read and validate the SID from C64U storage, then play the validated content'),
}


ERROR_GUIDANCE = {
    'playback-outcome-unknown': (
        'Playback outcome unknown. The command may have reached the C64U. '
        'Check its audio output before trying again.'),
    'playback-blocked': 'This SID is cataloged but is not eligible for physical playback.',
    'missing-source': 'The referenced SID file is missing. Use Locate/Relink.',
    'target-unavailable': 'The SID source is unavailable. Validate or Relink it.',
    'source-changed': 'The referenced SID changed. Validate it or use Locate/Relink.',
    'record-changed': 'The SID entry changed. Review playback again.',
    'device-unavailable': 'Connect to the SID source and target C64U, then try again.',
    'device-changed': 'The active C64U changed. Review playback again.',
    'session-changed': 'The C64U connection changed. Review playback again.',
    'storage-changed': 'The C64U storage changed. Review playback again.',
    'authentication': 'C64U authentication failed. Check the saved network password.',
    'firmware-rejection': 'The C64U firmware rejected the SID playback command.',
    'authorization': 'Playlist control authorization expired or changed. Use reviewed Play again.',
    'playlist-changed': 'The playlist changed. Use reviewed Play again.',
    'cancelled': 'The operation was cancelled before playback was requested.',
}


def source_text(source):
    if source.scope == C64U:
        return f'C64U {source.device_id} · {source.path}'
    return 'This computer · ' + source.path


def mechanism_text(value):
    return MECHANISM_LABELS.get(value, 'Core-selected C64U SID playback method')


def error_text(error):
    if error is None:return 'The operation did not complete.'
    return ERROR_GUIDANCE.get(error.code, error.message)


def sid_configuration_text(metadata):
    addresses = ' / '.join(f'${chip.address:04X}' for chip in metadata.chips)
    return f'{metadata.sid_count}SID · {addresses}'


def sid_models_text(metadata):
    return ' / '.join(chip.model for chip in metadata.chips)


def clock_text(clock):
    return {
        'PAL-and-NTSC': 'PAL or NTSC',
        'PAL': 'PAL', 'NTSC': 'NTSC', 'unknown': 'Unknown',
    }.get(clock, clock)


def playback_preview_lines(preview):
    """Return review text without embedding Core decisions in GTK."""
    addresses = ' / '.join(f'${value:04X}' for value in preview.sid_addresses)
    models = ' / '.join(preview.sid_models)
    return (
        f'Tune: {preview.title}',
        f'Source: {source_text(preview.source)}',
        f'Subtune: {preview.selected_subtune}',
        f'Target C64U: {preview.target_device_id}',
        f'Method: {mechanism_text(preview.mechanism)}',
        f'SID requirements: {preview.sid_count}SID · {addresses}',
        f'Models: {models}',
        f'Clock: {clock_text(preview.clock)}',
        'Duration: Unknown', '',
        'The running C64 program will be interrupted. Unsaved work may be lost.',
        '', 'Warnings:', *('• ' + item for item in preview.warnings),
    )


class SidJukeboxClient:
    """Client-owned selection/filter state and direct forwarding to Core."""
    def __init__(self, catalog, playback):
        self.catalog = catalog
        self.playback = playback
        self.query = ''
        self.favorites_only = False
        self.sort_key = 'title'
        self.selected_id = None
        self.playlist_id = None
        self.playlist_item_id = None

    def records(self):
        records=self.catalog.search(
            self.query, favorite=True if self.favorites_only else None)
        def value(tune):
            if self.sort_key=='author':return (tune.metadata.author.casefold(),tune.title.casefold())
            if self.sort_key=='released':return (tune.metadata.released.casefold(),tune.title.casefold())
            if self.sort_key=='format':return (tune.metadata.format.casefold(),tune.title.casefold())
            if self.sort_key=='favorite':return (not tune.favorite,tune.title.casefold())
            return (tune.title.casefold(),)
        return tuple(sorted(records,key=value))

    def select(self, tune_id):
        self.selected_id = tune_id
        return self.selected()

    def selected(self):
        if self.selected_id is None:return None
        try:return self.catalog.get(self.selected_id)
        except SidCatalogError as exc:
            if exc.code != 'not-found':raise
            self.selected_id = None
            return None

    @staticmethod
    def _can_play_tune(tune, connected):
        return bool(connected and tune and tune.state == 'available'
                    and tune.metadata.playback_eligible)

    @staticmethod
    def _blocked_reason(tune):
        if tune is None:return ''
        if tune.state != 'available':
            return tune.state_message or f'The SID source is {tune.state}.'
        if not tune.metadata.playback_eligible:
            return (tune.metadata.warnings[0] if tune.metadata.warnings else
                    'Core classified this SID as blocked from physical playback.')
        return ''

    def can_play_library(self, connected):
        return self._can_play_tune(self.selected(), connected)

    def library_blocked_reason(self):return self._blocked_reason(self.selected())

    def add_core_host(self, path):return self.catalog.add(SidSource.core_host(path))
    def add_c64u(self, device_id, path):
        return self.catalog.add(SidSource.c64u(device_id, path))
    def remove(self):return self.catalog.remove(self.selected_id)
    def validate(self):return self.catalog.validate_source(self.selected_id)
    def set_favorite(self, value):
        return self.catalog.set_favorite(self.selected_id, value)
    def set_notes(self, value):return self.catalog.set_notes(self.selected_id, value)

    def prepare_relink_core_host(self, path):
        return self.catalog.prepare_relink(self.selected_id, SidSource.core_host(path))

    def prepare_relink_c64u(self, device_id, path):
        return self.catalog.prepare_relink(
            self.selected_id, SidSource.c64u(device_id, path))

    def execute_relink(self, plan_id, accept_changed=False):
        return self.catalog.execute_relink(plan_id, accept_changed=accept_changed)

    def playlists(self):return self.catalog.list_playlists()
    def selected_playlist(self):
        if self.playlist_id is None:return None
        try:return self.catalog.get_playlist(self.playlist_id)
        except SidCatalogError as exc:
            if exc.code != 'not-found':raise
            self.playlist_id = None;self.playlist_item_id = None
            return None

    def create_playlist(self, title):return self.catalog.create_playlist(title)
    def rename_playlist(self, title):
        return self.catalog.rename_playlist(self.playlist_id, title)
    def delete_playlist(self):return self.catalog.delete_playlist(self.playlist_id)
    def add_playlist_item(self, subtune):
        return self.catalog.add_playlist_item(
            self.playlist_id, self.selected_id, subtune)
    def add_tune_to_playlist(self, playlist_id, tune_id, subtune):
        return self.catalog.add_playlist_item(playlist_id,tune_id,subtune)
    def remove_playlist_item(self):
        return self.catalog.remove_playlist_item(
            self.playlist_id, self.playlist_item_id)
    def remove_playlist_items(self, item_ids):
        return self.catalog.remove_playlist_items(self.playlist_id, tuple(item_ids))
    def reorder_playlist_item(self, new_index):
        return self.catalog.reorder_playlist_item(
            self.playlist_id, self.playlist_item_id, new_index)
    def reorder_playlist_items(self, ordered_item_ids):
        return self.catalog.reorder_playlist_items(
            self.playlist_id, tuple(ordered_item_ids))

    def playlist_target(self):
        playlist = self.selected_playlist()
        if playlist is None or not playlist.items:return None
        item = next((item for item in playlist.items
                     if item.id == self.playlist_item_id), playlist.items[0])
        try:tune = self.catalog.get(item.tune_id)
        except SidCatalogError:return None
        return playlist,item,tune

    def can_play_playlist(self, connected):
        target=self.playlist_target()
        return self._can_play_tune(target[2] if target else None, connected)

    def playlist_blocked_reason(self):
        target=self.playlist_target()
        if target is None:
            return ('Choose a playlist containing at least one SID tune.'
                    if self.selected_playlist() else 'Choose an active playlist.')
        return self._blocked_reason(target[2])

    def prepare_playlist_play(self):
        target=self.playlist_target()
        if target is None:
            raise SidCatalogError(
                'playlist-item', 'Choose a playlist containing at least one SID tune.')
        playlist,item,tune=target
        self.playlist_item_id=item.id
        return self.playback.prepare_play(
            tune.id, item.subtune, PlaylistContext(playlist.id, item.id))

    def execute_play(self, plan_id):return self.playback.execute_play(plan_id)
    def discard_play(self, plan_id):return self.playback.discard_plan(plan_id)
    def previous(self):return self.playback.previous()
    def next(self):return self.playback.next()
    def set_shuffle(self, enabled):return self.playback.set_shuffle(enabled)
    def playback_state(self):return self.playback.current_playback()

    def now_playing(self):
        snapshot=self.playback_state()
        tune_id=getattr(snapshot,'tune_id','')
        if not tune_id:return snapshot,None
        try:return snapshot,self.catalog.get(tune_id)
        except SidCatalogError:return snapshot,None
