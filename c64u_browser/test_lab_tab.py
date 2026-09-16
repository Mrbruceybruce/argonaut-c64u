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

from .test_lab import run_default_checks
from .hardware_checks import run_hardware_checks
from .ai_analysis import analyze_failures
from .ai_gateway import AIGateway, GatewayConfig, GatewayError
from .test_lab_history import run_with_history
from .test_lab_presentation import check_details, comparison_summary, summary
from .test_lab_schedule import HardwareSchedule
from .test_lab_saved import preferred_record, saved_hardware_results, saved_status
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
        self.saved_button.set_sensitive(False)
        self.verified_button.set_sensitive(False)
        toolbar = Gtk.Box(spacing=8)
        self.box.append(toolbar)
        self.run_button = app.button(toolbar, 'Run offline checks', self.run)
        self.hardware_button = app.button(toolbar, 'Run C64U checks', self.run_hardware)
        self.export_button = app.button(toolbar, 'Export JSON…', self.export)
        self.export_button.set_sensitive(False)
        self.analyze_button = app.button(toolbar, 'Explain failures', self.analyze)
        self.analyze_button.set_sensitive(False)
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

    def refresh_history(self, auto_load=False):
        self.saved_records = saved_hardware_results(self.app.preferences)
        if not self.saved_records:
            self.saved_overview.set_text('No identity-bound Development C64U profiles.')
            self.saved_choice.set_model(Gtk.StringList.new(['No bound C64Us']))
            self.saved_button.set_sensitive(False)
            self.verified_button.set_sensitive(False)
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

    def show_history(self):
        selected = self.saved_choice.get_selected()
        if selected < len(self.saved_records):
            record = self.saved_records[selected]
            if record['recent']:
                self.show_saved(record['recent'], record['profile'].name,
                                'Latest saved C64U result', record['profile'].id)

    def show_verified_history(self):
        selected = self.saved_choice.get_selected()
        if selected < len(self.saved_records):
            record = self.saved_records[selected]
            if record['verified']:
                self.show_saved(record['verified'], record['profile'].name,
                                'Last verified C64U result', record['profile'].id)

    def show_saved(self, report, name, source, profile_id):
        self.report = report
        self.comparison = None
        self.loaded_from_history = True
        self.saved_context = f'{source} for {name}. Verdicts come from saved checks.'
        self.analysis = None
        self.ai_status.set_text('')
        self.ai_details.get_buffer().set_text('')
        try:
            self.render()
            diagnosis = saved_diagnosis(
                self.unattended_ai_path.parent / CACHE_NAME, profile_id, report)
            if diagnosis:
                self.ai_status.set_text('Saved unattended local AI diagnosis:')
                self.ai_details.get_buffer().set_text(diagnosis)
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

    def run_hardware(self):
        client = None if getattr(self.app, 'offline_message', None) else self.app.client
        profile = self.app.active_profile if client is not None else None
        self._run_checks(lambda: run_hardware_checks(client, profile),
                         profile_id=profile.id if profile else None)

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

    def _run_checks(self, runner, profile_id=None):
        if self.app.busy:
            return
        self.summary.set_text('Running checks…')
        self.run_button.set_sensitive(False)
        self.hardware_button.set_sensitive(False)

        def done(result):
            self.run_button.set_sensitive(True)
            self.hardware_button.set_sensitive(True)
            if not isinstance(result, dict):
                self.summary.set_text('Could not run checks. See the status message below.')
                return
            self.report = result['report']
            self.comparison = result['comparison']
            self.loaded_from_history = False
            self.saved_context = ''
            self.analysis = None
            self.ai_status.set_text('')
            self.ai_details.get_buffer().set_text('')
            self.render()
            self.refresh_history()
            message = 'Test Lab: ' + summary(self.report)
            if not result['saved']:
                message += ' · Run history could not be saved.'
            self.app.status.set_text(message)
            if self.report['status'] == 'fail' and self.auto_analyze.get_active():
                self.analyze()

        def task():
            try:
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
        if self.app.busy or self.report is None or self.report['status'] != 'fail':
            return
        provider = 'ollama' if self.provider.get_selected() == 0 else 'openai'
        try:
            gateway = AIGateway(GatewayConfig(provider, self.model.get_text().strip()))
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
            self.ai_details.get_buffer().set_text(result['diagnosis'] or '')
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
