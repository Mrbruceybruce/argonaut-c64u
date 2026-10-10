# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone selector. The host supplies Core and its existing job admission.

No consumer is wired here. Consumers must validate returned references and bind
execution to their captured session; a picker result is not operation authority.
"""
from pathlib import Path
from gi.repository import GLib, Gtk, Pango
from .file_selection import ClickPolicy, FileListActivation
from .picker_model import PickerModel, PickerMode, PickerError, SID
from .storage import root_presentation


class FilePicker:
    """Call callback(tuple[PickerSelection, ...] | None) exactly once.

    host exposes window, core, run(task, done), and run_file_job(factory, done,
    failed=...). Remote reads use the existing foreground admission and Core
    session-bound listing job. Closing discards results; it does not cancel an
    unrelated host operation. The global presenter retains read cancellation.
    """
    def __init__(self, host, callback, *, mode=PickerMode.OPEN_FILE,
                 scopes=('core-host', 'c64u'), filter=SID, limit=1, local_path=None):
        self.host, self.callback = host, callback
        self.model = PickerModel(mode, scopes, filter, limit)
        self.closed = False
        self.scope = self.model.scopes[0]
        self.paths = {'core-host': str(local_path or Path.home()), 'c64u': '/'}
        self.dialog = Gtk.Dialog(title='Choose a folder' if mode == PickerMode.OPEN_FOLDER
                                 else 'Choose files', transient_for=host.window, modal=True)
        self.dialog.set_default_size(650, 480)
        self.dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        self.select = self.dialog.add_button('Select', Gtk.ResponseType.ACCEPT)
        self.select.set_sensitive(False)
        box = self.dialog.get_content_area()
        box.set_spacing(8)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(box, 'set_margin_' + side)(12)
        sources = Gtk.Box(spacing=8)
        for scope in self.model.scopes:
            button = Gtk.Button(label='This Computer' if scope == 'core-host' else 'C64 Ultimate')
            button.connect('clicked', lambda _, s=scope: self.navigate(s, self.paths[s]))
            sources.append(button)
        box.append(sources)
        nav = Gtk.Box(spacing=8)
        up = Gtk.Button(label='Parent folder')
        up.connect('clicked', self.go_parent)
        nav.append(up)
        self.path = Gtk.Entry(hexpand=True)
        self.path.update_property([Gtk.AccessibleProperty.LABEL], ['Picker folder path'])
        self.path.connect('activate', lambda _: self.navigate(self.scope, self.path.get_text()))
        nav.append(self.path)
        refresh = Gtk.Button(label='Refresh')
        refresh.connect('clicked', lambda _: self.navigate(self.scope, self.paths[self.scope]))
        nav.append(refresh)
        box.append(nav)
        box.append(Gtk.Label(label=filter.label, xalign=0))
        self.listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE
            if self.model.mode == PickerMode.OPEN_FILES else Gtk.SelectionMode.SINGLE)
        self.listing.update_property([Gtk.AccessibleProperty.LABEL], ['Files and folders to select'])
        self.listing.connect('selected-rows-changed', lambda _: self.update_selection())
        self.policy = ClickPolicy()
        self.activation = FileListActivation(self.listing, self.policy, self.activate)
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.listing)
        box.append(scroll)
        self.status = Gtk.Label(xalign=0, wrap=True)
        box.append(self.status)
        self.dialog.connect('response', self.response)
        self.dialog.connect('close-request', self.close_requested)
        self.unsubscribe = host.core.add_listener(self.session_event)
        self.dialog.present()
        self.navigate(self.scope, self.paths[self.scope])

    def clear(self):
        self.activation.cancel()
        while self.listing.get_first_child():
            self.listing.remove(self.listing.get_first_child())
        self.select.set_sensitive(False)

    def session_event(self, _):
        # Core may deliver on a worker. Recheck identity on the GTK thread.
        if not self.closed:
            GLib.idle_add(self.check_session)

    def check_session(self):
        if self.closed:
            return GLib.SOURCE_REMOVE
        token = self.model.loaded or self.model.pending
        if token and not self.model.current(token, self.host.core.device_session()):
            self.model.invalidate()
            self.clear()
            self.status.set_text('Connection changed. Refresh to browse this device again.')
        return GLib.SOURCE_REMOVE

    def failure(self, token, error):
        if self.closed or token.generation != self.model.generation:
            return
        self.model.invalidate()
        self.clear()
        self.status.set_text(str(error))

    def navigate(self, scope, path):
        if self.closed:
            return
        self.clear()
        try:
            token = self.model.begin(scope, path, self.host.core.device_session())
        except PickerError as exc:
            self.status.set_text(str(exc))
            return
        self.scope = scope
        self.paths[scope] = token.path
        self.path.set_text(token.path)
        self.status.set_text('Loading…')
        if scope == 'core-host':
            def task():
                try:
                    return self.model.local_listing(token.path)
                except OSError as exc:
                    return exc
            def done(result):
                if isinstance(result, Exception):
                    self.failure(token, result)
                else:
                    self.complete(token, result)
            admitted = self.host.run(task, done)
        else:
            def submit():
                if self.closed or not self.model.current(token, self.host.core.device_session()):
                    raise PickerError('Connection changed before browsing started.')
                return self.host.core.list_directory(token.path)
            def done(snapshot):
                if snapshot.state != 'succeeded':
                    self.failure(token, snapshot.error.message if snapshot.error else 'Browsing cancelled.')
                elif (snapshot.device_id, snapshot.session_id) != (token.device_id, token.session_id):
                    self.failure(token, 'Connection changed during browsing.')
                else:
                    self.complete(token, snapshot.result)
            admitted = self.host.run_file_job(submit, done, failed=lambda e: self.failure(token, e))
        if not admitted and self.model.pending == token:
            self.failure(token, 'Another operation is in progress. Try again when it finishes.')

    def complete(self, token, result):
        if self.closed:
            return
        try:
            if not self.model.complete(token, *result, self.host.core.device_session()):
                self.check_session()
                return
        except PickerError as exc:
            self.failure(token, exc)
            # complete() can invalidate a failed listing itself.
            if self.model.loaded is None:
                self.status.set_text(str(exc))
            return
        self.clear()
        if self.model.parent() != token.path:
            self.add_row('..', True, parent=True)
        for entry in self.model.entries:
            self.add_row(entry.name, entry.kind == 'dir', entry.size)
        description = root_presentation(token.path)[2] if token.scope == 'c64u' else ''
        self.status.set_text(description or ('Choose an item.' if self.model.entries else 'This folder is empty.'))
        self.update_selection()

    def add_row(self, name, directory, size=None, parent=False):
        row = Gtk.ListBoxRow(selectable=not parent, activatable=True)
        row.item = (name, directory)
        row.parent_entry = parent
        content = Gtk.Box(spacing=8)
        icon = 'folder-symbolic' if directory else 'text-x-generic-symbolic'
        if self.scope == 'c64u' and self.model.loaded.path == '/' and not parent:
            icon = root_presentation('/' + name)[1]
        content.append(Gtk.Image.new_from_icon_name(icon))
        label = Gtk.Label(label=name, xalign=0, hexpand=True, width_chars=1,
                          max_width_chars=40, ellipsize=Pango.EllipsizeMode.END)
        label.set_tooltip_text(name)
        content.append(label)
        content.append(Gtk.Label(label='' if directory or size is None else str(size), xalign=1))
        row.update_property([Gtk.AccessibleProperty.LABEL], [name])
        row.set_child(content)
        self.listing.append(row)

    def names(self):
        return tuple(row.item[0] for row in self.listing.get_selected_rows() if not row.parent_entry)

    def update_selection(self):
        self.check_session()
        if self.model.loaded is None:
            self.select.set_sensitive(False)
            return
        try:
            self.model.choose(self.names(), self.host.core.device_session())
            valid = True
        except PickerError:
            valid = False
        self.select.set_sensitive(valid and not self.closed)

    def go_parent(self, *_):
        if self.model.loaded:
            self.navigate(self.scope, self.model.parent())

    def activate(self, row):
        self.check_session()
        if self.closed or row.get_parent() is not self.listing or not self.model.loaded:
            return
        if row.parent_entry:
            self.go_parent()
        elif row.item[1]:
            self.navigate(self.scope, self.model.child(row.item[0]))
        else:
            self.response(self.dialog, Gtk.ResponseType.ACCEPT)

    def response(self, _, response):
        if self.closed:
            return
        if response == Gtk.ResponseType.ACCEPT:
            self.check_session()
            try:
                result = self.model.choose(self.names(), self.host.core.device_session())
            except PickerError as exc:
                self.status.set_text(str(exc))
                self.check_session()
                return
        else:
            result = None
        self.closed = True
        self.model.invalidate()
        self.activation.cancel()
        self.policy.close()
        self.unsubscribe()
        self.dialog.destroy()
        self.callback(result)

    def close_requested(self, *_):
        self.response(self.dialog, Gtk.ResponseType.CANCEL)
        return True
