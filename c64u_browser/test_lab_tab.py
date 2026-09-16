# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Development-only GTK view for deterministic Test Lab results."""
from datetime import datetime
import json
import os
from pathlib import Path
import time

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

from .api import BrowserError
from .test_lab import run_default_checks
from .test_lab_probe import run_diagnosis_probe
from .hardware_checks import run_hardware_checks
from .ai_analysis import analyze_failures
from .ai_presentation import readable_diagnosis
from .ai_gateway import AIGateway, GatewayConfig, GatewayError
from .c64_ai_launch import launch_c64_ai
from .c64_ai_bridge_control import (
    activate_bridge, bridge_status, enable_health_monitor,
    health_monitor_status, setup_bridge,
)
from .c64_ai_install import install_and_pair_c64_ai
from .test_lab_history import run_with_history
from .test_lab_presentation import (
    check_details, comparison_changes, comparison_summary, summary,
)
from .test_lab_schedule import HardwareSchedule
from .test_lab_saved import (
    preferred_record, saved_comparison, saved_hardware_results, saved_run_label,
    saved_status,
)
from .test_lab_auto_analysis import (
    CACHE_NAME, CONFIG_NAME, load_local_config, save_local_config,
    saved_diagnosis,
)


class TestLabTab:
    def __init__(self, app):
        self.app = app
        self.report = None
        self.comparison = None
        self.chooser = None
        self.analysis = None
        self.loaded_from_history = False
        self.saved_context = ''
        self.saved_records = []
        self.schedule = HardwareSchedule()
        self.schedule_source = None
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.box.append(Gtk.Label(
            label='Offline checks use simulations. C64U checks read the connected device without changing settings, drives, or files.',
            xalign=0, wrap=True))
        self.box.append(Gtk.Label(
            label=(getattr(app, 'operation_log_error', None) or
                   'Detailed C64U activity is saved privately while Development is open.'),
            xalign=0, wrap=True))
        self.saved_overview = Gtk.Label(label='No saved C64U results loaded.',
                                        xalign=0, wrap=True)
        self.box.append(self.saved_overview)
        saved_row = Gtk.Box(spacing=8)
        self.box.append(saved_row)
        saved_row.append(Gtk.Label(label='Saved C64U:', xalign=0))
        self.saved_choice = Gtk.DropDown.new_from_strings(['No bound C64Us'])
        self.saved_choice.set_hexpand(True)
        self.saved_choice.connect('notify::selected', self.history_selected)
        saved_row.append(self.saved_choice)
        self.saved_button = app.button(saved_row, 'View latest saved result',
                                       self.show_history)
        self.verified_button = app.button(saved_row, 'View last verified result',
                                          self.show_verified_history)
        app.button(saved_row, 'Refresh saved results', self.refresh_saved_history)
        self.saved_button.set_sensitive(False)
        self.verified_button.set_sensitive(False)
        archive_row = Gtk.Box(spacing=8)
        self.box.append(archive_row)
        archive_row.append(Gtk.Label(label='Saved runs:', xalign=0))
        self.saved_run_choice = Gtk.DropDown.new_from_strings(['No saved runs'])
        self.saved_run_choice.set_hexpand(True)
        archive_row.append(self.saved_run_choice)
        self.saved_run_button = app.button(archive_row, 'View selected run',
                                           self.show_selected_history)
        self.saved_run_button.set_sensitive(False)
        toolbar = Gtk.Box(spacing=8)
        self.box.append(toolbar)
        self.run_button = app.button(toolbar, 'Run offline checks', self.run)
        self.hardware_button = app.button(toolbar, 'Run C64U checks', self.run_hardware)
        self.export_button = app.button(toolbar, 'Export JSON…', self.export)
        self.export_button.set_sensitive(False)
        self.analyze_button = app.button(toolbar, 'Explain failures', self.analyze)
        self.analyze_button.set_sensitive(False)
        self.probe_button = app.button(toolbar, 'Test local AI (simulation)',
                                       self.run_probe)
        self.probe_button.set_tooltip_text(
            'Simulate a failed FTP login and ask only the local model to explain it.')
        self.c64_ai_button = app.button(toolbar, 'Launch C64 AI', self.launch_c64_ai)
        self.c64_ai_button.set_tooltip_text(
            'Enable the Command Interface for this session and start the paired USB2 client.')
        bridge_row = Gtk.Box(spacing=8)
        self.box.append(bridge_row)
        bridge_row.append(Gtk.Label(label='C64 AI bridge:', xalign=0))
        self.bridge_status = Gtk.Label(
            label='Checking local bridge…', xalign=0, hexpand=True, wrap=True)
        bridge_row.append(self.bridge_status)
        app.button(bridge_row, 'Refresh bridge', self.refresh_bridge_status)
        self.activate_bridge_button = app.button(
            bridge_row, 'Restart bridge', self.activate_bridge)
        self.pair_bridge_button = app.button(
            bridge_row, 'Install & pair C64U', self.pair_connected_c64)
        self.pair_bridge_button.set_tooltip_text(
            'Verify the connected C64U, install its matching USB2 client, and pair its fixed address.')
        self.bridge_path = self.app.preferences.path.parent / 'test-lab' / 'c64-ai-bridge.json'
        self.bridge_loaded = False
        self.bridge_state = 'unknown'
        health_row = Gtk.Box(spacing=8)
        self.box.append(health_row)
        health_row.append(Gtk.Label(label='Automatic health alerts:', xalign=0))
        self.health_status = Gtk.Label(
            label='Checking…', xalign=0, hexpand=True, wrap=True)
        health_row.append(self.health_status)
        self.health_button = app.button(
            health_row, 'Enable alerts', self.enable_health_alerts)
        self.schedule_check = Gtk.CheckButton(label='Run C64U checks every 30 minutes while connected')
        self.schedule_check.connect('toggled', self.schedule_toggled)
        self.box.append(self.schedule_check)
        self.summary = Gtk.Label(label='No run yet.', xalign=0, wrap=True)
        self.box.append(self.summary)
        self.changes = Gtk.Label(label='', xalign=0, wrap=True)
        self.box.append(self.changes)
        ai_options = Gtk.Box(spacing=8)
        self.box.append(ai_options)
        ai_options.append(Gtk.Label(label='AI:', xalign=0))
        self.provider = Gtk.DropDown.new_from_strings(['Local Ollama', 'OpenAI cloud'])
        ai_options.append(self.provider)
        self.model = Gtk.Entry(placeholder_text='Model name', hexpand=True)
        self.model.set_text(os.environ.get('ARGONAUT_AI_MODEL', ''))
        ai_options.append(self.model)
        self.auto_analyze = Gtk.CheckButton(label='Explain failed runs automatically')
        self.box.append(self.auto_analyze)
        self.unattended_ai_path = self.app.preferences.path.parent / 'test-lab' / CONFIG_NAME
        local_config_error = ''
        try:
            local_config = load_local_config(self.unattended_ai_path)
        except (GatewayError, OSError, ValueError):
            local_config = None
            local_config_error = 'Saved unattended local AI setting could not be read.'
        local_row = Gtk.Box(spacing=8)
        self.box.append(local_row)
        self.unattended_ai = Gtk.CheckButton(
            label='Explain unattended C64U failures with local AI')
        self.unattended_ai.set_active(local_config is not None)
        local_row.append(self.unattended_ai)
        self.unattended_model = Gtk.Entry(
            placeholder_text='Downloaded Ollama model', hexpand=True)
        if local_config is not None:
            self.unattended_model.set_text(local_config.model)
            if not self.model.get_text():
                self.model.set_text(local_config.model)
        local_row.append(self.unattended_model)
        app.button(local_row, 'Save local AI setting', self.save_unattended_ai)
        self.unattended_status = Gtk.Label(label=local_config_error,
                                           xalign=0, wrap=True)
        self.box.append(self.unattended_status)
        self.box.append(Gtk.Label(
            label='Only failed check details are sent for AI analysis. OpenAI cloud uses the OPENAI_API_KEY environment variable; the key is never saved in reports.',
            xalign=0, wrap=True))
        self.ai_status = Gtk.Label(label='', xalign=0, wrap=True)
        self.box.append(self.ai_status)
        panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        panes.set_position(300)
        self.box.append(panes)
        self.checks = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.checks.connect('row-selected', self.selected)
        left = Gtk.ScrolledWindow(min_content_width=220)
        left.set_child(self.checks)
        panes.set_start_child(left)
        self.details = Gtk.TextView(editable=False, cursor_visible=False,
                                    monospace=True, wrap_mode=Gtk.WrapMode.WORD)
        right = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        right.set_child(self.details)
        panes.set_end_child(right)
        self.ai_details = Gtk.TextView(editable=False, cursor_visible=False,
                                       wrap_mode=Gtk.WrapMode.WORD)
        ai_scroll = Gtk.ScrolledWindow(min_content_height=110)
        ai_scroll.set_child(self.ai_details)
        self.box.append(ai_scroll)
        self.app.tabs.connect('switch-page', self.shown)

    def save_unattended_ai(self):
        model = (self.unattended_model.get_text().strip()
                 if self.unattended_ai.get_active() else None)
        try:
            save_local_config(self.unattended_ai_path, model)
        except (GatewayError, OSError) as exc:
            self.unattended_status.set_text(str(exc))
            return
        self.unattended_status.set_text(
            'Unattended local explanations enabled for the next fleet run.'
            if model is not None else 'Unattended local explanations disabled.')

    def shown(self, _, page, _index):
        if page == self.box:
            self.refresh_history(auto_load=True)
            if not self.bridge_loaded:
                self.refresh_bridge_status()

    def show_bridge_status(self, status):
        self.bridge_loaded = True
        self.bridge_state = status.state
        self.bridge_status.set_text(status.message)
        addresses = ', '.join(status.allowed_clients) or 'No paired addresses'
        self.bridge_status.set_tooltip_text('Paired addresses: ' + addresses)
        self.pair_bridge_button.set_label(
            'Set up & install C64 AI' if status.state == 'setup'
            else 'Install & pair C64U')
        self.connection_changed()
        self.activate_bridge_button.set_label(
            'Start bridge' if status.state == 'stopped' else
            'Retry bridge' if status.state == 'network_changed' else
            'Restart bridge')
        self.activate_bridge_button.set_sensitive(
            status.state in ('ready', 'stopped', 'network_changed'))

    def show_health_status(self, status):
        self.health_status.set_text(status.message)
        self.health_button.set_sensitive(status.state != 'ready')

    def connection_changed(self):
        connected = (self.app.client is not None
                     and not getattr(self.app, 'offline_message', None)
                     and self.app.active_profile is not None)
        self.pair_bridge_button.set_sensitive(
            connected and self.bridge_state in (
                'ready', 'stopped', 'setup', 'model_unavailable', 'model_missing'))

    def refresh_bridge_status(self):
        if self.app.busy:
            return
        self.bridge_status.set_text('Checking local bridge…')
        self.health_status.set_text('Checking…')
        def done(statuses):
            self.show_bridge_status(statuses[0])
            self.show_health_status(statuses[1])
            self.app.status.set_text('C64 AI bridge and health alerts refreshed.')

        self.app.run(
            lambda: (bridge_status(self.bridge_path, check_model=True),
                     health_monitor_status()), done)

    def enable_health_alerts(self):
        self.health_status.set_text('Enabling automatic health alerts…')
        def done(status):
            self.show_health_status(status)
            self.app.status.set_text('Automatic C64 AI health alerts are on.')
        self.app.run(enable_health_monitor, done)

    def activate_bridge(self):
        def done(status):
            self.show_bridge_status(status)
            self.app.status.set_text('The local C64 AI bridge is ready.')

        def task():
            activate_bridge(self.bridge_path)
            return bridge_status(self.bridge_path, check_model=True)

        self.app.run(task, done)

    def pair_connected_c64(self):
        client = None if getattr(self.app, 'offline_message', None) else self.app.client
        profile = self.app.active_profile if client is not None else None
        model = (self.unattended_model.get_text().strip()
                 or self.model.get_text().strip() or 'gemma3:4b')

        def task():
            if client is None or profile is None:
                raise BrowserError('Connect an identity-bound C64U before pairing it.')
            profile.verify_identity(client.test_connection(), require_bound=True)
            if not self.bridge_path.exists():
                setup_bridge(self.bridge_path, model, profile.host)
            return install_and_pair_c64_ai(
                client, self.bridge_path, profile.host)

        def done(result):
            self.show_bridge_status(result.bridge)
            action = ('installed and paired' if result.client.installed
                      else 'verified and paired')
            self.app.status.set_text(
                f'The C64 AI client was {action}; the local bridge is ready.')

        self.app.run(task, done)

    def refresh_saved_history(self):
        self.refresh_history(auto_load=True)

    def refresh_history(self, auto_load=False):
        self.saved_records = saved_hardware_results(self.app.preferences)
        if not self.saved_records:
            self.saved_overview.set_text('No identity-bound Development C64U profiles.')
            self.saved_choice.set_model(Gtk.StringList.new(['No bound C64Us']))
            self.saved_button.set_sensitive(False)
            self.verified_button.set_sensitive(False)
            self.saved_run_choice.set_model(Gtk.StringList.new(['No saved runs']))
            self.saved_run_button.set_sensitive(False)
            return
        labels = [f"{record['profile'].name} — {saved_status(record)}"
                  for record in self.saved_records]
        self.saved_overview.set_text('Latest saved C64U results: ' +
                                     ' · '.join(labels))
        self.saved_choice.set_model(Gtk.StringList.new(labels))
        selected = preferred_record(self.saved_records,
                                    self.app.preferences.selected_id)
        self.saved_choice.set_selected(selected)
        self.history_selected()
        if auto_load:
            self.show_history()

    def history_selected(self, *_args):
        selected = self.saved_choice.get_selected()
        record = (self.saved_records[selected]
                  if selected < len(self.saved_records) else None)
        self.saved_button.set_sensitive(bool(record and record['recent']))
        self.verified_button.set_sensitive(bool(record and record['verified']))
        runs = record['runs'] if record else []
        labels = ([saved_run_label(item, index) for index, item in enumerate(runs)]
                  if runs else ['No saved runs'])
        self.saved_run_choice.set_model(Gtk.StringList.new(labels))
        self.saved_run_choice.set_selected(0)
        self.saved_run_button.set_sensitive(bool(runs))

    def show_selected_history(self):
        selected = self.saved_choice.get_selected()
        if selected >= len(self.saved_records):
            return
        record = self.saved_records[selected]
        run_index = self.saved_run_choice.get_selected()
        if run_index < len(record['runs']):
            report = record['runs'][run_index]['report']
            self.show_saved(report, record['profile'].name,
                            'Selected saved C64U result', record['profile'].id,
                            record)

    def show_history(self):
        selected = self.saved_choice.get_selected()
        if selected < len(self.saved_records):
            record = self.saved_records[selected]
            if record['recent']:
                self.show_saved(record['recent'], record['profile'].name,
                                'Latest saved C64U result', record['profile'].id,
                                record)

    def show_verified_history(self):
        selected = self.saved_choice.get_selected()
        if selected < len(self.saved_records):
            record = self.saved_records[selected]
            if record['verified']:
                self.show_saved(record['verified'], record['profile'].name,
                                'Last verified C64U result', record['profile'].id,
                                record)

    def show_saved(self, report, name, source, profile_id, record):
        self.report = report
        self.comparison = saved_comparison(record, report)
        self.loaded_from_history = True
        self.saved_context = f'{source} for {name}. Verdicts come from saved checks.'
        if report['status'] == 'skip':
            self.saved_context += ' This skipped run cannot confirm recovery.'
        else:
            self.saved_context += ' ' + comparison_summary(self.comparison)
            changes = comparison_changes(self.comparison, report)
            if changes:
                self.saved_context += ' ' + changes
        self.analysis = None
        self.ai_status.set_text('')
        self.ai_details.get_buffer().set_text('')
        try:
            self.render()
            diagnosis = saved_diagnosis(
                self.unattended_ai_path.parent / CACHE_NAME, profile_id, report)
            if diagnosis:
                self.ai_status.set_text('Saved unattended local AI diagnosis:')
                self.ai_details.get_buffer().set_text(readable_diagnosis(diagnosis))
        except (KeyError, TypeError, ValueError, IndexError):
            self.report = None
            while self.checks.get_first_child():
                self.checks.remove(self.checks.get_first_child())
            self.details.get_buffer().set_text('')
            self.summary.set_text('Saved report is incomplete or damaged.')
            self.changes.set_text('')
            self.export_button.set_sensitive(False)
            self.analyze_button.set_sensitive(False)

    def run(self):
        self._run_checks(run_default_checks)

    def run_probe(self):
        self._run_checks(run_diagnosis_probe, probe=True)

    def run_hardware(self):
        client = None if getattr(self.app, 'offline_message', None) else self.app.client
        profile = self.app.active_profile if client is not None else None
        self._run_checks(lambda: run_hardware_checks(client, profile),
                         profile_id=profile.id if profile else None)

    def launch_c64_ai(self):
        client = None if getattr(self.app, 'offline_message', None) else self.app.client
        profile = self.app.active_profile if client is not None else None
        self.app.status.set_text('Starting the paired C64 AI client…')

        def done(result):
            message = 'C64 AI client started from USB2.'
            if result['command_interface_changed']:
                message += ' Command Interface enabled for this session.'
            self.app.status.set_text(message)

        self.app.run(lambda: launch_c64_ai(client, profile), done)

    def schedule_toggled(self, button):
        if button.get_active():
            self.schedule.enable(time.monotonic())
            if self.schedule_source is None:
                self.schedule_source = GLib.timeout_add_seconds(60, self.schedule_tick)
        else:
            self.schedule.disable()

    def schedule_tick(self):
        if not self.schedule.enabled:
            self.schedule_source = None
            return False
        profile = self.app.active_profile
        connected = (self.app.client is not None
                     and not getattr(self.app, 'offline_message', None)
                     and profile is not None
                     and bool(profile.device_id or profile.device_mac))
        now = time.monotonic()
        if self.schedule.due(now, connected, self.app.busy):
            self.schedule.mark_run(now)
            self.run_hardware()
        return True

    def stop_schedule(self):
        self.schedule.disable()
        if self.schedule_source is not None:
            GLib.source_remove(self.schedule_source)
            self.schedule_source = None

    def _run_checks(self, runner, profile_id=None, probe=False):
        if self.app.busy:
            return
        self.summary.set_text('Simulating an FTP login failure…' if probe
                              else 'Running checks…')
        self.run_button.set_sensitive(False)
        self.hardware_button.set_sensitive(False)
        self.probe_button.set_sensitive(False)

        def done(result):
            self.run_button.set_sensitive(True)
            self.hardware_button.set_sensitive(True)
            self.probe_button.set_sensitive(True)
            if not isinstance(result, dict):
                self.summary.set_text('Could not run checks. See the status message below.')
                return
            self.report = result['report']
            self.comparison = result['comparison']
            self.loaded_from_history = probe
            self.saved_context = (
                'Expected simulated failure. No C64U was contacted and this probe was not saved.'
                if probe else '')
            self.analysis = None
            self.ai_status.set_text('')
            self.ai_details.get_buffer().set_text('')
            self.render()
            if not probe:
                self.refresh_history()
            message = ('Local AI probe: expected simulated FTP login failure.'
                       if probe else 'Test Lab: ' + summary(self.report))
            if not probe and not result['saved']:
                message += ' · Run history could not be saved.'
            self.app.status.set_text(message)
            if probe and self.report['status'] == 'fail':
                model = (self.unattended_model.get_text().strip()
                         if self.unattended_ai.get_active() else
                         self.model.get_text().strip())
                self._analyze_with_gateway('ollama', model)
            elif self.report['status'] == 'fail' and self.auto_analyze.get_active():
                self.analyze()

        def task():
            try:
                if probe:
                    return {'report': runner(), 'comparison': None, 'saved': False}
                return run_with_history(self.app.preferences.path, runner,
                                        profile_id=profile_id)
            except Exception as exc:
                return exc

        self.app.run(task, done)

    def render(self):
        while self.checks.get_first_child():
            self.checks.remove(self.checks.get_first_child())
        report = self.report
        self.summary.set_text(summary(report))
        self.changes.set_text(self.saved_context if self.loaded_from_history
                              else comparison_summary(self.comparison))
        self.export_button.set_sensitive(True)
        self.analyze_button.set_sensitive(report['status'] == 'fail')
        for index, check in enumerate(report['checks']):
            row = Gtk.ListBoxRow()
            row.check_index = index
            marker = {'pass': '✓', 'fail': '✕', 'skip': '–'}[check['status']]
            label = Gtk.Label(label=f"{marker}  {check['title']}",
                              xalign=0, wrap=True)
            label.set_margin_top(7)
            label.set_margin_bottom(7)
            row.set_child(label)
            self.checks.append(row)
        if report['checks']:
            self.checks.select_row(self.checks.get_row_at_index(0))

    def selected(self, _, row):
        text = (check_details(self.report['checks'][row.check_index])
                if row is not None and self.report else '')
        self.details.get_buffer().set_text(text)

    def analyze(self):
        provider = 'ollama' if self.provider.get_selected() == 0 else 'openai'
        self._analyze_with_gateway(provider, self.model.get_text().strip())

    def _analyze_with_gateway(self, provider, model):
        if self.app.busy or self.report is None or self.report['status'] != 'fail':
            return
        try:
            gateway = AIGateway(GatewayConfig(provider, model))
        except GatewayError as exc:
            self.ai_status.set_text(str(exc))
            return
        report = self.report
        self.ai_status.set_text('Analyzing failed checks…')
        self.analyze_button.set_sensitive(False)

        def task():
            try:
                return analyze_failures(report, gateway)
            except (GatewayError, ValueError, TypeError) as exc:
                return exc

        def done(result):
            self.analyze_button.set_sensitive(self.report is report and report['status'] == 'fail')
            if isinstance(result, Exception):
                self.ai_status.set_text(str(result))
                return
            if self.report is not report:
                return
            self.analysis = result
            self.ai_status.set_text('AI diagnosis for ' + ', '.join(result['check_ids']))
            self.ai_details.get_buffer().set_text(
                readable_diagnosis(result['diagnosis']))
            self.app.status.set_text('AI diagnosis is ready; test verdicts are unchanged.')

        self.app.run(task, done)

    def export(self):
        if self.report is None or self.chooser is not None:
            return
        # Hold this run's snapshot if another run starts before the chooser closes.
        report = json.dumps(self.report, indent=2, sort_keys=True) + '\n'
        chooser = Gtk.FileChooserNative.new('Export Test Lab report', self.app.window,
            Gtk.FileChooserAction.SAVE, 'Export', 'Cancel')
        self.chooser = chooser
        chooser.set_current_name(datetime.now().strftime('argonaut-test-lab-%Y%m%d-%H%M%S.json'))

        def response(_, code):
            file = chooser.get_file()
            chooser.destroy()
            self.chooser = None
            if code != Gtk.ResponseType.ACCEPT or not file:
                return
            path = file.get_path()
            if not path:
                self.app.status.set_text('Choose a local file for the report.')
                return
            try:
                Path(path).write_text(report, encoding='utf-8')
            except OSError as exc:
                self.app.status.set_text('Could not export Test Lab report: ' + str(exc))
            else:
                self.app.status.set_text('Test Lab report saved: ' + path)

        chooser.connect('response', response)
        chooser.show()
