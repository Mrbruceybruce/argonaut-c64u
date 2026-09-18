# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Read-only presentation of an authentic flat 1541 disk directory."""
from gi.repository import Gtk

from .disk_image_io import extract_new, suggested_name


class DiskImageDialog:
    def __init__(self, app, source, image):
        self.app = app
        self.image = image
        self.chooser = None
        directory = image.directory()
        validation = image.validate()
        self.dialog = Gtk.Dialog(
            title='D64 disk directory', transient_for=app.window, modal=True)
        self.dialog.set_default_size(760, 560)
        self.dialog.add_button('Close', Gtk.ResponseType.CLOSE)
        self.dialog.connect('response', self.close)
        box = self.dialog.get_content_area()
        self.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.controls)
        self.controls.append(Gtk.Label(
            label='Source image: ' + source, xalign=0, wrap=True, selectable=True))
        self.controls.append(Gtk.Label(
            label=(f'Disk directory: 0 "{directory.disk_name}" '
                   f'{directory.disk_id} {directory.dos_type}  ·  '
                   f'{directory.geometry.tracks}-track D64'
                   + (' · standard 1541 format' if directory.geometry.standard
                      else ' · extended nonstandard format')),
            xalign=0, wrap=True, selectable=True))
        actions = Gtk.Box(spacing=8)
        self.controls.append(actions)
        self.extract_button = app.button(actions, 'Extract selected…', self.extract)
        self.extract_button.set_sensitive(False)
        self.listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.listing.connect('row-selected', lambda *_: self.update())
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(self.listing)
        self.controls.append(scroll)
        for entry in directory.entries:
            display_type = (('*' if not entry.closed else '') + entry.file_type
                            + ('<' if entry.locked else ''))
            row = Gtk.ListBoxRow()
            row.entry = entry
            row.set_child(Gtk.Label(
                label=f'{entry.blocks:>5}  "{entry.name}"  {display_type}',
                xalign=0))
            self.listing.append(row)
        self.controls.append(Gtk.Label(
            label=f'{directory.blocks_free} BLOCKS FREE.', xalign=0, selectable=True))
        self.controls.append(Gtk.Label(
            label=(f'Structure check: standard 1541 directory and '
                   f'{validation.entries_checked} file chain(s) passed.'
                   if validation.standard_compatible else
                   f'Structure check: {len(validation.issues)} nonstandard or damaged '
                   'condition(s) detected. The image remains available read-only.'),
            xalign=0, wrap=True, selectable=True))
        if not directory.geometry.standard:
            self.controls.append(Gtk.Label(
                label='This extended-track image is readable but is not a standard 35-track 1541 disk.',
                xalign=0, wrap=True))
        self.status = Gtk.Label(
            label='Read-only view. Opening this directory does not change the disk image.',
            xalign=0, wrap=True, selectable=True)
        box.append(self.status)
        self.dialog.present()

    def close(self, *_):
        if self.app.busy:
            self.status.set_text('Wait for the current extraction to finish.')
            return
        if self.chooser is not None:
            self.chooser.destroy()
            self.chooser = None
        self.dialog.destroy()

    def update(self):
        self.extract_button.set_sensitive(self.listing.get_selected_row() is not None)

    def extract(self):
        row = self.listing.get_selected_row()
        if self.app.busy or row is None:
            return
        chooser = Gtk.FileChooserNative.new(
            'Extract file from D64', self.dialog, Gtk.FileChooserAction.SAVE,
            'Extract', 'Cancel')
        self.chooser = chooser
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
                    return extract_new(self.image, row.entry, path)
                except Exception as exc:
                    return exc

            def done(result):
                self.controls.set_sensitive(True)
                if isinstance(result, Exception):
                    self.status.set_text(str(result))
                else:
                    self.status.set_text(
                        f'Extracted {result["bytes"]:,} bytes to {result["path"]}. '
                        'The disk image was unchanged.')
            self.app.run(caught, done)

        chooser.connect('response', response)
        chooser.show()
