# SPDX-License-Identifier: GPL-3.0-or-later
"""Validated desktop preferences, separate from machine configuration."""
DEFAULTS={'remember_window':True,'width':1200,'height':850,'preview_scale':150,
          'preview_audio':True,'remember_folders':True,'developer_mode':False,
          'local_folder':'','remote_folders':{}}

def defaults():
    return {**DEFAULTS,'remote_folders':{}}

def validate(options):
    result=defaults()
    if not isinstance(options,dict):raise ValueError('Invalid application preferences')
    for key in ('remember_window','preview_audio','remember_folders',
                'developer_mode'):
        value=options.get(key,result[key])
        if type(value) is not bool:raise ValueError('Invalid preference: '+key)
        result[key]=value
    for key,low,high in (('width',600,10000),('height',400,10000),('preview_scale',50,300)):
        value=options.get(key,result[key])
        if type(value) is not int or not low<=value<=high:raise ValueError('Invalid preference: '+key)
        result[key]=value
    result['preview_scale']=normalize_scale(result['preview_scale'])
    local=options.get('local_folder','');remote=options.get('remote_folders',{})
    if not isinstance(local,str) or not isinstance(remote,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in remote.items()):
        raise ValueError('Invalid remembered folders')
    result.update(local_folder=local,remote_folders=dict(remote))
    return result


def normalize_scale(value):
    """Migrate old 50–200% preferences onto the new 25% grid."""
    return max(100,min(300,((int(value)+12)//25)*25))

def scale_control(value,changed=None):
    from gi.repository import Gtk
    row=Gtk.Box(spacing=6)
    minus=Gtk.Button(label='−');minus.set_tooltip_text('Decrease preview scale by 25%')
    entry=Gtk.Label(label=str(normalize_scale(value))+'%',width_chars=5)
    entry.set_tooltip_text('Preview scale: 100–300% in 25% steps')
    plus=Gtk.Button(label='+');plus.set_tooltip_text('Increase preview scale by 25%')
    for widget in (minus,entry,plus):row.append(widget)
    def set_value(value):
        value=normalize_scale(value);entry.set_text(str(value)+'%')
        minus.set_sensitive(value>100);plus.set_sensitive(value<300)
    def step(delta):
        set_value(int(entry.get_text().rstrip('%'))+delta)
        if changed:changed()
    minus.connect('clicked',lambda *_:step(-25));plus.connect('clicked',lambda *_:step(25))
    set_value(value)
    return row,entry,set_value


def show_preferences(app, page=0):
    from gi.repository import Gtk,Gio
    from copy import deepcopy
    from pathlib import Path
    from . import development
    from .test_lab_access import stop_background
    if app.preferences_error:
        app.status.set_text(app.preferences_error);return
    if app.busy:return
    existing=getattr(app,'preferences_dialog',None)
    if existing is not None:
        existing.pages.set_current_page(page);existing.present();return existing
    prefs=app.preferences
    dialog=Gtk.Dialog(title='Argonaut Preferences',transient_for=app.window,modal=True)
    dialog.add_button('Close',Gtk.ResponseType.CLOSE)
    app.preferences_dialog=dialog
    dialog.set_default_size(740,680)
    opened={'app_options':deepcopy(prefs.app_options),
            'screenshot_folder':prefs.screenshot_folder,
            'recording_folder':prefs.recording_folder}
    updating=[False]
    def destroy():
        app.preferences_dialog=None
        dialog.destroy()
    pages=Gtk.Notebook(vexpand=True);dialog.pages=pages;dialog.get_content_area().append(pages)
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
    general_scroll=Gtk.ScrolledWindow(vexpand=True);general_scroll.set_child(box)
    pages.append_page(general_scroll,Gtk.Label(label='General'))
    for side in ('top','bottom','start','end'):getattr(box,'set_margin_'+side)(16)
    checks={}
    for key,label in [('remember_window','Remember window size'),('preview_audio','Play preview audio by default'),('remember_folders','Remember last-used file folders')]:
        control=Gtk.CheckButton(label=label,active=prefs.app_options[key],halign=Gtk.Align.START);box.append(control);checks[key]=control
    if not development.enabled():
        developer_mode=Gtk.CheckButton(
            label='Enable Developer Mode and Test Lab after restart',
            active=prefs.app_options['developer_mode'],
            halign=Gtk.Align.START)
        developer_mode.set_tooltip_text(
            'Adds deterministic checks, saved diagnostics, and optional AI analysis. Nothing starts automatically.')
        box.append(developer_mode)
        checks['developer_mode']=developer_mode
    row=Gtk.Box(spacing=8);box.append(row);row.append(Gtk.Label(label='Preview scale (%)'))
    scale_row,scale,set_scale=scale_control(
        prefs.app_options['preview_scale'],lambda:auto_save_general());row.append(scale_row)
    folders={}
    active_chooser=[None]
    def close_chooser(*_):
        if active_chooser[0]:
            active_chooser[0].destroy();active_chooser[0]=None
        return False
    def browse(_,entry,label):
        if active_chooser[0]:return
        chooser=Gtk.FileChooserNative.new('Choose '+label.lower(),dialog,Gtk.FileChooserAction.SELECT_FOLDER,'Select','Cancel')
        chooser.set_modal(True);active_chooser[0]=chooser
        current=Path(entry.get_text()).expanduser() if entry.get_text() else Path.home()
        if current.is_dir():chooser.set_current_folder(Gio.File.new_for_path(str(current.absolute())))
        def chosen(_,code):
            selected=chooser.get_file() if code==Gtk.ResponseType.ACCEPT else None
            close_chooser()
            if selected:
                path=selected.get_path()
                if path:
                    entry.set_text(path);auto_save_general()
                else:error.set_text('Choose a local folder.')
        chooser.connect('response',chosen);chooser.show()
    for key,label in [('screenshot_folder','Screenshot folder'),('recording_folder','Recording folder')]:
        box.append(Gtk.Label(label=label,xalign=0))
        folderrow=Gtk.Box(spacing=8);box.append(folderrow)
        entry=Gtk.Entry(text=getattr(prefs,key),placeholder_text='Last used, or home if blank',hexpand=True);folderrow.append(entry);folders[key]=entry
        button=Gtk.Button(label='Browse…');folderrow.append(button)
        button.connect('clicked',browse,entry,label)
    note=Gtk.Label(label='General settings save automatically. Undo restores the values from when Preferences opened. Restore defaults keeps connection profiles and C64U settings.',wrap=True,xalign=0);box.append(note)
    error=Gtk.Label(wrap=True,xalign=0);box.append(error)
    actions=Gtk.Box(spacing=8);box.append(actions)
    undo=Gtk.Button(label='Undo');actions.append(undo)
    restore=Gtk.Button(label='Restore defaults…');actions.append(restore)

    def show_general(options,folder_values):
        updating[0]=True
        try:
            for key,control in checks.items():control.set_active(options[key])
            set_scale(options['preview_scale'])
            for key,entry in folders.items():entry.set_text(folder_values[key])
        finally:updating[0]=False

    def auto_save_general(message='Preferences saved automatically.'):
        if updating[0]:return True
        if app.busy:return False
        values={key:entry.get_text().strip() for key,entry in folders.items()}
        for key,value in values.items():
            if value and not Path(value).expanduser().is_dir():
                error.set_text('Choose an existing folder for '+key.replace('_',' ')+'.');return False
        old=deepcopy(prefs.app_options)
        oldfolders={key:getattr(prefs,key) for key in values}
        developer_was_enabled=old['developer_mode']
        prefs.app_options=validate(old)
        prefs.app_options.update({key:control.get_active() for key,control in checks.items()})
        prefs.app_options['preview_scale']=int(scale.get_text().rstrip('%'))
        for key,value in values.items():setattr(prefs,key,str(Path(value).expanduser().absolute()) if value else '')
        try:prefs.save()
        except (OSError,ValueError) as exc:
            prefs.app_options=old
            for key,value in oldfolders.items():setattr(prefs,key,value)
            show_general(old,oldfolders)
            error.set_text('Could not save preferences: '+str(exc));return False
        tab=app.streams_tab;tab.set_zoom(prefs.app_options['preview_scale']);tab.apply_scale()
        tab.audio.set_active(prefs.app_options['preview_audio'])
        show_general(prefs.app_options,
                     {key:getattr(prefs,key) for key in folders})
        developer_is_enabled=prefs.app_options['developer_mode']
        if developer_was_enabled != developer_is_enabled:
            error.set_text(
                'Preferences saved automatically. Restart Argonaut to apply Developer Mode.')
            if developer_was_enabled and not developer_is_enabled:
                def stopped(result):
                    app.status.set_text(
                        'Developer Mode is off; background tests stopped.'
                        if result else
                        'Developer Mode is off. Some background tests could not be stopped.')
                app.run(stop_background, stopped)
        elif message:error.set_text(message)
        return True

    for control in checks.values():
        control.connect('toggled',lambda *_:auto_save_general())
    for entry in folders.values():
        entry.connect('activate',lambda *_:auto_save_general())
        entry.connect('notify::has-focus',
                      lambda field,_:None if field.get_has_focus()
                      else auto_save_general())

    def undo_general(*_):
        show_general(opened['app_options'],{
            key:opened[key] for key in folders})
        auto_save_general('Changes undone.')
    undo.connect('clicked',undo_general)

    def restore_defaults(*_):
        existing=getattr(dialog,'restore_prompt',None)
        if existing:existing.present();return
        prompt=Gtk.Dialog(title='Restore default preferences?',
                          transient_for=dialog,modal=True)
        dialog.restore_prompt=prompt
        prompt.add_button('Cancel',Gtk.ResponseType.CANCEL)
        prompt.add_button('Restore defaults',Gtk.ResponseType.OK)
        label=Gtk.Label(
            label='Restore all General settings to their defaults? Device profiles and C64U settings will be kept.',
            wrap=True,xalign=0)
        for side in ('top','bottom','start','end'):
            getattr(label,'set_margin_'+side)(16)
        prompt.get_content_area().append(label)
        def decided(_,code):
            prompt.destroy();dialog.restore_prompt=None
            if code==Gtk.ResponseType.OK:
                show_general(defaults(),{key:'' for key in folders})
                if auto_save_general('Default preferences restored.'):
                    app.window.set_default_size(1200,850)
        prompt.connect('response',decided)
        prompt.connect('close-request',
                       lambda *_:(prompt.response(Gtk.ResponseType.CANCEL),True)[1])
        prompt.present()
    restore.connect('clicked',restore_defaults)
    from .connection_dialog import ConnectionDialog
    connections=ConnectionDialog(app,window=dialog)
    app.connection_dialog=connections
    pages.append_page(connections.page,Gtk.Label(label='Device details'))
    from .about import about_page
    pages.append_page(about_page(),Gtk.Label(label='About'))
    dialog.connections=connections
    def request_close():
        if app.busy:return
        close_chooser()
        if not auto_save_general(None):
            pages.set_current_page(0);return
        if not connections.dirty():destroy();return
        existing=getattr(dialog,'unsaved_prompt',None)
        if existing:existing.present();return
        prompt=Gtk.Dialog(title='Save device profile?',transient_for=dialog,modal=True)
        dialog.unsaved_prompt=prompt
        prompt.add_button('Keep editing',Gtk.ResponseType.CANCEL)
        prompt.add_button('Discard',Gtk.ResponseType.REJECT)
        prompt.add_button('Save',Gtk.ResponseType.OK)
        prompt.set_default_response(Gtk.ResponseType.CANCEL)
        label=Gtk.Label(label='Save unfinished device profile edits before closing?',wrap=True)
        for side in ('top','bottom','start','end'):getattr(label,'set_margin_'+side)(16)
        prompt.get_content_area().append(label)
        def decided(_,code):
            prompt.destroy();dialog.unsaved_prompt=None
            if code==Gtk.ResponseType.REJECT:destroy()
            elif code==Gtk.ResponseType.OK:
                try:connections.profile()
                except Exception as exc:
                    pages.set_current_page(1);connections.status.set_text(str(exc));return
                connections.save(after=destroy)
        prompt.connect('response',decided)
        prompt.connect('close-request',lambda *_:(prompt.response(Gtk.ResponseType.CANCEL),True)[1])
        prompt.present()
    dialog.connect('close-request',lambda *_:(request_close(),True)[1])
    dialog.connect('response',lambda *_:request_close())
    dialog.present();pages.set_current_page(page)
    return dialog
