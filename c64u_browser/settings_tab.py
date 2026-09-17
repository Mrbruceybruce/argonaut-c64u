# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""GTK settings presentation; section labels are independent of REST identities."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from .configuration import Configuration, display
from .api import BrowserError
from .backup_dialog import BackupActions
from .flash_dialog import FlashFiles
from .config_history import history_path, save_before_apply, read_previous
from .dependencies import enabled, controls_dependencies, inactive_reason, NETWORK_CATEGORIES, STATIC_FIELDS
from .settings_sections import section_entries, section_for, visible_entries, subsection_for, display_name
from .settings_safety import warnings_for

class SettingsTab:
    def __init__(self, app):
        self.app=app
        self.client=None
        self.loaded=False
        self.category=None
        self.all_settings={}
        self.favorites=set(app.preferences.setting_favorites)
        self.pending={}
        self.requires_refresh=False
        self.drafts={}
        self.errors={}
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        toolbar=Gtk.Box(spacing=8);self.box.append(toolbar)
        app.button(toolbar,'Reload from C64U',self.reload)
        self.apply_button=app.button(toolbar,'Review & Apply…',self.apply)
        self.revert_button=app.button(toolbar,'Discard edits',self.revert)
        self.flash_button=app.button(toolbar,'Save to Flash…',self.save_to_flash)
        self.backups=BackupActions(self)
        backupbar=Gtk.Box(spacing=8);self.box.append(backupbar)
        app.button(backupbar,'Export backup…',lambda:self.backups.choose())
        app.button(backupbar,'Restore backup…',lambda:self.backups.choose(True))
        app.button(backupbar,'Flash files…',self.open_flash_files)
        app.button(backupbar,'Undo last apply…',self.undo_apply)
        self.search=Gtk.SearchEntry(placeholder_text='Search settings…',hexpand=True)
        self.search.connect('search-changed',lambda *_: self.render())
        filters=Gtk.Box(spacing=8);self.box.append(filters)
        filters.append(self.search)
        self.favorite_filter=Gtk.CheckButton(label='Favorites')
        self.favorite_filter.connect('toggled',lambda *_: self.render())
        filters.append(self.favorite_filter)
        self.box.append(Gtk.Label(label='Changes are staged until you apply them. Save to Flash keeps the running configuration after power off. Changing LED Mode or enabling DHCP discards edits to fields that become inactive.',wrap=True,xalign=0))
        self.pending_summary=Gtk.Label(xalign=0,wrap=True)
        self.box.append(self.pending_summary)
        panes=Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL,vexpand=True);panes.set_position(270);self.box.append(panes)
        self.categories=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.categories.connect('row-selected',self.selected)
        scroll=Gtk.ScrolledWindow(min_content_width=220);scroll.set_child(self.categories);panes.set_start_child(scroll)
        right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);panes.set_end_child(right)
        self.heading=Gtk.Label(label='Connect to a C64 Ultimate to browse settings.',xalign=0,wrap=True);right.append(self.heading)
        self.rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True);scroll.set_child(self.rows);right.append(scroll);self.settings_scroll=scroll

    def undo_apply(self):
        if not self.client or self.app.busy:return
        if self.pending or self.drafts:
            self.app.status.set_text('Apply or discard edits before reviewing an undo.');return
        client=self.client
        try:path=history_path(self.app.preferences,self.app.active_profile,client)
        except BrowserError as exc:self.app.status.set_text(str(exc));return
        def task():
            data=read_previous(path)
            model=Configuration(client)
            return data,model.all_settings(model.categories())
        self.request(task,lambda result:self.backups.preview(*result,title='Undo last apply preview'),writing=True)

    def open_flash_files(self):
        if not self.client or self.app.busy:return
        if self.pending or self.drafts:
            self.app.status.set_text('Apply or discard edits before opening Flash files.');return
        self.flash_files=FlashFiles(self)

    @staticmethod
    def clear(box):
        while box.get_first_child():box.remove(box.get_first_child())

    def bind(self, client):
        self.requires_refresh=False
        self.rows.set_sensitive(True)
        self.client=client;self.loaded=False;self.category=None;self.all_settings={};self.favorites=set(self.app.preferences.setting_favorites)
        self.clear(self.categories);self.clear(self.rows)
        self.search.set_text('');self.favorite_filter.set_active(False)
        self.pending={};self.drafts={};self.errors={};self.update_edit_buttons()
        self.heading.set_text('Choose Reload from C64U to browse settings.' if client else 'Connect to a C64 Ultimate to browse settings.')

    def load_if_needed(self):
        if self.client and not self.loaded:self.reload()

    def reload(self):
        if not self.client:
            self.heading.set_text('Connect to a C64 Ultimate to browse settings.');return
        if self.app.busy:return
        if self.pending or self.drafts:
            self.app.status.set_text('Apply or discard your edits before reloading. Your edits are still here.');return
        client=self.client;previous=self.category
        self.clear(self.rows);self.heading.set_text('Reading configuration categories…')
        def task():
            model=Configuration(client);categories=model.categories()
            return model.all_settings(categories)
        def done(result):
            if self.client is not client:return
            all_settings=result
            sections=section_entries(all_settings)
            selected=previous if previous in sections else next(iter(sections),None)
            self.clear(self.categories)
            for name, entries in sections.items():
                row=Gtk.ListBoxRow();row.category=name
                label=Gtk.Label(label=f'{name} ({len(entries)})',xalign=0,wrap=True)
                label.set_margin_top(8);label.set_margin_bottom(8);row.set_child(label)
                self.categories.append(row)
            self.loaded=True;self.category=selected
            self.requires_refresh=False
            self.rows.set_sensitive(True)
            self.all_settings=all_settings
            row=self.categories.get_first_child()
            while row:
                if getattr(row, 'category', None)==selected:self.categories.select_row(row);break
                row=row.get_next_sibling()
            self.render()
            self.app.status.set_text(f'Read {sum(map(len,all_settings.values()))} settings in {len(sections)} sections from the active device.')
        self.request(task,done)

    def request(self, task, done, writing=False):
        client=self.client
        def caught():
            try:return task()
            except Exception as exc:return exc
        def finish(result):
            if self.client is not client:return
            if isinstance(result,Exception):
                if not writing:
                    self.clear(self.rows);self.heading.set_text('Could not read settings. Use Reload from C64U to retry.')
                self.app.status.set_text(('Operation could not be verified; device values may have changed. Edits are retained. ' if writing else '')+str(result))
            else:done(result)
        self.app.run(caught,finish)

    def selected(self, listing, row):
        if row is None or row.category==self.category or self.app.busy:return
        self.category=row.category
        # Section browsing uses the loaded snapshot; section names are never API paths.
        self.render()

    def render(self):
        if not self.loaded:
            return
        query=self.search.get_text().casefold().strip()
        only_favorites=self.favorite_filter.get_active()
        matches=visible_entries(self.all_settings,self.category,query,
                                self.favorites if only_favorites else None)
        self.show_results(matches, query, only_favorites)

    def update_edit_buttons(self):
        has_changes=bool(self.pending)
        self.apply_button.set_sensitive(has_changes and not self.errors and not self.requires_refresh and self.client is not None and not self.app.busy)
        self.revert_button.set_sensitive(bool(self.drafts or self.pending) and not self.app.busy)
        self.flash_button.set_sensitive(self.client is not None and not self.requires_refresh and not self.app.busy and not self.pending and not self.drafts)
        self.pending_summary.set_text(f'{len(self.pending)} pending change(s) · {len(self.errors)} invalid field(s)' if self.pending or self.drafts else 'No pending changes.')

    @staticmethod
    def typed_value(setting, text):
        return setting.parse(text)

    def stage(self, category, setting, value):
        if self.app.busy or self.requires_refresh or not enabled(category,setting.name,self.all_settings,self.pending):return
        key=(category,setting.name)
        self.drafts[key]=str(value)
        try:
            parsed=self.typed_value(setting,str(value))
            self.errors.pop(key,None)
            if display(parsed) == setting.current:
                self.pending.pop(key,None);self.drafts.pop(key,None)
            else:self.pending[key]=parsed
        except ValueError as exc:
            self.pending.pop(key,None);self.errors[key]=str(exc)
        if controls_dependencies(category,setting.name):
            for key in list(self.drafts):
                if not enabled(*key,self.all_settings,self.pending):
                    self.pending.pop(key,None);self.drafts.pop(key,None);self.errors.pop(key,None)
        self.update_edit_buttons()
        self.app.status.set_text(f'{len(self.pending)} setting change(s) staged locally. Apply temporarily to send them.')

    def confirm(self, title, text, button, callback):
        client=self.client
        dialog=Gtk.Dialog(title=title,transient_for=self.app.window,modal=True)
        dialog.set_default_size(640,360)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
        dialog.add_button(button,Gtk.ResponseType.OK)
        label=Gtk.Label(label=text,xalign=0,yalign=0,wrap=True,selectable=True)
        scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True);scroll.set_child(label)
        dialog.get_content_area().append(scroll)
        def response(_,code):
            dialog.destroy()
            if code==Gtk.ResponseType.OK and self.client is client and not self.app.busy:callback()
        dialog.connect('response',response);dialog.present()
        return dialog

    def apply(self):
        if not self.pending or self.errors or self.requires_refresh or not self.client or self.app.busy:return
        snapshot=dict(self.pending)
        originals={(c,s.name):s for c,rows in self.all_settings.items() for s in rows}
        lines=['Apply these changes to the running C64U? Nothing will be saved to flash.']
        warnings=warnings_for(snapshot)
        if warnings:
            lines.extend(['CAUTION — hardware compatibility change',*warnings])
        for key,value in snapshot.items():
            lines.append(f'{key[0]} · {display_name(*key)}\n{originals[key].current} → {display(value)}')
        button='Apply high-risk change' if warnings else 'Apply temporarily'
        return self.confirm('Review pending changes','\n\n'.join(lines),button,lambda:self.apply_reviewed(snapshot))

    def apply_reviewed(self, snapshot):
        if snapshot != self.pending or self.errors or self.requires_refresh or not self.client or self.app.busy:return
        client=self.client
        payload={}
        for (category,name),value in snapshot.items(): payload.setdefault(category,{})[name]=value
        expected={(c,s.name):s.current for c,rows in self.all_settings.items() for s in rows}
        profile=self.app.active_profile
        def task():
            model=Configuration(client)
            fresh=model.all_settings(list(payload))
            actual={(c,s.name):s.current for c,rows in fresh.items() for s in rows}
            if any(actual.get(key)!=expected.get(key) for key in snapshot):
                raise BrowserError('Device settings changed since review. Discard edits and reload before applying.')
            for category,rows in fresh.items():
                for setting in rows:
                    if setting.name in payload[category]:setting.parse(display(payload[category][setting.name]))
            path=history_path(self.app.preferences,profile,client)
            save_before_apply(path,fresh,payload,client.host)
            client.apply_configuration(payload)
            return Configuration(client).all_settings(list(payload))
        def done(result):
            self.all_settings.update(result)
            actual={(c,s.name):s.current for c,rows in result.items() for s in rows}
            for key,value in snapshot.items():
                if actual.get(key)==display(value):
                    self.pending.pop(key,None);self.drafts.pop(key,None)
            self.render()
            self.app.status.set_text('Applied and verified. Previous values saved for Undo last apply. Nothing was saved to flash.' if not self.pending else 'Some changes did not match the device readback. They remain pending for review.')
        self.request(task,done,writing=True)

    def revert(self):
        if self.app.busy:return
        self.pending={};self.drafts={};self.errors={};self.update_edit_buttons();self.render()
        self.app.status.set_text('Edits discarded. The C64U was not changed.')

    def save_to_flash(self):
        if not self.client or self.requires_refresh or self.app.busy:return
        client=self.client
        def confirmed():
            if self.pending or self.drafts:
                self.app.status.set_text('Apply your changes or choose Discard edits before saving to flash.')
                return
            self.request(lambda:client.save_configuration(),lambda _:self.app.status.set_text('C64U confirmed Save to Flash.'),writing=True)
        return self.confirm('Save configuration to flash','Save the entire running configuration, including changes made outside Argonaut, so it survives power off?','Save to Flash',confirmed)

    def show(self, category, rows):
        self.all_settings[category]=rows
        self.render()

    def show_results(self, matches, query='', only_favorites=False):
        self.clear(self.rows)
        scope='Favorites' if only_favorites else ('Search results' if query else (self.category or 'Settings'))
        self.heading.set_text(f'{scope} · {len(matches)} settings')
        if only_favorites and not matches:
            self.rows.append(Gtk.Label(label='No matching favorites. Clear the search or turn off Favorites and use ☆ beside a setting to add it.',wrap=True,xalign=0))
        last_subsection=None
        for category, setting in matches:
            section=section_for(category,setting.name) if query or only_favorites else self.category
            subsection=(section,subsection_for(section,category,setting.name))
            if subsection != last_subsection:
                label=subsection[1] if not query and not only_favorites else ' · '.join(subsection)
                self.rows.append(Gtk.Label(label=label,xalign=0,wrap=True,css_classes=['heading']))
                last_subsection=subsection
            line=Gtk.Box(spacing=6)
            favorite=Gtk.Button(label='★' if (category,setting.name) in self.favorites else '☆')
            favorite.set_tooltip_text('Remove from Favorites' if favorite.get_label()=='★' else 'Add to Favorites')
            favorite.connect('clicked',lambda _, key=(category,setting.name): self.toggle_favorite(key))
            line.append(favorite)
            value=self.drafts.get((category,setting.name),display(self.pending[(category,setting.name)]) if (category,setting.name) in self.pending else setting.current)
            title=f'{display_name(category,setting.name)} — {value}'
            if (category,setting.name) in self.pending: title+=' (staged)'
            expander=Gtk.Expander(label=title, expanded=False, hexpand=True)
            if category in NETWORK_CATEGORIES and setting.name in STATIC_FIELDS:
                expander.set_sensitive(enabled(category,setting.name,self.all_settings,self.pending))
                if not expander.get_sensitive():expander.set_tooltip_text(inactive_reason(category,setting.name))
            line.append(expander)
            summary=Gtk.Label(label='Current: '+setting.current,xalign=0,wrap=True,selectable=True)
            summary.set_margin_start(12);summary.set_margin_top(4);summary.set_margin_bottom(4)
            details=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
            details.append(summary)
            feedback=Gtk.Label(label=self.errors.get((category,setting.name),''),xalign=0,wrap=True)
            def edited(text, cat=category, item=setting, header=expander, error_label=feedback):
                self.stage(cat,item,text)
                key=(cat,item.name)
                error_label.set_text(self.errors.get(key,''))
                header.set_label(f'{display_name(cat,item.name)} — {text}'+(' (invalid)' if key in self.errors else ' (staged)' if key in self.pending else ''))
                if controls_dependencies(cat,item.name):self.render()
            available=enabled(category,setting.name,self.all_settings,self.pending)
            if not available:details.append(Gtk.Label(label=inactive_reason(category,setting.name),xalign=0))
            if available and setting.choices and setting.editable and setting.current != 'Hidden' and subsection[1] != 'Status':
                chooser=Gtk.ComboBoxText()
                for choice in setting.choices: chooser.append_text(choice)
                if value in setting.choices: chooser.set_active(setting.choices.index(value))
                chooser.connect('changed',lambda combo, change=edited: change(combo.get_active_text()))
                chooser.set_sensitive(expander.get_expanded())
                expander.connect('notify::expanded', lambda item, _pspec, control=chooser: control.set_sensitive(item.get_expanded()))
                # GTK ComboBox changes its active item on wheel events even when
                # its popup is closed. Require an explicit click to open/select.
                wheel=Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
                wheel.connect('scroll',lambda *_: True)
                chooser.add_controller(wheel)
                chooser.set_margin_start(12);details.append(chooser)
            elif available and setting.presets and setting.editable and subsection[1] != 'Status':
                chooser=Gtk.ComboBoxText.new_with_entry()
                for preset in setting.presets:chooser.append_text(preset or 'None')
                if value in setting.presets:chooser.set_active(setting.presets.index(value))
                else:chooser.get_child().set_text(value)
                def preset_changed(combo, change=edited, presets=setting.presets):
                    index=combo.get_active()
                    change(presets[index] if index>=0 else combo.get_child().get_text())
                chooser.connect('changed',preset_changed)
                wheel=Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
                wheel.connect('scroll',lambda *_: True);chooser.add_controller(wheel)
                details.append(chooser)
            elif available and setting.editable and setting.current != 'Hidden' and subsection[1] != 'Status':
                entry=Gtk.Entry(text=value,hexpand=True)
                entry.connect('changed',lambda control, change=edited:change(control.get_text()))
                details.append(entry)
            details.append(feedback)
            if setting.details:
                detail=Gtk.Label(label=setting.details,xalign=0,wrap=True,selectable=True)
                detail.set_margin_start(12);details.append(detail)
            expander.set_child(details)
            self.rows.append(line)
        self.app.status.set_text(f'{len(self.pending)} change(s) staged locally.' if self.pending else 'Showing the last loaded settings. Reload from C64U to refresh.')
        self.update_edit_buttons()

    def toggle_favorite(self, key):
        if self.app.busy:return
        if getattr(self.app, 'preferences_error', None):
            self.app.status.set_text('Cannot save favorites: '+self.app.preferences_error);return
        previous=set(self.app.preferences.setting_favorites)
        updated=set(self.favorites)
        if key in updated:updated.remove(key)
        else:updated.add(key)
        self.app.preferences.setting_favorites=updated
        try:self.app.preferences.save()
        except (OSError, BrowserError) as exc:
            self.app.preferences.setting_favorites=previous
            self.app.status.set_text('Could not save favorites: '+str(exc));return
        adjustment=self.settings_scroll.get_vadjustment()
        position=adjustment.get_value()
        self.favorites=updated
        self.render()
        def restore_scroll(*_):
            adjustment.set_value(min(position,max(adjustment.get_lower(),adjustment.get_upper()-adjustment.get_page_size())))
            return False
        self.rows.add_tick_callback(restore_scroll)
        self.app.status.set_text('Favorite saved on this computer.' if key in updated else 'Favorite removed.')
