# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared packaged-runtime check for Debian, Windows, and macOS builds."""
import json
from pathlib import Path
import sys
import tempfile


def run(package_metadata, report_path):
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Gst', '1.0')
    from gi.repository import Gio, Gst, Gtk

    from .about import show_about
    from .credentials import Credentials
    from .gui import Browser
    from .platform_support import local_roots, portable_root, publish_new
    from .profiles import Preferences
    from .version import ASSETS, build_info

    root = portable_root()
    if root:
        config_name = ('argonaut-development'
                       if package_metadata.get('development') else 'argonaut')
        assert Preferences().path == root / 'Data' / config_name / 'config.json'
        assert getattr(Credentials(), 'session_only', False)
        preferences = Preferences()
        preferences.save()
        assert preferences.path.is_file()
    Gst.init(None)
    for name in ('appsrc', 'audioconvert', 'audioresample', 'autoaudiosink',
                 'webmmux', 'vp8enc', 'vorbisenc', 'videoconvert'):
        assert Gst.ElementFactory.find(name), name
    assert Gtk.init_check(), 'GTK could not initialize'
    with tempfile.TemporaryDirectory() as directory:
        app = Browser()
        app.preferences = Preferences(Path(directory) / 'config.json')
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        app.activate()
        assert app.window and local_roots()
        assert (ASSETS / 'about-background.png').is_file()
        assert (ASSETS / 'argonaut.png').is_file()
        expected_version = package_metadata.get('version', '1.5')
        identity = build_info()
        assert identity['version'] == expected_version
        assert 'unpackaged' not in identity['build']
        if package_metadata.get('development'):
            assert Preferences().path.parent.name == 'argonaut-development'
            assert getattr(Credentials(), 'session_only', False)
            from .app_preferences import show_preferences
            preferences_dialog = show_preferences(app)
            assert preferences_dialog.pages.get_n_pages() == 3
            assert not preferences_dialog.connections.model.get_editable()
            assert preferences_dialog.connections.fields['case_edition'].get_editable()
            assert app.streams_tab.text_return.get_active()
            assert isinstance(app.streams_tab.zoom, Gtk.Label)
            assert app.test_lab_tab.health_button.get_label() == 'Enable alerts'
            assert app.test_lab_tab.background_button.get_label() == 'Enable checks'
            saved_scale = app.preferences.app_options['preview_scale']
            app.streams_tab.set_zoom(300)
            app.streams_tab.apply_scale()
            assert app.preferences.app_options['preview_scale'] == saved_scale
            from .local_networks import local_networks
            assert isinstance(local_networks(), list)
            preferences_dialog.response(Gtk.ResponseType.CANCEL)
            assert app.lookup_action('quit').get_enabled()
        about = show_about(app)
        assert about is show_about(app)
        about.close()
        assert app.preferences_dialog is None
        app.activate_action('quit', None)
        assert app.window not in app.get_windows()
        source = Path(directory) / 'a'
        destination = Path(directory) / 'b'
        source.write_bytes(b'test')
        publish_new(source, destination)
        assert destination.read_bytes() == b'test'
    Path(report_path).write_text(json.dumps({
        'result': 'passed', 'platform': sys.platform,
        'version': package_metadata.get('version'),
        'build': package_metadata.get('build'),
    }, sort_keys=True) + '\n', encoding='utf-8')
