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
    entry=Gtk.Entry(text=str(normalize_scale(value)),editable=False,width_chars=4,max_width_chars=4)
    entry.set_tooltip_text('Preview scale: 100–300% in 25% steps')
    plus=Gtk.Button(label='+');plus.set_tooltip_text('Increase preview scale by 25%')
    for widget in (minus,entry,Gtk.Label(label='%'),plus):row.append(widget)
    def set_value(value):
        value=normalize_scale(value);entry.set_text(str(value))
        minus.set_sensitive(value>100);plus.set_sensitive(value<300)
    def step(delta):
        set_value(int(entry.get_text())+delta)
        if changed:changed()
    minus.connect('clicked',lambda *_:step(-25));plus.connect('clicked',lambda *_:step(25))
    set_value(value)
    return row,entry,set_value


def show_preferences(app, page=0):
    from gi.repository import Gtk,Gio
    from pathlib import Path
    if app.preferences_error:
        app.status.set_text(app.preferences_error);return
    if app.busy:return
    existing=getattr(app,'preferences_dialog',None)
    if existing is not None:
        existing.pages.set_current_page(page);existing.present();return existing
    prefs=app.preferences
    dialog=Gtk.Dialog(title='Argonaut Preferences',transient_for=app.window,modal=True)
    dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
    dialog.add_button('Save',Gtk.ResponseType.OK)
    app.preferences_dialog=dialog
    dialog.set_default_size(740,680)
    dialog.connect('close-request',lambda *_: app.busy)
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
    row=Gtk.Box(spacing=8);box.append(row);row.append(Gtk.Label(label='Preview scale (%)'))
    scale_row,scale,set_scale=scale_control(prefs.app_options['preview_scale']);row.append(scale_row)
    folders={}
    active_chooser=[None]
    def close_chooser(*_):
        if active_chooser[0]:
            active_chooser[0].destroy();active_chooser[0]=None
        return False
    dialog.connect('close-request',close_chooser)
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
                if path:entry.set_text(path)
                else:error.set_text('Choose a local folder.')
        chooser.connect('response',chosen);chooser.show()
    for key,label in [('screenshot_folder','Screenshot folder'),('recording_folder','Recording folder')]:
        box.append(Gtk.Label(label=label,xalign=0))
        folderrow=Gtk.Box(spacing=8);box.append(folderrow)
        entry=Gtk.Entry(text=getattr(prefs,key),placeholder_text='Last used, or home if blank',hexpand=True);folderrow.append(entry);folders[key]=entry
        button=Gtk.Button(label='Browse…');folderrow.append(button)
        button.connect('clicked',browse,entry,label)
    note=Gtk.Label(label='Preview audio applies to the next preview session. Reset keeps connection profiles and C64U settings.',wrap=True,xalign=0);box.append(note)
    error=Gtk.Label(wrap=True,xalign=0);box.append(error)
    reset=Gtk.Button(label='Reset preferences');box.append(reset)
    reset_pending=[False]
    def reset_fields(*_):
        reset_pending[0]=True
        for key,control in checks.items():control.set_active(DEFAULTS[key])
        set_scale(150)
        for entry in folders.values():entry.set_text('')
    reset.connect('clicked',reset_fields)
    def response(_,code):
        if app.busy:return
        close_chooser()
        if code!=Gtk.ResponseType.OK:destroy();return
        values={key:entry.get_text().strip() for key,entry in folders.items()}
        for key,value in values.items():
            if value and not Path(value).expanduser().is_dir():error.set_text('Choose an existing folder for '+key.replace('_',' ')+'.');return
        old=prefs.app_options;oldfolders={key:getattr(prefs,key) for key in values}
        prefs.app_options=defaults() if reset_pending[0] else validate(old)
        prefs.app_options.update({key:control.get_active() for key,control in checks.items()})
        prefs.app_options['preview_scale']=int(scale.get_text())
        for key,value in values.items():setattr(prefs,key,str(Path(value).expanduser().absolute()) if value else '')
        try:prefs.save()
        except OSError as exc:
            prefs.app_options=old
            for key,value in oldfolders.items():setattr(prefs,key,value)
            error.set_text('Could not save preferences: '+str(exc));return
        tab=app.streams_tab;tab.set_zoom(prefs.app_options['preview_scale']);tab.apply_scale()
        tab.audio.set_active(prefs.app_options['preview_audio'])
        if reset_pending[0]:app.window.set_default_size(1200,850)
        destroy()
    from .connection_dialog import ConnectionDialog
    connections=ConnectionDialog(app,window=dialog)
    app.connection_dialog=connections
    pages.append_page(connections.page,Gtk.Label(label='Connections'))
    pages.append_page(connections.details_page,Gtk.Label(label='Device details'))
    dialog.connections=connections
    # Profile operations save explicitly; General preferences remain staged until Save.
    save_button=dialog.get_widget_for_response(Gtk.ResponseType.OK)
    def switched(_,child,index):save_button.set_visible(index==0)
    pages.connect('switch-page',switched)
    dialog.connect('response',response);dialog.present();pages.set_current_page(page)
    return dialog
