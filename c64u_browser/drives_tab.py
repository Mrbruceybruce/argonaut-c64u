# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Drive presentation uses the active shared client; no transport URLs here."""
import posixpath
from gi.repository import Gtk
from .api import BrowserError
from .disk_run import validate_path
from .file_picker import FilePicker
from .picker_model import PickerMode, DRIVES
from .drives_selection import remote_selection, validate_selection


class DrivesTab:
    def __init__(self, app):
        self.app=app;self.client=None;self.loaded=False;self.cards={};self.chooser=None;self.setting_path=False
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        toolbar=Gtk.Box(spacing=8);self.box.append(toolbar)
        app.button(toolbar,'Refresh drives',self.refresh)
        self.message=Gtk.Label(label='Connect to a C64 Ultimate to view drives.',xalign=0,wrap=True)
        self.box.append(self.message)
        scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True);self.box.append(scroll)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);scroll.set_child(content)
        for drive in ('a','b'):
            frame=Gtk.Frame(label='Drive '+drive.upper());content.append(frame)
            card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
            for side in ('top','bottom','start','end'):getattr(card,'set_margin_'+side)(12)
            frame.set_child(card)
            status=Gtk.Label(label='Not loaded',xalign=0,wrap=True,selectable=True);card.append(status)
            controls=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);card.append(controls)
            row=Gtk.Box(spacing=8);controls.append(row)
            for label,action in (('Turn on…','on'),('Turn off…','off'),('Reset…','reset'),('Eject…','remove')):
                app.button(row,label,lambda d=drive,a=action:self.action(d,a))
            mode=Gtk.DropDown.new_from_strings(['1541','1571','1581']);row.append(mode)
            app.button(row,'Change drive type…',lambda d=drive:self.change_type(d))
            path=Gtk.Entry(placeholder_text='Image path on the C64U, e.g. /USB2/Games/game.d64',hexpand=True)
            controls.append(path)
            row=Gtk.Box(spacing=8);controls.append(row)
            app.button(row,'Select Disk Image…',lambda d=drive:self.choose_image(d))
            access=Gtk.DropDown.new_from_strings(['Write-protected','Read/write image','Changes in memory only'])
            row.append(access)
            app.button(row,'Mount…',lambda d=drive:self.mount(d))
            if drive=='a':
                run=app.button(row,'Mount & Run…',self.mount_run)
                run.set_tooltip_text('Run a temporary D64 copy on Drive A. Requires network DMA service; original image is unchanged.')
            controls.append(Gtk.Label(label='Select an existing C64U image or enter its USB/SD path. This selector does not upload local files.',xalign=0,wrap=True))
            self.cards[drive]={'status':status,'controls':controls,'path':path,'access':access,'type':mode,'selection':None}
            path.connect('changed',lambda _,d=drive:self.path_changed(d))
        self.bind(None)

    def bind(self, client):
        self.client=client;self.loaded=False
        for card in self.cards.values():
            card['status'].set_text('Not loaded' if client else 'Disconnected')
            card['selection']=None
            card['controls'].set_sensitive(False);card['path'].set_text('');card['access'].set_selected(0)
        self.message.set_text('Refresh drives to read their status.' if client else 'Connect to a C64 Ultimate to view drives.')

    def load_if_needed(self):
        if self.client and not self.loaded:self.refresh()

    def request(self, task, success, action=False):
        if not self.client or self.app.busy:return
        client=self.client
        def caught():
            try:return task()
            except Exception as exc:return exc
        def done(result):
            if self.client is not client:return
            if isinstance(result,Exception):
                self.loaded=False
                for card in self.cards.values():
                    card['controls'].set_sensitive(False);card['status'].set_text('Status unavailable — refresh to retry')
                self.message.set_text(('Action could not be verified; drive state may have changed. ' if action else '')+str(result))
                return
            self.show(result);self.message.set_text(success)
        self.app.run(caught,done)

    def refresh(self):
        if self.client:self.request(self.client.read_drives,'Drive status refreshed from the active C64U.')

    def show(self, drives):
        self.loaded=True
        for drive,card in self.cards.items():
            info=drives.get(drive)
            card['controls'].set_sensitive(info is not None)
            if info is None:
                card['status'].set_text('Not reported by this device');continue
            image=posixpath.join(info.get('image_path',''),info.get('image_file','')) if info.get('image_file') else 'No disk mounted'
            card['status'].set_text(f"{'On' if info['enabled'] else 'Off'} · Device {info.get('bus_id','?')} · Type {info.get('type','?')} · ROM {info.get('rom','?')}\n{image}")
            if info.get('type') in ('1541','1571','1581'):
                card['type'].set_selected(('1541','1571','1581').index(info['type']))

    def confirm(self, drive, title, detail, operation, success='Command completed; drive status refreshed.', *, selection=None):
        if not self.client or not self.loaded or self.app.busy:return
        client=self.client
        if selection is not None:
            try:validate_selection(selection,self.app.core.device_session())
            except Exception as exc:self.message.set_text(str(exc));return
        dialog=Gtk.Dialog(title=title,transient_for=self.app.window,modal=True)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL);dialog.add_button(title,Gtk.ResponseType.OK)
        dialog.get_content_area().append(Gtk.Label(label=f'Drive {drive.upper()} on {client.host}\n\n{detail}',wrap=True,xalign=0))
        def response(_,code):
            dialog.destroy()
            if code!=Gtk.ResponseType.OK or self.client is not client:return
            if selection is not None:
                try:validate_selection(selection,self.app.core.device_session())
                except Exception as exc:self.message.set_text(str(exc));return
            def task():
                if selection is not None:return operation(client)
                operation(client)
                return client.read_drives()
            self.request(task,success,action=True)
        dialog.connect('response',response);dialog.present()
        return dialog

    def action(self, drive, action):
        descriptions={
            'on':('Turn on','Turn this drive on? If already on, it will reset.'),
            'off':('Turn off','Turn this drive off? It will no longer respond on the serial bus.'),
            'reset':('Reset drive','Reset this drive? Any current drive operation will be interrupted.'),
            'remove':('Eject disk','Remove the mounted disk? Finish any disk activity first.'),
        }
        title,detail=descriptions[action]
        return self.confirm(drive,title,detail,lambda client:client.drive_action(drive,action))

    def path_changed(self, drive):
        if self.setting_path:return
        card=self.cards[drive];card['selection']=None
        try:
            card['selection']=remote_selection(card['path'].get_text(),self.app.core.device_session())
        except BrowserError:pass
        except ValueError:pass

    def choose_image(self, drive):
        if self.chooser or not self.client or self.app.busy:return
        def chosen(results):
            self.chooser=None
            if not results:return
            try:
                if len(results)!=1:raise BrowserError('Choose one disk image.')
                self.select_image(results[0],drive)
            except Exception as exc:self.message.set_text(str(exc))
        self.chooser=FilePicker(self.app,chosen,mode=PickerMode.OPEN_FILE,
                                scopes=('c64u',),filter=DRIVES,limit=1)

    def select_image(self, selection, drive='a'):
        """Picker and Files shortcuts share this validated, nonexecuting boundary."""
        if drive not in self.cards:raise BrowserError('Choose Drive A or Drive B.')
        validate_selection(selection,self.app.core.device_session())
        card=self.cards[drive]
        self.setting_path=True
        try:card['path'].set_text(selection.path)
        finally:self.setting_path=False
        card['selection']=selection
        self.message.set_text(f'{selection.path} is selected for Drive {drive.upper()}. '
                              'Choose the access mode, then choose Mount… to review and confirm.')
        card['path'].grab_focus()

    def selected_image(self, drive):
        card=self.cards[drive];selection=card['selection']
        validate_selection(selection,self.app.core.device_session())
        if card['path'].get_text()!=selection.path:
            raise BrowserError('Image path changed. Select the disk image again.')
        return selection

    def mount(self, drive):
        try:selection=self.selected_image(drive)
        except Exception as exc:self.message.set_text(str(exc));return
        card=self.cards[drive];path=selection.path
        mode=('readonly','readwrite','unlinked')[card['access'].get_selected()]
        label=('write-protected','read/write image','changes in memory only')[card['access'].get_selected()]
        if not path:
            self.message.set_text('Choose a C64U disk image first.');return
        return self.confirm(drive,'Mount disk',f'Mount {path}\nMode: {label}\nThis replaces any disk currently mounted.',lambda _:self.app.core.execute_drive_image(selection,drive,mode),selection=selection)

    def change_type(self, drive):
        mode=('1541','1571','1581')[self.cards[drive]['type'].get_selected()]
        return self.confirm(drive,'Change drive type',f'Switch to {mode}? This also loads its configured ROM, replacing any temporary ROM.',lambda client:client.set_drive_type(drive,mode))

    def mount_run(self):
        try:
            selection=self.selected_image('a');path=selection.path
            validate_path(path)
        except (BrowserError,ValueError) as exc:
            self.message.set_text(str(exc));return
        return self.confirm('a','Mount & Run',
            f'Run {path} on Drive A?\n\nThis interrupts the current C64 program and replaces the mounted disk with a temporary copy. Changes are not saved to the original image; the selected mount write mode does not apply.\n\nRequires network DMA service on the C64U.',
            lambda _:self.app.core.execute_drive_image(selection,'a',run=True),
            'Mount & Run command sent. Check the C64U screen to confirm the program started; disk changes use a temporary copy.',selection=selection)
