# SPDX-License-Identifier: GPL-3.0-or-later
"""Validated desktop preferences, separate from machine configuration."""
DEFAULTS={'remember_window':True,'width':1200,'height':850,'preview_scale':150,
          'preview_audio':True,'remember_folders':True,'local_folder':'','remote_folders':{}}

def defaults():
    return {**DEFAULTS,'remote_folders':{}}

def validate(options):
    result=defaults()
    if not isinstance(options,dict):raise ValueError('Invalid application preferences')
    for key in ('remember_window','preview_audio','remember_folders'):
        value=options.get(key,result[key])
        if type(value) is not bool:raise ValueError('Invalid preference: '+key)
        result[key]=value
    for key,low,high in (('width',600,10000),('height',400,10000),('preview_scale',50,200)):
        value=options.get(key,result[key])
        if type(value) is not int or not low<=value<=high:raise ValueError('Invalid preference: '+key)
        result[key]=value
    local=options.get('local_folder','');remote=options.get('remote_folders',{})
    if not isinstance(local,str) or not isinstance(remote,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in remote.items()):
        raise ValueError('Invalid remembered folders')
    result.update(local_folder=local,remote_folders=dict(remote))
    return result


def show_preferences(app):
    from gi.repository import Gtk
    from pathlib import Path
    if app.preferences_error:
        app.status.set_text(app.preferences_error);return
    prefs=app.preferences
    dialog=Gtk.Dialog(title='Argonaut Preferences',transient_for=app.window,modal=True)
    dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
    dialog.add_button('Save',Gtk.ResponseType.OK)
    box=dialog.get_content_area();box.set_spacing(10)
    for side in ('top','bottom','start','end'):getattr(box,'set_margin_'+side)(16)
    checks={}
    for key,label in [('remember_window','Remember window size'),('preview_audio','Play preview audio by default'),('remember_folders','Remember last-used file folders')]:
        control=Gtk.CheckButton(label=label,active=prefs.app_options[key]);box.append(control);checks[key]=control
    row=Gtk.Box(spacing=8);box.append(row);row.append(Gtk.Label(label='Preview scale (%)'))
    scale=Gtk.SpinButton.new_with_range(50,200,1);scale.set_value(prefs.app_options['preview_scale']);row.append(scale)
    folders={}
    for key,label in [('screenshot_folder','Screenshot folder'),('recording_folder','Recording folder')]:
        box.append(Gtk.Label(label=label,xalign=0))
        entry=Gtk.Entry(text=getattr(prefs,key),placeholder_text='Last used, or home if blank',hexpand=True);box.append(entry);folders[key]=entry
    note=Gtk.Label(label='Preview audio applies to the next preview session. Reset keeps connection profiles and C64U settings.',wrap=True,xalign=0);box.append(note)
    error=Gtk.Label(wrap=True,xalign=0);box.append(error)
    reset=Gtk.Button(label='Reset preferences');box.append(reset)
    reset_pending=[False]
    def reset_fields(*_):
        reset_pending[0]=True
        for key,control in checks.items():control.set_active(DEFAULTS[key])
        scale.set_value(150)
        for entry in folders.values():entry.set_text('')
    reset.connect('clicked',reset_fields)
    def response(_,code):
        if code!=Gtk.ResponseType.OK:dialog.destroy();return
        values={key:entry.get_text().strip() for key,entry in folders.items()}
        for key,value in values.items():
            if value and not Path(value).expanduser().is_dir():error.set_text('Choose an existing folder for '+key.replace('_',' ')+'.');return
        old=prefs.app_options;oldfolders={key:getattr(prefs,key) for key in values}
        prefs.app_options=defaults() if reset_pending[0] else validate(old)
        prefs.app_options.update({key:control.get_active() for key,control in checks.items()})
        prefs.app_options['preview_scale']=scale.get_value_as_int()
        for key,value in values.items():setattr(prefs,key,str(Path(value).expanduser().absolute()) if value else '')
        try:prefs.save()
        except OSError as exc:
            prefs.app_options=old
            for key,value in oldfolders.items():setattr(prefs,key,value)
            error.set_text('Could not save preferences: '+str(exc));return
        tab=app.streams_tab;tab.zoom.set_text(str(prefs.app_options['preview_scale']));tab.apply_scale()
        tab.audio.set_active(prefs.app_options['preview_audio'])
        if reset_pending[0]:app.window.set_default_size(1200,850)
        dialog.destroy()
    dialog.connect('response',response);dialog.present();return dialog
