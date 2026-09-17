# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared deterministic package check for Debian, Windows, and macOS builds."""
import json
from pathlib import Path
import sys
import tempfile


class PackageSelfTestFailure(RuntimeError):
    """A named packaged-runtime check failed."""

    def __init__(self, check_id, message, error_kind='verification'):
        super().__init__(message)
        self.check_id = check_id
        self.error_kind = error_kind


def _require(condition, check_id, message, checks):
    if not condition:
        raise PackageSelfTestFailure(check_id, message)
    checks.append({'id': check_id, 'status': 'pass'})


def _write_report(path, metadata, result, checks, failure=None):
    report = {
        'schema': 1,
        'suite': 'package',
        'result': result,
        'platform': sys.platform,
        'version': metadata.get('version'),
        'build': metadata.get('build'),
        'checks': checks,
    }
    if failure is not None:
        report['failure'] = {
            'check_id': failure.check_id,
            'error_kind': failure.error_kind,
        }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.tmp')
    temporary.write_text(json.dumps(report, sort_keys=True) + '\n', encoding='utf-8')
    temporary.replace(destination)


def run(package_metadata, report_path):
    checks = []
    app = None
    try:
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
            _require(Preferences().path == root / 'Data' / config_name / 'config.json',
                     'package.portable_settings', 'Portable settings path is incorrect.',
                     checks)
            _require(getattr(Credentials(), 'session_only', False),
                     'package.portable_credentials',
                     'Portable credentials are not session-only.', checks)
            preferences = Preferences()
            preferences.save()
            _require(preferences.path.is_file(), 'package.portable_write',
                     'Portable settings could not be written.', checks)

        Gst.init(None)
        plugin_names = ('appsrc', 'audioconvert', 'audioresample', 'autoaudiosink',
                        'webmmux', 'vp8enc', 'vorbisenc', 'videoconvert')
        missing = [name for name in plugin_names if not Gst.ElementFactory.find(name)]
        _require(not missing, 'runtime.gstreamer',
                 'Required media plugins are unavailable.', checks)
        _require(Gtk.init_check(), 'runtime.gtk', 'GTK could not initialize.', checks)

        with tempfile.TemporaryDirectory() as directory:
            app = Browser()
            app.preferences = Preferences(Path(directory) / 'config.json')
            app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
            app.register(None)
            app.activate()
            _require(bool(app.window), 'ui.main_window',
                     'The main window did not open.', checks)
            _require(bool(local_roots()), 'filesystem.local_roots',
                     'No local file roots were found.', checks)
            _require((ASSETS / 'about-background.png').is_file() and
                     (ASSETS / 'argonaut.png').is_file(),
                     'package.assets', 'Required application artwork is missing.', checks)

            expected_version = package_metadata.get('version', '1.5')
            identity = build_info()
            _require(identity['version'] == expected_version and
                     'unpackaged' not in identity['build'],
                     'package.identity', 'Package build identity is incorrect.', checks)

            if package_metadata.get('development'):
                _require(Preferences().path.parent.name == 'argonaut-development',
                         'development.settings_isolation',
                         'Development settings are not isolated.', checks)
                _require(getattr(Credentials(), 'session_only', False),
                         'development.session_credentials',
                         'Development credentials are not session-only.', checks)
                from .app_preferences import show_preferences
                preferences_dialog = show_preferences(app)
                _require(preferences_dialog.pages.get_n_pages() == 3 and
                         not preferences_dialog.connections.model.get_editable() and
                         preferences_dialog.connections.fields[
                             'case_edition'].get_editable(),
                         'development.preferences_ui',
                         'Development Preferences layout is incorrect.', checks)
                _require(app.streams_tab.text_return.get_active() and
                         isinstance(app.streams_tab.zoom, Gtk.Label),
                         'development.streams_ui',
                         'Development Streams controls are incorrect.', checks)
                _require(app.test_lab_tab.health_button.get_label() ==
                         'Enable alerts' and
                         app.test_lab_tab.ai_test_result_button.get_label() ==
                         'View latest result' and
                         app.test_lab_tab.background_button.get_label() ==
                         'Enable checks',
                         'development.test_lab_controls',
                         'Test Lab automation controls are incorrect.', checks)
                _require(isinstance(app.test_lab_tab.box, Gtk.ScrolledWindow) and
                         app.test_lab_tab.box.get_policy()[1] ==
                         Gtk.PolicyType.ALWAYS and
                         app.test_lab_tab.ai_scroll.get_policy()[1] ==
                         Gtk.PolicyType.ALWAYS,
                         'development.test_lab_scroll',
                         'Test Lab cannot scroll vertically.', checks)
                saved_scale = app.preferences.app_options['preview_scale']
                app.streams_tab.set_zoom(300)
                app.streams_tab.apply_scale()
                _require(app.preferences.app_options['preview_scale'] == saved_scale,
                         'development.preference_isolation',
                         'The package check changed saved preview settings.', checks)
                from .local_networks import local_networks
                _require(isinstance(local_networks(), list),
                         'network.enumeration',
                         'Local network enumeration did not return a list.', checks)
                preferences_dialog.response(Gtk.ResponseType.CANCEL)
                _require(app.lookup_action('quit').get_enabled(), 'ui.quit_action',
                         'The Quit action is unavailable.', checks)
            else:
                from .test_lab_access import enabled as test_lab_enabled
                _require(not hasattr(app, 'test_lab_tab') and
                         not test_lab_enabled(app.preferences),
                         'stable.developer_mode_default_off',
                         'Stable Developer Mode was not off by default.', checks)
                app.preferences.app_options['developer_mode'] = True
                _require(test_lab_enabled(app.preferences),
                         'stable.developer_mode_opt_in',
                         'Stable Developer Mode could not be enabled.', checks)

            about = show_about(app)
            _require(about is show_about(app), 'ui.about_singleton',
                     'About opened more than one window.', checks)
            about.close()
            _require(app.preferences_dialog is None, 'ui.dialog_cleanup',
                     'A dialog remained registered after closing.', checks)
            app.activate_action('quit', None)
            _require(app.window not in app.get_windows(), 'ui.quit',
                     'The main window remained open after Quit.', checks)

            source = Path(directory) / 'a'
            destination = Path(directory) / 'b'
            source.write_bytes(b'test')
            publish_new(source, destination)
            _require(destination.read_bytes() == b'test',
                     'filesystem.publication',
                     'A newly published file did not match its source.', checks)
    except Exception as error:
        failure = (error if isinstance(error, PackageSelfTestFailure)
                   else PackageSelfTestFailure('package.unexpected',
                                               'Unexpected package failure.',
                                               type(error).__name__))
        checks.append({'id': failure.check_id, 'status': 'fail'})
        _write_report(report_path, package_metadata, 'failed', checks, failure)
        raise failure from error
    finally:
        if app is not None:
            app.quit()

    _write_report(report_path, package_metadata, 'passed', checks)
