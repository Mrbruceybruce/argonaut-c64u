# SPDX-License-Identifier: GPL-3.0-or-later
"""One managed-library controller for the catalog tab and native Settings page."""
from gi.repository import Gtk, GLib, Pango
from .managed_library import LibraryState
from .storage import root_presentation


class ManagedLibraryView:
    def __init__(self,app):
        self.app=app;self.generation=0;self.closed=False
        self.chooser=None;self.confirmation=None;self.forget_confirmation=None
        self.settings_dialog=None;self.available=();self.available_session=None
        self.box=self.column()
        self.main_message=Gtk.Label(xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,selectable=True)
        self.box.append(self.main_message)
        self.settings_button=Gtk.Button(label='Go to Settings')
        self.settings_button.connect('clicked',lambda *_:self.open_settings())
        self.box.append(self.settings_button)
        scroll=Gtk.ScrolledWindow(vexpand=True)
        self.rows=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        scroll.set_child(self.rows);self.box.append(scroll)
        self.box.append(Gtk.Label(label='Game importing is not available yet.',xalign=0,wrap=True))

        self.settings_box=self.column()
        heading=Gtk.Label(label='Game Library',xalign=0);heading.add_css_class('title-2')
        self.settings_box.append(heading)
        self.settings_box.append(Gtk.Label(label='Current library',xalign=0))
        self.message=Gtk.Label(xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,selectable=True)
        self.settings_box.append(self.message)
        actions=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
            column_spacing=8,row_spacing=6,max_children_per_line=4)
        self.settings_box.append(actions)
        self.refresh_button=Gtk.Button(label='Discover Libraries')
        self.refresh_button.connect('clicked',lambda *_:self.discover())
        self.select_button=Gtk.Button(label='Select Library')
        self.select_button.connect('clicked',lambda *_:self.select_available())
        self.create_button=Gtk.Button(label='Create Library')
        self.create_button.connect('clicked',lambda *_:self.choose_creation())
        self.forget_button=Gtk.Button(label='Forget Library')
        self.forget_button.connect('clicked',lambda *_:self.forget())
        for button in (self.refresh_button,self.select_button,self.create_button,self.forget_button):
            button.update_property([Gtk.AccessibleProperty.LABEL],[button.get_label()])
            actions.insert(button,-1)
        self.settings_box.append(Gtk.Label(label='Available libraries',xalign=0))
        self.discovery_message=Gtk.Label(label='Choose Discover Libraries to check USB/SD storage.',xalign=0,wrap=True)
        self.settings_box.append(self.discovery_message)
        self.choices=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.choices.update_property([Gtk.AccessibleProperty.LABEL],['Available Game Libraries'])
        self.choices.connect('row-selected',lambda *_:self.update_select())
        candidates=Gtk.ScrolledWindow(vexpand=True,hexpand=True,min_content_height=150)
        candidates.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        candidates.set_child(self.choices);self.settings_box.append(candidates)
        self.settings_box.append(Gtk.Label(label='Selection is saved separately from General settings. '
            'Forget keeps all files on the device. Libraries are never merged.',xalign=0,wrap=True))
        self.busy_controls=(self.refresh_button,self.select_button,self.create_button,
                            self.forget_button,self.choices,self.settings_button)
        self.unsubscribe=app.core.add_listener(lambda event:GLib.idle_add(self.event,event))
        self.reset()

    @staticmethod
    def column():
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        for side in ('top','bottom','start','end'):getattr(box,'set_margin_'+side)(16)
        return box

    def parent_window(self):
        return self.settings_dialog or self.app.window

    def open_settings(self):
        from .app_preferences import show_preferences, GAME_LIBRARY_PAGE
        return show_preferences(self.app,page=GAME_LIBRARY_PAGE)

    def attach_settings(self,dialog):
        self.settings_dialog=dialog

    def detach_settings(self):
        if self.chooser:self.chooser.close_requested()
        if self.confirmation:self.confirmation.response(Gtk.ResponseType.CANCEL)
        if self.forget_confirmation:self.forget_confirmation.response(Gtk.ResponseType.CANCEL)
        self.settings_dialog=None

    def matches(self,library,configured):
        return bool(configured and library.identity.device_id==configured['device_id']
            and library.identity.path==configured['path']
            and (not configured['library_id'] or library.identity.library_id==configured['library_id']))

    def event(self,event):
        if self.closed:return False
        if event.kind=='library-location-changed':
            # A successful explicit selection has already persisted and rendered.
            if (self.state.status=='valid' and self.matches(self.state.libraries[0],
                    self.app.preferences.game_library_location)
                    and self.state.session_id==self.app.core.device_session().session_id):return False
            self.reset()
        elif event.kind in ('connected','reconnected','disconnected','offline'):self.reset()
        return False

    def reset(self):
        self.generation+=1
        if self.forget_confirmation:self.forget_confirmation.response(Gtk.ResponseType.CANCEL)
        self.available=();self.available_session=None
        self.discovery_message.set_text('Choose Discover Libraries to check USB/SD storage.')
        configured=self.app.preferences.game_library_location
        self.render(LibraryState('unavailable' if configured else 'none',
            'Configured library is not loaded. Connect to its device and discover libraries.' if configured
            else 'No Game Library Configured'))

    @staticmethod
    def clear(box):
        while box.get_first_child():box.remove(box.get_first_child())

    def summary(self,library):
        identity=library.identity
        profile=getattr(self.app.core,'active_profile',None)
        name=getattr(profile,'name','') if self.app.core.device_session().device_id==identity.device_id else ''
        return (f'{name or "C64 Ultimate"} — {identity.root[1:]}\n'
            f'Device: {identity.device_id}\nStorage root: {identity.root}\n{identity.path}\nLibrary ID: {identity.library_id}\n'
            f'Revision {library.revision} · {len(library.games)} games')

    def render(self,state):
        self.state=state
        configured=self.app.preferences.game_library_location
        self.create_button.set_visible(state.status=='none' and configured is None)
        self.forget_button.set_visible(state.status=='valid' or configured is not None)
        self.clear(self.rows)
        self.message.set_text(state.message)
        if state.status=='valid':
            library=state.libraries[0]
            summary=self.summary(library)
            self.message.set_text('Available · '+summary+'\n'+state.message)
            if self.matches(library,configured):
                self.main_message.set_text('Game Library · Valid\n'+summary+'\n'+state.message)
                for game in library.games:
                    label=Gtk.Label(label=f'{game.title} · {game.format}\n{game.path}',
                        xalign=0,wrap=True,margin_top=5,margin_bottom=5)
                    self.rows.append(label)
            else:self.main_message.set_text('No Game Library Configured\n'
                'Choose an existing library or create a new one in Settings → Game Library.')
        elif configured:
            details=(f"Device: {configured['device_id']}\nStorage root: {configured['root']}\n"
                f"{configured['path']}\nLibrary ID: {configured['library_id'] or 'Not yet verified'}\n"
                'Revision and game count: not loaded')
            self.message.set_text('Game Library Unavailable\n'+details+'\n'+state.message)
            self.main_message.set_text('Game Library Unavailable\n'+details+'\n'+state.message)
        else:
            self.main_message.set_text('No Game Library Configured\n'
                'Choose an existing library or create a new one in Settings → Game Library.')
        self.render_available()

    def render_available(self):
        selected=self.choices.get_selected_row()
        selected_id=selected.library.identity if selected else None
        self.clear(self.choices)
        configured=self.app.preferences.game_library_location
        for library in self.available:
            row=Gtk.ListBoxRow();row.library=library
            text=self.summary(library)
            if self.matches(library,configured):text='Selected library\n'+text
            row.update_property([Gtk.AccessibleProperty.LABEL],[text])
            content=Gtk.Box(spacing=10)
            content.append(Gtk.Image.new_from_icon_name(root_presentation(library.identity.root)[1]))
            label=Gtk.Label(label=text,xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,hexpand=True)
            for side in ('top','bottom','start','end'):getattr(content,'set_margin_'+side)(8)
            content.append(label);row.set_child(content);self.choices.append(row)
            if selected_id==library.identity:self.choices.select_row(row)
        self.update_select()

    def update_select(self):
        self.select_button.set_sensitive(not self.app.busy and self.choices.get_selected_row() is not None)

    def select_available(self):
        row=self.choices.get_selected_row()
        if row:self.select(row.library.identity,self.available_session)

    def select(self,identity,session):
        if self.closed or self.app.busy:return
        if (session!=self.app.core.device_session()
                or not any(library.identity==identity for library in self.available)):
            self.discovery_message.set_text('Selection is stale. Discover libraries again.');return
        self.generation+=1;generation=self.generation
        configured=self.app.preferences.game_library_location
        configured=dict(configured) if configured else None
        def finished(snapshot):
            if self.closed or generation!=self.generation:return
            if (session!=self.app.core.device_session()
                    or configured!=self.app.preferences.game_library_location):
                self.reset();return
            if snapshot.state!='succeeded' or snapshot.result.status!='valid':
                self.discovery_message.set_text('Library selection was not saved. '+(
                    snapshot.result.message if snapshot.state=='succeeded' else
                    'Validation cancelled.' if snapshot.state=='cancelled' else snapshot.error.message));return
            library=snapshot.result.libraries[0]
            if library.identity!=identity:
                self.discovery_message.set_text('Library identity changed. Discover libraries again.');return
            try:self.app.core.configure_game_library(identity.path,identity=identity,expected_session=session)
            except Exception as exc:
                self.discovery_message.set_text('Library selection was not saved. '+str(exc));return
            self.render(snapshot.result)
        self.app.run_file_job(lambda:self.app.core.load_managed_library(
            selection=identity,expected_session=session),finished,
            failed=lambda exc:self.discovery_message.set_text(str(exc)))

    def discover(self):
        self.load(discover=True)

    def load(self,discover=False):
        if self.closed or self.app.busy:return
        self.generation+=1;generation=self.generation
        session=self.app.core.device_session()
        configured=self.app.preferences.game_library_location
        configured=dict(configured) if configured else None
        def finished(snapshot):
            if self.closed or generation!=self.generation:return
            if session!=self.app.core.device_session() or configured!=self.app.preferences.game_library_location:
                self.reset();return
            if snapshot.state!='succeeded':
                message='Library loading cancelled.' if snapshot.state=='cancelled' else snapshot.error.message
                if discover:
                    self.available=();self.available_session=None;self.render_available()
                    self.discovery_message.set_text(message)
                else:self.render(LibraryState('unavailable',message))
                return
            result=snapshot.result
            if discover or configured is None:
                self.available=result.libraries;self.available_session=session
                self.discovery_message.set_text(result.message+' Choose a library and select it explicitly.'
                    if result.libraries else result.message)
                self.render_available()
                if configured:self.load()
            else:self.render(result)
        def failed(exc):
            if not self.closed and generation==self.generation:
                if discover:self.discovery_message.set_text(str(exc))
                else:self.render(LibraryState('unavailable',str(exc)))
        factory=(lambda:self.app.core.load_managed_library(discover=True)) if discover else self.app.core.load_managed_library
        self.app.run_file_job(factory,finished,failed=failed)

    def forget(self):
        if self.closed or self.chooser or self.confirmation or self.forget_confirmation:return
        if self.app.busy:
            self.message.set_text('Another operation is in progress. Wait before forgetting the library.')
            return
        configured=self.app.preferences.game_library_location
        configured=dict(configured) if configured else None
        selected=(self.state.libraries[0].identity.preference()
                  if self.state.status=='valid' else configured)
        if selected is None:return
        generation=self.generation;state=self.state;session=self.app.core.device_session()
        dialog=Gtk.Dialog(title='Forget Library',transient_for=self.parent_window(),modal=True)
        self.forget_confirmation=dialog
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
        dialog.add_button('Forget Library',Gtk.ResponseType.OK)
        dialog.get_content_area().append(Gtk.Label(label=(
            f"Device: {selected['device_id']}\nLibrary: {selected['path']}\n"
            f"Library ID: {selected['library_id'] or 'Not yet verified'}\n\n"
            'Forget this library on this computer? This does not delete files. '
            'Its manifest, games, metadata and artwork stay on the device. '
            'You can find it again with Discover Libraries in Settings.'),
            wrap=True,xalign=0,selectable=True,margin_top=12,margin_bottom=12,margin_start=12,margin_end=12))
        def answered(widget,response):
            self.forget_confirmation=None;widget.destroy()
            if response!=Gtk.ResponseType.OK or self.closed:return
            if self.app.busy:
                self.message.set_text('Another operation is in progress. Library was not forgotten.')
                return
            if (generation!=self.generation or state!=self.state
                    or session!=self.app.core.device_session()
                    or configured!=self.app.preferences.game_library_location):
                self.message.set_text('Library selection or connection changed. Review Forget Library again.')
                return
            try:self.app.core.configure_game_library('',expected_session=session)
            except Exception as exc:
                self.message.set_text(str(exc));return
            # Invalidate pending loads even when discovery never saved a preference.
            self.reset()
        dialog.connect('response',answered);dialog.present()

    def choose_creation(self):
        if self.closed or self.app.busy or self.chooser or self.confirmation or self.forget_confirmation:return
        from .file_picker import FilePicker
        from .picker_model import PickerMode, PickerFilter
        def chosen(selections):
            self.chooser=None
            if not selections or self.closed:return
            try:
                if len(selections)!=1:raise ValueError('Choose one storage root.')
                target=self.app.core.prepare_library_creation(selections[0])
            except Exception as exc:
                self.message.set_text(str(exc));return
            dialog=Gtk.Dialog(title='Create empty Argonaut Library',transient_for=self.parent_window(),modal=True)
            self.confirmation=dialog
            dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
            dialog.add_button('Create Library',Gtk.ResponseType.OK)
            dialog.get_content_area().append(Gtk.Label(label=(
                f'Device: {target.device_id}\nStorage root: {target.root}\nDestination: {target.path}\n\n'
                'Create a new empty library here. Existing destinations are refused. '
                'No games will be imported. Interrupted creation may require recovery at this location.'),
                wrap=True,xalign=0,selectable=True,margin_top=12,margin_bottom=12,margin_start=12,margin_end=12))
            def answered(widget,response):
                self.confirmation=None;widget.destroy()
                if response!=Gtk.ResponseType.OK:
                    self.app.core.discard_library_creation(target.token);return
                def done(snapshot):
                    if self.closed:return
                    if snapshot.state=='succeeded':
                        session=self.app.core.device_session()
                        if (session.device_id,session.session_id)==(target.device_id,target.session_id):
                            self.render(snapshot.result)
                        else:self.reset()
                    else:
                        result=getattr(snapshot,'result',None)
                        self.render(LibraryState('unavailable',getattr(result,'message',None) or
                            ('Creation cancelled before publication.' if snapshot.state=='cancelled' else snapshot.error.message)))
                def failed(exc):
                    self.app.core.discard_library_creation(target.token)
                    if not self.closed:self.render(LibraryState('unavailable',str(exc)))
                self.app.run_file_job(lambda:self.app.core.create_managed_library(target),done,failed=failed)
            dialog.connect('response',answered);dialog.present()
        self.chooser=FilePicker(self.app,chosen,mode=PickerMode.OPEN_FOLDER,scopes=('c64u',),
            filter=PickerFilter('library-root','Choose a USB or SD storage root',()))

        self.chooser.dialog.set_transient_for(self.parent_window())

    def close(self):
        self.closed=True;self.generation+=1;self.unsubscribe()
        self.detach_settings()
