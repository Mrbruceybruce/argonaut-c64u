"""Wait for real GTK allocation; the timeout fails, never substitutes a size."""
from gi.repository import GLib


def allocated_frame(window, *widgets):
    assert window.get_visible(), 'Layout fixture must present its window'
    clock = window.get_frame_clock()
    assert clock is not None, 'Presented window has no frame clock'
    loop = GLib.MainLoop()
    painted = []
    expired = []
    def after_paint(_):
        painted.append(True)
        loop.quit()
    def deadline():
        expired.append(True)
        loop.quit()
        return False
    handler = clock.connect('after-paint', after_paint)
    timer = GLib.timeout_add(3000, deadline)
    clock.begin_updating()
    window.queue_resize()
    try:
        loop.run()
    finally:
        clock.end_updating()
        clock.disconnect(handler)
        if not expired:
            GLib.source_remove(timer)
    assert painted and not expired, 'GTK allocation frame deadline expired'
    for widget in (window, *widgets):
        assert widget.get_mapped(), 'Measured widget is not mapped'
        assert widget.get_width() > 0 and widget.get_height() > 0, (
            f'Mapped {type(widget).__name__} has zero allocation')
