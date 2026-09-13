# SPDX-License-Identifier: GPL-3.0-or-later
"""About window with bundled artwork and selectable package identity."""
import platform
from gi.repository import Gtk
from .version import ASSETS, build_info
from .platform_support import portable_root

REPOSITORY = 'https://github.com/Mrbruceybruce/argonaut-c64u'

def about_page():
    scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    scroll.set_child(box)
    picture = Gtk.Picture.new_for_filename(str(ASSETS / 'about-background.png'))
    picture.set_content_fit(Gtk.ContentFit.CONTAIN)
    picture.set_can_shrink(True)
    picture.set_size_request(-1, 300)
    box.append(picture)
    details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
    for side in ('start','end','bottom'):
        getattr(details, 'set_margin_'+side)(20)
    box.append(details)
    title = Gtk.Label(label='Argonaut', xalign=0)
    title.add_css_class('title-1')
    details.append(title)
    details.append(Gtk.Label(label='C64 Ultimate Control & Management', xalign=0, wrap=True))
    info = build_info()
    mode = ' · Portable' if portable_root() is not None else ''
    identity = Gtk.Label(label=f"Version {info['version']}\nBuild {info['build']}\n{platform.system()} · {platform.machine()}{mode}",
                         xalign=0, selectable=True, wrap=True)
    details.append(identity)
    details.append(Gtk.Label(label='Copyright © 2026 Bruce Marcus', xalign=0, wrap=True))
    links = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=4)
    for text, uri in [('GitHub', REPOSITORY), ('Quick-start guide', REPOSITORY+'/blob/main/docs/QUICK-START.md'),
                      ('GPL-3.0-or-later', 'https://www.gnu.org/licenses/gpl-3.0.html')]:
        links.insert(Gtk.LinkButton(uri=uri, label=text), -1)
    details.append(links)
    return scroll

def show_about(app):
    from .app_preferences import show_preferences
    return show_preferences(app, page=2)
