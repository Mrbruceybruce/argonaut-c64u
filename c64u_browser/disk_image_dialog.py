# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Authentic flat Commodore disk directory and safe D64 staging."""
from pathlib import Path
import posixpath

from gi.repository import Gio, GLib, Gtk

from .disk_image import D64Image, D71Image, D81Image
from .disk_image_edit import D64EditSession, D71EditSession, D81EditSession
from .disk_image_io import (
    extract_new, read_host_file_for_disk, save_edited_copy, suggested_import_type,
    suggested_name)


class DiskImageDialog:
    def __init__(self, app, source, image):
        self.app = app
        self.image = image
        self.source = source
        self.chooser = None
        self.prompt = None
        self.name_entry = None
        self.restore_focus_on_destroy = False
        directory = image.directory()
        validation = image.validate()
        format_name = image.format_name
        drive_model = image.drive_model
        session_type = ({D64Image: D64EditSession, D71Image: D71EditSession,
                         D81Image: D81EditSession}
                        .get(type(image)))
        try:
            self.session = session_type(image) if session_type else None
        except Exception:
            self.session = None
        self.dialog = Gtk.Dialog(
            title=f'{format_name} disk directory', transient_for=app.window, modal=True)
        self.dialog.set_default_size(760, 560)
        self.dialog.add_button('Close', Gtk.ResponseType.CLOSE)
        self.dialog.connect('response', self.close)
        self.dialog.connect('close-request', self.close_request)
        self.dialog.connect('destroy', self.destroyed)
        box = self.dialog.get_content_area()
        self.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.controls)
        self.controls.append(Gtk.Label(
            label='Source image: ' + source, xalign=0, wrap=True))
        self.controls.append(Gtk.Label(
            label=(f'Disk directory: 0 "{directory.disk_name}" '
                   f'{directory.disk_id} {directory.dos_type}  ·  '
                   f'{directory.geometry.tracks}-track {format_name}'
                   + (f' · standard {drive_model} format' if directory.geometry.standard
                      else ' · extended nonstandard format')),
            xalign=0, wrap=True))
        file_actions = Gtk.Box(spacing=8)
        self.controls.append(file_actions)
        self.extract_button = app.icon_button(
            file_actions, 'Extract selected…', 'document-save-symbolic', self.extract)
        self.extract_button.set_sensitive(False)
        self.add_button = app.icon_button(
            file_actions, 'Add file…', 'list-add-symbolic', self.add_file)
        self.rename_button = app.icon_button(
            file_actions, 'Rename…', 'document-edit-symbolic', self.rename)
        self.remove_button = app.icon_button(
            file_actions, 'Remove', 'edit-delete-symbolic', self.remove)
        edit_actions = Gtk.Box(spacing=8)
        edit_actions.set_halign(Gtk.Align.END)
        self.controls.append(edit_actions)
        self.discard_button = app.button(edit_actions, 'Discard changes', self.discard)
        self.save_button = app.button(edit_actions, 'Save image as…', self.save_copy)
        self.listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.listing.connect('row-selected', lambda *_: self.update())
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(self.listing)
        self.controls.append(scroll)
        self.free_label = Gtk.Label(xalign=0, selectable=True)
        self.controls.append(self.free_label)
        self.validation_label = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.controls.append(self.validation_label)
        self.staged_label = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.controls.append(self.staged_label)
        self.status = Gtk.Label(
            label=('Source image is unchanged. Stage edits here, then save a validated '
                   'copy under a new local filename.' if self.session else
                   f'Read-only {format_name} view. The source image is unchanged.'),
            xalign=0, wrap=True, selectable=True)
        box.append(self.status)
        self.render()
        if not directory.geometry.standard:
            self.status.set_text(
                'Read-only view. This extended-track image is not a standard 35-track 1541 disk.')
        self.dialog.present()

    def close_request(self, *_):
        self.close()
        return True

    def destroyed(self, *_):
        if getattr(self.app, 'disk_image_dialog', None) is self:
            self.app.disk_image_dialog = None
        if self.restore_focus_on_destroy:
            GLib.idle_add(self.restore_parent_focus)

    def restore_parent_focus(self):
        window = getattr(self.app, 'window', None)
        if window is not None:
            window.present()
        return False

    def render(self):
        image = self.session.image if self.session else self.image
        directory = image.directory()
        validation = image.validate()
        child = self.listing.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.listing.remove(child)
            child = following
        for entry in directory.entries:
            display_type = (('*' if not entry.closed else '') + entry.file_type
                            + ('<' if entry.locked else ''))
            if entry.file_type == 'CBM':
                display_type = ('CBM partition' +
                                (' (subdirectory-capable)'
                                 if entry.partition_kind == 'subdirectory-capable'
                                 else ''))
            row = Gtk.ListBoxRow()
            row.entry = entry
            row.set_child(Gtk.Label(
                label=f'{entry.blocks:>5}  "{entry.name}"  {display_type}',
                xalign=0))
            self.listing.append(row)
        self.free_label.set_text(f'{directory.blocks_free} BLOCKS FREE.')
        partitions = sum(entry.file_type == 'CBM' for entry in directory.entries)
        checked = f'{validation.entries_checked} file chain(s)'
        if partitions:
            checked += f' and {partitions} CBM partition allocation(s)'
        self.validation_label.set_text(
            f'Structure check: standard {image.drive_model} directory and '
                   f'{checked} passed.'
                   if validation.standard_compatible else
                   f'Structure check: {len(validation.issues)} nonstandard or damaged '
                   'condition(s) detected. The image remains available read-only.')
        count = len(self.session.changes) if self.session else 0
        self.staged_label.set_text(
            f'Staged changes: {count}. The source image has not been changed.' if count else
            'Staged changes: none.')
        self.update()

    def close(self, *_):
        if self.app.busy:
            self.status.set_text('Wait for the current extraction to finish.')
            return
        if self.prompt is not None:
            return
        if self.session and self.session.has_unsaved_changes:
            prompt = Gtk.Dialog(
                title='Discard staged disk changes?', transient_for=self.dialog, modal=True)
            self.prompt = prompt
            prompt.add_button('Keep editing', Gtk.ResponseType.CANCEL)
            prompt.add_button('Discard', Gtk.ResponseType.OK)
            prompt.get_content_area().append(Gtk.Label(
                label='The source disk image is unchanged, but the staged edits will be lost.',
                margin_top=12, margin_bottom=12, margin_start=12, margin_end=12,
                wrap=True))
            def response(_, code):
                prompt.destroy()
                self.prompt = None
                if code == Gtk.ResponseType.OK:
                    self.session.discard()
                    self.close()
            prompt.connect('response', response)
            prompt.present()
            return
        if self.chooser is not None:
            self.chooser.destroy()
            self.chooser = None
        self.restore_focus_on_destroy = True
        self.dialog.destroy()

    def refresh_local_destination(self, path):
        destination = Path(path)
        if destination.parent.resolve() == self.app.local.resolve():
            self.app.refresh_local((destination.name,))

    def update(self):
        row = self.listing.get_selected_row()
        selected = row is not None
        editable = self.session is not None
        self.extract_button.set_sensitive(
            selected and row.entry.file_type in ('PRG', 'SEQ', 'USR', 'REL'))
        self.add_button.set_sensitive(editable)
        self.rename_button.set_sensitive(editable and selected)
        self.remove_button.set_sensitive(
            editable and selected and self.session.can_remove(row.entry))
        dirty = editable and self.session.dirty
        self.discard_button.set_sensitive(dirty)
        self.save_button.set_sensitive(editable and self.session.has_unsaved_changes)

    def _name_prompt(self, title, name, accept, callback, file_type=None,
                     cancelled=None):
        prompt = Gtk.Dialog(title=title, transient_for=self.dialog, modal=True)
        self.prompt = prompt
        prompt.add_button('Cancel', Gtk.ResponseType.CANCEL)
        action = prompt.add_button(accept, Gtk.ResponseType.OK)
        prompt.set_default_response(Gtk.ResponseType.OK)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                          margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        entry = Gtk.Entry(text=name, max_length=16, hexpand=True)
        self.name_entry = entry
        content.append(Gtk.Label(label='C64 disk filename (up to 16 characters):', xalign=0))
        content.append(entry)
        types = None
        if file_type is not None:
            types = Gtk.ComboBoxText()
            for value in ('PRG', 'SEQ', 'USR'):
                types.append_text(value)
            types.set_active(('PRG', 'SEQ', 'USR').index(file_type))
            content.append(Gtk.Label(label='C64 file type:', xalign=0))
            content.append(types)
        prompt.get_content_area().append(content)
        def update(*_):
            action.set_sensitive(bool(entry.get_text().strip()))
        entry.connect('changed', update)
        entry.connect(
            'activate', lambda *_: prompt.response(Gtk.ResponseType.OK)
            if action.get_sensitive() else None)
        update()
        def response(_, code):
            value = entry.get_text()
            chosen_type = types.get_active_text() if types else None
            prompt.destroy()
            self.prompt = None
            self.name_entry = None
            if code == Gtk.ResponseType.OK:
                callback(value, chosen_type)
            elif cancelled:
                cancelled()
        prompt.connect('response', response)
        prompt.present()

    def rename(self):
        row = self.listing.get_selected_row()
        if self.app.busy or not self.session or row is None:
            return
        def apply(name, _):
            try:
                self.session.rename(row.entry, name)
                self.render()
                self.status.set_text('Rename staged. Save an edited copy to publish the change.')
            except Exception as exc:
                self.status.set_text(str(exc))
        self._name_prompt('Rename disk file', row.entry.name, 'Stage rename', apply)

    def remove(self):
        row = self.listing.get_selected_row()
        if self.app.busy or not self.session or row is None:
            return
        try:
            self.session.remove(row.entry)
            self.render()
            self.status.set_text('Removal staged. The source image is unchanged.')
        except Exception as exc:
            self.status.set_text(str(exc))

    def discard(self):
        if self.app.busy or not self.session:
            return
        self.session.discard()
        self.render()
        self.status.set_text('All staged changes discarded. The source image was unchanged.')

    def add_file(self):
        if self.app.busy or not self.session:
            return
        chooser = Gtk.FileChooserNative.new(
            f'Choose files to add to {self.image.format_name} copy',
            self.dialog, Gtk.FileChooserAction.OPEN,
            'Choose', 'Cancel')
        chooser.set_select_multiple(True)
        chooser.set_current_folder(Gio.File.new_for_path(str(self.app.local)))
        self.chooser = chooser
        def response(_, code):
            files = chooser.get_files()
            chosen = ([files.get_item(index) for index in range(files.get_n_items())]
                      if code == Gtk.ResponseType.ACCEPT else [])
            chooser.destroy()
            self.chooser = None
            if not chosen:
                return
            paths = [file.get_path() for file in chosen]
            if any(not path for path in paths):
                self.status.set_text('Choose a local file.')
                return
            if len(paths) > 64:
                self.status.set_text('Choose at most 64 files in one Add operation.')
                return
            def loaded(result):
                if isinstance(result, Exception):
                    self.status.set_text(str(result))
                    return
                items = [(path, data, Path(path).stem[:16],
                          suggested_import_type(path, data))
                         for path, data in result]
                self._batch_add_review(items)
            def caught():
                try:
                    return [(path, read_host_file_for_disk(
                        path, self.image.geometry.sectors * 254)) for path in paths]
                except Exception as exc:
                    return exc
            self.app.run(caught, loaded)
        chooser.connect('response', response)
        chooser.show()

    def _batch_add_review(self, items):
        """Review and validate one or many imports before staging the batch."""
        prompt = Gtk.Dialog(
            title='Review files to add', transient_for=self.dialog, modal=True)
        self.prompt = prompt
        prompt.set_default_size(760, min(620, 190 + len(items) * 48))
        prompt.add_button('Cancel', Gtk.ResponseType.CANCEL)
        action = prompt.add_button(
            'Add file' if len(items) == 1 else f'Add {len(items)} files',
            Gtk.ResponseType.OK)
        prompt.set_default_response(Gtk.ResponseType.OK)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                          margin_top=12, margin_bottom=12,
                          margin_start=12, margin_end=12)
        content.append(Gtk.Label(
            label=('Review the C64 filename and type for each host file. '
                   'The complete batch is validated before any file is staged.'),
            xalign=0, wrap=True))
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        for column, title in enumerate(('Host file', 'C64 filename', 'Type')):
            heading = Gtk.Label(label=title, xalign=0)
            heading.add_css_class('heading')
            grid.attach(heading, column, 0, 1, 1)
        rows = []
        for index, (path, data, name, file_type) in enumerate(items, 1):
            source = Gtk.Label(label=Path(path).name, xalign=0,
                               hexpand=True, tooltip_text=str(path))
            entry = Gtk.Entry(text=name, max_length=16, hexpand=True)
            entry.set_activates_default(True)
            types = Gtk.ComboBoxText()
            for value in ('PRG', 'SEQ', 'USR'):
                types.append_text(value)
            types.set_active(('PRG', 'SEQ', 'USR').index(file_type))
            grid.attach(source, 0, index, 1, 1)
            grid.attach(entry, 1, index, 1, 1)
            grid.attach(types, 2, index, 1, 1)
            rows.append((path, data, entry, types))
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True,
                                    min_content_height=min(360, len(items) * 48 + 40))
        scroll.set_child(grid)
        content.append(scroll)
        message = Gtk.Label(xalign=0, wrap=True)
        message.add_css_class('error')
        content.append(message)
        prompt.get_content_area().append(content)

        def update(*_):
            action.set_sensitive(all(entry.get_text().strip()
                                     for _, _, entry, _ in rows))
        for _, _, entry, _ in rows:
            entry.connect('changed', update)
        update()

        def response(_, code):
            if code != Gtk.ResponseType.OK:
                prompt.destroy()
                self.prompt = None
                return
            reviewed = [(path, data, entry.get_text(), types.get_active_text())
                        for path, data, entry, types in rows]
            try:
                self.session.add_files(
                    (data, name, file_type)
                    for _, data, name, file_type in reviewed)
            except Exception as exc:
                message.set_text(str(exc))
                return
            prompt.destroy()
            self.prompt = None
            self.render()
            count = len(reviewed)
            self.status.set_text(
                f'{count} file addition(s) staged. The source image is unchanged.')
        prompt.connect('response', response)
        prompt.present()

    def save_copy(self):
        if self.app.busy or not self.session or not self.session.dirty:
            return
        chooser = Gtk.FileChooserNative.new(
            f'Save {self.image.format_name} image as',
            self.dialog, Gtk.FileChooserAction.SAVE,
            'Save image', 'Cancel')
        self.chooser = chooser
        chooser.set_current_folder(Gio.File.new_for_path(str(self.app.local)))
        source_leaf = posixpath.basename(str(self.source).replace('\\', '/'))
        extension = self.session.extension
        stem = (source_leaf[:-len(extension)]
                if source_leaf.casefold().endswith(extension) else 'disk')
        chooser.set_current_name(stem + '-edited' + extension)
        def response(_, code):
            file = chooser.get_file()
            chooser.destroy()
            self.chooser = None
            if code != Gtk.ResponseType.ACCEPT or not file:
                return
            path = file.get_path()
            if not path:
                self.status.set_text('Choose a local destination file.')
                return
            self.controls.set_sensitive(False)
            def caught():
                try:
                    return save_edited_copy(self.session, path)
                except Exception as exc:
                    return exc
            def done(result):
                self.controls.set_sensitive(True)
                self.update()
                if isinstance(result, Exception):
                    self.status.set_text(str(result))
                else:
                    self.refresh_local_destination(result['path'])
                    self.status.set_text(
                        f'Saved validated copy with {result["changes"]} staged change(s) '
                        f'to {result["path"]}. The source image was unchanged.')
            self.app.run(caught, done)
        chooser.connect('response', response)
        chooser.show()

    def extract(self):
        row = self.listing.get_selected_row()
        if self.app.busy or row is None:
            return
        chooser = Gtk.FileChooserNative.new(
            'Extract file from D64', self.dialog, Gtk.FileChooserAction.SAVE,
            'Extract', 'Cancel')
        self.chooser = chooser
        chooser.set_current_folder(Gio.File.new_for_path(str(self.app.local)))
        chooser.set_current_name(suggested_name(row.entry))

        def response(_, code):
            file = chooser.get_file()
            chooser.destroy()
            self.chooser = None
            if code != Gtk.ResponseType.ACCEPT or not file:
                return
            path = file.get_path()
            if not path:
                self.status.set_text('Choose a local destination file.')
                return
            self.controls.set_sensitive(False)

            def caught():
                try:
                    image = self.session.image if self.session else self.image
                    return extract_new(image, row.entry, path)
                except Exception as exc:
                    return exc

            def done(result):
                self.controls.set_sensitive(True)
                if isinstance(result, Exception):
                    self.status.set_text(str(result))
                else:
                    self.refresh_local_destination(result['path'])
                    self.status.set_text(
                        f'Extracted {result["bytes"]:,} bytes to {result["path"]}. '
                        'The disk image was unchanged.')
            self.app.run(caught, done)

        chooser.connect('response', response)
        chooser.show()
