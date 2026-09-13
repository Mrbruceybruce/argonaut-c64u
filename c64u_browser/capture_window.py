# SPDX-License-Identifier: GPL-3.0-or-later
"""A clean, native-aspect GTK canvas. It never owns or drains a stream."""
from gi.repository import Gtk,Gdk,Graphene,Gsk
from .video_geometry import fit

class CaptureCanvas(Gtk.Widget):
    def __init__(self, use_cairo=False):
        self.use_cairo=use_cairo or not hasattr(Gtk.Snapshot,'append_scaled_texture')
        super().__init__(hexpand=True,vexpand=True)
        self.texture=None;self.integer=True;self.surface=None
        self.set_overflow(Gtk.Overflow.HIDDEN)

    def set_frame(self,texture,rgb=None):
        self.texture=texture;self.surface=None
        if texture and self.use_cairo:
            # GTK 4.8 fallback uses a Cairo surface prepared by the media worker.
            # rgb is actually preconverted native-endian RGB24 in this fallback.
            import cairo
            self.surface=cairo.ImageSurface.create_for_data(rgb,cairo.FORMAT_RGB24,384,texture.get_height(),384*4)
        self.queue_draw()

    def do_snapshot(self,snapshot):
        bounds=Graphene.Rect().init(0,0,self.get_width(),self.get_height())
        black=Gdk.RGBA();black.parse('black');snapshot.append_color(black,bounds)
        if not self.texture:return
        x,y,w,h=fit(self.texture.get_width(),self.texture.get_height(),self.get_width(),self.get_height(),self.integer)
        target=Graphene.Rect().init(x,y,w,h)
        if not self.use_cairo:
            snapshot.append_scaled_texture(self.texture,Gsk.ScalingFilter.NEAREST,target)
        elif self.surface:
            import cairo
            cr=snapshot.append_cairo(target)
            cr.translate(x,y);cr.scale(w/384,h/self.texture.get_height())
            cr.set_source_surface(self.surface,0,0);cr.get_source().set_filter(cairo.FILTER_NEAREST);cr.paint()

class CaptureWindow(Gtk.Window):
    def __init__(self,app,on_close):
        super().__init__(application=app,title='Argonaut — C64 Capture',default_width=768,default_height=544)
        self.canvas=CaptureCanvas();self.set_child(self.canvas)
        self.connect('close-request',lambda *_:(on_close(),False)[1])
