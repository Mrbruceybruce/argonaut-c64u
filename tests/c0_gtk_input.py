"""Real XTest input for explicit offline GTK checks (GDK_BACKEND=x11)."""
import ctypes
import time
import gi
gi.require_version('GdkX11', '4.0')
from gi.repository import GLib, Graphene, GdkX11


def pump(seconds=.06):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        time.sleep(.002)


class Input:
    def __init__(self, window):
        self.window = window
        self.x = ctypes.CDLL('libX11.so.6')
        self.t = ctypes.CDLL('libXtst.so.6')
        self.x.XOpenDisplay.restype = ctypes.c_void_p
        self.display = self.x.XOpenDisplay(None)
        assert self.display, 'X11 display required'
        signatures = {
            'XFlush': [ctypes.c_void_p], 'XCloseDisplay': [ctypes.c_void_p],
            'XRaiseWindow': [ctypes.c_void_p, ctypes.c_ulong],
            'XSetInputFocus': [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong],
            'XDefaultRootWindow': [ctypes.c_void_p],
            'XKeysymToKeycode': [ctypes.c_void_p, ctypes.c_ulong],
            'XStringToKeysym': [ctypes.c_char_p],
            'XTranslateCoordinates': [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong)],
            'XQueryPointer': [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)],
        }
        for name, signature in signatures.items():getattr(self.x, name).argtypes = signature
        self.x.XDefaultRootWindow.restype = ctypes.c_ulong
        self.x.XStringToKeysym.restype = ctypes.c_ulong
        self.t.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        for name in ('XTestFakeButtonEvent', 'XTestFakeKeyEvent'):
            getattr(self.t, name).argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.root = self.x.XDefaultRootWindow(self.display)
        root, child = ctypes.c_ulong(), ctypes.c_ulong()
        rx, ry, wx, wy, mask = ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_uint()
        self.x.XQueryPointer(self.display, self.root, ctypes.byref(root), ctypes.byref(child),
            ctypes.byref(rx), ctypes.byref(ry), ctypes.byref(wx), ctypes.byref(wy), ctypes.byref(mask))
        self.saved_pointer = rx.value, ry.value
        self.held = set()
        pump()
        assert isinstance(window.get_surface(), GdkX11.X11Surface), 'Use GDK_BACKEND=x11'
        self.wid = window.get_surface().get_xid()
        self.x.XRaiseWindow(self.display, self.wid)
        self.x.XSetInputFocus(self.display, self.wid, 1, 0)
        self.flush()

    def flush(self):
        self.x.XFlush(self.display)
        pump()

    def move(self, widget, x=15, y=None):
        point = Graphene.Point(); point.init(x, widget.get_height()/2 if y is None else y)
        valid, point = widget.compute_point(self.window, point)
        assert valid
        rx, ry, child = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
        self.x.XTranslateCoordinates(self.display, self.wid, self.root, 0, 0,
            ctypes.byref(rx), ctypes.byref(ry), ctypes.byref(child))
        tx, ty = self.window.get_surface_transform()
        scale = self.window.get_scale_factor()
        self.t.XTestFakeMotionEvent(self.display, -1,
            rx.value + round((point.x + tx)*scale), ry.value + round((point.y + ty)*scale), 0)
        self.flush()

    def button(self, down, button=1):
        self.t.XTestFakeButtonEvent(self.display, button, down, 0)
        self.flush()

    def key(self, name, down):
        code = self.x.XKeysymToKeycode(self.display, self.x.XStringToKeysym(name.encode()))
        assert code
        self.t.XTestFakeKeyEvent(self.display, code, down, 0)
        (self.held.add if down else self.held.discard)(name)
        self.flush()

    def press(self, name, modifier=None):
        if modifier:self.key(modifier, True)
        self.key(name, True); self.key(name, False)
        if modifier:self.key(modifier, False)

    def click(self, widget, modifier=None, button=1, twice=False, **position):
        self.move(widget, **position)
        if modifier:self.key(modifier, True)
        self.button(True, button); self.button(False, button)
        if twice:self.button(True, button); self.button(False, button)
        if modifier:self.key(modifier, False)

    def close(self):
        for key in tuple(self.held):self.key(key, False)
        self.t.XTestFakeButtonEvent(self.display, 1, False, 0)
        self.t.XTestFakeMotionEvent(self.display, -1, *self.saved_pointer, 0)
        self.x.XFlush(self.display)
        self.x.XCloseDisplay(self.display)
