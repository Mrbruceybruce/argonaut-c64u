"""Presentation-only status checks on an isolated GTK display, with no device IO."""
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import unittest
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango
from c64u_browser.jobs import CoreJob, JobProgress
import test_preferences_ui
import header_gtk_check
import c0_gtk_input


class StatusLayout(unittest.TestCase):
    settle = header_gtk_check.HeaderGtk.settle

    def setUp(self):
        trap = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        trap.start();self.addCleanup(trap.stop)
        self.f = test_preferences_ui.PreferencesUI();self.f.setUp()
        self.addCleanup(self.f.doCleanups);self.addCleanup(self.f.tearDown)
        self.app = self.f.app;self.window = self.app.window
        self.jobs = [];self.addCleanup(self.finish_jobs)
        self.settle()

    def finish_jobs(self):
        for job in self.jobs:
            if job.snapshot().state not in ('succeeded', 'failed', 'cancelled'):job.run()
        self.settle()

    def start(self, cancellable=True):
        job = CoreJob('file.synthetic', lambda _:None);self.jobs.append(job)
        self.assertTrue(self.app.run_file_job(lambda:job, Mock(), cancellable=cancellable))
        self.settle();return job

    def assert_usable_restored_focus(self):
        focus = self.window.get_focus()
        self.assertIsNotNone(focus)
        self.assertIsNot(focus, self.app.cancel_button)
        self.assertTrue(focus.get_mapped())
        self.assertTrue(focus.is_sensitive())
        self.assertIs(focus.get_root(), self.window)
        self.assertTrue(focus.grab_focus())
        self.assertIs(self.window.get_focus(), focus)

    def test_native_structure_padding_and_idle(self):
        app = self.app;region = app.status_region;row = app.status_row
        separator = region.get_first_child()
        self.assertIsInstance(separator, Gtk.Separator)
        self.assertEqual(separator.get_orientation(), Gtk.Orientation.HORIZONTAL)
        self.assertIs(separator.get_next_sibling(), row)
        self.assertEqual((row.get_margin_start(), row.get_margin_end(), row.get_margin_top(), row.get_margin_bottom()), (12,12,8,8))
        self.assertEqual(row.get_spacing(), 8)
        self.assertTrue(app.status_label.get_selectable());self.assertTrue(app.status_label.get_hexpand())
        self.assertEqual(app.status_label.get_wrap_mode(), Pango.WrapMode.WORD_CHAR)
        self.assertEqual(app.status_label.get_ellipsize(), Pango.EllipsizeMode.NONE)
        self.assertEqual(app.cancel_button.get_valign(), Gtk.Align.START)
        self.assertNotIn(region, app.busy_controls);self.assertNotIn(row, app.busy_controls)
        app.status.set_text('Idle message stays unchanged.')
        self.assertEqual(app.operation.state, 'IDLE')
        self.assertEqual(app.status_label.get_text(), 'Idle message stays unchanged.')
        self.assertFalse(app.cancel_button.get_visible())

    def test_running_cancel_keyboard_sticky_and_terminal_focus(self):
        job = self.start();app = self.app
        self.assertEqual(app.operation.state, 'RUNNING')
        self.assertTrue(app.cancel_button.get_visible());self.assertTrue(app.cancel_button.is_sensitive())
        self.assertTrue(app.cancel_button.grab_focus())
        self.assertIs(self.window.get_focus(), app.cancel_button)
        with patch.object(app.core.files, 'cancel', side_effect=lambda _:job.request_cancel()) as cancel, \
             patch('c0_gtk_input.pump', self.settle):
            input = c0_gtk_input.Input(self.window)
            try:input.press('space')
            finally:input.close()
            cancel.assert_called_once_with(job.id)  # Real Space alone must cancel.
            app.cancel_button.emit('clicked');cancel.assert_called_once_with(job.id)
        self.assertEqual(app.operation.state, 'CANCELLATION_REQUESTED')
        self.assert_usable_restored_focus()
        sticky = app.status_label.get_text()
        job.report_committed(JobProgress('late', 3, 5, 'files', 'Late progress'))
        app.status.set_text('Unrelated');self.settle()
        self.assertEqual(app.status_label.get_text(), sticky)
        self.assertFalse(app.cancel_button.get_visible())
        self.assertIsNotNone(app.foreground.token)
        job.run();self.settle()
        self.assertEqual(app.operation.state, 'TERMINAL')
        self.assertIsNone(app.foreground.token)
        self.assertFalse(app.cancel_button.get_visible())

    def test_noncancellable_and_refused_cancellation(self):
        job = self.start(False);self.assertFalse(self.app.cancel_button.get_visible())
        job.run();self.settle()
        job = self.start();self.app.cancel_button.grab_focus()
        with patch.object(self.app.core.files, 'cancel', return_value=False) as cancel:
            self.app.cancel_button.emit('clicked');self.app.cancel_button.emit('clicked')
            cancel.assert_called_once()
        self.assertEqual(self.app.operation.state, 'RUNNING')
        self.assertIn('not accepted', self.app.status_label.get_text())
        self.assertFalse(self.app.cancel_button.get_visible())
        self.assert_usable_restored_focus()
        self.assertIsNotNone(self.app.foreground.token)
        job.run();self.settle()

    def test_neutral_terminal_outcomes_preserve_exact_text(self):
        app = self.app
        classes = tuple(app.status_label.get_css_classes())
        for state, message in (('failed','Failed: operation rejected.'),
                ('cancelled','Cancelled before mutation.'),
                ('succeeded','Command accepted — audible playback not verified.'),
                ('failed','Outcome uncertain; inspect the device. No retry.')):
            job = NS(operation='synthetic');token = object()
            app.operation.begin(job, token)
            app.operation.finish(job, token, NS(state=state,result=NS(message=message),error=None))
            self.assertEqual(app.operation.state, 'TERMINAL')
            self.assertEqual(app.status_label.get_text(), message)
            self.assertEqual(tuple(app.status_label.get_css_classes()), classes)
            self.assertFalse(app.cancel_button.get_visible())
        self.assertFalse(any(isinstance(w, (Gtk.Image, Gtk.Spinner, Gtk.ProgressBar))
                             for w in self.f.walk(app.status_region)))

    def check_bounds(self):
        app = self.app;label = app.status_label;cancel = app.cancel_button
        _, lb = label.compute_bounds(app.status_row)
        _, cb = cancel.compute_bounds(app.status_row)
        self.assertGreater(label.get_width(), 0)
        self.assertLessEqual(lb.get_x()+lb.get_width(), cb.get_x())
        self.assertLessEqual(cb.get_x()+cb.get_width(), app.status_row.get_width())
        self.assertEqual(lb.get_y(), cb.get_y())
        layout = label.get_layout()
        self.assertLessEqual(layout.get_pixel_size()[1], label.get_height())
        self.assertGreater(layout.get_line_count(), 1)
        self.assertTrue(cancel.get_mapped())

    def test_long_messages_narrow_normal_wide_and_minimum(self):
        app = self.app;job = self.start()
        message = 'Operation warning: '+('Long prose needs to remain readable. '*20)+'\n/USB1/'+('unbroken-path-'*120)
        job.report(JobProgress('read',0,None,'items',message));self.settle()
        for width in (1200,1,3840):
            self.window.set_default_size(width,850);self.settle();self.check_bounds()
            self.assertEqual(app.status_label.get_text(),message)
        region = app.status_region;region.get_parent().remove(region)
        narrow = Gtk.Window();narrow.set_child(region);self.addCleanup(narrow.destroy)
        self.window = narrow
        for width in (320,480):
            narrow.set_default_size(width,200);narrow.present();self.settle();self.check_bounds()
            self.assertLessEqual(narrow.get_width(),width)
        # Return the region before fixture shutdown and pending job completion.
        narrow.set_child(None);app.window.get_child().append(region)
        self.window = app.window

    def test_status_text_selection_and_clipboard(self):
        label = self.app.status_label;text = 'Exact status /USB1/a-long-path — uncertain outcome.'
        self.app.status.set_text(text);label.grab_focus();label.select_region(0,-1)
        self.assertEqual(label.get_selection_bounds(), (True,0,len(text)))
        label.emit('copy-clipboard')
        loop = GLib.MainLoop();result=[];expired=[]
        def ready(clipboard, response):
            result.append(clipboard.read_text_finish(response));loop.quit()
        def timeout():expired.append(True);loop.quit();return False
        deadline=GLib.timeout_add(3000,timeout)
        label.get_clipboard().read_text_async(None,ready)
        try:loop.run()
        finally:
            if not expired:GLib.source_remove(deadline)
        self.assertFalse(expired);self.assertEqual(result,[text])

    def test_appearance_reactivation_and_shutdown(self):
        app=self.app;region=app.status_region;provider=app.file_pane_css
        settings=Gtk.Settings.get_default();old=settings.get_property('gtk-application-prefer-dark-theme')
        self.addCleanup(settings.set_property,'gtk-application-prefer-dark-theme',old)
        app.status.set_text('Outcome unknown. Keep this evidence.')
        with patch.object(Gtk.StyleContext,'add_provider_for_display') as add:
            for dark in (False,True):
                settings.set_property('gtk-application-prefer-dark-theme',dark)
                app.do_activate();self.settle()
                self.assertIs(app.status_region,region);self.assertIs(app.file_pane_css,provider)
                self.assertEqual(app.status_label.get_text(),'Outcome unknown. Keep this evidence.')
            add.assert_not_called()
        app.window.close();self.f.drain_events()
        self.assertFalse(app.window.get_visible());self.assertFalse(self.f.owned_windows())

    def test_stale_progress_and_terminal_cannot_replace_current_view(self):
        first=self.start();old_token=self.app.foreground.token
        first.run();self.settle();second=self.start();view=self.app.operation.view
        self.app.operation.progress(first,old_token,JobProgress('old',1,2,'files','Old'),lambda _,p:p.message)
        self.app.operation.finish(first,old_token,first.snapshot())
        self.assertEqual(self.app.operation.view,view)
        self.assertEqual(self.app.status_label.get_text(),view.message)
        self.assertTrue(self.app.cancel_button.get_visible())
        second.run();self.settle()


class FullWindowGeometry(unittest.TestCase):
    """Use the original committed constructor, not a hand-built approximation.

    The rest of gui.py and the supporting production modules must match HEAD.
    Both variants run in one process/display/theme with identical fixtures.
    """
    settle = header_gtk_check.HeaderGtk.settle

    def test_baseline_comparison(self):
        import ast
        import json
        import subprocess
        import c64u_browser.gui as gui
        baseline = '7faf761b89fe213f2ebad4d522d3d395548987cd'
        source = subprocess.check_output(['git','show',baseline+':c64u_browser/gui.py'],text=True)
        tree = ast.parse(source)
        constructor = next(n for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='Browser'
                           for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='do_activate')
        namespace = dict(vars(gui))
        exec(compile(ast.Module(body=[constructor],type_ignores=[]),'<committed Browser.do_activate>','exec'),namespace)
        original = namespace['do_activate']
        current = gui.Browser.do_activate
        records = []
        with patch('socket.socket.connect',side_effect=AssertionError('Network forbidden')):
            for variant, constructor in (('baseline',original),('modified',current)):
                self.f = test_preferences_ui.PreferencesUI()
                # GObject caches the activation vfunc; call the chosen body
                # explicitly rather than relying on a Python vfunc monkeypatch.
                with patch.object(gui.Browser,'activate',lambda app:constructor(app)):
                    self.f.setUp()
                app=self.f.app;self.window=app.window
                # Measurement windows must not persist their stress-test sizes.
                app.preferences.app_options['remember_window']=False
                try:
                    self.assertEqual(hasattr(app,'status_region'),variant=='modified')
                    self.assertEqual(app.status_row.get_margin_start(),12 if variant=='modified' else 0)
                    self.settle()
                    settings=Gtk.Settings.get_default()
                    environment=(settings.get_property('gtk-theme-name'),
                                 settings.get_property('gtk-application-prefer-dark-theme'),
                                 settings.get_property('gtk-xft-dpi'),self.window.get_scale_factor())
                    for content,message in (
                        ('short','Working…'),
                        ('prose','Operation warning: '+('Long prose needs to remain readable. '*20)),
                        ('path','/USB1/'+('x'*1560))):
                        app.operation.begin(NS(operation='synthetic'),object())
                        app.operation.message=message;app.operation._emit()
                        for width in (640,1200,3840):
                            self.window.set_default_size(width,850);self.settle()
                            def measure(widget,orientation,for_size=-1):
                                m=widget.measure(orientation,for_size)
                                return [m.minimum,m.natural]
                            region=getattr(app,'status_region',app.status_row)
                            def bounds(widget):
                                valid,b=widget.compute_bounds(self.window)
                                self.assertTrue(valid)
                                return [b.get_x(),b.get_y(),b.get_width(),b.get_height()]
                            record=dict(variant=variant,content=content,requested=[width,850],
                                allocated=[self.window.get_width(),self.window.get_height()],
                                horizontal=measure(self.window,Gtk.Orientation.HORIZONTAL),
                                vertical_unconstrained=measure(self.window,Gtk.Orientation.VERTICAL),
                                vertical_at_width=measure(self.window,Gtk.Orientation.VERTICAL,self.window.get_width()),
                                controls_vertical=measure(app.controls,Gtk.Orientation.VERTICAL,app.controls.get_width()),
                                controls_horizontal=measure(app.controls,Gtk.Orientation.HORIZONTAL),
                                status_horizontal=measure(region,Gtk.Orientation.HORIZONTAL),
                                cancel_min_height=measure(app.cancel_button,Gtk.Orientation.VERTICAL)[0],
                                separator_height=(measure(region.get_first_child(),Gtk.Orientation.VERTICAL)[0]
                                                  if variant=='modified' else 0),
                                vertical_padding=app.status_row.get_margin_top()+app.status_row.get_margin_bottom(),
                                horizontal_padding=app.status_row.get_margin_start()+app.status_row.get_margin_end(),
                                outer_horizontal=app.window.get_child().get_margin_start()+app.window.get_child().get_margin_end(),
                                status=bounds(region),cancel=bounds(app.cancel_button),
                                label=bounds(app.status_label),lines=app.status_label.get_layout().get_line_count(),
                                text_size=list(app.status_label.get_layout().get_pixel_size()),environment=environment)
                            records.append(record)
                            print('STATUS_GEOMETRY '+json.dumps(record),flush=True)
                            for name in ('status','cancel','label'):
                                x,y,w,h=record[name]
                                self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
                                self.assertLessEqual(x+w,record['allocated'][0])
                                self.assertLessEqual(y+h,record['allocated'][1])
                            self.assertTrue(app.cancel_button.get_mapped())
                            lx,ly,lw,lh=record['label'];cx,cy,cw,ch=record['cancel']
                            self.assertLessEqual(lx+lw,cx)
                            self.assertLessEqual(record['text_size'][0],lw)
                            self.assertLessEqual(record['text_size'][1],lh)
                            self.assertEqual(record['allocated'][1],max(850,record['vertical_at_width'][0]))
                            self.assertEqual(app.status_label.get_text(),message)
                finally:
                    app.operation.set_text('')
                    self.f.tearDown();self.f.doCleanups()
        for before,after in zip(records[:9],records[9:]):
            self.assertEqual(before['environment'],after['environment'])
            self.assertEqual(before['content'],after['content'])
            self.assertEqual(before['requested'],after['requested'])
            # Character wrapping must not introduce a larger minimum width.
            self.assertLessEqual(after['horizontal'][0],before['horizontal'][0])
            # Exact height accounting: content wrapping at the actual width,
            # native Cancel minimum, controls, padding, and native separator.
            # No percentage or arbitrary growth tolerance is permitted.
            decoration=after['vertical_padding']+after['separator_height']
            self.assertEqual(after['vertical_unconstrained'][0]-before['vertical_unconstrained'][0],decoration)
            content_delta=(max(after['text_size'][1],after['cancel_min_height'])-
                           max(before['text_size'][1],before['cancel_min_height']))
            controls_delta=after['controls_vertical'][0]-before['controls_vertical'][0]
            self.assertEqual(after['vertical_at_width'][0]-before['vertical_at_width'][0],
                             decoration+content_delta+controls_delta)
            for index in (0,1):
                expected=max(before['controls_horizontal'][index],
                             after['status_horizontal'][index])+after['outer_horizontal']
                self.assertEqual(after['horizontal'][index],expected)
            # Natural width can gain only the explicitly added horizontal padding.
            self.assertEqual(after['status_horizontal'][1]-before['status_horizontal'][1],
                             after['horizontal_padding'])
