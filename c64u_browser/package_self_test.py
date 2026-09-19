# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared deterministic package check for Debian, Windows, and macOS builds."""
import json
from pathlib import Path
import sys
import tempfile
import time


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
        from gi.repository import Gio, GLib, Gst, Gtk

        from .about import show_about
        from .credentials import Credentials
        from .disk_image import D64Image, D71Image, D81Image, sectors_on_track
        from .disk_image_edit import D64EditSession, create_blank_d64_image
        from .disk_image_dialog import DiskImageDialog
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
            _require(app.quick_connect_button.get_label() == 'Quick Connect' and
                     not app.disconnect_button.get_sensitive() and
                     app.new_d64_button.get_tooltip_text() == 'New D64 disk…' and
                     app.remote_new_d64_button.get_tooltip_text() ==
                     'New D64 disk on C64U…' and
                     not app.remote_new_d64_button.get_sensitive() and
                     app.tabs.get_tab_label_text(app.settings_tab.box) ==
                     'Ultimate Menu',
                     'ui.quick_connect',
                     'Main-window connection or disk controls are incorrect.', checks)
            _require(app.file_pane_labels[True].get_text() == 'Local files · Active' and
                     app.file_pane_labels[False].get_text() == 'C64 Ultimate files' and
                     app.file_pane_boxes[True].has_css_class(
                         'argonaut-file-pane-active') and
                     app.file_pane_boxes[False].has_css_class(
                         'argonaut-file-pane-inactive'),
                     'ui.active_file_pane',
                     'The active file pane is not identified visibly.', checks)
            app.populate(app.llist, [
                ('SOURCE COPY', False, 1), ('DESTINATION COPY', False, 1)])
            app.select_names(
                app.llist, ('SOURCE COPY', 'DESTINATION COPY', 'NOT PRESENT'))
            _require(
                tuple(row.item[0] for row in app.llist.get_selected_rows()) ==
                ('SOURCE COPY', 'DESTINATION COPY'),
                'ui.copy_selection',
                'Completed copy items could not be selected after refresh.', checks)
            app.refresh_local()
            blank = create_blank_d64_image('PACKAGE BLANK', 'P1')
            _require(blank.directory().blocks_free == 664 and
                     not blank.directory().entries and
                     blank.validate().standard_compatible,
                     'disk.blank_d64',
                     'Blank D64 creation is not structurally valid.', checks)
            blank_id = create_blank_d64_image('C64U STYLE', '')
            _require(blank_id.directory().disk_id == '' and
                     blank_id.validate().standard_compatible,
                     'disk.blank_d64_optional_id',
                     'A C64U-style blank disk ID is not structurally valid.', checks)
            rel_data = bytearray(blank.source_bytes)
            sector_number = lambda track, sector: sum(
                sectors_on_track(value) for value in range(1, track)) + sector
            rel_data_offset = sector_number(17, 0) * 256
            rel_side_offset = sector_number(17, 10) * 256
            rel_bam = sector_number(18, 0) * 256 + 4 + 16 * 4
            for sector in (0, 10):
                rel_data[rel_bam] -= 1
                rel_data[rel_bam + 1 + sector // 8] &= ~(1 << (sector % 8))
            rel_data[rel_data_offset:rel_data_offset + 3] = bytes((0, 2, 0x41))
            rel_data[rel_side_offset:rel_side_offset + 18] = bytes(
                (0, 17, 0, 40, 17, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 17, 0))
            rel_directory = sector_number(18, 1) * 256 + 2
            rel_data[rel_directory:rel_directory + 30] = bytes(30)
            rel_data[rel_directory:rel_directory + 3] = bytes((0x84, 17, 0))
            rel_data[rel_directory + 3:rel_directory + 19] = (
                b'PACKAGE REL' + b'\xa0' * 5)
            rel_data[rel_directory + 19:rel_directory + 22] = bytes((17, 10, 40))
            rel_data[rel_directory + 28:rel_directory + 30] = bytes((2, 0))
            rel_image = D64Image(rel_data)
            rel_session = D64EditSession(rel_image)
            rel_entry = rel_session.image.directory().entries[0]
            rel_session.remove(rel_entry)
            _require(rel_image.validate().standard_compatible and
                     rel_session.image.directory().blocks_free == 664 and
                     not rel_session.image.directory().entries,
                     'disk.rel_remove',
                     'REL data and side sectors were not removed safely.', checks)
            create_dialog = app.new_d64()
            create_entries = app.d64_create_entries
            _require(create_dialog.get_title() == 'Create blank D64 disk' and
                     tuple(entry.get_text() for entry in create_entries) ==
                     ('new-disk.d64', 'UNTITLED', ''),
                     'ui.blank_d64',
                     'Blank D64 creation controls are incorrect.', checks)
            create_entries[1].set_text('new disk')
            create_entries[2].set_text('a1')
            _require(tuple(entry.get_text() for entry in create_entries[1:]) ==
                     ('NEW DISK', 'A1'),
                     'ui.c64_name_uppercase',
                     'C64-visible disk text did not show its transmitted case.', checks)
            create_dialog.response(Gtk.ResponseType.CANCEL)
            rel_dialog = DiskImageDialog(app, 'Package REL check', rel_image)
            rel_row = rel_dialog.listing.get_first_child()
            rel_dialog.listing.select_row(rel_row)
            rel_dialog.extract()
            extract_folder = rel_dialog.chooser.get_current_folder()
            deadline = time.monotonic() + 3
            while extract_folder is None and time.monotonic() < deadline:
                while GLib.MainContext.default().pending():
                    GLib.MainContext.default().iteration(False)
                time.sleep(0.01)
                extract_folder = rel_dialog.chooser.get_current_folder()
            _require(extract_folder is not None and
                     Path(extract_folder.get_path()).resolve() == app.local.resolve(),
                     'ui.disk_extract_folder',
                     'Extract selected did not open in the visible local folder.', checks)
            rel_dialog.chooser.emit('response', Gtk.ResponseType.CANCEL)
            _require(rel_dialog.remove_button.get_sensitive(), 'ui.rel_remove',
                     'A valid unlocked REL file cannot be staged for removal.', checks)
            rel_dialog.dialog.destroy()
            image_data = bytearray(174848)
            header_offset = sum(sectors_on_track(track)
                                for track in range(1, 18)) * 256
            directory_offset = header_offset + 256
            image_data[header_offset:header_offset + 3] = bytes((18, 1, 0x41))
            image_data[header_offset + 0x90:header_offset + 0xa0] = (
                b'PACKAGE TEST' + b'\xa0' * 4)
            image_data[header_offset + 0xa2:header_offset + 0xa4] = b'64'
            image_data[header_offset + 0xa5:header_offset + 0xa7] = b'2A'
            image_data[directory_offset:directory_offset + 2] = bytes((0, 255))
            disk_dialog = DiskImageDialog(
                app, 'Package D64 check', D64Image(blank.source_bytes))
            _require(disk_dialog.listing.get_first_child() is None and
                     disk_dialog.status.get_text().startswith('Source image is unchanged.') and
                     disk_dialog.add_button.get_sensitive() and
                     disk_dialog.rename_button.get_icon_name() ==
                     'document-edit-symbolic' and
                     disk_dialog.save_button.get_label() == 'Save image as…' and
                     disk_dialog.discard_button.get_label() == 'Discard changes' and
                     not disk_dialog.save_button.get_sensitive(),
                     'ui.disk_directory',
                     'The staged D64 directory window is incorrect.', checks)
            disk_dialog.add_file()
            add_folder = disk_dialog.chooser.get_current_folder()
            deadline = time.monotonic() + 3
            while add_folder is None and time.monotonic() < deadline:
                while GLib.MainContext.default().pending():
                    GLib.MainContext.default().iteration(False)
                time.sleep(0.01)
                add_folder = disk_dialog.chooser.get_current_folder()
            _require(add_folder is not None and
                     Path(add_folder.get_path()).resolve() == app.local.resolve(),
                     'ui.disk_add_folder',
                     'Add file did not open in the visible local folder.', checks)
            disk_dialog.chooser.emit('response', Gtk.ResponseType.CANCEL)
            disk_dialog._batch_add_review([
                ('ONE.PRG', b'package one', 'SAVE ONE', 'PRG'),
                ('TWO.SEQ', b'package two', 'SAVE TWO', 'SEQ'),
            ])
            _require(disk_dialog.prompt is not None and
                     disk_dialog.prompt.get_title() == 'Review files to add',
                     'ui.disk_add_review',
                     'A batch import did not open one review dialog.', checks)
            disk_dialog.prompt.response(Gtk.ResponseType.OK)
            added = disk_dialog.session.image.directory().entries
            _require([(entry.name, entry.file_type) for entry in added] ==
                     [('SAVE ONE', 'PRG'), ('SAVE TWO', 'SEQ')] and
                     len(disk_dialog.session.changes) == 2,
                     'ui.disk_add_batch',
                     'The reviewed import batch was not staged together.', checks)
            disk_dialog.save_copy()
            save_folder = disk_dialog.chooser.get_current_folder()
            deadline = time.monotonic() + 3
            while save_folder is None and time.monotonic() < deadline:
                while GLib.MainContext.default().pending():
                    GLib.MainContext.default().iteration(False)
                time.sleep(0.01)
                save_folder = disk_dialog.chooser.get_current_folder()
            _require(save_folder is not None and
                     Path(save_folder.get_path()).resolve() == app.local.resolve(),
                     'ui.disk_save_folder',
                     'Save as did not open in the visible local folder.', checks)
            disk_dialog.chooser.emit('response', Gtk.ResponseType.CANCEL)
            activated = []
            disk_dialog._name_prompt(
                'Package filename check', 'TEST', 'Add file',
                lambda name, kind: activated.append((name, kind)), 'PRG')
            disk_dialog.name_entry.emit('activate')
            _require(activated == [('TEST', 'PRG')] and disk_dialog.prompt is None,
                     'ui.disk_name_return',
                     'Return does not activate the disk filename action.', checks)
            disk_dialog.dialog.destroy()
            app.drives_tab.select_image('/USB2/PACKAGE.D64')
            _require(app.drives_tab.cards['a']['path'].get_text() ==
                     '/USB2/PACKAGE.D64' and
                     'selected for Drive A' in app.drives_tab.message.get_text(),
                     'ui.disk_mount_selection',
                     'A C64U disk image could not be prepared for Drive A.', checks)
            d71_data = bytearray(349696)
            d71_data[header_offset:header_offset + 4] = bytes((18, 1, 0x41, 0x80))
            d71_data[header_offset + 0x90:header_offset + 0xa0] = (
                b'PACKAGE D71' + b'\xa0' * 5)
            d71_data[header_offset + 0xa2:header_offset + 0xa4] = b'71'
            d71_data[header_offset + 0xa5:header_offset + 0xa7] = b'2A'
            d71_data[directory_offset:directory_offset + 2] = bytes((0, 255))
            d71_dialog = DiskImageDialog(
                app, 'Package D71 check', D71Image(d71_data))
            _require(d71_dialog.dialog.get_title() == 'D71 disk directory' and
                     d71_dialog.listing.get_first_child() is None and
                     d71_dialog.status.get_text().startswith('Source image is unchanged.') and
                     d71_dialog.add_button.get_sensitive() and
                     d71_dialog.session.format_name == 'D71',
                     'ui.d71_directory',
                     'The staged D71 directory window is incorrect.', checks)
            d71_dialog.dialog.destroy()
            d81_data = bytearray(819200)
            d81_header = (40 - 1) * 40 * 256
            d81_directory = d81_header + 3 * 256
            d81_data[d81_header:d81_header + 3] = bytes((40, 3, 0x44))
            d81_data[d81_header + 4:d81_header + 20] = (
                b'PACKAGE D81' + b'\xa0' * 5)
            d81_data[d81_header + 0x16:d81_header + 0x18] = b'81'
            d81_data[d81_header + 0x19:d81_header + 0x1b] = b'3D'
            d81_data[d81_header + 256:d81_header + 262] = bytes(
                (40, 2, 0x44, 0xbb, 0x38, 0x31))
            d81_data[d81_header + 512:d81_header + 518] = bytes(
                (0, 255, 0x44, 0xbb, 0x38, 0x31))
            d81_data[d81_directory:d81_directory + 2] = bytes((0, 255))
            d81_entry = d81_directory + 2
            d81_data[d81_entry:d81_entry + 3] = bytes((0x85, 80, 0))
            d81_data[d81_entry + 3:d81_entry + 19] = (
                b'PARTITION' + b'\xa0' * 7)
            d81_data[d81_entry + 28:d81_entry + 30] = bytes((10, 0))
            d81_dialog = DiskImageDialog(
                app, 'Package D81 check', D81Image(d81_data))
            d81_row = d81_dialog.listing.get_first_child()
            d81_dialog.listing.select_row(d81_row)
            _require(d81_dialog.dialog.get_title() == 'D81 disk directory' and
                     'CBM partition' in d81_row.get_child().get_text() and
                     not d81_dialog.extract_button.get_sensitive() and
                     not d81_dialog.remove_button.get_sensitive() and
                     d81_dialog.status.get_text().startswith('Source image is unchanged.') and
                     d81_dialog.add_button.get_sensitive() and
                     d81_dialog.session.format_name == 'D81',
                     'ui.d81_directory',
                     'The staged D81 directory window is incorrect.', checks)
            d81_dialog.dialog.destroy()
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
                         isinstance(app.streams_tab.zoom, Gtk.Label) and
                         not app.preferences.app_options['replay_enabled'] and
                         app.streams_tab.replay_button.get_label() ==
                         'Save recent 30 seconds…' and
                         not app.streams_tab.replay_button.get_sensitive(),
                         'development.streams_ui',
                         'Development Streams controls are incorrect.', checks)
                app.streams_tab.text_input.set_text('print "hello"')
                _require(app.streams_tab.text_input.get_text() == 'PRINT "HELLO"',
                         'development.streams_uppercase',
                         'Streams does not preview the uppercase text sent to the C64.',
                         checks)
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
                         Gtk.PolicyType.ALWAYS and
                         all(control.get_halign() == Gtk.Align.START for control in (
                             app.test_lab_tab.schedule_check,
                             app.test_lab_tab.auto_analyze,
                             app.test_lab_tab.unattended_ai)),
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
