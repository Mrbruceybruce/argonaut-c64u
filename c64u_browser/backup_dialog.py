# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Backup file selection and a restore preview that only stages edits."""
from gi.repository import Gtk
from .configuration import Configuration,display
from .dependencies import controls_dependencies
from .backups import snapshot,read_backup,write_backup,differences

class BackupActions:
 def __init__(self,tab):self.tab=tab;self.chooser=None
 def choose(self,restore=False):
  tab=self.tab
  if not tab.client or tab.app.busy:return
  if not tab.loaded:
   tab.reload();tab.app.status.set_text("Loading settings. Choose backup or restore again when loading finishes.");return
  if tab.pending or tab.drafts:
   tab.app.status.set_text('Apply or discard pending edits before backup or restore.');return
  client=tab.client
  chooser=Gtk.FileChooserNative.new('Restore settings backup' if restore else 'Export settings backup',tab.app.window,Gtk.FileChooserAction.OPEN if restore else Gtk.FileChooserAction.SAVE,'Open' if restore else 'Save','Cancel')
  self.chooser=chooser
  if not restore:chooser.set_current_name('argonaut-settings.json')
  def response(_,code):
   file=chooser.get_file();chooser.destroy();self.chooser=None
   if code!=Gtk.ResponseType.ACCEPT or not file or tab.client is not client or tab.app.busy:return
   path=file.get_path()
   if not path:tab.app.status.set_text('Choose a local file.');return
   def task():
    model=Configuration(client);settings=model.all_settings(model.categories())
    if restore:return read_backup(path),settings
    data=snapshot(settings,client.host);write_backup(path,data);return data
   def done(result):
    if restore:self.preview(*result)
    else:tab.app.status.set_text('Settings backup saved. Passwords, read-only information and C64U Model are omitted; ROM and media files are not included.')
   tab.request(task,done)
  chooser.connect('response',response);chooser.show()
 def preview(self,data,settings,extra_skipped=0,title='Restore preview'):
  tab=self.tab;client=tab.client
  changes,skipped=differences(data,settings)
  skipped+=extra_skipped
  dialog=Gtk.Dialog(title=title,transient_for=tab.app.window,modal=True)
  dialog.set_default_size(750,550);dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
  stage=dialog.add_button('Stage selected changes',Gtk.ResponseType.OK)
  box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
  box.append(Gtk.Label(label=f'{len(changes)} differences · {skipped} read-only, sensitive, unavailable or incompatible settings omitted.\nSelect changes to stage, then use Review & Apply. Nothing is saved to flash. Referenced ROM/media files must already be installed. Network changes may disconnect the device.',xalign=0,wrap=True))
  checks=[]
  for category,setting,value in changes:
   check=Gtk.CheckButton(label=f'{category} · {setting.name}\n{setting.current} → {display(value)}',active=False)
   box.append(check);checks.append(check)
  def update(*_):stage.set_sensitive(any(c.get_active() for c in checks))
  for check in checks:check.connect('toggled',update)
  update()
  scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True);scroll.set_child(box);dialog.get_content_area().append(scroll)
  def response(_,code):
   dialog.destroy()
   if code!=Gtk.ResponseType.OK or tab.client is not client or tab.app.busy or tab.pending or tab.drafts:return
   tab.all_settings=settings;tab.requires_refresh=False
   for check,(category,setting,value) in sorted(zip(checks,changes),key=lambda pair:not controls_dependencies(pair[1][0],pair[1][1].name)):
    if check.get_active():tab.stage(category,setting,display(value))
   tab.render();tab.update_edit_buttons()
  dialog.connect('response',response);dialog.present()
  return dialog,checks
