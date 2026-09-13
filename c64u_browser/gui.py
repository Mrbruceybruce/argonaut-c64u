# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""GTK4 presentation; all remote work runs on a single worker thread."""
from . import development
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import posixpath
import sys
import time
import uuid
from threading import Event
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk, Gio, Graphene
from .api import UltimateClient, BrowserError, ConnectionFailure
from .files import operate, child
from .navigation import History
from .storage import storage_root, discover, initial_directory
from .storage_ui import DriveButtons
from .deletion import prepare as prepare_deletion, delete_reviewed
from .folder_copy import build_plan, execute_plan
from .profiles import Preferences
from .credentials import Credentials
from .connection_dialog import ConnectionDialog
from .settings_tab import SettingsTab
from .drives_tab import DrivesTab
from .machine_tab import MachineTab
from .recovery import Recovery
from .media_tab import MediaTab
from .streams_tab import StreamsTab


class Browser(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.local.Argonaut.Development' if development.enabled() else 'org.local.Argonaut')
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.local = Path.cwd()
        self.remote = '/USB2'
        self.remote_root = '/USB2'
        self.local_root = Path.home()
        self.drive_bars = {}
        self.client = None
        self.busy = False
        self.copy_cancel = None
        self.drag_payload = None
        self.file_clipboard = None
        self.histories = {True: History(self.local), False: History(self.remote)}
        self.history_buttons = {}
        self.preferences = Preferences()
        self.preferences_error = None
        try: self.preferences.load()
        except (BrowserError, OSError) as exc: self.preferences_error = str(exc)
        remembered=self.preferences.app_options['local_folder']
        self.local=Path(remembered) if self.preferences.app_options['remember_folders'] and remembered and Path(remembered).is_dir() else Path.home()
        self.histories[True]=History(self.local)
        self.credentials = Credentials()
        self.session_passwords = {}
        self.active_profile = None
        self.device_info = None
        self.recovery=None
        self.offline_message=None

    def button(self, box, label, callback):
        button = Gtk.Button(label=label)
        button.connect('clicked', lambda _: callback())
        box.append(button)
        return button

    def icon_button(self, box, label, icon, callback):
        button = self.button(box, label, callback)
        button.set_icon_name(icon)
        button.set_tooltip_text(label)
        button.update_property([Gtk.AccessibleProperty.LABEL], [label])
        return button

    def do_startup(self):
        Gtk.Application.do_startup(self)
        # GTK's macOS/Quartz backend only enables the app-menu "Quit" item and
        # the Cmd+Q accelerator if an "app.quit" action actually exists; without
        # this, both stay permanently disabled on macOS (Linux/Windows menus are
        # unaffected, since this app doesn't build its own menubar there).
        quit_action = Gio.SimpleAction.new('quit', None)
        quit_action.connect('activate', self.request_quit)
        self.add_action(quit_action)
        accel = '<Meta>q' if sys.platform == 'darwin' else '<Primary>q'
        self.set_accels_for_action('app.quit', [accel])


    def request_quit(self,*_):
        window=getattr(self,'window',None)
        if window is not None:
            # Preserve close-request handlers: saved geometry and busy guard.
            window.close()
        else:
            self.pool.shutdown(wait=False)
            self.quit()

    def do_activate(self):
        # A second launcher activation must present the existing app, not create
        # another main window sharing the same worker and shutdown handler.
        if getattr(self, 'window', None) in self.get_windows():
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='Argonaut Development — C64 Ultimate Control & Management' if development.enabled() else 'Argonaut — C64 Ultimate Control & Management')
        from .version import ASSETS
        Gtk.IconTheme.get_for_display(self.window.get_display()).add_search_path(str(ASSETS))
        self.window.set_icon_name('argonaut')
        options=self.preferences.app_options
        self.window.set_default_size(options['width'] if options['remember_window'] else 1200, options['height'] if options['remember_window'] else 850)
        self.window.connect('close-request',self.remember_window)
        self.window.connect('close-request', self.close)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ('top', 'bottom', 'start', 'end'): getattr(outer, 'set_margin_' + side)(12)
        self.window.set_child(outer)
        self.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.append(self.controls)
        connection = Gtk.Box(spacing=8)
        self.controls.append(connection)
        self.connection_label = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        connection.append(self.connection_label)
        from .app_preferences import show_preferences
        self.button(connection, 'Preferences…', lambda: show_preferences(self))
        self.button(connection, 'Disconnect', self.disconnect_device)
        self.tabs = Gtk.Notebook(vexpand=True)
        self.controls.append(self.tabs)
        files = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.tabs.append_page(files, Gtk.Label(label='Files'))
        actions=Gtk.Box(spacing=8);files.append(actions)
        self.partial_upload=None
        self.partial_button=self.button(actions,'Delete partial upload…',self.delete_partial)
        self.partial_button.set_sensitive(False)
        panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        panes.set_position(490)
        panes.set_shrink_start_child(False)
        panes.set_shrink_end_child(False)
        panes.set_vexpand(True)
        files.append(panes)
        self.controls.set_vexpand(True)
        self.lpath, self.llist = self.pane(panes, True)
        self.rpath, self.rlist = self.pane(panes, False)
        self.settings_tab = SettingsTab(self)
        self.tabs.append_page(self.settings_tab.box, Gtk.Label(label='Settings'))
        self.drives_tab=DrivesTab(self)
        self.tabs.append_page(self.drives_tab.box,Gtk.Label(label='Drives'))
        self.machine_tab=MachineTab(self)
        self.tabs.append_page(self.machine_tab.box,Gtk.Label(label='Machine'))
        self.media_tab=MediaTab(self)
        self.tabs.append_page(self.media_tab.box,Gtk.Label(label='SID/Media'))
        self.streams_tab=StreamsTab(self)
        self.tabs.append_page(self.streams_tab.box,Gtk.Label(label='Streams'))
        self.tabs.connect('switch-page', lambda _, page, index: self.settings_tab.load_if_needed() if index == 1 else self.drives_tab.load_if_needed() if index == 2 else None)
        self.status = Gtk.Label(label='Open Preferences → Device details to select or discover a C64 Ultimate.', xalign=0, wrap=True, selectable=True)
        outer.append(self.status)
        self.cancel_button = self.button(actions, 'Cancel transfer', self.cancel_transfer)
        self.cancel_button.set_sensitive(False)
        self.cancel_button.set_halign(Gtk.Align.START)
        # Keep the Files action row reachable while a transfer is running.
        self.busy_controls = [connection, panes, self.partial_button,
            self.settings_tab.box, self.drives_tab.box, self.machine_tab.box,
            self.media_tab.box, self.streams_tab.box]
        self.refresh_local()
        self.window.present()
        self.update_connection_header()
        self.recovery=Recovery(self)
        if self.preferences_error: self.status.set_text(self.preferences_error)
        else: GLib.idle_add(self.auto_connect)

    def pane(self, panes, local):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        label = Gtk.Label(label='Local files' if local else 'C64 Ultimate files', xalign=0)
        box.append(label)
        toolbar = Gtk.Box(spacing=6)
        box.append(toolbar)
        self.icon_button(toolbar, 'Home', 'go-home-symbolic', lambda: self.go_home(local))
        back = self.icon_button(toolbar, 'Back', 'go-previous-symbolic', lambda: self.history_move(local, -1))
        forward = self.icon_button(toolbar, 'Forward', 'go-next-symbolic', lambda: self.history_move(local, 1))
        self.history_buttons[local] = (back, forward)
        self.icon_button(toolbar, 'Refresh', 'view-refresh-symbolic', self.refresh_local if local else self.refresh_remote)
        self.icon_button(toolbar, 'Copy', 'edit-copy-symbolic', lambda: self.copy_selection(local))
        self.icon_button(toolbar, 'Paste', 'edit-paste-symbolic', lambda: self.paste_files(local))
        self.icon_button(toolbar, 'New folder…', 'folder-new-symbolic', lambda: self.new_folder(local))
        drives=DriveButtons(self,local);self.drive_bars[local]=drives
        box.append(drives.box)
        path = Gtk.Entry()
        path.connect('activate', lambda entry: self.navigate(local, entry.get_text()))
        box.append(path)
        self.update_history_buttons()
        mouse = Gtk.GestureClick(button=0)
        mouse.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        def side_button(gesture, count, x, y):
            button = gesture.get_current_button()
            if button in (8, 9):
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                self.history_move(local, -1 if button == 8 else 1)
        mouse.connect('pressed', side_button)
        box.add_controller(mouse)
        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE)
        listing.set_activate_on_single_click(False)
        listing.connect('row-activated', lambda _, row: self.activate_row(local, row))
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        listing.set_vexpand(True)
        click = Gtk.GestureClick(button=3)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect('pressed', lambda gesture, count, x, y: self.clicked(listing, local, gesture, count, x, y))
        listing.add_controller(click)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', lambda _, key, code, state: self.file_key(local, key, state))
        listing.add_controller(keys)
        source = Gtk.DragSource(actions=Gdk.DragAction.COPY)
        source.connect('prepare', lambda _, x, y: self.drag_prepare(listing, local, x, y))
        source.connect('drag-end', lambda *_: setattr(self, 'drag_payload', None))
        listing.add_controller(source)
        target = Gtk.DropTarget.new(str, Gdk.DragAction.COPY)
        target.connect('drop', lambda _, value, x, y: self.dropped(listing, local, value, x, y))
        listing.add_controller(target)
        scroll.set_child(listing)
        box.append(scroll)
        (panes.set_start_child if local else panes.set_end_child)(box)
        return path, listing

    def populate(self, listing, entries):
        while listing.get_first_child(): listing.remove(listing.get_first_child())
        for name, directory, size in [('..', True, 0)] + entries:
            row = Gtk.ListBoxRow()
            row.item = (name, directory)
            label = Gtk.Label(label=f'{"📁" if directory else "  "}  {name}    {"" if directory else str(size) + " bytes"}', xalign=0)
            label.set_margin_top(7)
            label.set_margin_bottom(7)
            row.set_child(label)
            listing.append(row)

    def refresh_local(self):
        try:
            entries = [(p.name, p.is_dir(), p.stat().st_size) for p in self.local.iterdir()]
            self.populate(self.llist, sorted(entries, key=lambda e: (not e[1], e[0].casefold())))
            self.lpath.set_text(str(self.local))
            self.drive_bars[True].refresh()
            return True
        except OSError as exc: self.status.set_text(str(exc))

    def run(self, task, done):
        if self.busy: return
        self.busy = True
        sensitivity = [(widget, widget.get_sensitive()) for widget in self.busy_controls]
        for widget, _ in sensitivity: widget.set_sensitive(False)
        self.status.set_text('Working…')
        try:
            future = self.pool.submit(task)
        except Exception as exc:
            self.busy = False
            for widget, sensitive in sensitivity: widget.set_sensitive(sensitive)
            error = BrowserError('Could not start the operation. Close and reopen Argonaut. '+str(exc))
            try: done(error)
            except Exception: pass
            self.status.set_text(str(error))
            return
        def finish():
            self.busy = False
            for widget, sensitive in sensitivity: widget.set_sensitive(sensitive)
            try: done(future.result())
            except Exception as exc:
                self.end_copy_cancel()
                if isinstance(exc, ConnectionFailure) and exc.kind in ('host', 'network', 'authentication') and self.recovery:
                    self.recovery.lost(str(exc))
                    if exc.kind=='authentication':self.recovery.paused=True
                self.status.set_text(str(exc))
            return False
        future.add_done_callback(lambda _: GLib.idle_add(finish))

    def open_connections(self):
        if self.busy: return
        if self.preferences_error:
            self.status.set_text(self.preferences_error); return
        from .app_preferences import show_preferences
        show_preferences(self,page=1)

    def update_connection_header(self):
        selected = self.preferences.selected()
        if self.active_profile:
            info = self.device_info['info']
            text = f"Connected · {self.active_profile.name} · {self.active_profile.host}:{self.active_profile.http_port} · Firmware {info['firmware_version']} · API {self.device_info['version']['version']}"
            if self.offline_message:text=f'Offline · {self.active_profile.name} · {self.offline_message}'
            if selected and selected.id != self.active_profile.id: text += f' · Selected for next connection: {selected.name}'
        else:
            text = 'Disconnected' + (f' · Selected: {selected.name}' if selected else ' · No device selected')
        self.connection_label.set_text(text)

    def activate_connection(self, profile, client, info, listing):
        self.offline_message=None
        self.client, self.active_profile, self.device_info = client, profile, info
        self.drag_payload = None
        self.file_clipboard = None
        self.histories[False] = History(listing[0])
        self.show_remote(listing)
        self.settings_tab.bind(client)
        self.settings_tab.box.set_sensitive(True)
        self.drives_tab.bind(client)
        self.machine_tab.bind(client)
        self.media_tab.bind(client)
        self.streams_tab.bind(client)
        if self.recovery:self.recovery.watch(profile,client,info)
        if self.tabs.get_current_page() == 1: self.settings_tab.load_if_needed()
        if self.tabs.get_current_page() == 2: self.drives_tab.load_if_needed()
        self.update_connection_header()

    def disconnect_device(self):
        if self.busy: return
        if self.recovery:self.recovery.cancel()
        self.offline_message=None
        self.client = self.active_profile = self.device_info = None
        self.drive_bars[False].refresh()
        self.drag_payload = None
        while self.rlist.get_first_child(): self.rlist.remove(self.rlist.get_first_child())
        self.rpath.set_text('')
        self.update_history_buttons()
        self.settings_tab.bind(None)
        self.settings_tab.box.set_sensitive(True)
        self.drives_tab.bind(None)
        self.machine_tab.bind(None)
        self.media_tab.bind(None)
        self.streams_tab.bind(None)
        self.update_connection_header()
        self.status.set_text('Disconnected.')

    def connection_lost(self, message):
        if not self.active_profile:return
        self.offline_message=message;self.client=None;self.drag_payload=None
        while self.rlist.get_first_child():self.rlist.remove(self.rlist.get_first_child())
        self.rpath.set_text('')
        self.update_history_buttons()
        # Retain local drafts, but block sending their old snapshot after reconnect.
        self.settings_tab.client=None;self.settings_tab.requires_refresh=True
        self.settings_tab.rows.set_sensitive(False)
        self.settings_tab.box.set_sensitive(False)
        self.drives_tab.bind(None);self.machine_tab.bind(None)
        self.media_tab.bind(None)
        self.streams_tab.bind(None)
        self.drive_bars[False].refresh()
        self.update_connection_header()

    def connection_restored(self, client, info, listing):
        self.client=client;self.device_info=info;self.offline_message=None
        self.file_clipboard = None
        self.histories[False] = History(listing[0])
        self.show_remote(listing)
        self.settings_tab.client=client;self.settings_tab.loaded=False
        self.settings_tab.box.set_sensitive(True);self.settings_tab.update_edit_buttons()
        self.settings_tab.heading.set_text('Reconnected. '+('Discard retained edits, then reload settings.' if self.settings_tab.pending or self.settings_tab.drafts else 'Reload settings before editing or saving.'))
        self.drives_tab.bind(client);self.machine_tab.bind(client)
        self.media_tab.bind(client)
        self.streams_tab.bind(client)
        self.update_connection_header()
        self.status.set_text('Reconnected to the same C64U. Choose Reload from C64U in Settings to read its current values; retained edits were not sent.')

    def auto_connect(self):
        profile = self.preferences.selected()
        if not profile or not profile.auto_connect: return False
        def task():
            client = profile.client(self.credentials.get(profile.id))
            info=client.test_connection()
            profile.verify_identity(info,require_bound=True)
            return profile, client, info, initial_directory(client,self.preferences.app_options['remote_folders'].get(profile.id,'/USB2') if self.preferences.app_options['remember_folders'] else '/USB2')
        self.run(task, lambda result: self.activate_connection(*result))
        return False

    def show_remote(self, result):
        self.remote, entries = result
        if self.active_profile and self.preferences.app_options['remember_folders']:
            self.preferences.app_options['remote_folders'][self.active_profile.id]=self.remote;self.save_app_preferences()
        self.remote_root=storage_root(self.remote) or '/'
        self.drive_bars[False].refresh()
        self.rpath.set_text(self.remote)
        self.populate(self.rlist, [(e.name, e.kind == 'dir', e.size or 0) for e in entries])
        self.status.set_text('Connected · ' + self.remote)
        self.update_history_buttons()

    def refresh_remote(self):
        if not self.client:self.status.set_text('Connect first.');return
        client=self.client;path=self.remote
        def task():
            roots=discover(client)
            if storage_root(path) not in roots:return ('/',[])
            return client.list_directory(path)
        def done(result):
            if self.client is client:
                self.show_remote(result)
                if result[0]=='/':self.status.set_text('Select an available drive above the path.')
        self.run(task,done)

    def update_history_buttons(self):
        for local, buttons in self.history_buttons.items():
            for offset, button in zip((-1, 1), buttons):
                button.set_sensitive((local or self.client is not None) and self.histories[local].target(offset) is not None)

    def go_home(self, local):
        if self.busy: return
        if not local and not self.client:
            self.status.set_text('Connect first.'); return
        self.navigate(local, str(self.local_root) if local else self.remote_root)

    def history_move(self, local, offset):
        if self.busy: return
        target = self.histories[local].target(offset)
        if target is not None: self.navigate(local, target, offset)

    def navigate(self, local, target, offset=None):
        if self.busy: return
        history = self.histories[local]
        if local:
            old = self.local
            candidate = Path(target).expanduser().absolute()
            if not candidate.is_dir():
                self.lpath.set_text(str(old))
                self.status.set_text('Choose an existing local folder.'); return
            self.local = candidate
            if self.refresh_local():
                if self.preferences.app_options['remember_folders']:
                    self.preferences.app_options['local_folder']=str(candidate);self.save_app_preferences()
                history.visit(candidate, offset)
                self.update_history_buttons()
            else:
                self.local = old
                self.lpath.set_text(str(old))
        elif self.client:
            if not storage_root(target):
                self.status.set_text('Choose a USB or SD drive above the path.'); return
            if '..' in target.split('/'):
                self.status.set_text('Use the parent folder row to navigate.'); return
            client = self.client
            def loaded(result):
                if self.client is not client: return
                history.visit(result[0], offset)
                self.show_remote(result)
            self.run(lambda: client.list_directory(target), loaded)

    def activate_row(self, local, row):
        self.menu_token = None
        name, directory = row.item
        if name == '..':
            self.navigate(local, str(self.local.parent) if local else (posixpath.dirname(self.remote) if self.remote != self.remote_root else self.remote_root))
        elif directory: self.navigate(local, str(self.local / name) if local else posixpath.join(self.remote, name))

    def selected(self, local):
        rows = (self.llist if local else self.rlist).get_selected_rows()
        if len(rows) != 1 or rows[0].item[0] == '..': raise BrowserError('Select exactly one item first.')
        return rows[0].item

    def guarded(self, action):
        try:
            action()
        except (BrowserError, OSError) as exc: self.status.set_text(str(exc))

    def completed(self, result):
        self.refresh_local()
        if not self.client:
            self.status.set_text('Completed: ' + str(result))
            return
        def refreshed(listing):
            self.show_remote(listing)
            self.status.set_text('Completed: ' + str(result))
        self.run(lambda: self.client.list_directory(self.remote), refreshed)

    def cancel_transfer(self):
        if self.copy_cancel:
            self.copy_cancel.set()
            self.cancel_button.set_sensitive(False)
            self.status.set_text('Cancelling transfer… waiting for the current network operation to return.')

    def begin_copy_cancel(self):
        event = Event()
        self.copy_cancel = event
        self.cancel_button.set_sensitive(True)
        def check():
            if event.is_set(): raise BrowserError('Transfer cancelled by user.')
        return check

    def end_copy_cancel(self):
        self.copy_cancel = None
        self.cancel_button.set_sensitive(False)

    def progress_callback(self):
        event = self.copy_cancel
        def check():
            if event is not None and event.is_set(): raise BrowserError('Transfer cancelled by user.')
        last = [0.0]
        def progress(count):
            check()
            now = time.monotonic()
            if now - last[0] >= 0.15:
                last[0] = now
                def update():
                    self.status.set_text(f'Transferred {count:,} bytes…')
                    return False
                GLib.idle_add(update)
        progress.check = check
        return progress

    def clicked(self, listing, local, gesture, count, x, y):
        if self.busy or count != 1: return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        row = listing.get_row_at_y(int(y))
        if row and row.item[0] == '..': return
        # Preserve a selection when opening its context menu.
        if row not in listing.get_selected_rows():
            listing.unselect_all()
            if row: listing.select_row(row)
        self.menu(listing, local, row, x, y)

    def menu(self, listing, local, row, x, y):
        if getattr(self, 'popover', None): self.popover.popdown()
        popover = Gtk.Popover()
        self.popover = popover
        # Anchor outside the scrolling list: focusing the menu must not scroll it.
        anchor = listing.get_ancestor(Gtk.ScrolledWindow)
        point = Graphene.Point(); point.init(x, y)
        valid, point = listing.compute_point(anchor, point)
        if not valid:return
        popover.set_parent(anchor)
        rect = Gdk.Rectangle(); rect.x = int(point.x); rect.y = int(point.y); rect.width = rect.height = 1
        popover.set_pointing_to(rect)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        popover.set_child(box)
        def action(fn):
            popover.popdown()
            self.guarded(fn)
        if row:
            name, directory = row.item
            multiple = len(listing.get_selected_rows()) > 1
            if not multiple and not local and not directory and name.lower().endswith('.sid'):
                client=self.client;path=posixpath.join(self.remote,name)
                def open_sid():
                    if self.client is client and self.media_tab.select_file(path):
                        self.tabs.set_current_page(self.tabs.page_num(self.media_tab.box))
                self.button(box,'Open in SID/Media',lambda:action(open_sid))
            self.button(box, 'Copy', lambda: action(lambda: self.copy_selection(local)))
            if not multiple:
                self.button(box, 'Rename…', lambda: action(lambda: self.rename_item(local, name)))
            self.button(box, 'Delete selected…' if multiple else 'Delete…', lambda: action(lambda: self.delete_selected(local)))
        else:
            self.button(box, 'New folder…', lambda: action(lambda: self.new_folder(local)))
        self.button(box, 'Paste', lambda: action(lambda: self.paste_files(local)))
        popover.connect('closed', lambda widget: widget.unparent())
        popover.popup()

    def drag_prepare(self, listing, local, x, y):
        self.menu_token = None
        if self.busy: return None
        row = listing.get_row_at_y(int(y))
        if row is None or row.item[0] == '..': return None
        rows = listing.get_selected_rows()
        if row not in rows:
            listing.unselect_all(); listing.select_row(row); rows = [row]
        token = uuid.uuid4().hex
        self.drag_payload = (token, local, self.local if local else self.remote, [r.item[0] for r in rows])
        return Gdk.ContentProvider.new_for_value(token)

    def dropped(self, listing, local, value, x, y):
        payload = self.drag_payload
        if self.busy or not payload or value != payload[0] or local == payload[1]: return False
        if not self.client:
            self.status.set_text('Open Preferences → Device details and connect to a C64U first.'); return False
        row = listing.get_row_at_y(int(y))
        destination = self.local if local else self.remote
        if row and row.item[1]:
            name = row.item[0]
            if name == '..':
                destination = self.local.parent if local else (posixpath.dirname(self.remote) if self.remote != self.remote_root else self.remote_root)
            else: destination = self.local / name if local else child(self.remote, name)
        _, source_local, parent, names = payload
        self.drag_payload = None
        self.start_copy(source_local, parent, names, local, destination, self.client)
        return True

    def file_key(self, local, key, state):
        if key == Gdk.KEY_Delete and not state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            self.delete_selected(local); return True
        if state & Gdk.ModifierType.CONTROL_MASK:
            if key in (Gdk.KEY_c, Gdk.KEY_C): self.copy_selection(local); return True
            if key in (Gdk.KEY_v, Gdk.KEY_V): self.paste_files(local); return True
        if state & Gdk.ModifierType.ALT_MASK:
            if key == Gdk.KEY_Left: self.history_move(local, -1); return True
            if key == Gdk.KEY_Right: self.history_move(local, 1); return True
        return False

    def copy_selection(self, local):
        if self.busy: return
        rows = (self.llist if local else self.rlist).get_selected_rows()
        if not rows or any(r.item[0] == '..' for r in rows):
            self.status.set_text('Select files or folders to copy.'); return
        if not local and not self.client:
            self.status.set_text('Connect first.'); return
        self.file_clipboard = (local, self.local if local else self.remote,
                               tuple(r.item[0] for r in rows), None if local else self.client)
        self.status.set_text(f'{len(rows)} item(s) ready to copy. Open a destination folder and choose Paste.')

    def paste_files(self, local):
        if self.busy: return
        if not self.file_clipboard:
            self.status.set_text('Copy files or folders in Argonaut first.'); return
        source_local, parent, names, source_client = self.file_clipboard
        if not source_local and source_client is not self.client:
            self.status.set_text('The source connection changed. Select and copy the files again.'); return
        if not local and not self.client:
            self.status.set_text('Connect first.'); return
        self.start_copy(source_local, parent, names, local,
                        self.local if local else self.remote, self.client)

    def start_copy(self, source_local, parent, names, local, destination, client):
        names = tuple(names)
        def transfer(plan):
            if self.busy or (not (local and source_local) and self.client is not client): return
            self.begin_copy_cancel()
            progress = self.progress_callback()
            def finished(result):
                self.end_copy_cancel()
                message, partial = result.message, result.partial
                if result.error: self.copy_report(result)
                if partial:
                    self.partial_upload = (client, partial)
                    self.partial_button.set_sensitive(True)
                self.refresh_local()
                if not self.client:
                    self.status.set_text(message); return
                current = self.client
                folder = self.remote
                def refresh():
                    try: return current.list_directory(folder), None
                    except Exception as exc: return None, str(exc)
                def refreshed(result):
                    listing, error = result
                    if listing is not None and self.client is current: self.show_remote(listing)
                    self.status.set_text(message + (' · Could not refresh C64U: ' + error if error else ''))
                self.run(refresh, refreshed)
            self.run(lambda: execute_plan(client, plan, source_local, local, progress), finished)
        def checked(plan):
            if self.copy_cancel is not None and self.copy_cancel.is_set():
                self.end_copy_cancel()
                self.status.set_text('Transfer cancelled; nothing copied.'); return
            self.end_copy_cancel()
            existing = plan.conflicts
            if not existing: transfer(plan); return
            dialog = Gtk.Dialog(title='Files already exist', transient_for=self.window, modal=True)
            dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
            dialog.add_button('Skip existing', Gtk.ResponseType.OK)
            replace_button=dialog.add_button('Replace', Gtk.ResponseType.APPLY)
            replace_button.set_sensitive(bool(plan.replacements))
            dialog.set_default_response(Gtk.ResponseType.CANCEL)
            label = Gtk.Label(label='These names already exist in the destination:\n\n' + '\n'.join(existing) + '\n\nReplace overwrites matching regular files. Existing folders merge; folder/file conflicts and copies onto themselves are skipped.\nDestination: '+str(destination), wrap=True, selectable=True)
            label.set_margin_top(16); label.set_margin_bottom(16)
            label.set_margin_start(16); label.set_margin_end(16)
            scroll = Gtk.ScrolledWindow(min_content_width=440, min_content_height=180, max_content_height=400)
            scroll.set_child(label); dialog.get_content_area().append(scroll)
            def response(widget, answer):
                widget.destroy()
                if answer == Gtk.ResponseType.APPLY:
                    replaced={step.relative for step in plan.replacements}
                    plan.conflicts=[name for name in plan.conflicts if name not in replaced]
                    plan.steps.extend(plan.replacements)
                    transfer(plan)
                elif answer == Gtk.ResponseType.OK:
                    if plan.steps: transfer(plan)
                    else: self.status.set_text('All files skipped; nothing copied.')
                else: self.status.set_text('Copy cancelled; nothing copied.')
            dialog.connect('response', response); dialog.present()
        check = self.begin_copy_cancel()
        self.run(lambda: build_plan(client, source_local, parent, names, local, destination, check), checked)

    def copy_report(self, report):
        dialog = Gtk.Dialog(title='Copy stopped', transient_for=self.window, modal=True)
        dialog.set_default_size(650, 420)
        dialog.add_button('Close', Gtk.ResponseType.CLOSE)
        text = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        text.get_buffer().set_text(report.details())
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(text); dialog.get_content_area().append(scroll)
        dialog.connect('response', lambda widget, _: widget.destroy())
        dialog.present()

    def new_folder(self, local):
        parent = self.local if local else self.remote
        if not local and not self.client: raise BrowserError('Connect first.')
        def submit(name):
            child('/USB2', name)  # Validate one filename on either side.
            target = parent / name if local else child(parent, name)
            def task():
                if local: target.mkdir()
                else: operate(self.client, 'mkdir', target)
                return str(target)
            self.run(task, self.completed)
        self.prompt('New folder', 'Folder name:', submit, action_label='Create folder')

    def rename_item(self, local, name):
        parent = self.local if local else self.remote
        target = parent / name if local else child(parent, name)
        def submit(new):
            child('/USB2', new)
            def task():
                if local:
                    # GIO refuses replacement unless OVERWRITE is explicitly requested.
                    Gio.File.new_for_path(str(target)).move(Gio.File.new_for_path(str(parent / new)), Gio.FileCopyFlags.NONE, None, None, None)
                    return str(parent / new)
                return operate(self.client, 'rename', target, new_name=new)
            self.run(task, self.completed)
        self.prompt('Rename', 'New name:', submit, name, action_label='Rename')

    def delete_item(self, local, name):
        target=self.local/name if local else child(self.remote,name)
        return self.delete_dialog(local,[target],self.client)

    def delete_selected(self,local):
        if self.busy:return
        listing=self.llist if local else self.rlist
        names=[r.item[0] for r in listing.get_selected_rows() if r.item[0]!='..']
        if not names:self.status.set_text('Select files or folders to delete.');return
        targets=[self.local/name if local else child(self.remote,name) for name in names]
        return self.delete_dialog(local,targets,self.client)

    def delete_partial(self):
        if self.busy or not self.partial_upload:return
        original,path=self.partial_upload
        if not self.client or (self.client.host,self.client.http_port,self.client.port)!=(original.host,original.http_port,original.port):
            self.status.set_text('Connect to '+original.host+' before deleting this partial upload.');return
        return self.delete_dialog(False,[path],self.client,partial=True)

    def delete_dialog(self,local,targets,client,partial=False):
        if self.busy or (not local and not client):return
        targets=tuple(targets)
        dialog=Gtk.Dialog(title='Delete partial upload' if partial else 'Delete selected items',transient_for=self.window,modal=True)
        dialog.set_default_size(650,350)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
        button=dialog.add_button('Delete',Gtk.ResponseType.OK);button.add_css_class('destructive-action')
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        device='This computer' if local else 'C64U '+client.host
        label=Gtk.Label(label='Preparing the deletion list…',xalign=0,yalign=0,wrap=True,selectable=True)
        button.set_sensitive(False)
        reviewed = []
        closed = [False]
        scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True);scroll.set_child(label);dialog.get_content_area().append(scroll)
        def response(_,code):
            closed[0] = True
            dialog.destroy()
            if code!=Gtk.ResponseType.OK or self.busy or not reviewed:return
            if not local and self.client is not client:
                self.status.set_text('Connection changed. Review the deletion again.');return
            items = reviewed[0]
            def task():
                return delete_reviewed(client,local,targets,items)
            def done(result):
                removed,error=result
                if partial and not error:
                    self.partial_upload=None;self.partial_button.set_sensitive(False)
                message=f'Deleted {len(removed)} of {len(items)} item(s).'+(' Stopped: '+error if error else '')
                self.refresh_local();self.status.set_text(message)
                if not local and self.client is client:
                    parent=self.remote
                    def refresh():
                        try:return client.list_directory(parent)
                        except Exception as exc:return exc
                    def refreshed(result):
                        if self.client is client and self.remote==parent and not isinstance(result,Exception):self.show_remote(result)
                        self.status.set_text(message+(' Refresh failed: '+str(result) if isinstance(result,Exception) else ''))
                    self.run(refresh,refreshed)
            self.run(task,done)
        dialog.connect('response',response);dialog.present()
        def prepared(result):
            if closed[0]: return
            items, error = result
            if error:
                label.set_text('Could not prepare deletion: '+error+'\n\nNothing was deleted. Close this dialog and try again.'); return
            reviewed.append(items)
            label.set_text(device+'\n\nDelete permanently: '+str(len(items))+' items, including folder contents?\n\n'+'\n'.join(i.path+('/' if i.kind=='dir' else '') for i in items))
            button.set_sensitive(bool(items))
        def scan():
            try: return prepare_deletion(client,local,targets), None
            except Exception as exc: return (), str(exc)
        self.run(scan,prepared)
        return dialog

    def prompt(self, title, text, callback, initial='', exact_confirmation=None, action_label='OK'):
        dialog = Gtk.Dialog(title=title, transient_for=self.window, modal=True)
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        confirm = dialog.add_button(action_label, Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.append(Gtk.Label(label=text, wrap=True))
        entry = Gtk.Entry(text=initial, hexpand=True)
        box.append(entry)
        feedback = Gtk.Label(label='', wrap=True)
        box.append(feedback)
        def validate(*_):
            matches = exact_confirmation is None or entry.get_text() == exact_confirmation
            confirm.set_sensitive(matches)
            feedback.set_text('' if matches else 'Type the full path exactly, including uppercase and lowercase letters.')
            return matches
        entry.connect('changed', validate)
        validate()
        def response(_, code):
            value = entry.get_text()
            if code == Gtk.ResponseType.OK and not validate():
                return
            dialog.destroy()
            if code == Gtk.ResponseType.OK: self.guarded(lambda: callback(value))
        dialog.connect('response', response)
        dialog.set_default_response(Gtk.ResponseType.OK)
        entry.connect('activate', lambda _: dialog.response(Gtk.ResponseType.OK) if validate() else None)
        dialog.present()
        entry.grab_focus()
        return dialog, entry, confirm

    def save_app_preferences(self):
        if self.preferences_error:return
        try:self.preferences.save()
        except OSError as exc:self.status.set_text('Could not save Argonaut preferences: '+str(exc))

    def remember_window(self,*_):
        if not self.busy and self.preferences.app_options['remember_window'] and not self.window.is_maximized():
            self.preferences.app_options.update(width=max(600,self.window.get_width()),height=max(400,self.window.get_height()))
            self.save_app_preferences()
        return False

    def close(self, *_):
        if self.busy:
            self.status.set_text('Wait for the current operation to finish before closing.')
            return True
        if self.recovery:self.recovery.close()
        if self.streams_tab.close() is True:
            self.status.set_text('Finishing recording and stopping streams…')
            if not getattr(self,'closing_media',False):
                self.closing_media=True
                def finish_close():
                    if self.streams_tab.close() is True:return True
                    self.pool.shutdown(wait=False);self.quit();return False
                GLib.timeout_add(100,finish_close)
            return True
        self.pool.shutdown(wait=False)
        # Child windows must not keep an application with a stopped worker alive.
        self.quit()
        return False


def main():
    if not Gtk.init_check():
        raise SystemExit('No desktop display available. Launch this from a GNOME terminal.')
    app = Browser()
    return Gtk.Application.run(app, None)

if __name__ == '__main__':
    main()
