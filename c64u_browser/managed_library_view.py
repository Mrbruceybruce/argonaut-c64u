# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only managed-library presentation; legacy catalog remains untouched."""
from gi.repository import Gtk, GLib
from .managed_library import LibraryState


class ManagedLibraryView:
    def __init__(self,app):
        self.app=app;self.generation=0;self.closed=False;self.chooser=None;self.confirmation=None
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        for side in ('top','bottom','start','end'):getattr(self.box,'set_margin_'+side)(12)
        self.message=Gtk.Label(xalign=0,wrap=True,selectable=True);self.box.append(self.message)
        self.refresh_button=Gtk.Button(label='Load managed library')
        self.refresh_button.connect('clicked',lambda *_:self.load());self.box.append(self.refresh_button)
        self.create_button=Gtk.Button(label='Create Library')
        self.create_button.connect('clicked',lambda *_:self.choose_creation());self.box.append(self.create_button)
        self.choices=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);self.box.append(self.choices)
        scroll=Gtk.ScrolledWindow(vexpand=True)
        self.rows=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        scroll.set_child(self.rows);self.box.append(scroll)
        self.box.append(Gtk.Label(label='Empty libraries can be created explicitly. Import and migration are not available. '
            'Existing legacy catalog data is preserved separately.',xalign=0,wrap=True))
        self.unsubscribe=app.core.add_listener(lambda event:GLib.idle_add(self.event,event))
        self.reset()

    def event(self,event):
        if not self.closed and event.kind in ('connected','reconnected','disconnected','offline','library-location-changed'):
            self.reset()
        return False

    def reset(self):
        self.generation+=1
        configured=self.app.preferences.game_library_location
        self.render(LibraryState('unavailable' if configured else 'none',
            'Configured library is not loaded. Connect to its device and load it.' if configured
            else 'Game Library is not configured. Connect and load to check USB/SD library locations.'))

    @staticmethod
    def clear(box):
        while box.get_first_child():box.remove(box.get_first_child())

    def render(self,state):
        self.state=state;self.message.set_text(state.message)
        self.create_button.set_visible(state.status=='none' and self.app.preferences.game_library_location is None)
        self.clear(self.rows);self.clear(self.choices)
        if state.status=='valid':
            library=state.libraries[0]
            self.message.set_text(state.message+'\n'+library.identity.path+
                f' · revision {library.revision} · {len(library.games)} game(s)\n'
                f'Device: {library.identity.device_id} · Library ID: {library.identity.library_id}')
            for game in library.games:
                label=Gtk.Label(label=f'{game.title} · {game.format}\n{game.path}',
                    xalign=0,ellipsize=3,margin_top=5,margin_bottom=5)
                label.set_tooltip_text(game.path);self.rows.append(label)
        elif state.status=='multiple':
            session=self.app.core.device_session()
            for library in state.libraries:
                identity=library.identity
                button=Gtk.Button(label=identity.path+' · '+identity.library_id)
                button.connect('clicked',lambda _,i=identity,s=session:self.select(i,s))
                self.choices.append(button)

    def select(self,identity,session):
        try:self.app.core.configure_game_library(identity.path,identity=identity,expected_session=session)
        except Exception as exc:
            self.render(LibraryState('unavailable',str(exc)));return
        # Location event clears obsolete choices; loading remains an explicit action.
        self.reset()

    def load(self):
        self.generation+=1;generation=self.generation
        session=self.app.core.device_session()
        configured=self.app.preferences.game_library_location
        configured=dict(configured) if configured else None
        def finished(snapshot):
            if self.closed or generation!=self.generation:return
            if session!=self.app.core.device_session() or configured!=self.app.preferences.game_library_location:
                self.reset();return
            if snapshot.state=='succeeded':self.render(snapshot.result)
            else:self.render(LibraryState('unavailable',
                'Library loading cancelled.' if snapshot.state=='cancelled' else snapshot.error.message))
        def failed(exc):
            if not self.closed and generation==self.generation:
                self.render(LibraryState('unavailable',str(exc)))
        self.app.run_file_job(self.app.core.load_managed_library,finished,failed=failed)

    def choose_creation(self):
        if self.chooser or self.confirmation:return
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
            dialog=Gtk.Dialog(title='Create empty Argonaut Library',transient_for=self.app.window,modal=True)
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

    def close(self):
        self.closed=True;self.generation+=1;self.unsubscribe()
        if self.chooser:self.chooser.close_requested()
        if self.confirmation:self.confirmation.response(Gtk.ResponseType.CANCEL)
