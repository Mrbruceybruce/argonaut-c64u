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
from .folder_copy import build_plan, execute_plan, completed_roots
from .profiles import Preferences
from .credentials import Credentials
from .connection_dialog import ConnectionDialog
from .settings_tab import SettingsTab
from .drives_tab import DrivesTab
from .machine_tab import MachineTab
from .recovery import Recovery
from .media_tab import MediaTab
from .streams_tab import StreamsTab
from .diagnostics import enable_private_log, disable_private_log
from .test_lab_access import enabled as test_lab_enabled
from .platform_support import local_hidden


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
        self.file_pane_boxes = {}
        self.file_pane_labels = {}
        self.active_file_pane = True
        self.preferences = Preferences()
        self.preferences_error = None
        try: self.preferences.load()
        except (BrowserError, OSError) as exc: self.preferences_error = str(exc)
        self.operation_log = None
        self.operation_log_error = None
        if test_lab_enabled(self.preferences):
            try:
                self.operation_log = enable_private_log(self.preferences.path)
            except OSError:
                self.operation_log_error = 'Private activity log is unavailable.'
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
        self.quick_connect_button = self.button(
            connection, 'Quick Connect', self.quick_connect)
        self.quick_connect_button.set_tooltip_text(
            'Connect to the last-used device profile')
        self.button(connection, 'Preferences…', lambda: show_preferences(self))
        self.disconnect_button = self.button(
            connection, 'Disconnect', self.disconnect_device)
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
        css = Gtk.CssProvider()
        css.load_from_data(
            b'.argonaut-file-pane { border: 2px solid transparent; border-radius: 6px; padding: 4px; }\n'
            b'.argonaut-file-pane-active { border-color: #3584e4; }\n'
            b'.argonaut-file-pane-inactive button { opacity: 0.78; }\n'
            b'.argonaut-file-pane-inactive button:disabled { opacity: 0.45; }\n'
            b'.argonaut-file-pane-inactive button.suggested-action { background-image: none; background-color: #77767b; color: #ffffff; }\n'
            b'.argonaut-file-pane-inactive entry { background-color: alpha(@window_fg_color, 0.06); }\n'
            b'.argonaut-file-pane-inactive row:selected { background-color: #5e5c64; color: #ffffff; }\n'
            b'.argonaut-file-pane-inactive row:selected label { color: #ffffff; }\n'
            b'.argonaut-error-message { color: #c01c28; font-size: 1.083333em; }')
        Gtk.StyleContext.add_provider_for_display(
            self.window.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.file_pane_css = css
        self.set_active_file_pane(True)
        self.settings_tab = SettingsTab(self)
        self.tabs.append_page(self.settings_tab.box, Gtk.Label(label='Ultimate Menu'))
        self.drives_tab=DrivesTab(self)
        self.tabs.append_page(self.drives_tab.box,Gtk.Label(label='Drives'))
        self.machine_tab=MachineTab(self)
        self.tabs.append_page(self.machine_tab.box,Gtk.Label(label='Machine'))
        self.media_tab=MediaTab(self)
        self.tabs.append_page(self.media_tab.box,Gtk.Label(label='SID/Media'))
        self.streams_tab=StreamsTab(self)
        self.tabs.append_page(self.streams_tab.box,Gtk.Label(label='Streams'))
        if test_lab_enabled(self.preferences):
            from .test_lab_tab import TestLabTab
            self.test_lab_tab = TestLabTab(self)
            self.tabs.append_page(self.test_lab_tab.box, Gtk.Label(label='Test Lab'))
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
        if hasattr(self, 'test_lab_tab'):
            self.busy_controls.append(self.test_lab_tab.box)
        self.refresh_local()
        self.window.present()
        self.update_connection_header()
        self.recovery=Recovery(self)
        if self.preferences_error: self.status.set_text(self.preferences_error)
        else: GLib.idle_add(self.auto_connect)

    def pane(self, panes, local):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        pane_click = Gtk.GestureClick(button=1)
        pane_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        pane_click.connect(
            'pressed', lambda *_: self.set_active_file_pane(local))
        box.add_controller(pane_click)
        label = Gtk.Label(label='Local files' if local else 'C64 Ultimate files', xalign=0)
        box.add_css_class('argonaut-file-pane')
        self.file_pane_boxes[local] = box
        self.file_pane_labels[local] = label
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
        if local:
            self.new_d64_button = self.icon_button(
                toolbar, 'New D64 disk…', 'document-new-symbolic', self.new_d64)
        else:
            self.remote_new_d64_button = self.icon_button(
                toolbar, 'New D64 disk on C64U…', 'document-new-symbolic',
                self.new_remote_d64)
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
        activate_pane = Gtk.GestureClick(button=1)
        activate_pane.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        activate_pane.connect(
            'pressed', lambda *_: self.activate_file_pane_pointer(local))
        scroll.add_controller(activate_pane)
        listing.set_vexpand(True)
        click = Gtk.GestureClick(button=3)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect('pressed', lambda gesture, count, x, y: self.clicked(listing, local, gesture, count, x, y))
        listing.add_controller(click)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', lambda _, key, code, state: self.file_key(local, key, state))
        listing.add_controller(keys)
        focus = Gtk.EventControllerFocus()
        focus.connect('enter', lambda *_: self.set_active_file_pane(local))
        listing.add_controller(focus)
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

    def set_active_file_pane(self, local):
        self.active_file_pane = local
        for pane_local, box in self.file_pane_boxes.items():
            active = pane_local == local
            box.remove_css_class(
                'argonaut-file-pane-inactive' if active else 'argonaut-file-pane-active')
            box.add_css_class(
                'argonaut-file-pane-active' if active else 'argonaut-file-pane-inactive')
            base = 'Local files' if pane_local else 'C64 Ultimate files'
            self.file_pane_labels[pane_local].set_text(
                base + (' · Active' if active else ''))

    def activate_file_pane_pointer(self, local):
        """Activate a pane without focusing a list row and moving its viewport."""
        self.set_active_file_pane(local)

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

    def select_names(self, listing, names):
        wanted = set(names)
        listing.unselect_all()
        if not wanted:
            return
        row = listing.get_first_child()
        while row is not None:
            if row.item[0] in wanted:
                listing.select_row(row)
            row = row.get_next_sibling()

    def refresh_local(self, select=()):
        try:
            entries = []
            show_hidden = bool(self.preferences.app_options.get(
                'show_hidden_local', False))
            for p in self.local.iterdir():
                if not show_hidden and local_hidden(p):
                    continue
                # Some files never resolve via stat(), most notably dangling
                # symlinks such as Emacs' ".#name" lock files, which point at
                # a "user@host.pid:boot-time" string that was never a real
                # path. One such entry shouldn't take down the whole listing;
                # show it with a placeholder size instead of aborting.
                try:
                    entries.append((p.name, p.is_dir(), p.stat().st_size))
                except OSError:
                    entries.append((p.name, False, 0))
            self.populate(self.llist, sorted(entries, key=lambda e: (not e[1], e[0].casefold())))
            Browser.select_names(self, self.llist, select)
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
        self.quick_connect_button.set_sensitive(self.active_profile is None)
        self.disconnect_button.set_sensitive(self.active_profile is not None)
        if hasattr(self, 'remote_new_d64_button'):
            self.remote_new_d64_button.set_sensitive(self.client is not None)
        if hasattr(self, 'test_lab_tab'):
            self.test_lab_tab.connection_changed()

    def quick_connect(self):
        """Connect to the selected (last-used) profile without opening Preferences."""
        if self.busy or self.active_profile:
            return
        if self.preferences_error:
            self.status.set_text(self.preferences_error)
            return
        profile = self.preferences.selected()
        if not profile:
            self.status.set_text(
                'Choose or create a device profile before using Quick Connect.')
            self.open_connections()
            return
        password = (self.session_passwords.get(profile.id) or
                    self.credentials.get(profile.id))
        def task():
            client = profile.client(password)
            info = client.test_connection()
            profile.verify_identity(info, require_bound=True)
            folder = (self.preferences.app_options['remote_folders'].get(
                profile.id, '/USB2')
                if self.preferences.app_options['remember_folders'] else '/USB2')
            return profile, client, info, initial_directory(client, folder)
        self.run(task, lambda result: self.activate_connection(*result))

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
        self.status.set_text('Reconnected to the same C64U. Choose Reload from C64U in Ultimate Menu to read its current values; retained edits were not sent.')

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

    def show_remote(self, result, select=()):
        self.remote, entries = result
        if self.active_profile and self.preferences.app_options['remember_folders']:
            self.preferences.app_options['remote_folders'][self.active_profile.id]=self.remote;self.save_app_preferences()
        self.remote_root=storage_root(self.remote) or '/'
        self.drive_bars[False].refresh()
        self.rpath.set_text(self.remote)
        self.populate(self.rlist, [(e.name, e.kind == 'dir', e.size or 0) for e in entries])
        Browser.select_names(self, self.rlist, select)
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
        elif name.casefold().endswith(('.d64', '.d71', '.d81')): self.open_disk_image(local, name)

    def open_disk_image(self, local, name):
        if self.busy:return
        from .disk_image_io import read_local_disk_image, read_remote_disk_image
        source = self.local / name if local else posixpath.join(self.remote, name)
        client = self.client
        if not local and client is None:
            self.status.set_text('Connect first.');return
        def task():
            return (read_local_disk_image(source) if local
                    else read_remote_disk_image(client, source))
        def done(image):
            if not local and self.client is not client:
                self.status.set_text('Connection changed. Open the disk image again.');return
            from .disk_image_dialog import DiskImageDialog
            self.disk_image_dialog = DiskImageDialog(self, str(source), image)
            self.status.set_text(
                f'Opened an authentic Commodore {image.drive_model} disk directory.')
        self.run(task,done)

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
        self.set_active_file_pane(local)
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
            if not multiple and not directory and name.casefold().endswith(('.d64', '.d71', '.d81')):
                self.button(box, 'Open disk image',
                            lambda: action(lambda: self.open_disk_image(local, name)))
            if (not multiple and not local and not directory and
                    name.casefold().endswith(('.d64', '.g64', '.d71', '.g71', '.d81'))):
                self.button(box, 'Mount…',
                            lambda: action(lambda: self.open_mount_in_drives(name)))
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
            if local:
                self.button(box, 'New D64 disk…', lambda: action(self.new_d64))
            else:
                self.button(box, 'New D64 disk on C64U…',
                            lambda: action(self.new_remote_d64))
        self.button(box, 'Paste', lambda: action(lambda: self.paste_files(local)))
        popover.connect('closed', lambda widget: widget.unparent())
        popover.popup()

    def open_mount_in_drives(self, name):
        """Open Drives with one remote image prepared for Drive A."""
        if not self.client:
            raise BrowserError('Connect first.')
        if not name.casefold().endswith(('.d64', '.g64', '.d71', '.g71', '.d81')):
            raise BrowserError('Choose a D64, G64, D71, G71 or D81 image.')
        path = posixpath.join(self.remote, name)
        self.drives_tab.select_image(path, 'a')
        self.tabs.set_current_page(self.tabs.page_num(self.drives_tab.box))

    def drag_prepare(self, listing, local, x, y):
        self.menu_token = None
        self.set_active_file_pane(local)
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
                copied = completed_roots(names, result.completed)
                if result.error: self.copy_report(result)
                if partial:
                    self.partial_upload = (client, partial)
                    self.partial_button.set_sensitive(True)
                local_selection = ()
                if source_local and Path(parent).resolve() == self.local.resolve():
                    local_selection = copied
                if local and Path(destination).resolve() == self.local.resolve():
                    local_selection = tuple(dict.fromkeys(local_selection + copied))
                self.refresh_local(local_selection)
                if not self.client:
                    self.status.set_text(message); return
                current = self.client
                folder = self.remote
                def refresh():
                    try: return current.list_directory(folder), None
                    except Exception as exc: return None, str(exc)
                def refreshed(result):
                    listing, error = result
                    remote_selection = ()
                    if (not source_local and
                            posixpath.normpath(str(parent)) == posixpath.normpath(folder)):
                        remote_selection = copied
                    if (not local and
                            posixpath.normpath(str(destination)) == posixpath.normpath(folder)):
                        remote_selection = tuple(dict.fromkeys(
                            remote_selection + copied))
                    if listing is not None and self.client is current:
                        self.show_remote(listing, remote_selection)
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

    def new_d64(self):
        """Create a validated blank D64 in the current local folder."""
        if self.busy or getattr(self, 'd64_create_prompt', None) is not None:
            return
        dialog = Gtk.Dialog(
            title='Create blank D64 disk', transient_for=self.window, modal=True)
        self.d64_create_prompt = dialog
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        create = dialog.add_button('Create disk', Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        content.append(Gtk.Label(
            label='The new standard 35-track image will be created in:\n' + str(self.local),
            xalign=0, wrap=True, selectable=True))
        filename = Gtk.Entry(text='new-disk.d64', hexpand=True)
        disk_name = Gtk.Entry(text='UNTITLED', max_length=16, hexpand=True)
        disk_id = Gtk.Entry(max_length=2, hexpand=True)
        from .text_input import uppercase_entry
        disk_name.connect('changed', uppercase_entry)
        disk_id.connect('changed', uppercase_entry)
        self.d64_create_entries = (filename, disk_name, disk_id)
        for label, entry in (
                ('Local filename:', filename),
                ('C64 disk name (up to 16 characters):', disk_name),
                ('C64 disk ID (exactly 2 characters or none):', disk_id)):
            content.append(Gtk.Label(label=label, xalign=0))
            content.append(entry)
        feedback = Gtk.Label(xalign=0, wrap=True)
        content.append(feedback)
        dialog.get_content_area().append(content)

        def validate(*_):
            leaf = filename.get_text().strip()
            identifier = disk_id.get_text().strip()
            okay = (bool(leaf and disk_name.get_text().strip())
                    and len(identifier) in (0, 2)
                    and leaf not in ('.', '..')
                    and '/' not in leaf and '\\' not in leaf)
            create.set_sensitive(okay)
            feedback.set_text('' if okay else
                              'Enter one local filename and a disk name. '
                              'Leave the disk ID blank or enter exactly 2 characters.')
            return okay

        for entry in self.d64_create_entries:
            entry.connect('changed', validate)
        filename.connect('activate', lambda *_: disk_name.grab_focus())
        disk_name.connect('activate', lambda *_: disk_id.grab_focus())
        disk_id.connect(
            'activate', lambda *_: dialog.response(Gtk.ResponseType.OK)
            if validate() else None)
        validate()

        folder = self.local
        def response(_, code):
            leaf = filename.get_text().strip()
            name = disk_name.get_text()
            identifier = disk_id.get_text()
            if code == Gtk.ResponseType.OK and not validate():
                return
            dialog.destroy()
            self.d64_create_prompt = None
            self.d64_create_entries = None
            if code != Gtk.ResponseType.OK:
                return
            if not leaf.casefold().endswith('.d64'):
                leaf += '.d64'
            destination = folder / leaf
            from .disk_image_io import create_blank_d64
            def done(result):
                self.refresh_local((Path(result['path']).name,))
                self.status.set_text(
                    'Created a validated standard D64 with 664 blocks free. '
                    'The new local image is selected.')
            self.run(lambda: create_blank_d64(destination, name, identifier), done)

        dialog.connect('response', response)
        dialog.present()
        filename.grab_focus()
        return dialog

    def new_remote_d64(self):
        """Create and verify a blank D64 using the connected C64U API."""
        if self.busy or getattr(self, 'remote_d64_create_prompt', None) is not None:
            return
        if not self.client:
            self.status.set_text('Connect first.')
            return
        dialog = Gtk.Dialog(
            title='Create blank D64 on C64U', transient_for=self.window, modal=True)
        self.remote_d64_create_prompt = dialog
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        create = dialog.add_button('Create disk', Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        content.append(Gtk.Label(
            label='The C64U will create a standard 35-track image in:\n' + self.remote,
            xalign=0, wrap=True))
        filename = Gtk.Entry(text='new-disk.d64', hexpand=True)
        disk_name = Gtk.Entry(text='UNTITLED', max_length=16, hexpand=True)
        from .text_input import uppercase_entry
        disk_name.connect('changed', uppercase_entry)
        content.append(Gtk.Label(label='C64U filename:', xalign=0))
        content.append(filename)
        content.append(Gtk.Label(
            label='C64 disk name (up to 16 characters):', xalign=0))
        content.append(disk_name)
        feedback = Gtk.Label(xalign=0, wrap=True)
        content.append(feedback)
        dialog.get_content_area().append(content)

        def validate(*_):
            leaf = filename.get_text().strip()
            label = disk_name.get_text().strip()
            okay = (bool(leaf and label) and leaf not in ('.', '..')
                    and '/' not in leaf and '\\' not in leaf
                    and not any(ord(character) < 32 or ord(character) == 127
                                for character in leaf + label))
            create.set_sensitive(okay)
            feedback.remove_css_class('argonaut-error-message')
            feedback.set_text('' if okay else
                              'Enter one ordinary filename and a disk name.')
            return okay

        filename.connect('changed', validate)
        disk_name.connect('changed', validate)
        filename.connect('activate', lambda *_: disk_name.grab_focus())
        disk_name.connect(
            'activate', lambda *_: dialog.response(Gtk.ResponseType.OK)
            if validate() else None)
        validate()
        client, folder = self.client, self.remote

        def response(_, code):
            leaf = filename.get_text().strip()
            label = disk_name.get_text().strip()
            if code == Gtk.ResponseType.OK and not validate():
                return
            if code != Gtk.ResponseType.OK:
                dialog.destroy()
                self.remote_d64_create_prompt = None
                return
            if not leaf.casefold().endswith('.d64'):
                leaf += '.d64'
            try:
                destination = child(folder, leaf)
            except BrowserError as exc:
                feedback.add_css_class('argonaut-error-message')
                feedback.set_text(str(exc))
                return

            content.set_sensitive(False)
            create.set_sensitive(False)
            feedback.remove_css_class('argonaut-error-message')
            feedback.set_text('Creating and validating the disk image…')

            def task():
                from .disk_image_io import create_remote_blank_d64
                try:
                    create_remote_blank_d64(client, destination, label)
                    return client.list_directory(folder), leaf
                except Exception as exc:
                    return exc

            def done(result):
                if isinstance(result, Exception):
                    content.set_sensitive(True)
                    create.set_sensitive(True)
                    feedback.add_css_class('argonaut-error-message')
                    feedback.set_text(str(result))
                    return
                dialog.destroy()
                self.remote_d64_create_prompt = None
                if self.client is not client:
                    self.status.set_text(
                        'Connection changed after D64 creation; refresh the C64U folder.')
                    return
                listing, created_leaf = result
                self.show_remote(listing, (created_leaf,))
                self.status.set_text(
                    'Created and verified a standard blank D64 on the C64U; '
                    'the new image is selected.')
            self.run(task, done)

        dialog.connect('response', response)
        dialog.present()
        filename.grab_focus()
        return dialog

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
        if getattr(self, 'test_lab_tab', None): self.test_lab_tab.stop_schedule()
        disable_private_log(getattr(self, 'operation_log', None))
        self.operation_log = None
        self.streams_tab.close()
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
