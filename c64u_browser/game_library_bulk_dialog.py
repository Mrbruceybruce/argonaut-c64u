# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Thin GTK review client for Core-owned Game Library Bulk Import."""
from gi.repository import GLib, Gtk

from .game_library_client import (
    BULK_FILTERS, BulkReviewState, bulk_progress_text, client_error_text,
)


CLASSIFICATION_LABELS = {
    'new-valid':'New game image',
    'already-cataloged-source':'Already cataloged',
    'duplicate-catalog-content':'Duplicate catalog content',
    'duplicate-scan-content':'Duplicate content in this scan',
    'duplicate-scan-path':'Duplicate source in this scan',
    'changed-existing-source':'Changed existing source',
    'invalid-image':'Invalid image',
    'unsupported-file':'Unsupported file',
    'inaccessible-file':'Inaccessible file',
    'branch-unavailable':'Folder unavailable',
}


class BulkImportDialog:
    def __init__(self, tab, preview):
        self.tab = tab
        self.app = tab.app
        self.client = tab.client
        self.preview = preview
        self.state = BulkReviewState(preview)
        self.executing = False
        self.finished = False
        self.row_checks = {}

        self.dialog = Gtk.Dialog(
            title='Review Game Library Bulk Import',
            transient_for=self.app.window, modal=True)
        self.dialog.set_default_size(940, 680)
        self.cancel_button = self.dialog.add_button(
            'Cancel', Gtk.ResponseType.CANCEL)
        self.import_button = self.dialog.add_button(
            self.state.import_label, Gtk.ResponseType.OK)
        self.import_button.add_css_class('suggested-action')
        self.dialog.connect('response', self._response)
        self.dialog.connect('destroy', self._destroyed)

        content = self.dialog.get_content_area()
        content.set_spacing(8)
        content.set_margin_top(12);content.set_margin_bottom(12)
        content.set_margin_start(12);content.set_margin_end(12)
        self.summary = Gtk.Label(xalign=0, wrap=True, selectable=True)
        content.append(self.summary)

        controls = Gtk.Box(spacing=8)
        content.append(controls)
        controls.append(Gtk.Label(label='Show:', xalign=0))
        self.filter = Gtk.ComboBoxText()
        for key, label in BULK_FILTERS:self.filter.append(key, label)
        self.filter.set_active_id('all')
        self.filter.connect('changed', self._filter_changed)
        controls.append(self.filter)
        self.select_all_button = Gtk.Button(label='Select all new')
        self.select_none_button = Gtk.Button(label='Select none')
        self.select_all_button.connect('clicked', lambda *_:self.select_all_new())
        self.select_none_button.connect('clicked', lambda *_:self.select_none())
        controls.append(self.select_all_button);controls.append(self.select_none_button)

        header = Gtk.Box(spacing=8)
        for text, expand in (('Import', False), ('Path / name', True),
                             ('Format', False), ('Size', False),
                             ('Classification / reason', True)):
            label = Gtk.Label(label=text, xalign=0, hexpand=expand)
            label.add_css_class('heading');header.append(label)
        content.append(header)
        self.rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True,
                                         min_content_height=320)
        self.scroll.set_child(self.rows);content.append(self.scroll)
        self.progress = Gtk.Label(xalign=0, wrap=True, selectable=True)
        content.append(self.progress)
        self._refresh_summary();self._refresh_rows();self._update_import()
        self.dialog.present()

    def _destroyed(self, *_):
        if getattr(self.tab, 'bulk_dialog', None) is self:
            self.tab.bulk_dialog = None

    def _refresh_summary(self):
        totals = self.state.totals()
        self.summary.set_text(
            f'{totals["entries"]:,} entries examined · '
            f'{totals["candidates"]:,} D64/CRT candidates · '
            f'{totals["new"]:,} new · {totals["cataloged"]:,} already cataloged · '
            f'{totals["duplicates"]:,} duplicate · {totals["changed"]:,} changed · '
            f'{totals["problems"]:,} invalid/inaccessible · '
            f'{totals["unsupported"]:,} unsupported')

    @staticmethod
    def _size_text(candidate):
        size = candidate.size if candidate.size is not None else candidate.declared_size
        return '—' if size is None else f'{size:,} bytes'

    def _candidate_row(self, candidate):
        row = Gtk.ListBoxRow(selectable=False, activatable=False)
        box = Gtk.Box(spacing=8)
        box.set_margin_top(5);box.set_margin_bottom(5)
        box.set_margin_start(5);box.set_margin_end(5)
        check = Gtk.CheckButton(active=candidate.id in self.state.selected)
        check.set_sensitive(candidate.importable and not self.executing)
        check.update_property([Gtk.AccessibleProperty.LABEL],
                              [f'Import {candidate.relative_path}'])
        check.connect('toggled', self._candidate_toggled, candidate.id)
        self.row_checks[candidate.id] = check;box.append(check)
        box.append(Gtk.Label(label=candidate.relative_path, xalign=0,
                             hexpand=True, ellipsize=3))
        box.append(Gtk.Label(label=candidate.format or '—', xalign=0))
        box.append(Gtk.Label(label=self._size_text(candidate), xalign=0))
        reason = CLASSIFICATION_LABELS.get(
            candidate.classification, candidate.classification)
        if candidate.message:reason += ' — ' + candidate.message
        box.append(Gtk.Label(label=reason, xalign=0, hexpand=True,
                             wrap=True, selectable=True))
        row.set_child(box);return row

    def _issue_row(self, issue):
        row = Gtk.ListBoxRow(selectable=False, activatable=False)
        label = Gtk.Label(
            label=f'    {issue.path}    Folder unavailable — {issue.message}',
            xalign=0, wrap=True, selectable=True,
            margin_top=5, margin_bottom=5, margin_start=5, margin_end=5)
        row.set_child(label);return row

    def _refresh_rows(self):
        while self.rows.get_first_child():self.rows.remove(self.rows.get_first_child())
        self.row_checks = {}
        for candidate in self.state.rows():
            self.rows.append(self._candidate_row(candidate))
        if self.state.filter in ('all', 'problems'):
            for issue in self.preview.issues:self.rows.append(self._issue_row(issue))

    def _candidate_toggled(self, button, candidate_id):
        try:self.state.set_selected(candidate_id, button.get_active())
        except ValueError:
            button.set_active(False)
        self._update_import()

    def _filter_changed(self, widget):
        self.state.set_filter(widget.get_active_id() or 'all')
        self._refresh_rows();self._update_import()

    def select_all_new(self):
        self.state.select_all_new();self._refresh_rows();self._update_import()

    def select_none(self):
        self.state.select_none();self._refresh_rows();self._update_import()

    def _update_import(self):
        self.import_button.set_label(self.state.import_label)
        self.import_button.set_sensitive(
            self.state.count > 0 and not self.executing and not self.finished)

    def _set_review_sensitive(self, value):
        self.filter.set_sensitive(value)
        self.select_all_button.set_sensitive(value)
        self.select_none_button.set_sensitive(value)
        eligible = set(self.preview.eligible_candidate_ids)
        for candidate_id, check in self.row_checks.items():
            check.set_sensitive(value and candidate_id in eligible)

    def _response(self, _dialog, code):
        if self.finished:
            self.dialog.destroy();return
        if code != Gtk.ResponseType.OK:
            if self.executing:
                self.tab.cancel_operation()
                self.progress.set_text('Cancelling Bulk Import…')
                self.cancel_button.set_sensitive(False)
                return
            self.client.discard_bulk_import(self.preview.plan_id)
            self.dialog.destroy();return
        if self.executing or not self.state.count:return
        try:
            selection = self.client.select_bulk_candidates(
                self.preview, self.state.selected_ids())
            job = self.client.execute_bulk_import(selection)
        except Exception as exc:
            self.progress.set_text(str(exc) + ' Scan the folder or files again.')
            self.import_button.set_sensitive(False)
            return
        self.executing = True;self._set_review_sensitive(False)
        self._update_import();self.cancel_button.set_label('Cancel import')
        self.progress.set_text('Starting reviewed Bulk Import…')
        def event(update):
            progress = update.job.progress
            if update.kind == 'progress' and progress:
                GLib.idle_add(self.progress.set_text,
                              bulk_progress_text(progress))
        job.add_listener(event)
        self.tab._run_job(job, self._finished)

    def _finished(self, snapshot):
        self.executing = False;self.finished = True
        self.cancel_button.set_sensitive(True);self.cancel_button.set_label('Close')
        self.import_button.set_visible(False)
        if snapshot.state != 'succeeded':
            if snapshot.state == 'cancelled':
                message = 'Bulk Import cancelled before catalog publication.'
            else:
                message = client_error_text(snapshot.error)
                if snapshot.error and snapshot.error.code in ('plan', 'session', 'device'):
                    message += ' Scan the folder or files again.'
            self.summary.set_text(message);self.progress.set_text(message)
            self.tab._show(message);return
        result = snapshot.result
        message = (f'Bulk Import complete: {result.created_count:,} added · '
                   f'{result.skipped_count:,} skipped/reclassified · '
                   f'{result.failure_count:,} failed.')
        self.summary.set_text(message);self.progress.set_text(message)
        while self.rows.get_first_child():self.rows.remove(self.rows.get_first_child())
        notable = tuple(item for item in result.outcomes if item.status != 'created')
        if not notable:
            row = Gtk.ListBoxRow(selectable=False, activatable=False)
            row.set_child(Gtk.Label(label='All approved games were added.',
                                    xalign=0, margin_top=8, margin_bottom=8))
            self.rows.append(row)
        for outcome in notable:
            detail = CLASSIFICATION_LABELS.get(
                outcome.classification, outcome.classification)
            if outcome.message:detail += ' — ' + outcome.message
            row = Gtk.ListBoxRow(selectable=False, activatable=False)
            row.set_child(Gtk.Label(
                label=f'{outcome.source.path}    {detail}', xalign=0,
                wrap=True, selectable=True, margin_top=5, margin_bottom=5))
            self.rows.append(row)
        self.tab.refresh(False)
        self.tab._show(message)
