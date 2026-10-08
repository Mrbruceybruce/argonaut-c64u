# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Connection UI delegates transport, discovery and persistence to shared components."""
from gi.repository import Gtk, GLib
from .api import BrowserError
from .core import CoreError
from .profiles import Profile
from .discovery import preferred_subnet, validate_subnet

class ConnectionDialog:
    def __init__(self, app, window=None):
        self.app = app
        self.current_id = None
        self._credential_state='UNKNOWN'
        self._credential_pending=False
        self._credential_generation=0
        self._closed=False
        self._networks=None
        self._scanning=False
        self._scan_generation=0
        self.window = window or Gtk.Window(title='Argonaut — Connections', transient_for=app.window, modal=True)
        if window is None:self.window.set_default_size(680,650)
        self.window.connect('close-request', self.close_requested)
        self.window.connect('unrealize', self.window_closed)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ('top','bottom','start','end'): getattr(outer,'set_margin_'+side)(16)
        page_scroll=Gtk.ScrolledWindow();page_scroll.set_overlay_scrolling(False);page_scroll.set_child(outer)
        self.page=page_scroll
        if window is None:self.window.set_child(page_scroll)
        self.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16); outer.append(self.controls)
        def section(title):
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
            heading=Gtk.Label(label=title,xalign=0);heading.add_css_class('heading')
            box.append(heading);self.controls.append(box)
            return box
        self.identity_section=section('Device identity and details')
        self.fields = {}
        for key,label,default in [('name','Connection name',''),('host','Hostname / IP',''),('http','REST port','80'),('ftp','FTP port','21')]:
            row = Gtk.Box(spacing=8); self.identity_section.append(row)
            row.append(Gtk.Label(label=label,width_chars=15,xalign=0))
            entry = Gtk.Entry(text=default,hexpand=True); row.append(entry); self.fields[key]=entry
        details_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        self.details_page=details_box
        self.device_identity=Gtk.Label(xalign=0,wrap=True,selectable=True)
        details_box.append(self.device_identity)
        self.details_profile=Gtk.Label(xalign=0,wrap=True);details_box.append(self.details_profile)
        for key,label in [('serial_number','Serial number'),('case_edition','Box model'),('notes','Notes')]:
            row=Gtk.Box(spacing=8);details_box.append(row)
            row.append(Gtk.Label(label=label,width_chars=15,xalign=0))
            entry=Gtk.Entry(hexpand=True);row.append(entry);self.fields[key]=entry
        self.fields['case_edition'].set_placeholder_text('Model checked on the shipping box')
        self.fields['case_edition'].set_tooltip_text('Enter the model checked on the shipping box. Saved with this profile; does not change the C64U hardware model.')
        details_box.append(Gtk.Label(label='Box model is your shipping-box label. C64U Model is read-only firmware information and may differ from the box label.',xalign=0,wrap=True))
        self.model=Gtk.Entry(editable=False,hexpand=True)
        modelrow=Gtk.Box(spacing=8);modelrow.append(Gtk.Label(label='C64U Model',width_chars=15,xalign=0));modelrow.append(self.model);details_box.append(modelrow)
        modelrow=Gtk.Box(spacing=8);details_box.append(modelrow)
        app.button(modelrow,'Read model from C64U',self.read_model)
        self.details_status=Gtk.Label(xalign=0,wrap=True);details_box.append(self.details_status)
        self.fields['name'].connect('changed',lambda *_:self.details_profile.set_text('Connection: '+(self.fields['name'].get_text() or 'New connection')))
        self.fields['host'].connect('changed',lambda *_:self.model.set_text('Not read'))
        self.identity_section.append(details_box)
        self.credentials_section=section('Credentials')
        row=Gtk.Box(spacing=8);self.credentials_section.append(row)
        row.append(Gtk.Label(label='Password',width_chars=15,xalign=0))
        self.password=Gtk.PasswordEntry(show_peek_icon=True,hexpand=True,placeholder_text='Network password')
        row.append(self.password)
        self.credential_status=Gtk.Label(xalign=0,wrap=True);self.credentials_section.append(self.credential_status)
        row=Gtk.Box(spacing=8);self.credentials_section.append(row)
        self.remember=Gtk.CheckButton(label='Remember password');row.append(self.remember)
        self.forget_button=app.button(row,'Forget Password',self.forget)
        self.retry_credential_button=app.button(row,'Retry credential check',self.refresh_credential_state)
        self.retry_credential_button.set_visible(False)
        if app.core.credentials_session_only:
            self.remember.set_visible(False);self.remember.set_sensitive(False)
            self.forget_button.set_visible(False);self.forget_button.set_sensitive(False)
        self.password.connect('changed',lambda *_:self.paint_credential_state())
        for key in ('host','http','ftp'):
            self.fields[key].connect('changed',lambda *_:self.refresh_credential_state())
        self.status = Gtk.Label(label='Discover network connections or enter a hostname and ports manually.',wrap=True,xalign=0,selectable=True)
        self.controls.append(self.status)
        self.discovery_section=section('Network Discovery')
        row=Gtk.Box(spacing=8);self.discovery_section.append(row)
        app.button(row,'Discover',lambda:self.scan(False))
        row=Gtk.Box(spacing=8);self.discovery_section.append(row)
        row.append(Gtk.Label(label='Subnet',xalign=0))
        self.subnet=Gtk.Entry(placeholder_text='192.168.68.0/24',hexpand=True);row.append(self.subnet)
        self.scan_subnet_button=app.button(row,'Scan Subnet',lambda:self.scan(True))
        self.scan_subnet_button.set_sensitive(False)
        self.subnet_validation=Gtk.Label(xalign=0,wrap=True);self.discovery_section.append(self.subnet_validation)
        self.subnet.connect('changed',self.validate_subnet_field)
        self.scan_progress=Gtk.ProgressBar(show_text=True);self.scan_progress.set_visible(False)
        self.discovery_section.append(self.scan_progress)
        self.devices=Gtk.ListBox();self.devices.connect('row-selected',self.discovered)
        scroll=Gtk.ScrolledWindow(min_content_height=110);scroll.set_child(self.devices);self.discovery_section.append(scroll)
        self._candidate_rows={}
        self.controls.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self.profiles_section=section('Saved Network Connections')
        self.profiles_section.append(Gtk.Label(label='Ethernet and Wi-Fi are separate connections, even for the same C64 Ultimate.',xalign=0,wrap=True))
        self.saved = Gtk.ComboBoxText(hexpand=True)
        self.saved.connect('changed', self.selected)
        row = Gtk.Box(spacing=8); self.profiles_section.append(row)
        label=Gtk.Label(label='Connection',width_chars=15,xalign=0)
        label.set_mnemonic_widget(self.saved);row.append(label);row.append(self.saved)
        self.selection_status=Gtk.Label(xalign=0,wrap=True)
        self.profiles_section.append(self.selection_status)
        self.profile_actions=Gtk.Box(spacing=8);self.profiles_section.append(self.profile_actions)
        app.button(self.profile_actions,'New',self.new)
        app.button(self.profile_actions,'Save Profile',self.save)
        app.button(self.profile_actions,'Delete Profile',self.delete)
        self.auto = Gtk.CheckButton(label='Connect automatically at startup when this connection is selected')
        self.auto.set_halign(Gtk.Align.START)
        self.profiles_section.append(self.auto)
        self.connection_actions=Gtk.Box(spacing=8,halign=Gtk.Align.END)
        self.controls.append(self.connection_actions)
        app.button(self.connection_actions,'Test',self.test)
        app.button(self.connection_actions,'Connect',self.connect)
        # Keep Enter in Password mapped to Connect; no persistence action is default.
        self.password.connect('activate',lambda *_:self.connect())
        self.reload()
        self._background(self.app.core.discovery_networks,self.networks_loaded)
        if window is None:self.window.present()

    def close_requested(self, *_):
        # Preferences may veto closing to offer Save / Discard / Keep editing.
        return self.app.busy

    def window_closed(self, *_):
        self._closed=True
        self._credential_generation+=1

    def _background(self, task, done):
        # Auxiliary metadata work must not block GTK or claim the connection busy state.
        try:future=self.app.pool.submit(task)
        except RuntimeError:
            done(BrowserError('Could not check local state. Close and reopen Argonaut.'));return
        def finish():
            if self._closed:return False
            try:value=future.result()
            except Exception as exc:value=exc
            done(value)
            return False
        future.add_done_callback(lambda _:GLib.idle_add(finish))

    def paint_credential_state(self):
        saved=self._credential_state == 'PRESENT' and not self.password.get_text()
        self.password.set_property('placeholder-text','••••••••' if saved else 'Network password')
        if self.app.core.credentials_session_only:
            self.credential_status.set_text(self.app.core.credential_mode+' mode — passwords are session-only.')
        elif self._credential_state == 'UNKNOWN':
            self.credential_status.set_text('Checking saved-password status…' if self._credential_pending else
                'Unable to determine saved-password status. Retry credential check before saving this profile.')
        else:
            self.credential_status.set_text('Saved password available' if saved else
                'Entered password overrides saved/session password.' if self.password.get_text() else '')

    def refresh_credential_state(self):
        self._credential_pending=not self.app.core.credentials_session_only
        self._credential_generation+=1
        generation=self._credential_generation
        self._credential_state='UNKNOWN'
        self.remember.set_inconsistent(not self.app.core.credentials_session_only)
        self.remember.set_sensitive(False)
        self.forget_button.set_sensitive(False)
        self.retry_credential_button.set_visible(False)
        self.paint_credential_state()
        if self.app.core.credentials_session_only:return
        def begin():
            if self._closed or generation != self._credential_generation:return False
            try:profile=self.profile()
            except BrowserError:
                self._credential_pending=False
                self.retry_credential_button.set_visible(True)
                self.paint_credential_state()
                return False
            def done(value):
                if generation != self._credential_generation:return
                self._credential_pending=False
                self.forget_button.set_sensitive(bool(self.current_id))
                if type(value) is not bool:
                    self.retry_credential_button.set_visible(True)
                    self.paint_credential_state()
                    return
                self._credential_state='PRESENT' if value else 'ABSENT'
                self.remember.set_inconsistent(False)
                self.remember.set_sensitive(True)
                self.remember.set_active(value)
                self.paint_credential_state()
                # Async initial indication is baseline state, not an unsaved user edit.
                self._saved_fields=(*self._saved_fields[:-1],self.remember.get_active())
            self._background(lambda:self.app.core.has_saved_credential(profile),done)
            return False
        GLib.timeout_add(150,begin)

    def networks_loaded(self, value):
        if isinstance(value,Exception):
            self._networks=()
            self.subnet_validation.set_text(str(value))
            self.scan_subnet_button.set_sensitive(False)
            return
        self._networks=tuple(value)
        if not self.subnet.get_text():
            self.subnet.set_text(preferred_subnet(self._networks,[self.fields['host'].get_text().strip()]))
        self.validate_subnet_field()

    def validate_subnet_field(self, *_):
        try:
            if self._networks is None:raise ValueError('Reading local IPv4 networks…')
            network=validate_subnet(self.subnet.get_text().strip(),self._networks)
        except ValueError as exc:
            self.scan_subnet_button.set_sensitive(False)
            self.subnet_validation.set_text(str(exc))
            return None
        self.scan_subnet_button.set_sensitive(not self._scanning)
        self.subnet_validation.set_text(str(network)+' · '+str(len(tuple(network.hosts())))+' addresses to probe')
        return str(network)

    def read_model(self):
        try:p=self.profile()
        except BrowserError as exc:self.status.set_text(str(exc));return
        entered=self.password.get_text()
        def done(value):self.model.set_text(value);self.status.set_text('Model is read-only and reported by this C64U.')
        self.submit(lambda:self.app.core.read_model(p,entered),done)

    def reload(self):
        self.saved.remove_all()
        for profile in self.app.core.profiles(): self.saved.append(profile.id,profile.name)
        selected=self.app.core.selected_profile()
        self.saved.set_active_id(selected.id if selected else '')
        if self.saved.get_active_id() is None: self.new()

    def selected(self, combo):
        profile = next((p for p in self.app.core.profiles() if p.id == combo.get_active_id()),None)
        if not profile: return
        self.current_id = profile.id
        self.selection_status.set_text('Editing saved connection: '+profile.name)
        self.device_identity.set_text('Saved device ID: '+(profile.device_id or 'Not bound'))
        for key,value in [('name',profile.name),('host',profile.host),('http',profile.http_port),('ftp',profile.ftp_port)]: self.fields[key].set_text(str(value))
        for key in ('serial_number','case_edition','notes'):self.fields[key].set_text(getattr(profile,key))
        self.model.set_text('Not read')
        self.auto.set_active(profile.auto_connect); self.password.set_text(''); self.remember.set_active(False)
        self.mark_clean()
        self.refresh_credential_state()

    def new(self):
        self.current_id = None
        self.selection_status.set_text('New connection — not saved')
        self.device_identity.set_text('Saved device ID: Not bound')
        self.saved.set_active(-1)
        for key,value in [('name',''),('host',''),('http','80'),('ftp','21')]: self.fields[key].set_text(value)
        for key in ('serial_number','case_edition','notes'):self.fields[key].set_text('')
        self.model.set_text('Not read')
        self.auto.set_active(False); self.password.set_text(''); self.remember.set_active(False)
        self.mark_clean()
        self.refresh_credential_state()

    def snapshot(self):
        return (tuple((key,field.get_text()) for key,field in self.fields.items()),
                self.auto.get_active(),self.password.get_text(),self.remember.get_active())

    def mark_clean(self):
        self._saved_fields=self.snapshot()

    def dirty(self):
        return self.snapshot()!=self._saved_fields

    def profile(self):
        try:
            p = Profile.new(self.fields['name'].get_text().strip() or self.fields['host'].get_text().strip(),
                            self.fields['host'].get_text().strip(),http_port=int(self.fields['http'].get_text()),
                            ftp_port=int(self.fields['ftp'].get_text()),auto_connect=self.auto.get_active(),
                            **{key:self.fields[key].get_text() for key in ('serial_number','case_edition','notes')})
            if self.current_id:
                p.id = self.current_id
                old=next((item for item in self.app.core.profiles() if item.id==p.id),None)
                if old:p.device_id=old.device_id;p.device_mac=old.device_mac
            return p.validate()
        except (ValueError, BrowserError) as exc: raise BrowserError(str(exc)) from exc

    def submit(self, task, done):
        if self.app.busy: return
        self.controls.set_sensitive(False); self.status.set_text('Working…')
        if hasattr(self,'window') and hasattr(self.window,'pages'):self.window.pages.set_sensitive(False)
        def finish(result):
            self.controls.set_sensitive(True)
            if hasattr(self,'window') and hasattr(self.window,'pages'):self.window.pages.set_sensitive(True)
            if getattr(self,'_scanning',False):
                self._scanning=False
                self.validate_subnet_field()
                if isinstance(result,Exception):self.scan_progress.set_text('Search failed')
            if isinstance(result,Exception):
                if isinstance(result,CoreError) and getattr(result,'saved_profile_id',None):
                    # The profile file succeeded but the independent native store failed.
                    # Keep the typed edit for retry and bind it to the already saved ID.
                    self.current_id=result.saved_profile_id
                    self.app.update_connection_header()
                self.status.set_text(str(result))
            else: done(result)
        def caught():
            try: return task()
            except Exception as exc: return exc
        self.app.run(caught,finish)


    def test(self):
        try: p = self.profile()
        except BrowserError as exc: self.status.set_text(str(exc)); return
        entered = self.password.get_text()
        def task():
            try:result=self.app.core.test_profile(p,entered)
            except CoreError as exc:
                code=getattr(exc,'code','connection')
                return f'{code.capitalize()} failure: {exc}'
            data=result.device_info;info=data['info']
            return f"Success · {info['product']} · Firmware {info['firmware_version']} · API {data['version']['version']} · Hostname {info.get('hostname','unavailable')} · ID {info.get('unique_id','unavailable')}"
        self.submit(task, self.status.set_text)

    def persist(self, p, entered, remember):
        return self.app.core.save_profile(p,entered,remember)

    def save(self, after=None):
        if self._credential_pending:
            self.status.set_text('Checking saved password state. Please try Save Profile again in a moment.');return
        if not self.app.core.credentials_session_only and self._credential_state == 'UNKNOWN':
            self.status.set_text('Unable to determine saved-password status. Retry credential check before saving this profile.');return
        try: p = self.profile()
        except BrowserError as exc: self.status.set_text(str(exc)); return
        entered, remember = self.password.get_text(), self.remember.get_active()
        def done(p):
            self.current_id=p.id; self.reload(); self.app.update_connection_header()
            password_note=(self.app.core.credential_mode+' mode — passwords are session-only.'
                if self.app.core.credentials_session_only else
                'Password saved in the system credential store (not authentication-tested).'
                if remember and entered else 'Saved password unchanged.' if remember else
                'Stored password removed. Session password may remain until Forget Password or exit.')
            self.status.set_text('Profile saved. '+password_note)
            if after:after()
        self.submit(lambda:self.persist(p,entered,remember),done)

    def connect(self):
        try: p = self.profile()
        except BrowserError as exc: self.status.set_text(str(exc)); return
        entered = self.password.get_text()
        def task():return self.app.core.test_profile(p,entered)
        def done(result):
            info=result.device_info;reported=result.reported_device_id
            def finish_connection():
                def finish_task():
                    folder=self.app.preferences.app_options['remote_folders'].get(p.id,'/USB2') if self.app.preferences.app_options['remember_folders'] else '/USB2'
                    return self.app.core.connect(p,entered_password=entered,
                        remember=False,bind_identity=True,persist=True,
                        remote_folder=folder)
                def connected(result):
                    self.app.activate_connection(result)
                    self.current_id=result.profile.id;self.reload()
                    if hasattr(self.window,'pages'):self.status.set_text('Connected · Authenticated. Connection profile updated; password storage unchanged.')
                    else:self.window.destroy()
                self.submit(finish_task,connected)
            if p.device_id or p.device_mac:finish_connection();return
            dialog=Gtk.Dialog(title='Confirm profile device',transient_for=self.window,modal=True)
            dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
            dialog.add_button('Connect to this device',Gtk.ResponseType.OK)
            details=info['info']
            label=Gtk.Label(label=f"Associate {p.name} with this C64U?\nAddress: {p.host}\nHostname: {details.get('hostname','Not reported')}\nFirmware: {details.get('firmware_version','Not reported')}\nDevice ID: {reported or 'Not reported'}\nNetwork MAC: {info.get('network_mac') or 'Not available'}\n\n"+('The device ID is preferred; the saved network MAC is a fallback when the ID is absent.' if reported else 'The network MAC will identify this connection. Ethernet and Wi-Fi need separate profiles.' if info.get('network_mac') else 'This device cannot be identified for automatic connection.'),wrap=True,xalign=0)
            dialog.get_content_area().append(label)
            def response(_,code):
                dialog.destroy()
                if code==Gtk.ResponseType.OK and not self.app.busy:finish_connection()
            dialog.connect('response',response);dialog.present()
        self.submit(task,done)

    def add_candidate(self, candidate):
        key=(candidate.host,candidate.port)
        row=self._candidate_rows.get(key)
        if row is None:
            row=Gtk.ListBoxRow();self._candidate_rows[key]=row;self.devices.append(row)
        row.candidate=candidate
        name=candidate.info.get('info',candidate.info.get('ident',{})).get('hostname','Candidate')
        row.set_child(Gtk.Label(label=f'{name} · {candidate.host}:{candidate.port} · {candidate.status}\n{candidate.source}',xalign=0,wrap=True))

    def scan(self, fallback):
        if self.app.busy:return
        subnet=self.validate_subnet_field() if fallback else ''
        if fallback and subnet is None:return
        if fallback:self.subnet.set_text(subnet)
        self._scanning=True
        self._scan_generation+=1
        generation=self._scan_generation
        self._candidate_rows={}
        while self.devices.get_first_child():self.devices.remove(self.devices.get_first_child())
        self.scan_progress.set_visible(True);self.scan_progress.set_fraction(0)
        self.scan_progress.set_text('Scanning '+subnet+'…' if fallback else 'Discovering network connections…')
        def deliver(callback,*args):
            def update():
                if not self._closed and generation == self._scan_generation and self._scanning:callback(*args)
                return False
            GLib.idle_add(update)
        def progress(completed,total):
            self.scan_progress.set_fraction(completed/total if total else 1)
            self.scan_progress.set_text(f'{completed}/{total} addresses checked · {completed*100//total if total else 100}%')
        if not fallback:
            def pulse():
                if self._closed or generation != self._scan_generation or not self._scanning:return False
                self.scan_progress.pulse();return True
            GLib.timeout_add(100,pulse)
        def task():
            callbacks={'progress':lambda n,total:deliver(progress,n,total),
                       'found':lambda candidate:deliver(self.add_candidate,candidate)} if fallback else {}
            return self.app.core.discover(subnet=subnet,**callbacks)
        def done(result):
            candidates,notes,networks=result
            if not fallback:
                self._networks=tuple(networks)
                if not self.subnet.get_text():
                    hosts=[self.fields['host'].get_text().strip()]+[c.host for c in candidates]
                    self.subnet.set_text(preferred_subnet(networks,hosts))
            for candidate in candidates:self.add_candidate(candidate)
            self.scan_progress.set_fraction(1)
            message=f'Search complete — {len(self._candidate_rows)} network connections found'
            self.scan_progress.set_text('100% · '+message if fallback else message)
            self.status.set_text(message+'. '+' '.join(notes))
            self.validate_subnet_field()
        self.submit(task,done)

    def discovered(self, listing, row):
        if not row:return
        self.new(); c=row.candidate
        self.selection_status.set_text('Discovered connection — not saved')
        self.fields['host'].set_text(c.host); self.fields['http'].set_text(str(c.port))
        self.fields['name'].set_text(c.info.get('info',{}).get('hostname') or 'C64 Ultimate')

    def forget(self):
        if not self.current_id:return
        profile_id=self.current_id
        def task():
            self.app.core.forget_credential(profile_id)
        def done(_):
            self._credential_generation+=1
            self._credential_state='ABSENT'
            self._credential_pending=False
            self.remember.set_inconsistent(False)
            self.remember.set_sensitive(not self.app.core.credentials_session_only)
            self.retry_credential_button.set_visible(False)
            self.password.set_text('');self.remember.set_active(False)
            self.paint_credential_state()
            self.status.set_text('Stored and session password removed. The current connection remains active until you disconnect.')
        self.submit(task,done)

    def delete(self):
        if not self.current_id:return
        profile_id=self.current_id
        def task():self.app.core.delete_profile(profile_id)
        def done(_):
            if self.app.active_profile and self.app.active_profile.id==profile_id:self.app.disconnect_device()
            self.reload();self.status.set_text('Profile deleted.');self.app.update_connection_header()
        self.submit(task,done)
