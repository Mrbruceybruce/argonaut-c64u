from .platform_support import local_roots, contains_path
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Compact storage selectors for mounted local volumes and C64U media."""
from pathlib import Path
from gi.repository import Gtk,Gio,Pango
from .storage import storage_root

class DriveButtons:
 def __init__(self,app,local):
  self.app=app;self.local=local
  self.box=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=4,row_spacing=4,min_children_per_line=1,max_children_per_line=8)
  self.paths=[]
  if local:
   self.monitor=Gio.VolumeMonitor.get()
   for signal in ('mount-added','mount-removed','mount-changed'):
    self.monitor.connect(signal,lambda *_:self.refresh())
  self.refresh()
 def refresh(self):
  while self.box.get_first_child():self.box.remove(self.box.get_first_child())
  if self.local:
   locations=[('Home',str(Path.home()),'user-home-symbolic')]+local_roots()
   seen={path for _,path,_ in locations}
   for mount in self.monitor.get_mounts():
    path=mount.get_root().get_path()
    if path and path not in seen:
     locations.append((mount.get_name(),path,'drive-removable-media-symbolic'));seen.add(path)
   self.paths=[path for _,path,_ in locations]
   current=str(self.app.local)
   matches=[p for p in self.paths if contains_path(p,current)]
   self.app.local_root=Path(max(matches,key=len)) if matches else Path.home()
   selected=str(self.app.local_root)
  else:
   roots=getattr(self.app.client,'storage_roots',[]) if self.app.client else []
   if not isinstance(roots,list):roots=[]
   locations=[(path[1:],path,'media-flash-sd-mmc-symbolic' if path=='/SD' else 'drive-removable-media-symbolic') for path in roots]
   selected=storage_root(self.app.remote)
  for name,path,icon in locations:
   button=Gtk.Button();content=Gtk.Box(spacing=4)
   content.append(Gtk.Image.new_from_icon_name(icon))
   label=Gtk.Label(label=name,max_width_chars=16,ellipsize=Pango.EllipsizeMode.END);content.append(label)
   button.set_child(content);button.set_tooltip_text('Open '+path)
   button.update_property([Gtk.AccessibleProperty.LABEL],['Open '+name+' · '+path])
   if path==selected:button.add_css_class('suggested-action')
   button.connect('clicked',lambda _,target=path:self.app.navigate(self.local,target))
   self.box.append(button)
  if not locations:self.box.append(Gtk.Label(label='No USB/SD drives found. Use Refresh to scan.',wrap=True,xalign=0))
