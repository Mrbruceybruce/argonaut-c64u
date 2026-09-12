import sys
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Connection UI delegates transport, discovery and persistence to shared components."""
from .storage import initial_directory
from dataclasses import replace
from gi.repository import Gtk, GLib
from .api import BrowserError, ConnectionFailure
from .profiles import Profile
from .discovery import standard_scan, subnet_scan, local_networks, preferred_subnet

class ConnectionDialog:
    def __init__(self, app):
        self.app = app
        self.current_id = None
        self.window = Gtk.Window(title='Argonaut — Connections', transient_for=app.window, modal=True)
        self.window.set_default_size(680, 650)
        self.window.connect('close-request', lambda *_: app.busy)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ('top','bottom','start','end'): getattr(outer,'set_margin_'+side)(16)
        page_scroll=Gtk.ScrolledWindow();page_scroll.set_child(outer)
        self.window.set_child(page_scroll)
        self.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); outer.append(self.controls)
        self.saved = Gtk.ComboBoxText()
        self.saved.connect('changed', self.selected)
        row = Gtk.Box(spacing=8); self.controls.append(row); row.append(self.saved)
        app.button(row,'New profile',self.new)
        app.button(row,'Save profile',self.save)
        app.button(row,'Delete profile',self.delete)
        self.controls.append(Gtk.Label(label='Discovered devices — password-protected candidates require identification',xalign=0,wrap=True))
        self.devices = Gtk.ListBox(); self.devices.connect('row-selected',self.discovered)
        scroll = Gtk.ScrolledWindow(min_content_height=110); scroll.set_child(self.devices); self.controls.append(scroll)
        row = Gtk.Box(spacing=8); self.controls.append(row)
        app.button(row,'Scan again',lambda: self.scan(False))
        self.subnet = Gtk.Entry(placeholder_text='Local subnet, e.g. 192.168.68.0/22',hexpand=True); row.append(self.subnet)
        app.button(row,'Scan subnet',lambda:self.scan(True))
        self.fields = {}
        for key,label,default in [('name','Profile name',''),('host','Hostname / IP',''),('http','REST port','80'),('ftp','FTP port','21')]:
            row = Gtk.Box(spacing=8); self.controls.append(row)
            row.append(Gtk.Label(label=label,width_chars=15,xalign=0))
            entry = Gtk.Entry(text=default,hexpand=True); row.append(entry); self.fields[key]=entry
        details=Gtk.Expander(label='Optional device details · saved on this computer')
        details_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);details.set_child(details_box)
        self.controls.append(details)
        for key,label in [('serial_number','Serial number'),('case_edition','Case edition'),('notes','Notes')]:
            row=Gtk.Box(spacing=8);details_box.append(row)
            row.append(Gtk.Label(label=label,width_chars=15,xalign=0))
            entry=Gtk.Entry(hexpand=True);row.append(entry);self.fields[key]=entry
        self.password = Gtk.PasswordEntry(show_peek_icon=True,placeholder_text='Network password (blank: use saved password)')
        self.controls.append(self.password)
        self.remember = Gtk.CheckButton(label='Store entered password in '+('Windows Credential Manager' if sys.platform=='win32' else 'macOS Keychain' if sys.platform=='darwin' else 'GNOME keyring'))
        if getattr(app.credentials,"session_only",False) is True:
            self.remember.set_label("Portable mode: passwords stay in this session only")
            self.remember.set_sensitive(False)
        self.controls.append(self.remember)
        self.auto = Gtk.CheckButton(label='Connect automatically at startup when this profile is selected')
        self.controls.append(self.auto)
        row = Gtk.Box(spacing=8); self.controls.append(row)
        app.button(row,'Test connection',self.test)
        app.button(row,'Connect',self.connect)
        app.button(row,'Forget saved password',self.forget)
        self.password.connect('activate',lambda *_:self.connect())
        self.status = Gtk.Label(label='Scan for devices or enter a hostname and ports manually.',wrap=True,xalign=0,selectable=True)
        outer.append(self.status)
        self.reload()
        self.window.present()

    def reload(self):
        self.saved.remove_all()
        for profile in self.app.preferences.profiles: self.saved.append(profile.id,profile.name)
        self.saved.set_active_id(self.app.preferences.selected_id or '')
        if self.saved.get_active_id() is None: self.new()

    def selected(self, combo):
        profile = next((p for p in self.app.preferences.profiles if p.id == combo.get_active_id()),None)
        if not profile: return
        self.current_id = profile.id
        for key,value in [('name',profile.name),('host',profile.host),('http',profile.http_port),('ftp',profile.ftp_port)]: self.fields[key].set_text(str(value))
        for key in ('serial_number','case_edition','notes'):self.fields[key].set_text(getattr(profile,key))
        self.auto.set_active(profile.auto_connect); self.password.set_text(''); self.remember.set_active(False)

    def new(self):
        self.current_id = None
        self.saved.set_active(-1)
        for key,value in [('name',''),('host',''),('http','80'),('ftp','21')]: self.fields[key].set_text(value)
        for key in ('serial_number','case_edition','notes'):self.fields[key].set_text('')
        self.auto.set_active(False); self.password.set_text(''); self.remember.set_active(False)

    def profile(self):
        try:
            p = Profile.new(self.fields['name'].get_text().strip() or self.fields['host'].get_text().strip(),
                            self.fields['host'].get_text().strip(),http_port=int(self.fields['http'].get_text()),
                            ftp_port=int(self.fields['ftp'].get_text()),auto_connect=self.auto.get_active(),
                            **{key:self.fields[key].get_text() for key in ('serial_number','case_edition','notes')})
            if self.current_id:
                p.id = self.current_id
                old=next((item for item in self.app.preferences.profiles if item.id==p.id),None)
                if old:p.device_id=old.device_id;p.device_mac=old.device_mac
            return p.validate()
        except (ValueError, BrowserError) as exc: raise BrowserError(str(exc)) from exc

    def submit(self, task, done):
        if self.app.busy: return
        self.controls.set_sensitive(False); self.status.set_text('Working…')
        def finish(result):
            self.controls.set_sensitive(True)
            if isinstance(result,Exception): self.status.set_text(str(result))
            else: done(result)
        def caught():
            try: return task()
            except Exception as exc: return exc
        self.app.run(caught,finish)

    def credential(self, profile, entered):
        if entered: return entered
        # Never reuse a profile credential if its destination has been edited.
        old = next((p for p in self.app.preferences.profiles if p.id == profile.id),None)
        if old and (old.host,old.http_port,old.ftp_port)==(profile.host,profile.http_port,profile.ftp_port):
            return self.app.session_passwords.get(profile.id) or self.app.credentials.get(profile.id)
        return ''

    def test(self):
        try: p = self.profile()
        except BrowserError as exc: self.status.set_text(str(exc)); return
        entered = self.password.get_text()
        def task():
            client = p.client(self.credential(p,entered))
            try: data = client.test_connection()
            except ConnectionFailure as exc: return f'{exc.kind.capitalize()} failure: {exc}'
            p.verify_identity(data)
            info = data['info']
            return f"Success · {info['product']} · Firmware {info['firmware_version']} · API {data['version']['version']} · Hostname {info.get('hostname','unavailable')} · ID {info.get('unique_id','unavailable')}"
        self.submit(task, self.status.set_text)

    def persist(self, p, entered, remember):
        prefs = self.app.preferences
        old = next((x for x in prefs.profiles if x.id == p.id),None)
        changed = old and (old.host,old.http_port,old.ftp_port)!=(p.host,p.http_port,p.ftp_port)
        # Give a changed destination a fresh credential identity; never forward old secrets.
        if changed: p = replace(p,id=Profile.new(p.name,p.host).id)
        if remember and entered: self.app.credentials.set(p.id,entered)
        before, selected = prefs.profiles, prefs.selected_id
        prefs.profiles = [p if x.id == (old.id if old else p.id) else x for x in before]
        if not old: prefs.profiles.append(p)
        prefs.selected_id = p.id
        try: prefs.save()
        except Exception:
            prefs.profiles, prefs.selected_id = before, selected
            raise
        if entered: self.app.session_passwords[p.id] = entered
        return p

    def save(self):
        try: p = self.profile()
        except BrowserError as exc: self.status.set_text(str(exc)); return
        entered, remember = self.password.get_text(), self.remember.get_active()
        def done(p):
            self.current_id=p.id; self.reload(); self.app.update_connection_header()
            password_note=('Password saved in the system credential store.' if remember else 'Entered password is available for this session only.') if entered else 'Saved password unchanged.'
            self.status.set_text('Profile saved. '+password_note)
        self.submit(lambda:self.persist(p,entered,remember),done)

    def connect(self):
        try: p = self.profile()
        except BrowserError as exc: self.status.set_text(str(exc)); return
        entered, remember = self.password.get_text(), self.remember.get_active()
        def task():
            client=p.client(self.credential(p,entered))
            info=client.test_connection()
            reported=p.verify_identity(info)
            return client,info,reported
        def done(result):
            client,info,reported=result
            def finish_connection():
                def finish_task():
                    # Recheck after review before accessing files or saving the identity.
                    current=client.test_connection()
                    candidate=replace(p,device_id=reported or p.device_id,device_mac=info.get('network_mac','') or p.device_mac)
                    candidate.verify_identity(current)
                    listing=initial_directory(client)
                    saved=self.persist(candidate,entered,remember)
                    return saved,client,current,listing
                def connected(result):
                    self.app.activate_connection(*result);self.window.destroy()
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

    def scan(self, fallback):
        subnet = self.subnet.get_text().strip()
        if fallback and not subnet:
            self.status.set_text('Enter one connected local subnet. At most 1024 addresses, eight probes at a time.'); return
        def task():
            if fallback: return subnet_scan(subnet), ['Controlled LAN scan complete.'], []
            candidates, notes = standard_scan()
            return candidates, notes, local_networks()
        def done(result):
            candidates,notes,networks=result
            if not self.subnet.get_text():
                hosts = [self.fields['host'].get_text().strip()] + [c.host for c in candidates]
                self.subnet.set_text(preferred_subnet(networks, hosts))
            while self.devices.get_first_child(): self.devices.remove(self.devices.get_first_child())
            for candidate in candidates:
                row=Gtk.ListBoxRow(); row.candidate=candidate
                name = candidate.info.get('info',candidate.info.get('ident',{})).get('hostname','Candidate')
                row.set_child(Gtk.Label(label=f'{name} · {candidate.host}:{candidate.port} · {candidate.status}\n{candidate.source}',xalign=0,wrap=True)); self.devices.append(row)
            self.status.set_text(' '.join(notes)+(' No verified devices found; manual connection and explicit subnet scanning remain available.' if not candidates else ' Select a device to fill its address.'))
        self.submit(task,done)

    def discovered(self, listing, row):
        if not row:return
        self.new(); c=row.candidate
        self.fields['host'].set_text(c.host); self.fields['http'].set_text(str(c.port))
        self.fields['name'].set_text(c.info.get('info',{}).get('hostname') or 'C64 Ultimate')

    def forget(self):
        if not self.current_id:return
        profile_id=self.current_id
        def task():
            self.app.credentials.delete(profile_id); self.app.session_passwords.pop(profile_id,None)
        self.submit(task,lambda _:self.status.set_text('Saved password removed. The current connection remains active until you disconnect.'))

    def delete(self):
        if not self.current_id:return
        profile_id=self.current_id
        def task():
            self.app.credentials.delete(profile_id)
            prefs=self.app.preferences
            before,selected=prefs.profiles,prefs.selected_id
            prefs.profiles=[p for p in before if p.id!=profile_id]
            if prefs.selected_id==profile_id:prefs.selected_id=None
            try:prefs.save()
            except Exception:
                prefs.profiles,prefs.selected_id=before,selected;raise
            self.app.session_passwords.pop(profile_id,None)
        def done(_):
            if self.app.active_profile and self.app.active_profile.id==profile_id:self.app.disconnect_device()
            self.reload();self.status.set_text('Profile deleted.');self.app.update_connection_header()
        self.submit(task,done)
