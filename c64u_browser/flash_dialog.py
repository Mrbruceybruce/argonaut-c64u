# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Native Flash file management with explicit upload and configuration review."""
from pathlib import Path
import posixpath
from gi.repository import Gtk
from .api import BrowserError
from .storage import storage_root
from .configuration import Configuration
from .native_files import FLASH_FOLDERS,read_local,read_remote,validate_upload,upload_flash,config_backup

class FlashFiles:
 def __init__(self,tab):
  self.tab=tab;self.app=tab.app;self.client=tab.client;self.chooser=None
  self.dialog=Gtk.Dialog(title='C64U Flash files',transient_for=self.app.window,modal=True)
  self.dialog.set_default_size(760,520);self.dialog.add_button('Close',Gtk.ResponseType.CLOSE)
  self.dialog.connect('response',self.close)
  box=self.dialog.get_content_area()
  self.controls=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);box.append(self.controls)
  self.folders=Gtk.ComboBoxText()
  for label,path in FLASH_FOLDERS.items():self.folders.append(path,label+' · '+path)
  self.folders.set_active(0);self.controls.append(self.folders)
  actions=Gtk.Box(spacing=6);self.controls.append(actions)
  self.app.button(actions,'Upload file…',self.choose_local).set_tooltip_text('Choose a file on your computer and copy it into the selected Flash folder.')
  self.app.button(actions,'Copy selected drive file…',self.copy_usb).set_tooltip_text('Copy the file selected in the C64U side of Files from its storage drive into the selected Flash folder. The original stays in place.')
  self.app.button(actions,'Refresh',self.refresh).set_tooltip_text('Read the selected Flash folder again to show its current files.')
  self.preview_button=self.app.button(actions,'Preview config…',self.preview)
  self.save_button=self.app.button(actions,'Save a copy…',self.save_copy)
  self.preview_button.set_tooltip_text('Review compatible settings from the selected native configuration. Choose changes to stage, then use Review & Apply.')
  self.save_button.set_tooltip_text('Download the selected Flash file to your computer. The original stays in Flash.')
  self.listing=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
  self.listing.connect('row-selected',lambda *_:self.update())
  scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True);scroll.set_child(self.listing);self.controls.append(scroll)
  self.controls.append(Gtk.Label(label='Uploads save files in Flash without selecting a ROM or applying settings. Existing files are not replaced. Select an installed ROM in Settings afterward. For C64U drive files, select one on the C64U side of Files before opening this dialog.',wrap=True,xalign=0))
  self.status=Gtk.Label(xalign=0,wrap=True,selectable=True);box.append(self.status)
  self.folders.connect('changed',lambda *_:self.refresh())
  self.dialog.present();self.refresh()
 def close(self,*_):
  if self.app.busy:self.status.set_text('Wait for the current operation to finish.');return
  self.dialog.destroy()
 def folder(self):return self.folders.get_active_id()
 def update(self):
  row=self.listing.get_selected_row()
  self.save_button.set_sensitive(row is not None)
  self.preview_button.set_sensitive(self.folder()=='/Flash/configs' and row is not None and row.name.lower().endswith('.cfg'))
 def run(self,task,done):
  if self.app.busy or self.tab.client is not self.client:return
  self.controls.set_sensitive(False);self.status.set_text('Working…')
  def caught():
   try:return task()
   except Exception as exc:return exc
  def finish(result):
   self.controls.set_sensitive(True)
   if self.tab.client is not self.client:self.status.set_text('Connection changed. Close and reopen Flash files.');return
   if isinstance(result,Exception):self.status.set_text(str(result))
   else:done(result)
  self.app.run(caught,finish)
 def refresh(self,after=None):
  if self.app.busy:return
  folder=self.folder()
  while self.listing.get_first_child():self.listing.remove(self.listing.get_first_child())
  self.update()
  def task():
   root=self.client.list_directory('/Flash')[1]
   if not any(e.name==posixpath.basename(folder) and e.kind=='dir' for e in root):return []
   return self.client.list_directory(folder)[1]
  def done(entries):
   for entry in entries:
    if entry.kind!='file' or entry.name.startswith('argonaut-part-'):continue
    row=Gtk.ListBoxRow();row.name=entry.name
    row.set_child(Gtk.Label(label=f'{entry.name} · {entry.size if entry.size is not None else "?"} bytes',xalign=0,wrap=True))
    self.listing.append(row)
   self.status.set_text('Select a file, or upload a new one. Missing folders are created only when uploading.');self.update()
   if after:after()
  self.run(task,done)
 def choose_local(self):
  if self.app.busy:return
  chooser=Gtk.FileChooserNative.new('Upload to '+self.folder(),self.dialog,Gtk.FileChooserAction.OPEN,'Choose','Cancel');self.chooser=chooser
  def response(_,code):
   file=chooser.get_file();chooser.destroy();self.chooser=None
   if code!=Gtk.ResponseType.ACCEPT or not file:return
   path=file.get_path()
   if not path:self.status.set_text('Choose a local file.');return
   self.prepare(path,False)
  chooser.connect('response',response);chooser.show()
 def copy_usb(self):
  rows=self.app.rlist.get_selected_rows()
  if len(rows)!=1 or rows[0].item[1] or rows[0].item[0]=='..':self.status.set_text('Select one C64U drive file in Files, then reopen Flash files.');return
  path=posixpath.join(self.app.remote,rows[0].item[0])
  if not storage_root(path):self.status.set_text('Choose a USB or SD file.');return
  self.prepare(path,True)
 def prepare(self,path,remote):
  folder=self.folder();name=Path(path).name
  def task():
   data=read_remote(self.client,path) if remote else read_local(path)
   validate_upload(folder,name,data);return data
  def done(data):
   dialog=Gtk.Dialog(title='Confirm Flash upload',transient_for=self.dialog,modal=True)
   dialog.add_button('Cancel',Gtk.ResponseType.CANCEL);dialog.add_button('Upload',Gtk.ResponseType.OK)
   dialog.get_content_area().append(Gtk.Label(label=f'Source: {path}\nDestination: {folder}/{name}\nSize: {len(data):,} bytes\n\nSave this file in Flash? No ROM or settings will be activated.',wrap=True,xalign=0))
   def response(_,code):
    dialog.destroy()
    if code!=Gtk.ResponseType.OK:return
    def uploaded(destination):
     self.refresh(after=lambda:self.tab.reload() if not self.tab.pending and not self.tab.drafts else None)
     self.app.status.set_text('Saved and verified: '+destination)
    self.run(lambda:upload_flash(self.client,folder,name,data),uploaded)
   dialog.connect('response',response);dialog.present()
  self.run(task,done)
 def save_copy(self):
  row=self.listing.get_selected_row()
  if self.app.busy or row is None:return
  source=self.folder()+'/'+row.name
  chooser=Gtk.FileChooserNative.new('Save a copy',self.dialog,Gtk.FileChooserAction.SAVE,'Save','Cancel');self.chooser=chooser
  chooser.set_current_name(row.name)
  def response(_,code):
   file=chooser.get_file();chooser.destroy();self.chooser=None
   if code!=Gtk.ResponseType.ACCEPT or not file:return
   path=file.get_path()
   if not path:self.status.set_text('Choose a local file.');return
   def task():
    import os,tempfile
    data=read_remote(self.client,source)
    destination=Path(path)
    # A private staging file avoids leaving a partial backup on failure.
    with tempfile.NamedTemporaryFile(dir=destination.parent,delete=False) as stream:
     temporary=stream.name
     try:stream.write(data);stream.flush();os.fsync(stream.fileno())
     except BaseException:os.unlink(temporary);raise
    try:os.replace(temporary,destination)
    finally:
     if os.path.exists(temporary):os.unlink(temporary)
    return path
   self.run(task,lambda path:self.status.set_text('Copy saved: '+path))
  chooser.connect('response',response);chooser.show()

 def preview(self):
  row=self.listing.get_selected_row()
  if self.folder()!='/Flash/configs' or row is None:return
  path=self.folder()+'/'+row.name
  def task():
   data=read_remote(self.client,path)
   model=Configuration(self.client);settings=model.all_settings(model.categories())
   converted,skipped=config_backup(data,settings)
   return converted,settings,skipped
  def done(result):
   self.dialog.destroy()
   self.tab.backups.preview(result[0],result[1],extra_skipped=result[2],title='Native configuration preview')
  self.run(task,done)
