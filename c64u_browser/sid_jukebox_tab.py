# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""GTK presentation for the Core-owned SID Jukebox."""
from pathlib import Path
import json
import posixpath

from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from .api import BrowserError
from .sid_jukebox_client import (
    SidJukeboxClient, clock_text, error_text,
    playback_preview_lines, sid_configuration_text, sid_models_text, source_text,
)


class SidJukeboxTab:
    def __init__(self, app):
        self.app = app
        self.client = SidJukeboxClient(app.core.sid_catalog, app.core.sid_jukebox)
        self.connected = bool(app.core.device_session().session_id)
        self.loading = False;self.job_busy = False;self.chooser = None
        self.rows = {};self.playlist_rows = {};self.playlist_menu = None
        self.drag_token=GLib.uuid_string_random()

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        toolbar = Gtk.Box(spacing=8);self.box.append(toolbar)
        self.search = Gtk.SearchEntry(
            placeholder_text='Search title, author, notes, or source', hexpand=True)
        self.search.connect('search-changed', self._search_changed);toolbar.append(self.search)
        self.favorites = Gtk.CheckButton(label='Favorites only')
        self.favorites.connect('toggled', self._favorites_changed);toolbar.append(self.favorites)
        toolbar.append(Gtk.Label(label='Sort'))
        self.sort_choice=Gtk.ComboBoxText()
        for key,label in (('title','Title'),('author','Author'),('released','Released'),
                          ('format','Format'),('favorite','Favorites first')):
            self.sort_choice.append(key,label)
        self.sort_choice.set_active_id('title')
        self.sort_choice.connect('changed',self._sort_changed);toolbar.append(self.sort_choice)

        actions = Gtk.Box(spacing=8);self.box.append(actions)
        self.add_local_button = app.button(actions, 'Add local SID files…', self.add_local)
        self.add_c64u_button = app.button(actions, 'Add selected C64U SID', self.add_c64u)
        self.validate_button = app.button(actions, 'Validate', self.validate)
        self.relink_button = app.button(actions, 'Locate/Relink…', self.relink)
        self.remove_button = app.button(actions, 'Remove from Jukebox…', self.remove)
        self.cancel_button = app.button(actions, 'Cancel operation', self.cancel_operation)
        self.cancel_button.set_sensitive(False)

        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL,
                         vexpand=True, hexpand=True)
        pane.set_position(450);pane.set_shrink_start_child(False)
        pane.set_shrink_end_child(False);self.box.append(pane)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.library_column=left
        self.library_state = Gtk.Label(xalign=0, wrap=True);left.append(self.library_state)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE,
                                activate_on_single_click=False)
        self.list.connect('row-selected', self._selected)
        self.list.connect('row-activated',lambda *_:self.add_playlist_items())
        library_keys=Gtk.EventControllerKey()
        library_keys.connect('key-pressed',self._library_key_pressed)
        self.list.add_controller(library_keys)
        library_drag=Gtk.DragSource();library_drag.set_actions(Gdk.DragAction.COPY)
        library_drag.connect('prepare',self._library_drag_prepare)
        self.list.add_controller(library_drag);self.library_drag=library_drag
        self.library_scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True)
        self.library_scroll.set_child(self.list);left.append(self.library_scroll)

        self.library_summary=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        left.append(self.library_summary)
        self.heading = Gtk.Label(label='Select SID tunes to add to a playlist.',
                                 xalign=0, wrap=True)
        self.heading.add_css_class('title-4');self.library_summary.append(self.heading)
        self.metadata = Gtk.Label(xalign=0,wrap=True,selectable=True)
        self.library_summary.append(self.metadata)
        self.requirements = Gtk.Label(xalign=0,wrap=True,selectable=True)
        self.library_summary.append(self.requirements)
        self.warnings = Gtk.Label(xalign=0,wrap=True,selectable=True)
        self.library_summary.append(self.warnings)
        library_actions=Gtk.Box(spacing=8);self.library_summary.append(library_actions)
        library_actions.append(Gtk.Label(label='Subtune'))
        self.subtune=Gtk.SpinButton.new_with_range(1,1,1);library_actions.append(self.subtune)
        self.add_item_button=app.button(
            library_actions,'Add to active playlist',self.add_playlist_items)
        self.add_to_button=app.button(library_actions,'Add to…',self.choose_playlist_for_add)
        self.details_button=app.button(library_actions,'Details…',self.show_library_details)
        pane.set_start_child(left)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                        vexpand=True, hexpand=True)
        for side in ('top','bottom','start','end'):
            getattr(right, 'set_margin_' + side)(10)
        pane.set_end_child(right)

        self.playlist_section=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,spacing=6,vexpand=True)
        right.append(self.playlist_section)
        playlist_heading=Gtk.Label(label='Active Playlist',xalign=0)
        playlist_heading.add_css_class('title-3');self.playlist_section.append(playlist_heading)
        title_row = Gtk.Box(spacing=8);self.playlist_section.append(title_row)
        self.playlist_choice = Gtk.ComboBoxText(hexpand=True)
        self.playlist_choice.connect('changed', self._playlist_changed)
        title_row.append(self.playlist_choice)
        self.new_playlist_button = app.button(title_row, 'New…', self.new_playlist)
        self.rename_playlist_button = app.button(title_row, 'Rename…', self.rename_playlist)
        self.delete_playlist_button = app.button(title_row, 'Delete…', self.delete_playlist)
        item_actions = Gtk.Box(spacing=8);self.playlist_section.append(item_actions)
        self.remove_item_button = app.button(
            item_actions, 'Remove selected', self.remove_playlist_items)
        self.up_button = app.button(item_actions, 'Move up', lambda:self.move_playlist_items(-1))
        self.down_button = app.button(item_actions, 'Move down', lambda:self.move_playlist_items(1))
        self.playlist_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE,
                                         activate_on_single_click=False)
        self.playlist_list.connect('row-selected', self._playlist_item_selected)
        playlist_keys=Gtk.EventControllerKey()
        playlist_keys.connect('key-pressed',self._playlist_key_pressed)
        self.playlist_list.add_controller(playlist_keys)
        playlist_drag=Gtk.DragSource();playlist_drag.set_actions(Gdk.DragAction.MOVE)
        playlist_drag.connect('prepare',self._playlist_drag_prepare)
        self.playlist_list.add_controller(playlist_drag);self.playlist_drag=playlist_drag
        playlist_drop=Gtk.DropTarget.new(
            GObject.TYPE_STRING,Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        playlist_drop.connect('drop',self._playlist_drop)
        self.playlist_list.add_controller(playlist_drop);self.playlist_drop=playlist_drop
        playlist_menu=Gtk.GestureClick();playlist_menu.set_button(3)
        playlist_menu.connect('pressed',self._playlist_context_menu)
        self.playlist_list.add_controller(playlist_menu)
        self.playlist_scroll = Gtk.ScrolledWindow(vexpand=True,hexpand=True)
        self.playlist_scroll.set_child(self.playlist_list)
        self.playlist_section.append(self.playlist_scroll)

        self.transport_row = Gtk.Box(spacing=8);self.playlist_section.append(self.transport_row)
        self.play_button = app.button(self.transport_row, 'Review & Play playlist…', self.play)
        self.previous_button = app.button(self.transport_row, 'Previous', self.previous)
        self.next_button = app.button(self.transport_row, 'Next', self.next)
        self.shuffle = Gtk.CheckButton(label='Shuffle')
        self.shuffle.connect('toggled', self._shuffle_toggled)
        self.transport_row.append(self.shuffle)

        right.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self.now_playing_section=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,spacing=3)
        right.append(self.now_playing_section)
        now_heading=Gtk.Label(label='Now Playing',xalign=0)
        now_heading.add_css_class('title-3');self.now_playing_section.append(now_heading)
        self.now_playing_heading=Gtk.Label(xalign=0,wrap=True)
        self.now_playing_heading.add_css_class('title-4')
        self.now_playing_section.append(self.now_playing_heading)
        self.now_playing_metadata=Gtk.Label(xalign=0,wrap=True,selectable=True)
        self.now_playing_section.append(self.now_playing_metadata)
        self.now_playing_source=Gtk.Label(xalign=0,ellipsize=3,selectable=True)
        self.now_playing_section.append(self.now_playing_source)
        self.now_playing_requirements=Gtk.Label(xalign=0,wrap=True,selectable=True)
        self.now_playing_section.append(self.now_playing_requirements)
        self.now_playing_warnings=Gtk.Label(xalign=0,wrap=True,selectable=True)
        self.now_playing_section.append(self.now_playing_warnings)
        self.duration = Gtk.Label(label='Duration: Unknown', xalign=0)
        self.now_playing_section.append(self.duration)
        self.now_playing_section.append(Gtk.Label(
            label='A command accepted by the C64U does not verify audible playback.',
            xalign=0,wrap=True))

        self.message = Gtk.Label(xalign=0, wrap=True, selectable=True);self.box.append(self.message)
        self.busy_controls = (self.search, self.favorites, self.add_local_button,
            self.add_c64u_button, self.validate_button, self.relink_button,
            self.remove_button, pane)
        self.refresh(False);self.refresh_playlists();self._sync_playback_state()

    def bind(self, connected):
        self.connected = bool(connected);self._sync_playback_state();self._update_actions()

    def _show(self, message):
        self.message.set_text(message);self.app.status.set_text(message)

    def _search_changed(self, entry):
        self.client.query = entry.get_text();self.refresh(True)

    def _favorites_changed(self, button):
        self.client.favorites_only = button.get_active();self.refresh(True)

    def _sort_changed(self,choice):
        self.client.sort_key=choice.get_active_id() or 'title';self.refresh(True)

    def _selected_library_ids(self):
        return tuple(row.tune_id for row in sorted(
            self.list.get_selected_rows(),key=lambda row:row.get_index()))

    def _selected_playlist_ids(self):
        return tuple(row.item_id for row in sorted(
            self.playlist_list.get_selected_rows(),key=lambda row:row.get_index()))

    def refresh(self, preserve=True):
        wanted_ids=(self._selected_library_ids() if preserve else ())
        wanted = self.client.selected_id if preserve else None
        was_loading=self.loading;self.loading=True
        while self.list.get_first_child():self.list.remove(self.list.get_first_child())
        self.rows = {}
        try:records = self.client.records()
        except Exception as exc:
            self.loading=was_loading
            self.library_state.set_text('SID Jukebox is unavailable: ' + str(exc))
            self._clear_details();return
        for tune in records:
            row = Gtk.ListBoxRow();row.tune_id = tune.id
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            for side in ('top','bottom','start','end'):getattr(box, 'set_margin_' + side)(6)
            marker = '★' if tune.favorite else '☆'
            box.append(Gtk.Label(label=f'{marker}  {tune.title}    {tune.metadata.format}',
                                 xalign=0, ellipsize=3))
            box.append(Gtk.Label(label=f'{tune.state.capitalize()} · {source_text(tune.source)}',
                                 xalign=0, ellipsize=3))
            row.set_child(box);self.list.append(row);self.rows[tune.id] = row
        self.library_state.set_text(
            ('No SID tunes match this search.' if self.client.query or self.client.favorites_only
             else 'Your SID Jukebox is empty. Add a SID file without moving the original.')
            if not records else f'{len(records)} SID tune(s) shown')
        for tune_id in wanted_ids:
            if tune_id in self.rows:self.list.select_row(self.rows[tune_id])
        if not wanted_ids:
            if wanted in self.rows:self.list.select_row(self.rows[wanted])
            elif wanted:self.client.selected_id = None
        selected=self.list.get_selected_rows()
        primary=(self.rows.get(wanted) if wanted in self.rows and self.rows[wanted] in selected
                 else (selected[-1] if selected else None))
        self.client.select(primary.tune_id if primary else None)
        self.loading=was_loading
        self._load_details()

    def _selected(self, _list, row):
        if self.loading:return
        selected=self.list.get_selected_rows()
        primary=(row if row in selected else (selected[-1] if selected else None))
        self.client.select(primary.tune_id if primary else None);self._load_details()

    def _clear_details(self):
        self.loading = True
        self.heading.set_text('Select SID tunes to add to a playlist.')
        for label in (self.metadata,self.requirements,self.warnings):label.set_text('')
        self.subtune.set_range(1,1);self.subtune.set_value(1)
        self.loading = False;self._update_actions()

    def _load_details(self):
        tune = self.client.selected()
        if tune is None:self._clear_details();return
        m = tune.metadata;self.loading = True
        selected_count=len(self._selected_library_ids())
        self.heading.set_text(tune.title if selected_count<=1 else
                              f'{selected_count} SID tunes selected')
        self.metadata.set_text(
            f'{m.author or "Unknown"} · {m.released or "Unknown"} · '
            f'{m.format} v{m.version} · {m.songs} subtune(s)')
        self.requirements.set_text(
            f'{clock_text(m.clock)} · {sid_configuration_text(m)} · '
            f'Models: {sid_models_text(m)}')
        warning=('None' if not m.warnings else m.warnings[0]+
                 (f' (+{len(m.warnings)-1} more in Details)' if len(m.warnings)>1 else ''))
        self.warnings.set_text('Warnings: '+warning)
        self.subtune.set_range(1,m.songs);self.subtune.set_value(m.start_song)
        self.loading = False;self._update_actions()

    def _update_actions(self):
        tune = self.client.selected();selected_ids=self._selected_library_ids()
        selected = tune is not None;single=len(selected_ids)==1
        for button in (self.validate_button,self.relink_button,self.remove_button,
                       self.details_button):
            button.set_sensitive(single and not self.job_busy)
        self.add_local_button.set_sensitive(not self.job_busy)
        self.add_c64u_button.set_sensitive(self.connected and not self.job_busy)
        self.play_button.set_sensitive(
            self.client.can_play_playlist(self.connected) and not self.job_busy)
        snapshot = self.client.playback_state()
        navigation = (self.connected and snapshot.playlist_authorized
                      and snapshot.playlist_id == self.client.playlist_id
                      and not self.job_busy)
        self.previous_button.set_sensitive(navigation);self.next_button.set_sensitive(navigation)
        self.shuffle.set_sensitive(navigation);self.cancel_button.set_sensitive(self.job_busy)
        self.search.set_sensitive(not self.job_busy);self.favorites.set_sensitive(not self.job_busy)
        self.sort_choice.set_sensitive(not self.job_busy);self.list.set_sensitive(not self.job_busy)
        self.subtune.set_sensitive(single and not self.job_busy)
        playlist = self.client.selected_playlist()
        has_playlist = playlist is not None
        self.rename_playlist_button.set_sensitive(has_playlist and not self.job_busy)
        self.delete_playlist_button.set_sensitive(has_playlist and not self.job_busy)
        self.add_item_button.set_sensitive(bool(selected_ids) and not self.job_busy)
        self.add_to_button.set_sensitive(bool(selected_ids) and not self.job_busy)
        selected_playlist_ids=self._selected_playlist_ids()
        has_item = has_playlist and bool(selected_playlist_ids)
        self.remove_item_button.set_sensitive(has_item and not self.job_busy)
        selected_set=set(selected_playlist_ids)
        item_ids=tuple(item.id for item in playlist.items) if playlist else ()
        can_up=any(index>0 and item_id in selected_set
                   and item_ids[index-1] not in selected_set
                   for index,item_id in enumerate(item_ids))
        can_down=any(index<len(item_ids)-1 and item_id in selected_set
                     and item_ids[index+1] not in selected_set
                     for index,item_id in enumerate(item_ids))
        self.up_button.set_sensitive(
            has_item and can_up and not self.job_busy)
        self.down_button.set_sensitive(
            has_item and can_down and not self.job_busy)
        if not self.client.can_play_playlist(self.connected):
            self.play_button.set_tooltip_text(
                self.client.playlist_blocked_reason() or 'Connect to a C64U to play.')
        else:self.play_button.set_tooltip_text(None)

    def _run_job(self, job, finished):
        self.job_busy = True;self._update_actions()
        def event(update):
            progress = update.job.progress
            if update.kind == 'progress' and progress and progress.message:
                GLib.idle_add(lambda:(self._show(progress.message),False)[1])
        job.add_listener(event)
        def done(snapshot):
            self.job_busy = False;self._update_actions();finished(snapshot)
        self.app.run_file_job(job, done)

    def cancel_operation(self):
        if self.job_busy:self.app.cancel_transfer()

    def _library_key_pressed(self,_controller,keyval,_keycode,_state):
        if keyval not in (Gdk.KEY_Return,Gdk.KEY_KP_Enter):return False
        GLib.idle_add(lambda:(self.add_playlist_items(),False)[1]);return True

    def _playlist_key_pressed(self,_controller,keyval,_keycode,_state):
        if (_state & Gdk.ModifierType.CONTROL_MASK
                and keyval in (Gdk.KEY_a,Gdk.KEY_A)):
            self.playlist_list.select_all();self._update_actions();return True
        if keyval not in (Gdk.KEY_Delete,Gdk.KEY_KP_Delete,Gdk.KEY_BackSpace):return False
        if not self._selected_playlist_ids():return False
        GLib.idle_add(lambda:(self.remove_playlist_items(),False)[1]);return True

    def _drag_content(self,kind,ids):
        ids=tuple(ids)
        if not ids or len(ids)>1000:return None
        payload=json.dumps(
            {'token':self.drag_token,'kind':kind,'ids':ids},separators=(',',':'))
        value=GObject.Value();value.init(GObject.TYPE_STRING);value.set_string(payload)
        return Gdk.ContentProvider.new_for_value(value)

    def _drag_value(self,value):
        if not isinstance(value,str) or len(value)>65536:return None,()
        try:data=json.loads(value)
        except (TypeError,ValueError):return None,()
        kind=data.get('kind') if isinstance(data,dict) else None
        ids=data.get('ids') if isinstance(data,dict) else None
        if (data.get('token')!=self.drag_token
                or kind not in ('library','playlist') or not isinstance(ids,list)
                or not 0<len(ids)<=1000 or any(not isinstance(item,str) for item in ids)
                or len(set(ids))!=len(ids)):
            return None,()
        return kind,tuple(ids)

    def _library_drag_prepare(self,_source,_x,y):
        row=self.list.get_row_at_y(int(y))
        if row is not None and row not in self.list.get_selected_rows():
            self.list.unselect_all();self.list.select_row(row)
        return self._drag_content('library',self._selected_library_ids())

    def _playlist_drag_prepare(self,_source,_x,y):
        row=self.playlist_list.get_row_at_y(int(y))
        if row is not None and row not in self.playlist_list.get_selected_rows():
            self.playlist_list.unselect_all();self.playlist_list.select_row(row)
        return self._drag_content('playlist',self._selected_playlist_ids())

    def _playlist_drop_index(self,y):
        row=self.playlist_list.get_row_at_y(int(y))
        if row is None:return len(self.playlist_rows)
        allocation=row.get_allocation()
        return row.index+(1 if y>=allocation.y+(allocation.height/2) else 0)

    def _playlist_drop(self,_target,value,_x,y):
        kind,ids=self._drag_value(value)
        if kind=='library':
            visible=set(self.rows)
            if any(item not in visible for item in ids):return False
            ids=tuple(sorted(ids,key=lambda item:self.rows[item].get_index()))
            self._add_tune_ids(ids);return True
        if kind=='playlist':
            playlist=self.client.selected_playlist()
            if playlist is None:return False
            current=tuple(item.id for item in playlist.items)
            if any(item not in current for item in ids):return False
            self._move_playlist_selection_to(ids,self._playlist_drop_index(y));return True
        return False

    def _playlist_context_menu(self,_gesture,_press,x,y):
        row=self.playlist_list.get_row_at_y(int(y))
        if row is None:return
        self._open_playlist_context_menu(row,x,y)

    def _open_playlist_context_menu(self,row,x=0,y=0):
        if row not in self.playlist_list.get_selected_rows():
            self.playlist_list.unselect_all();self.playlist_list.select_row(row)
        if self.playlist_menu is not None:self.playlist_menu.unparent()
        menu=Gtk.Popover(has_arrow=True);menu.set_parent(self.playlist_list)
        rectangle=Gdk.Rectangle();rectangle.x=int(x);rectangle.y=int(y)
        rectangle.width=1;rectangle.height=1;menu.set_pointing_to(rectangle)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3,
                    margin_top=6,margin_bottom=6,margin_start=6,margin_end=6)
        for label,action in (
                ('Remove selected',self.remove_playlist_items),
                ('Move to top',lambda:self.move_playlist_items('top')),
                ('Move up',lambda:self.move_playlist_items(-1)),
                ('Move down',lambda:self.move_playlist_items(1)),
                ('Move to bottom',lambda:self.move_playlist_items('bottom'))):
            button=Gtk.Button(label=label);button.connect(
                'clicked',lambda _button,callback=action:(menu.popdown(),callback()))
            box.append(button)
        menu.set_child(box)
        def closed(popover):
            if popover.get_parent() is not None:popover.unparent()
            if self.playlist_menu is popover:self.playlist_menu=None
        menu.connect('closed',closed)
        self.playlist_menu=menu;menu.popup()

    def show_library_details(self):
        tune=self.client.selected()
        if tune is None or len(self._selected_library_ids())!=1:return
        metadata=tune.metadata
        dialog=Gtk.Dialog(title='SID Library Details',transient_for=self.app.window,modal=True)
        dialog.set_default_size(620,520)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
        dialog.add_button('Save',Gtk.ResponseType.OK)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,
                        margin_top=12,margin_bottom=12,margin_start=12,margin_end=12)
        state=tune.state.capitalize()+' · Playback: '+metadata.playback_classification.capitalize()
        if tune.state_message:state+=' — '+tune.state_message
        technical=(f'{tune.title}\nAuthor: {metadata.author or "Unknown"}\n'
            f'Released: {metadata.released or "Unknown"}\n'
            f'{metadata.format} v{metadata.version} · {metadata.songs} subtune(s)\n'
            f'{sid_configuration_text(metadata)} · Models: {sid_models_text(metadata)} · '
            f'Clock: {clock_text(metadata.clock)}\n{state}\n'
            f'Source: {source_text(tune.source)}\nSHA-256: {metadata.sha256}\n'
            'Warnings: '+('\n'.join('• '+item for item in metadata.warnings)
                           if metadata.warnings else 'None'))
        content.append(Gtk.Label(label=technical,xalign=0,wrap=True,selectable=True))
        favorite=Gtk.CheckButton(label='Favorite',active=tune.favorite);content.append(favorite)
        content.append(Gtk.Label(label='Notes',xalign=0))
        notes=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,accepts_tab=False)
        notes.get_buffer().set_text(tune.notes)
        note_scroll=Gtk.ScrolledWindow(vexpand=True);note_scroll.set_child(notes)
        content.append(note_scroll);dialog.get_content_area().append(content)
        def response(widget,code):
            if code==Gtk.ResponseType.OK:
                start,end=notes.get_buffer().get_bounds()
                try:
                    self.client.set_favorite(favorite.get_active())
                    self.client.set_notes(notes.get_buffer().get_text(start,end,True))
                except Exception as exc:self._show(str(exc))
                else:self._show('SID Library details saved.');self.refresh(True)
            widget.destroy()
        dialog.connect('response',response);dialog.present();return dialog

    @staticmethod
    def _sid_filter(chooser):
        filter_ = Gtk.FileFilter();filter_.set_name('SID tunes')
        filter_.add_pattern('*.sid');filter_.add_pattern('*.SID');chooser.add_filter(filter_)

    def add_local(self):
        if self.chooser:return
        chooser = Gtk.FileChooserNative.new('Add SID tunes',self.app.window,
            Gtk.FileChooserAction.OPEN,'Add','Cancel')
        chooser.set_select_multiple(True);chooser.set_current_folder(
            Gio.File.new_for_path(str(self.app.local)))
        self._sid_filter(chooser);self.chooser = chooser
        def response(_,code):
            files=chooser.get_files();chosen=([files.get_item(i) for i in range(files.get_n_items())]
                if code==Gtk.ResponseType.ACCEPT else [])
            chooser.destroy();self.chooser=None
            paths=tuple(item.get_path() for item in chosen if item.get_path())
            if paths:self._add_local_paths(paths)
        chooser.connect('response',response);chooser.show()

    def _add_local_paths(self, paths, index=0, added=0, failures=()):
        if index >= len(paths):
            self.refresh(False);self._show(
                f'Added {added} SID tune(s).' +
                (f' {len(failures)} file(s) were not added: {failures[0]}' if failures else ''))
            return
        try:job=self.client.add_core_host(paths[index])
        except Exception as exc:
            self._add_local_paths(paths,index+1,added,failures+(str(exc),));return
        def finished(snapshot):
            if snapshot.state!='succeeded':
                self._add_local_paths(paths,index+1,added,failures+(error_text(snapshot.error),));return
            created=bool(snapshot.result.created)
            self._add_local_paths(paths,index+1,added+created,failures)
        self._run_job(job,finished)

    def _selected_remote_source(self):
        rows=self.app.rlist.get_selected_rows()
        if len(rows)!=1 or rows[0].item[0]=='..' or rows[0].item[1]:
            raise BrowserError('Select one SID file in the C64U Files pane.')
        name=rows[0].item[0]
        if not name.casefold().endswith('.sid'):raise BrowserError('Select a .sid file.')
        session=self.app.core.device_session()
        if not session.device_id or not session.session_id:raise BrowserError('Connect first.')
        return session.device_id,posixpath.join(self.app.remote,name)

    def add_c64u(self):
        try:device_id,path=self._selected_remote_source()
        except Exception as exc:self._show(str(exc));return
        self.add_c64u_path(device_id,path)

    def add_c64u_path(self, device_id, path):
        try:job=self.client.add_c64u(device_id,path)
        except Exception as exc:self._show(str(exc));return False
        self._show('Validating C64U SID…')
        def finished(snapshot):
            if snapshot.state!='succeeded':self._show(error_text(snapshot.error));return
            self.client.select(snapshot.result.tune.id);self.refresh(True)
            self._show('C64U SID is available in SID Jukebox.')
        self._run_job(job,finished);return True

    def remove(self):
        tune=self.client.selected()
        if tune is None:return
        dialog=Gtk.Dialog(title='Remove from SID Jukebox?',transient_for=self.app.window,modal=True)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
        dialog.add_button('Remove catalog entry',Gtk.ResponseType.OK)
        dialog.get_content_area().append(Gtk.Label(
            label=f'Remove “{tune.title}” from SID Jukebox?\n\nThe SID file will not be deleted or changed.',
            wrap=True,xalign=0,margin_top=12,margin_bottom=12,margin_start=12,margin_end=12))
        def response(widget,code):
            widget.destroy()
            if code!=Gtk.ResponseType.OK:return
            try:self.client.remove()
            except Exception as exc:self._show(str(exc));return
            self.client.selected_id=None;self.refresh(False);self.refresh_playlists()
            self._show('Catalog entry removed. The SID file was not deleted.')
        dialog.connect('response',response);dialog.present()

    def validate(self):
        try:job=self.client.validate()
        except Exception as exc:self._show(str(exc));return
        self._show('Validating SID source…')
        def finished(snapshot):
            if snapshot.state!='succeeded':self._show(error_text(snapshot.error));return
            self.refresh(True);self._show('SID source validation: '+snapshot.result.tune.state+'.')
        self._run_job(job,finished)

    def relink(self):
        if self.client.selected() is None:return
        dialog=Gtk.Dialog(title='Locate/Relink SID',transient_for=self.app.window,modal=True)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
        dialog.add_button('Choose local SID…',1)
        dialog.add_button('Use selected C64U SID',2)
        dialog.get_content_area().append(Gtk.Label(
            label='Choose a replacement on this computer or use the SID currently selected in the C64U Files pane.',
            wrap=True,xalign=0,margin_top=12,margin_bottom=12,margin_start=12,margin_end=12))
        def response(widget,code):
            widget.destroy()
            if code==1:self._choose_relink_local()
            elif code==2:self._prepare_relink_c64u()
        dialog.connect('response',response);dialog.present()

    def _choose_relink_local(self):
        if self.chooser:return
        chooser=Gtk.FileChooserNative.new('Locate replacement SID',self.app.window,
            Gtk.FileChooserAction.OPEN,'Review','Cancel');self._sid_filter(chooser)
        tune=self.client.selected();current=Path(tune.source.path).parent
        if tune.source.scope!='c64u' and current.is_dir():
            chooser.set_current_folder(Gio.File.new_for_path(str(current)))
        self.chooser=chooser
        def response(_,code):
            file=chooser.get_file();chooser.destroy();self.chooser=None
            if code!=Gtk.ResponseType.ACCEPT or not file or not file.get_path():return
            try:job=self.client.prepare_relink_core_host(file.get_path())
            except Exception as exc:self._show(str(exc));return
            self._run_job(job,self._relink_prepared)
        chooser.connect('response',response);chooser.show()

    def _prepare_relink_c64u(self):
        try:device_id,path=self._selected_remote_source();job=self.client.prepare_relink_c64u(device_id,path)
        except Exception as exc:self._show(str(exc));return
        self._run_job(job,self._relink_prepared)

    def _relink_prepared(self,snapshot):
        if snapshot.state!='succeeded':self._show(error_text(snapshot.error));return
        preview=snapshot.result
        dialog=Gtk.Dialog(title='Review SID Relink',transient_for=self.app.window,modal=True)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
        dialog.add_button('Relink' if preview.content_matches else 'Accept different content',Gtk.ResponseType.OK)
        comparison=('SHA-256 matches the cataloged SID.' if preview.content_matches else
                    'SHA-256 differs. Approval changes the cataloged content identity.')
        dialog.get_content_area().append(Gtk.Label(
            label=f'New source: {source_text(preview.source)}\n{preview.metadata.format} v{preview.metadata.version}\n\n{comparison}',
            wrap=True,xalign=0,margin_top=12,margin_bottom=12,margin_start=12,margin_end=12))
        def response(widget,code):
            widget.destroy()
            if code!=Gtk.ResponseType.OK:return
            try:job=self.client.execute_relink(preview.plan_id,not preview.content_matches)
            except Exception as exc:self._show(str(exc));return
            self._run_job(job,lambda result:(self.refresh(True),self._show(
                'SID Relink completed.' if result.state=='succeeded' else error_text(result.error))))
        dialog.connect('response',response);dialog.present()

    def _playlist_changed(self,choice):
        if self.loading:return
        self.client.playlist_id=choice.get_active_id() or None
        self.client.playlist_item_id=None;self.refresh_playlist_items();self._update_actions()
        playlist=self.client.selected_playlist()
        snapshot=self.client.playback_state();self.loading=True
        self.shuffle.set_active(bool(snapshot.playlist_authorized
            and snapshot.playlist_id==self.client.playlist_id and snapshot.shuffle))
        self.loading=False
        self._show('Playlist selected: '+playlist.title+'.' if playlist else
                   'No playlist selected.')

    def refresh_playlists(self):
        wanted=self.client.playlist_id;self.loading=True;self.playlist_choice.remove_all()
        playlists=self.client.playlists()
        for playlist in playlists:self.playlist_choice.append(playlist.id,playlist.title)
        if wanted and any(item.id==wanted for item in playlists):
            selected_id=wanted
        elif playlists:selected_id=playlists[0].id
        else:selected_id=None
        self.client.playlist_id=selected_id
        self.client.playlist_item_id=(self.client.playlist_item_id
            if selected_id==wanted else None)
        if selected_id:self.playlist_choice.set_active_id(selected_id)
        self.loading=False;self.refresh_playlist_items();self._update_actions()

    def refresh_playlist_items(self, selected_ids=None):
        wanted=self.client.playlist_item_id;was_loading=self.loading
        if selected_ids is None:selected_ids=self._selected_playlist_ids()
        self.loading=True
        while self.playlist_list.get_first_child():self.playlist_list.remove(self.playlist_list.get_first_child())
        self.playlist_rows={};playlist=self.client.selected_playlist()
        snapshot=self.client.playback_state()
        playing=(getattr(snapshot,'playlist_item_id','')
                 if playlist is not None and getattr(snapshot,'playlist_id','')==playlist.id
                 else '')
        if playlist is not None:
            for index,item in enumerate(playlist.items):
                row=Gtk.ListBoxRow();row.item_id=item.id;row.index=index
                row.playing=item.id==playing
                try:title=self.client.catalog.get(item.tune_id).title
                except Exception:title='Missing SID entry'
                marker='▶' if row.playing else ' '
                row.set_child(Gtk.Label(label=f'{marker} {index+1}. {title} · Subtune {item.subtune}',xalign=0,
                                        margin_top=5,margin_bottom=5,margin_start=5,margin_end=5))
                self.playlist_list.append(row);self.playlist_rows[item.id]=row
        selected_ids=tuple(item_id for item_id in selected_ids
                           if item_id in self.playlist_rows)
        if wanted in self.playlist_rows and wanted not in selected_ids:
            selected_ids=selected_ids+(wanted,)
        for item_id in selected_ids:
            self.playlist_list.select_row(self.playlist_rows[item_id])
        self.client.playlist_item_id=(wanted if wanted in self.playlist_rows else
            (selected_ids[-1] if selected_ids else None))
        self.loading=was_loading

    def _playlist_item_selected(self,_list,row):
        if self.loading:return
        selected=self.playlist_list.get_selected_rows()
        primary=(row if row in selected else (selected[-1] if selected else None))
        self.client.playlist_item_id=primary.item_id if primary else None
        self._update_actions()

    def _text_prompt(self,title,initial,accepted,success):
        dialog=Gtk.Dialog(title=title,transient_for=self.app.window,modal=True)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL);dialog.add_button('Save',Gtk.ResponseType.OK)
        entry=Gtk.Entry(text=initial,hexpand=True,margin_top=12,margin_bottom=12,margin_start=12,margin_end=12)
        dialog.get_content_area().append(entry)
        def response(widget,code):
            value=entry.get_text();widget.destroy()
            if code==Gtk.ResponseType.OK:
                try:playlist=accepted(value)
                except Exception as exc:self._show(str(exc));return
                self.client.playlist_id=playlist.id
                self.client.playlist_item_id=None
                self.refresh_playlists()
                self._show(success)
        dialog.connect('response',response);dialog.present();return dialog

    def new_playlist(self):return self._text_prompt(
        'New SID playlist','',self.client.create_playlist,'Playlist created.')
    def rename_playlist(self):
        playlist=self.client.selected_playlist()
        if playlist:return self._text_prompt(
            'Rename SID playlist',playlist.title,self.client.rename_playlist,
            'Playlist renamed.')

    def delete_playlist(self):
        playlist=self.client.selected_playlist()
        if playlist is None:return
        dialog=Gtk.Dialog(title='Delete SID playlist?',transient_for=self.app.window,modal=True)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL);dialog.add_button('Delete playlist',Gtk.ResponseType.OK)
        dialog.get_content_area().append(Gtk.Label(label=f'Delete “{playlist.title}”? SID files stay in the catalog.',
            wrap=True,margin_top=12,margin_bottom=12,margin_start=12,margin_end=12))
        def response(widget,code):
            widget.destroy()
            if code==Gtk.ResponseType.OK:
                try:self.client.delete_playlist()
                except Exception as exc:self._show(str(exc));return
                self.client.playlist_id=None;self.client.playlist_item_id=None;self.refresh_playlists()
                self._show('Playlist deleted.')
        dialog.connect('response',response);dialog.present()

    def _default_playlist(self):
        playlist=self.client.selected_playlist()
        if playlist is not None:return playlist
        playlists=self.client.playlists()
        if playlists:
            self.client.playlist_id=playlists[0].id;self.refresh_playlists()
            return self.client.selected_playlist()
        playlist=self.client.create_playlist('Playlist 1')
        self.client.playlist_id=playlist.id;self.client.playlist_item_id=None
        self.refresh_playlists();return playlist

    def _add_tune_ids(self,tune_ids,playlist_id=None):
        tune_ids=tuple(tune_ids)
        if not tune_ids:return
        try:
            if playlist_id is None:playlist=self._default_playlist()
            else:
                self.client.playlist_id=playlist_id;self.client.playlist_item_id=None
                self.refresh_playlists();playlist=self.client.selected_playlist()
            if playlist is None:raise BrowserError('Choose or create a playlist first.')
            single=len(tune_ids)==1;added=[]
            for tune_id in tune_ids:
                tune=self.client.catalog.get(tune_id)
                subtune=(int(self.subtune.get_value()) if single
                         else tune.metadata.start_song)
                added.append(self.client.add_tune_to_playlist(
                    playlist.id,tune_id,subtune))
        except Exception as exc:self._show(str(exc));return
        self.client.playlist_item_id=added[-1].id
        self.refresh_playlist_items(tuple(item.id for item in added));self._update_actions()
        self._show(f'Added {len(tune_ids)} SID tune(s) to {playlist.title}.')

    def add_playlist_items(self,playlist_id=None):
        return self._add_tune_ids(self._selected_library_ids(),playlist_id)

    def choose_playlist_for_add(self):
        if not self._selected_library_ids():return
        playlists=self.client.playlists()
        dialog=Gtk.Dialog(title='Add to playlist',transient_for=self.app.window,modal=True)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL);dialog.add_button('Add',Gtk.ResponseType.OK)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,
                    margin_top=12,margin_bottom=12,margin_start=12,margin_end=12)
        choice=Gtk.ComboBoxText(hexpand=True)
        for playlist in playlists:choice.append(playlist.id,playlist.title)
        choice.append('__new__','New playlist…')
        choice.set_active_id(self.client.playlist_id if self.client.playlist_id else '__new__')
        name=Gtk.Entry(placeholder_text='New playlist name')
        name.set_sensitive(choice.get_active_id()=='__new__')
        choice.connect('changed',lambda item:name.set_sensitive(item.get_active_id()=='__new__'))
        box.append(choice);box.append(name);dialog.get_content_area().append(box)
        def response(widget,code):
            selected=choice.get_active_id();title=name.get_text().strip();widget.destroy()
            if code!=Gtk.ResponseType.OK:return
            try:
                if selected=='__new__':
                    title=title or f'Playlist {len(self.client.playlists())+1}'
                    selected=self.client.create_playlist(title).id
                self.add_playlist_items(selected)
            except Exception as exc:self._show(str(exc))
        dialog.connect('response',response);dialog.present();return dialog

    def remove_playlist_items(self):
        item_ids=self._selected_playlist_ids()
        if not item_ids:return
        try:self.client.remove_playlist_items(item_ids)
        except Exception as exc:self._show(str(exc));return
        self.client.playlist_item_id=None;self.refresh_playlist_items();self._update_actions()
        self._sync_playback_state()
        self._show(f'Removed {len(item_ids)} playlist item(s).')

    def _apply_playlist_order(self,ordered_ids,selected_ids,message):
        try:self.client.reorder_playlist_items(ordered_ids)
        except Exception as exc:self._show(str(exc));return False
        if self.client.playlist_item_id not in selected_ids:
            self.client.playlist_item_id=selected_ids[-1] if selected_ids else None
        self.refresh_playlist_items(selected_ids);self._sync_playback_state();self._update_actions()
        self._show(message);return True

    def move_playlist_items(self,direction):
        selected_ids=self._selected_playlist_ids()
        playlist=self.client.selected_playlist()
        if not selected_ids or playlist is None:return
        selected=set(selected_ids);ordered=[item.id for item in playlist.items]
        if direction=='top':ordered=[*selected_ids,*[item for item in ordered if item not in selected]]
        elif direction=='bottom':ordered=[item for item in ordered if item not in selected]+list(selected_ids)
        elif direction<0:
            for index in range(1,len(ordered)):
                if ordered[index] in selected and ordered[index-1] not in selected:
                    ordered[index-1],ordered[index]=ordered[index],ordered[index-1]
        else:
            for index in range(len(ordered)-2,-1,-1):
                if ordered[index] in selected and ordered[index+1] not in selected:
                    ordered[index],ordered[index+1]=ordered[index+1],ordered[index]
        if tuple(ordered)==tuple(item.id for item in playlist.items):return
        self._apply_playlist_order(
            tuple(ordered),selected_ids,
            f'Moved {len(selected_ids)} playlist item(s).')

    def _move_playlist_selection_to(self,selected_ids,target_index):
        playlist=self.client.selected_playlist()
        if playlist is None:return
        current=tuple(item.id for item in playlist.items);selected=set(selected_ids)
        if not selected or any(item not in current for item in selected):return
        moving=tuple(item for item in current if item in selected)
        target_index=max(0,min(len(current),target_index))
        insertion=target_index-sum(
            1 for index,item in enumerate(current) if index<target_index and item in selected)
        remaining=[item for item in current if item not in selected]
        ordered=tuple(remaining[:insertion])+moving+tuple(remaining[insertion:])
        if ordered==current:return
        self._apply_playlist_order(
            ordered,moving,f'Moved {len(moving)} playlist item(s).')

    def play(self):
        if not self.client.can_play_playlist(self.connected):return
        try:job=self.client.prepare_playlist_play()
        except Exception as exc:self._show(str(exc));return
        self.refresh_playlist_items();self._update_actions()
        self._show('Preparing SID playback…');self._run_job(job,self._play_prepared)

    def _play_prepared(self,snapshot):
        if snapshot.state!='succeeded':self._show(error_text(snapshot.error));self.refresh(True);return
        preview=snapshot.result
        dialog=Gtk.Dialog(title='Review SID Playback',transient_for=self.app.window,modal=True)
        dialog.set_default_size(640,480);dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
        dialog.add_button('Take over C64 and play SID',Gtk.ResponseType.OK)
        text=Gtk.TextView(editable=False,cursor_visible=False,wrap_mode=Gtk.WrapMode.WORD_CHAR)
        text.get_buffer().set_text('\n'.join(playback_preview_lines(preview)))
        scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True)
        scroll.set_child(text);dialog.get_content_area().append(scroll)
        def response(widget,code):
            widget.destroy()
            if code!=Gtk.ResponseType.OK:
                self.client.discard_play(preview.plan_id);self._show('Playback cancelled before sending a command.');return
            try:job=self.client.execute_play(preview.plan_id)
            except Exception as exc:self._show(str(exc));return
            self._run_job(job,self._play_finished)
        dialog.connect('response',response);dialog.present()

    def _play_finished(self,snapshot):
        if snapshot.state=='succeeded':
            self._show('Command accepted — audible playback not verified.')
            self._sync_playback_state();self._update_actions();return
        self._show(error_text(snapshot.error));self._sync_playback_state();self._update_actions()

    def _transition(self,direction):
        try:job=self.client.previous() if direction=='previous' else self.client.next()
        except Exception as exc:self._show(getattr(exc,'args',(str(exc),))[0]);self._sync_playback_state();self._update_actions();return
        self._show(('Previous' if direction=='previous' else 'Next')+' SID…')
        def finished(snapshot):
            if snapshot.state!='succeeded':self._show(error_text(snapshot.error))
            elif snapshot.result.status=='boundary':self._show(snapshot.result.message)
            else:
                self._show('Command accepted — audible playback not verified.')
            self._sync_playback_state();self._update_actions()
        self._run_job(job,finished)

    def previous(self):self._transition('previous')
    def next(self):self._transition('next')

    def _shuffle_toggled(self,button):
        if self.loading:return
        try:snapshot=self.client.set_shuffle(button.get_active())
        except Exception as exc:
            self.loading=True;button.set_active(False);self.loading=False
            self._show(str(exc));self._update_actions();return
        self._show('Shuffle is '+('on.' if snapshot.shuffle else 'off.'))

    def _sync_playback_state(self):
        snapshot=self.client.playback_state();self.loading=True
        self.shuffle.set_active(snapshot.shuffle if snapshot.playlist_authorized else False)
        if snapshot.playlist_authorized and snapshot.playlist_id:
            self.client.playlist_id=snapshot.playlist_id
            self.playlist_choice.set_active_id(snapshot.playlist_id)
            # Editable GTK selection and Core's logical playback cursor are
            # intentionally independent. refresh_playlist_items() reads the
            # snapshot separately to draw the single playing marker.
            self.refresh_playlist_items()
        self.loading=False;self._sync_now_playing()

    def _sync_now_playing(self):
        snapshot,tune=self.client.now_playing()
        if tune is None:
            self.now_playing_heading.set_text(
                'No SID command has been accepted in this session.')
            for label in (self.now_playing_metadata,self.now_playing_source,
                          self.now_playing_requirements,self.now_playing_warnings):
                label.set_text('')
            return
        metadata=tune.metadata
        subtune=getattr(snapshot,'selected_subtune',None)
        self.now_playing_heading.set_text(
            tune.title+(f' · Subtune {subtune}' if subtune is not None else ''))
        self.now_playing_metadata.set_text(f'{metadata.format} v{metadata.version}')
        self.now_playing_source.set_text('Source: '+source_text(tune.source))
        self.now_playing_requirements.set_text(
            f'{sid_configuration_text(metadata)} · Models: {sid_models_text(metadata)} · '
            f'Clock: {clock_text(metadata.clock)}')
        warning=('None' if not metadata.warnings else metadata.warnings[0]+
                 (f' (+{len(metadata.warnings)-1} more; review Library Details)'
                  if len(metadata.warnings)>1 else ''))
        self.now_playing_warnings.set_text('Warnings: '+warning)
