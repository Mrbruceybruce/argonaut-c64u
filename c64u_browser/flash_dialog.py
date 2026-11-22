# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Native Flash file management with explicit upload and configuration review."""
from pathlib import Path
import posixpath
from gi.repository import Gtk
from .api import BrowserError
from .storage import storage_root
from .native_files import FLASH_FOLDERS
from .file_service import FileLocation

class FlashFiles:
 def __init__(self,tab):
  self.tab=tab;self.app=tab.app;self.client=tab.client;self.chooser=None
  self.session=self.app.core.device_session();self.closed=False;self.confirmation=None;self.plan_id=None
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
  self.controls.append(Gtk.Label(label='Uploads save files in Flash without selecting a ROM or applying settings. Existing files are not replaced. Select an installed ROM in Ultimate Menu afterward. For C64U drive files, select one on the C64U side of Files before opening this dialog.',wrap=True,xalign=0))
  self.status=Gtk.Label(xalign=0,wrap=True,selectable=True);box.append(self.status)
  self.folders.connect('changed',lambda *_:self.refresh())
  self.dialog.present();self.refresh()
 def current(self):
  if self.closed:return False
  if (self.session!=self.app.core.device_session() or not self.session.session_id
      or self.tab.client is not self.client):
   self.retire();return False
  return True
 def retire(self):
  if self.closed:return
  self.closed=True
  if self.chooser is not None:self.chooser.destroy();self.chooser=None
  if self.confirmation is not None:self.confirmation.destroy();self.confirmation=None
  if self.plan_id is not None:self.app.core.files.discard_plan(self.plan_id);self.plan_id=None
  self.dialog.destroy()
 def close(self,*_):
  if not self.current():return
  if self.app.busy:self.status.set_text('Wait for the current operation to finish.');return
  self.retire()
 def folder(self):return self.folders.get_active_id()
 def update(self):
  row=self.listing.get_selected_row()
  self.save_button.set_sensitive(row is not None)
  self.preview_button.set_sensitive(self.folder()=='/Flash/configs' and row is not None and row.name.lower().endswith('.cfg'))
 def run(self,task,done):
  if not self.current() or self.app.busy:return
  self.controls.set_sensitive(False);self.status.set_text('Working…')
  def caught():
   try:return task()
   except Exception as exc:return exc
  consumed=False
  def finish(result):
   nonlocal consumed
   if consumed:return
   consumed=True
   if not self.current():return
   self.controls.set_sensitive(True)
   if isinstance(result,Exception):self.status.set_text(str(result))
   else:done(result)
  self.app.run(caught,finish)
 def run_core_job(self,job,done,*,discard_stale=None):
  if not self.current() or self.app.busy:return
  def admitted():
   if not self.current():raise BrowserError('Connection changed. Reopen Flash files.')
   return job()
  def started(_job):
   if self.current():
    self.controls.set_sensitive(False);self.status.set_text('Working…')
  consumed=False
  def finish(snapshot):
   nonlocal consumed
   if consumed:return
   consumed=True
   if not self.current():
    if discard_stale is not None:discard_stale(snapshot)
    evidence=getattr(snapshot.result,'flash',None)
    if evidence is not None:self.app.status.set_text(evidence.message()+' Connection changed. Reopen Flash files.')
    return
   self.controls.set_sensitive(True);done(snapshot)
  def failed(exc):
   if self.current():self.controls.set_sensitive(True);self.status.set_text(str(exc))
  return self.app.run_file_job(admitted,finish,started=started,failed=failed)
 def refresh(self,after=None):
  if not self.current() or self.app.busy:return
  folder=self.folder()
  while self.listing.get_first_child():self.listing.remove(self.listing.get_first_child())
  self.update()
  def task():return self.app.core.read_flash(self.session,folder)
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
  if not self.current() or self.app.busy:return
  if self.chooser is not None:return
  folder=self.folder()
  chooser=Gtk.FileChooserNative.new('Upload to '+folder,self.dialog,Gtk.FileChooserAction.OPEN,'Choose','Cancel');self.chooser=chooser
  consumed=False
  def response(_,code):
   nonlocal consumed
   if consumed:return
   consumed=True
   if not self.current() or self.chooser is not chooser:return
   file=chooser.get_file();chooser.destroy();self.chooser=None
   if code!=Gtk.ResponseType.ACCEPT or not file:return
   path=file.get_path()
   if not path:self.status.set_text('Choose a local file.');return
   self.prepare(path,False,folder=folder)
  chooser.connect('response',response);chooser.show()
 def copy_usb(self):
  if not self.current() or self.app.busy:return
  rows=self.app.rlist.get_selected_rows()
  if len(rows)!=1 or rows[0].item[1] or rows[0].item[0]=='..':self.status.set_text('Select one C64U drive file in Files, then reopen Flash files.');return
  path=posixpath.join(self.app.remote,rows[0].item[0])
  if not storage_root(path):self.status.set_text('Choose a USB or SD file.');return
  self.prepare(path,True)
 def prepare(self,path,remote,*,folder=None):
  if not self.current() or self.app.busy:return
  folder=folder if folder is not None else self.folder();name=Path(path).name
  source=FileLocation.c64u(path) if remote else FileLocation.core_host(path)
  job=lambda: self.app.core.files.prepare_native_upload(source,folder,name,expected_session=self.session)
  def done(snapshot):
   if snapshot.state!='succeeded':self.status.set_text(snapshot.error.message);return
   preview=snapshot.result;self.plan_id=preview.plan_id
   dialog=Gtk.Dialog(title='Confirm Flash upload',transient_for=self.dialog,modal=True)
   self.confirmation=dialog
   dialog.add_button('Cancel',Gtk.ResponseType.CANCEL);dialog.add_button('Upload',Gtk.ResponseType.OK)
   dialog.get_content_area().append(Gtk.Label(label=f'Source: {path}\nDestination: {folder}/{name}\nSize: {preview.size:,} bytes\n\nSave this file in Flash? No ROM or settings will be activated.',wrap=True,xalign=0))
   consumed=False
   def response(_,code):
    nonlocal consumed
    if consumed:return
    consumed=True
    if not self.current():return
    dialog.destroy();self.confirmation=None;self.plan_id=None
    if code!=Gtk.ResponseType.OK or self.app.busy:
     self.app.core.files.discard_plan(preview.plan_id);return
    def uploaded(destination):
     self.refresh(after=lambda:self.tab.reload() if not self.tab.pending and not self.tab.drafts else None)
     self.app.status.set_text(destination.message)
    upload=lambda: self.app.core.files.execute_native_upload(preview.plan_id)
    def finished(result):
     if result.state=='succeeded':uploaded(result.result)
     else:self.status.set_text(result.result.message if result.result else result.error.message)
    self.run_core_job(upload,finished)
   dialog.connect('response',response);dialog.present()
  def discard_stale(snapshot):
   if snapshot.state=='succeeded':self.app.core.files.discard_plan(snapshot.result.plan_id)
  self.run_core_job(job,done,discard_stale=discard_stale)
 def save_copy(self):
  row=self.listing.get_selected_row()
  if not self.current() or self.app.busy or row is None or self.chooser is not None:return
  source=self.folder()+'/'+row.name
  chooser=Gtk.FileChooserNative.new('Save a copy',self.dialog,Gtk.FileChooserAction.SAVE,'Save','Cancel');self.chooser=chooser
  chooser.set_current_name(row.name)
  consumed=False
  def response(_,code):
   nonlocal consumed
   if consumed:return
   consumed=True
   if not self.current() or self.chooser is not chooser:return
   file=chooser.get_file();chooser.destroy();self.chooser=None
   if code!=Gtk.ResponseType.ACCEPT or not file:return
   path=file.get_path()
   if not path:self.status.set_text('Choose a local file.');return
   job=lambda: self.app.core.files.save_native_copy(
    FileLocation.c64u(source),FileLocation.core_host(path),expected_session=self.session)
   def done(result):
    if result.state=='succeeded':self.status.set_text('Copy saved: '+result.result['destination'].path)
    else:self.status.set_text(result.error.message)
   self.run_core_job(job,done)
  chooser.connect('response',response);chooser.show()

 def preview(self):
  if not self.current() or self.app.busy:return
  row=self.listing.get_selected_row()
  if self.folder()!='/Flash/configs' or row is None:return
  folder=self.folder();name=row.name
  def task():return self.app.core.read_flash(self.session,folder,name=name)
  def done(result):
   self.retire()
   self.tab.backups.preview(result[0],result[1],extra_skipped=result[2],
    title='Native configuration preview',expected_session=self.session)
  self.run(task,done)
