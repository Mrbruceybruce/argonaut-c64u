# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""GTK presentation for the Core-owned Game Library."""
from pathlib import Path
import posixpath

from gi.repository import Gio, GLib, Gtk

from .api import BrowserError
from .game_library import C64U, CORE_HOST
from .game_library_client import (
    GameLibraryClient, add_results_text, client_error_text, mechanism_text,
    source_text,
)
from .game_library_bulk_dialog import BulkImportDialog


class GameLibraryTab:
    SEARCH_DEBOUNCE_MS = 300

    def __init__(self, app):
        self.app = app
        self.client = GameLibraryClient(
            app.core.game_library, app.core.game_launch)
        self.connected = bool(app.core.device_session().session_id)
        self.loading_details = False
        self.job_busy = False
        self.chooser = None
        self.bulk_dialog = None
        self.rows = {}
        self._search_source = None
        self._search_generation = 0
        self._closed = False

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        toolbar = Gtk.Box(spacing=8)
        self.box.append(toolbar)
        self.search = Gtk.SearchEntry(placeholder_text='Search title, notes, or source',
                                      hexpand=True)
        self.search.connect('changed', self._search_changed)
        self.search.connect('activate', self._search_activated)
        toolbar.append(self.search)
        self.favorites = Gtk.CheckButton(label='Favorites only')
        self.favorites.connect('toggled', self._favorites_changed)
        toolbar.append(self.favorites)

        actions = Gtk.Box(spacing=8)
        self.box.append(actions)
        self.add_local_button = app.button(
            actions, 'Add local files…', self.add_local)
        self.add_c64u_button = app.button(
            actions, 'Add selected C64U file(s)', self.add_c64u)
        bulk_actions = Gtk.Box(spacing=8)
        self.box.append(bulk_actions)
        self.scan_local_button = app.button(
            bulk_actions, 'Scan local folder…', self.scan_local_folder)
        self.scan_c64u_button = app.button(
            bulk_actions, 'Scan C64U folder…', self.scan_c64u_folder)
        self.validate_button = app.button(actions, 'Validate', self.validate)
        self.relink_button = app.button(actions, 'Locate/Relink…', self.relink)
        self.remove_button = app.button(
            actions, 'Remove from library…', self.remove)
        self.launch_button = app.button(actions, 'Review & Launch…', self.launch)
        self.cancel_button = app.button(
            actions, 'Cancel operation', self.cancel_operation)
        self.cancel_button.set_sensitive(False)

        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL,
                         vexpand=True, hexpand=True)
        pane.set_position(500)
        pane.set_shrink_start_child(False)
        pane.set_shrink_end_child(False)
        self.box.append(pane)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.library_state = Gtk.Label(xalign=0, wrap=True)
        left.append(self.library_state)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE,
                                activate_on_single_click=True)
        self.list.connect('row-selected', self._selected)
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(self.list)
        left.append(scroll)
        pane.set_start_child(left)

        detail_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(details, 'set_margin_' + side)(12)
        detail_scroll.set_child(details)
        pane.set_end_child(detail_scroll)

        self.detail_heading = Gtk.Label(
            label='Select a game to view its details.', xalign=0, wrap=True)
        self.detail_heading.add_css_class('title-3')
        details.append(self.detail_heading)
        details.append(Gtk.Label(label='Title', xalign=0))
        self.title = Gtk.Entry(hexpand=True)
        self.title.connect('activate', lambda *_:self.save_details())
        details.append(self.title)
        self.favorite = Gtk.CheckButton(label='Favorite')
        self.favorite.connect('toggled', self._favorite_toggled)
        details.append(self.favorite)
        self.source = Gtk.Label(xalign=0, wrap=True, selectable=True)
        details.append(self.source)
        self.state = Gtk.Label(xalign=0, wrap=True, selectable=True)
        details.append(self.state)
        details.append(Gtk.Label(label='Notes', xalign=0))
        self.notes = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                  accepts_tab=False)
        self.notes.set_size_request(-1, 110)
        note_scroll = Gtk.ScrolledWindow(min_content_height=110)
        note_scroll.set_child(self.notes)
        details.append(note_scroll)
        details.append(Gtk.Label(label='Artwork reference', xalign=0))
        art_row = Gtk.Box(spacing=8)
        self.artwork = Gtk.Entry(editable=False, hexpand=True)
        art_row.append(self.artwork)
        app.button(art_row, 'Choose image…', self.choose_artwork)
        app.button(art_row, 'Clear', self.clear_artwork)
        details.append(art_row)
        self.artwork_picture = Gtk.Picture()
        self.artwork_picture.set_size_request(180, 180)
        self.artwork_picture.set_can_shrink(True)
        details.append(self.artwork_picture)
        self.save_button = app.button(details, 'Save details', self.save_details)

        self.message = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.box.append(self.message)
        self.busy_controls = (
            self.search, self.favorites, self.add_local_button,
            self.add_c64u_button, self.scan_local_button,
            self.scan_c64u_button, self.validate_button, self.relink_button,
            self.remove_button, self.launch_button, pane)
        self.refresh()

    def bind(self, connected):
        self.connected = bool(connected)
        self._update_actions()

    def _show(self, message):
        self.message.set_text(message)
        self.app.status.set_text(message)

    def _search_changed(self, entry):
        text = entry.get_text()
        if not text:
            self._apply_search_now(text)
            return
        self._cancel_pending_search()
        generation = self._search_generation
        client = self.client
        self._search_source = GLib.timeout_add(
            self.SEARCH_DEBOUNCE_MS, self._debounced_search,
            generation, client, text)

    def _search_activated(self, entry):
        self._apply_search_now(entry.get_text())

    def _cancel_pending_search(self):
        self._search_generation += 1
        if self._search_source is not None:
            GLib.source_remove(self._search_source)
            self._search_source = None

    def _debounced_search(self, generation, client, text):
        if generation == self._search_generation:
            self._search_source = None
        if (self._closed or generation != self._search_generation
                or self.client is not client):
            return GLib.SOURCE_REMOVE
        client.query = text
        self.refresh(preserve=True)
        return GLib.SOURCE_REMOVE

    def _apply_search_now(self, text):
        self._cancel_pending_search()
        if self._closed:return
        self.client.query = text
        self.refresh(preserve=True)

    def _favorites_changed(self, button):
        self._cancel_pending_search()
        if self._closed:return
        self.client.query = self.search.get_text()
        self.client.favorites_only = button.get_active()
        self.refresh(preserve=True)

    def close(self):
        self._closed = True
        self._cancel_pending_search()

    def refresh(self, preserve=True):
        wanted = self.client.selected_id if preserve else None
        while self.list.get_first_child():
            self.list.remove(self.list.get_first_child())
        self.rows = {}
        try:records = self.client.records()
        except Exception as exc:
            self.library_state.set_text('Game Library is unavailable: ' + str(exc))
            self._clear_details();return
        for record in records:
            row = Gtk.ListBoxRow()
            row.record_id = record.id
            summary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            summary.set_margin_top(7);summary.set_margin_bottom(7)
            summary.set_margin_start(7);summary.set_margin_end(7)
            marker = '★' if record.favorite else '☆'
            title = Gtk.Label(
                label=f'{marker}  {record.title}    {record.format}',
                xalign=0, ellipsize=3)
            summary.append(title)
            summary.append(Gtk.Label(
                label=f'{record.state.capitalize()} · {source_text(record.source)}',
                xalign=0, ellipsize=3))
            row.set_child(summary);self.list.append(row)
            self.rows[record.id] = row
        if not records:
            self.library_state.set_text(
                'No games match this search.' if self.client.query
                or self.client.favorites_only else
                'Your Game Library is empty. Add a D64 or CRT without moving the original file.')
        else:
            self.library_state.set_text(f'{len(records)} game(s) shown')
        if wanted in self.rows:self.list.select_row(self.rows[wanted])
        elif wanted:self.client.selected_id = None
        self._load_details()

    def _selected(self, _listing, row):
        self.client.select(row.record_id if row else None)
        self._load_details()

    def _clear_details(self):
        self.loading_details = True
        self.detail_heading.set_text('Select a game to view its details.')
        self.title.set_text('');self.favorite.set_active(False)
        self.source.set_text('');self.state.set_text('')
        self.notes.get_buffer().set_text('');self.artwork.set_text('')
        self.artwork_picture.set_file(None)
        self.loading_details = False
        self._update_actions()

    def _load_details(self):
        record = self.client.selected()
        if record is None:self._clear_details();return
        self.loading_details = True
        self.detail_heading.set_text(f'{record.title} · {record.format}')
        self.title.set_text(record.title)
        self.favorite.set_active(record.favorite)
        self.source.set_text(source_text(record.source))
        state = record.state.capitalize()
        if record.state_message:state += ' — ' + record.state_message
        self.state.set_text(state)
        self.notes.get_buffer().set_text(record.notes)
        path = record.artwork.path if record.artwork else ''
        self.artwork.set_text(path)
        self.artwork_picture.set_file(
            Gio.File.new_for_path(path) if path and Path(path).is_file() else None)
        self.loading_details = False
        self._update_actions()

    def _update_actions(self):
        record = self.client.selected()
        selected = record is not None
        for button in (self.validate_button, self.relink_button,
                       self.remove_button, self.save_button):
            button.set_sensitive(selected and not self.job_busy)
        self.add_local_button.set_sensitive(not self.job_busy)
        self.add_c64u_button.set_sensitive(self.connected and not self.job_busy)
        self.scan_local_button.set_sensitive(not self.job_busy)
        self.scan_c64u_button.set_sensitive(self.connected and not self.job_busy)
        self.launch_button.set_sensitive(
            self.client.can_launch(self.connected) and not self.job_busy)
        self.cancel_button.set_sensitive(self.job_busy)
        self.search.set_sensitive(not self.job_busy)
        self.favorites.set_sensitive(not self.job_busy)
        self.list.set_sensitive(not self.job_busy)
        self.title.set_sensitive(selected and not self.job_busy)
        self.favorite.set_sensitive(selected and not self.job_busy)
        self.notes.set_sensitive(selected and not self.job_busy)

    def _run_job(self, job, finished):
        self.job_busy = True;self._update_actions()
        def done(snapshot):
            self.job_busy = False;self._update_actions();finished(snapshot)
        self.app.run_file_job(job, done)

    def cancel_operation(self):
        if self.job_busy:self.app.cancel_transfer()

    def _favorite_toggled(self, button):
        if self.loading_details or not self.client.selected():return
        try:self.client.set_favorite(button.get_active())
        except Exception as exc:self._show(str(exc));return
        self.refresh(preserve=True)

    def save_details(self):
        record = self.client.selected()
        if record is None:return
        start, end = self.notes.get_buffer().get_bounds()
        try:
            self.client.edit_title(self.title.get_text())
            self.client.set_notes(self.notes.get_buffer().get_text(start, end, True))
        except Exception as exc:self._show(str(exc));return
        self._show('Game Library details saved.')
        self.refresh(preserve=True)

    def _game_filter(self, chooser):
        filter_ = Gtk.FileFilter();filter_.set_name('D64 and CRT games')
        filter_.add_pattern('*.d64');filter_.add_pattern('*.D64')
        filter_.add_pattern('*.crt');filter_.add_pattern('*.CRT')
        chooser.add_filter(filter_)

    def add_local(self):
        if self.chooser:return
        chooser = Gtk.FileChooserNative.new(
            'Add D64 or CRT to Game Library', self.app.window,
            Gtk.FileChooserAction.OPEN, 'Add', 'Cancel')
        chooser.set_select_multiple(True)
        chooser.set_current_folder(Gio.File.new_for_path(str(self.app.local)))
        self._game_filter(chooser);self.chooser = chooser
        def response(_, code):
            files = chooser.get_files()
            chosen = ([files.get_item(index) for index in range(files.get_n_items())]
                      if code == Gtk.ResponseType.ACCEPT else [])
            chooser.destroy();self.chooser = None
            if not chosen:return
            paths = tuple(item.get_path() for item in chosen)
            paths = tuple(path for path in paths if path)
            if not paths:
                self._show('Choose files on the Argonaut Core computer.');return
            if len(paths) > 64:
                self._show('Choose at most 64 games in one Add operation.');return
            self._add_local_paths(paths)
        chooser.connect('response', response);chooser.show()

    def _add_local_paths(self, paths, index=0, results=(), failures=()):
        if index >= len(paths):
            self.refresh(False)
            self._show(add_results_text(results, failures))
            return
        try:job = self.client.add_core_host(paths[index])
        except Exception as exc:
            self._add_local_paths(
                paths, index + 1, results, failures + (str(exc),))
            return
        def finished(snapshot):
            if snapshot.state != 'succeeded':
                self._add_local_paths(
                    paths, index + 1, results,
                    failures + (client_error_text(snapshot.error),))
                return
            self._add_local_paths(
                paths, index + 1, results + (snapshot.result,), failures)
        self._run_job(job, finished)

    def _selected_remote_source(self):
        rows = self.app.rlist.get_selected_rows()
        if len(rows) != 1 or rows[0].item[0] == '..' or rows[0].item[1]:
            raise BrowserError('Select one D64 or CRT file in the C64U Files pane.')
        session = self.app.core.device_session()
        if not session.device_id or not session.session_id:
            raise BrowserError('Connect to the source C64U first.')
        return session.device_id, posixpath.join(self.app.remote, rows[0].item[0])

    def _selected_remote_files(self):
        rows = self.app.rlist.get_selected_rows()
        if not rows:
            raise BrowserError('Select one or more D64 or CRT files in the C64U Files pane.')
        names = []
        for row in rows:
            name, directory = row.item
            if (name == '..' or directory
                    or not name.casefold().endswith(('.d64', '.crt'))):
                raise BrowserError('Select only D64 or CRT files in the C64U Files pane.')
            names.append(name)
        session = self.app.core.device_session()
        if not session.device_id or not session.session_id:
            raise BrowserError('Connect to the source C64U first.')
        paths = tuple(posixpath.join(self.app.remote, name) for name in names)
        return session.device_id, paths

    def add_c64u(self):
        try:
            device_id, paths = self._selected_remote_files()
            if len(paths) > 1:
                job = self.client.scan_c64u_sources(device_id, paths)
                self._start_bulk_scan(job);return
            job = self.client.add_c64u(device_id, paths[0])
        except Exception as exc:self._show(str(exc));return
        def finished(snapshot):
            if snapshot.state != 'succeeded':
                self._show(client_error_text(snapshot.error));return
            self.client.select(snapshot.result.record.id)
            self.refresh(True);self._show('C64U game reference added to the library.')
        self._run_job(job, finished)

    def _scan_options(self, title, description, submit):
        dialog = Gtk.Dialog(title=title, transient_for=self.app.window, modal=True)
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        dialog.add_button('Scan', Gtk.ResponseType.OK)
        area = dialog.get_content_area();area.set_spacing(8)
        area.set_margin_top(12);area.set_margin_bottom(12)
        area.set_margin_start(12);area.set_margin_end(12)
        area.append(Gtk.Label(label=description, xalign=0, wrap=True,
                              selectable=True))
        recursive = Gtk.CheckButton(label='Include subfolders')
        recursive.set_halign(Gtk.Align.START);area.append(recursive)
        def response(widget, code):
            include = recursive.get_active();widget.destroy()
            if code == Gtk.ResponseType.OK:
                try:submit(include)
                except Exception as exc:self._show(str(exc))
        dialog.connect('response', response);dialog.present()
        dialog.recursive = recursive
        return dialog

    def scan_local_folder(self):
        if self.chooser:return
        chooser = Gtk.FileChooserNative.new(
            'Choose Game Library folder', self.app.window,
            Gtk.FileChooserAction.SELECT_FOLDER, 'Choose', 'Cancel')
        chooser.set_current_folder(Gio.File.new_for_path(str(self.app.local)))
        self.chooser = chooser
        def response(_, code):
            file = chooser.get_file();chooser.destroy();self.chooser = None
            if code != Gtk.ResponseType.ACCEPT or not file:return
            path = file.get_path()
            if not path:
                self._show('Choose a folder on the Argonaut Core computer.');return
            self._scan_options(
                'Scan local folder for games', path,
                lambda recursive:self._start_bulk_scan(
                    self.client.scan_core_host_folder(
                        path, recursive=recursive)))
        chooser.connect('response', response);chooser.show()

    def _selected_remote_folder(self):
        rows = self.app.rlist.get_selected_rows()
        if len(rows) != 1 or rows[0].item[0] == '..' or not rows[0].item[1]:
            raise BrowserError('Select one C64U folder to scan for games.')
        session = self.app.core.device_session()
        if not session.device_id or not session.session_id:
            raise BrowserError('Connect to the source C64U first.')
        return session.device_id, posixpath.join(
            self.app.remote, rows[0].item[0])

    def scan_c64u_folder(self, path=None):
        try:
            session = self.app.core.device_session()
            if path is None:
                device_id, path = self._selected_remote_folder()
            elif not session.device_id or not session.session_id:
                raise BrowserError('Connect to the source C64U first.')
            else:device_id = session.device_id
        except Exception as exc:self._show(str(exc));return
        return self._scan_options(
            'Scan C64U folder for games', path,
            lambda recursive:self._start_bulk_scan(
                self.client.scan_c64u_folder(
                    device_id, path, recursive=recursive)))

    def _start_bulk_scan(self, job):
        self._run_job(job, self._bulk_scanned)
        self._show('Scanning Game Library candidates…')

    def _bulk_scanned(self, snapshot):
        if snapshot.state != 'succeeded':
            message = ('Game Library scan cancelled.' if snapshot.state == 'cancelled'
                       else client_error_text(snapshot.error))
            self._show(message);return
        self.bulk_dialog = BulkImportDialog(self, snapshot.result)
        self._show('Game Library scan complete. Review the candidates.')

    def remove(self):
        record = self.client.selected()
        if record is None:return
        dialog = Gtk.Dialog(title='Remove from Game Library?',
                            transient_for=self.app.window, modal=True)
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        dialog.add_button('Remove catalog entry', Gtk.ResponseType.OK)
        dialog.get_content_area().append(Gtk.Label(
            label=(f'Remove “{record.title}” from the Game Library?\n\n'
                   'The referenced game file will not be deleted or changed.'),
            wrap=True, xalign=0, margin_top=12, margin_bottom=12,
            margin_start=12, margin_end=12))
        def answered(widget, code):
            widget.destroy()
            if code != Gtk.ResponseType.OK:return
            try:self.client.remove()
            except Exception as exc:self._show(str(exc));return
            self.client.selected_id = None;self.refresh(False)
            self._show('Catalog entry removed. The game file was not deleted.')
        dialog.connect('response', answered);dialog.present()

    def validate(self):
        try:job = self.client.validate()
        except Exception as exc:self._show(str(exc));return
        def finished(snapshot):
            if snapshot.state != 'succeeded':
                self._show(client_error_text(snapshot.error));return
            self.refresh(True)
            self._show('Source validation: ' + snapshot.result.record.state + '.')
        self._run_job(job, finished)

    def relink(self):
        record = self.client.selected()
        if record is None:return
        if record.source.scope == C64U:
            try:
                device_id, path = self._selected_remote_source()
                job = self.client.prepare_relink_c64u(device_id, path)
            except Exception as exc:self._show(str(exc));return
            self._run_job(job, self._relink_prepared);return
        if self.chooser:return
        chooser = Gtk.FileChooserNative.new(
            'Locate replacement D64 or CRT', self.app.window,
            Gtk.FileChooserAction.OPEN, 'Review', 'Cancel')
        current = Path(record.source.path).parent
        if current.is_dir():chooser.set_current_folder(Gio.File.new_for_path(str(current)))
        self._game_filter(chooser);self.chooser = chooser
        def response(_, code):
            file = chooser.get_file();chooser.destroy();self.chooser = None
            if code != Gtk.ResponseType.ACCEPT or not file:return
            path = file.get_path()
            if not path:return
            try:job = self.client.prepare_relink_core_host(path)
            except Exception as exc:self._show(str(exc));return
            self._run_job(job, self._relink_prepared)
        chooser.connect('response', response);chooser.show()

    def _relink_prepared(self, snapshot):
        if snapshot.state != 'succeeded':
            self._show(client_error_text(snapshot.error));return
        preview = snapshot.result
        dialog = Gtk.Dialog(title='Review Locate/Relink',
                            transient_for=self.app.window, modal=True)
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        button = dialog.add_button(
            'Relink' if preview.content_matches else 'Accept different content',
            Gtk.ResponseType.OK)
        if not preview.content_matches:button.add_css_class('destructive-action')
        comparison = ('SHA-256 matches the cataloged game.' if preview.content_matches
                      else 'SHA-256 differs. Accepting this changes the cataloged content identity.')
        dialog.get_content_area().append(Gtk.Label(
            label=(f'New source: {source_text(preview.source)}\n'
                   f'Format: {preview.format}\nSize: {preview.size:,} bytes\n\n'
                   + comparison), wrap=True, selectable=True, xalign=0,
            margin_top=12, margin_bottom=12, margin_start=12, margin_end=12))
        def answered(widget, code):
            widget.destroy()
            if code != Gtk.ResponseType.OK:return
            try:job = self.client.execute_relink(
                preview.plan_id, not preview.content_matches)
            except Exception as exc:self._show(str(exc));return
            def finished(result):
                if result.state != 'succeeded':
                    self._show(client_error_text(result.error));return
                self.refresh(True);self._show('Game source Relink completed.')
            self._run_job(job, finished)
        dialog.connect('response', answered);dialog.present()

    def choose_artwork(self):
        if not self.client.selected() or self.chooser:return
        chooser = Gtk.FileChooserNative.new(
            'Choose Game Library artwork', self.app.window,
            Gtk.FileChooserAction.OPEN, 'Choose', 'Cancel')
        filter_ = Gtk.FileFilter();filter_.set_name('PNG, JPEG, or WebP images')
        for pattern in ('*.png','*.PNG','*.jpg','*.JPG','*.jpeg','*.JPEG','*.webp','*.WEBP'):
            filter_.add_pattern(pattern)
        chooser.add_filter(filter_);self.chooser = chooser
        def response(_, code):
            file = chooser.get_file();chooser.destroy();self.chooser = None
            if code != Gtk.ResponseType.ACCEPT or not file:return
            path = file.get_path()
            if not path:return
            try:self.client.set_artwork(path)
            except Exception as exc:self._show(str(exc));return
            self._load_details();self._show('Artwork reference saved.')
        chooser.connect('response', response);chooser.show()

    def clear_artwork(self):
        if not self.client.selected():return
        try:self.client.set_artwork('')
        except Exception as exc:self._show(str(exc));return
        self._load_details();self._show('Artwork reference cleared.')

    def launch(self):
        if not self.client.can_launch(self.connected):return
        try:job = self.client.prepare_launch()
        except Exception as exc:self._show(str(exc));return
        self._run_job(job, self._launch_prepared)
        self._show('Preparing launch preview…')

    def _launch_prepared(self, snapshot):
        if snapshot.state != 'succeeded':
            self._show(client_error_text(snapshot.error));self.refresh(True);return
        preview = snapshot.result
        dialog = Gtk.Dialog(title='Review Game Launch',
                            transient_for=self.app.window, modal=True)
        dialog.set_default_size(620, 420)
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        dialog.add_button('Reset C64 and send command', Gtk.ResponseType.OK)
        lines = [
            f'Game: {preview.title}', f'Format: {preview.format}',
            f'Source: {source_text(preview.source)}',
            f'Target C64U: {preview.target_device_id}',
            f'Method: {mechanism_text(preview.mechanism)}', '',
            'The running C64 program will be interrupted and the C64 will reset.',
        ]
        if preview.format == 'CRT':
            lines.extend(('', 'Temporary cartridge:',
                'Reset restarts this cartridge. Reboot returns to the permanently configured cartridge, if one exists. Launching another CRT replaces it.'))
        lines.extend(('', 'Warnings:', *('• ' + item for item in preview.warnings)))
        text = Gtk.TextView(editable=False, cursor_visible=False,
                            wrap_mode=Gtk.WrapMode.WORD_CHAR)
        text.get_buffer().set_text('\n'.join(lines))
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(text);dialog.get_content_area().append(scroll)
        def answered(widget, code):
            widget.destroy()
            if code != Gtk.ResponseType.OK:
                self.client.discard_launch(preview.plan_id)
                self._show('Launch cancelled before sending a command.');return
            try:job = self.client.execute_launch(preview.plan_id)
            except Exception as exc:self._show(str(exc));return
            self._run_job(job, self._launch_finished)
        dialog.connect('response', answered);dialog.present()

    def _launch_finished(self, snapshot):
        if snapshot.state == 'succeeded':
            self._show(
                'Command accepted. Argonaut cannot verify that the game reached a playable screen.')
            return
        self._show(client_error_text(snapshot.error))
        self.refresh(True)
