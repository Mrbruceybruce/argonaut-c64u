"""Offline Files dialog presentation; real mapped GTK and XTest keyboard input."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch, Mock
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango
import c1_gtk_check
from gtk_layout_fixture import allocated_frame
from c0_gtk_input import Input


class FilesDialogs(unittest.TestCase):
    setUp = c1_gtk_check.StorageGtk.setUp
    tearDown = c1_gtk_check.StorageGtk.tearDown
    show = c1_gtk_check.StorageGtk.show

    def settle(self, dialog):
        if dialog.get_visible():allocated_frame(dialog)
        self.fixture.drain_events()

    def key(self, dialog, key):
        self.settle(dialog)
        with patch('c0_gtk_input.pump', side_effect=lambda *args:self.settle(self.app.window)):
            inp = Input(dialog)
            try:inp.press(key)
            finally:inp.close()

    def layout(self, dialog):
        box = dialog.get_content_area()
        self.assertEqual(12, box.get_spacing())
        self.assertEqual(0, box.get_margin_bottom())
        for side in ('top','start','end'):
            self.assertEqual(20, getattr(box,'get_margin_'+side)())
        footer = dialog.get_widget_for_response(Gtk.ResponseType.CANCEL).get_parent()
        self.assertEqual(8, footer.get_spacing())
        self.assertEqual(16, footer.get_margin_top())
        self.assertEqual(Gtk.Align.END, footer.get_halign())
        self.settle(dialog)
        for w in self.fixture.walk(box):
            if isinstance(w, Gtk.Label):
                self.assertEqual(Pango.WrapMode.WORD_CHAR,w.get_wrap_mode())

    def prepare_delete(self):
        self.client.host = '192.0.2.20'
        patcher = patch.object(self.app,'run_file_job')
        launch = patcher.start()
        self.addCleanup(patcher.stop)
        dialog = self.app.delete_dialog(False,['/USB1/'+'p'*300],self.client)
        return dialog, launch, launch.call_args.args[1]

    def preview(self):
        return NS(state='succeeded',result=NS(plan_id='reviewed-plan',items=[
            NS(path='/USB1/'+str(i)+'p'*300,kind='file') for i in range(40)]))

    def test_rename_opt_in_focus_enter_and_other_prompt_unchanged(self):
        with patch.object(self.app,'run') as run:
            self.app.rename_item(True,'original.d64')
            dialog=next(w for w in Gtk.Window.get_toplevels() if w.get_title()=='Rename')
            entry=next(w for w in self.fixture.walk(dialog) if isinstance(w,Gtk.Entry))
            self.layout(dialog)
            self.assertEqual('original.d64',entry.get_text())
            self.assertTrue(dialog.get_focus().is_ancestor(entry))
            entry.set_text('renamed.d64');self.key(dialog,'Return')
            self.assertEqual(1,run.call_count)
        dialog,entry,button=self.app.prompt('Other','Name:',lambda value:None)
        self.assertEqual(0,dialog.get_content_area().get_margin_start())
        dialog.response(Gtk.ResponseType.CANCEL)

    def test_rename_invalid_name_does_not_submit(self):
        with patch.object(self.app,'run') as run:
            self.app.rename_item(True,'original')
            dialog=next(w for w in Gtk.Window.get_toplevels() if w.get_title()=='Rename')
            entry=next(w for w in self.fixture.walk(dialog) if isinstance(w,Gtk.Entry))
            entry.set_text('../invalid');dialog.response(Gtk.ResponseType.OK)
            run.assert_not_called()
            self.assertTrue(self.app.status_label.get_text())

    def test_delete_preparation_safe_focus_paths_and_geometry(self):
        dialog,launch,prepared=self.prepare_delete()
        button=dialog.get_widget_for_response(Gtk.ResponseType.OK)
        self.assertFalse(button.get_sensitive());self.layout(dialog)
        self.assertIs(dialog.get_focus(),dialog.get_widget_for_response(Gtk.ResponseType.CANCEL))
        self.assertTrue(button.has_css_class('destructive-action'))
        prepared(self.preview());self.assertTrue(button.get_sensitive())
        scroll=next(w for w in self.fixture.walk(dialog) if isinstance(w,Gtk.ScrolledWindow))
        self.assertTrue(next(w for w in self.fixture.walk(scroll) if isinstance(w,Gtk.Label)).get_selectable())
        settings=dialog.get_settings();font=settings.get_property('gtk-font-name')
        try:
            for face in (font,'Sans 18'):
                settings.set_property('gtk-font-name',face)
                for width in (420,800):
                    dialog.set_default_size(width,-1);self.settle(dialog)
                    self.assertGreater(scroll.get_height(),0)
                    self.assertLess(scroll.get_height(),dialog.get_height())
                    self.assertLessEqual(button.get_width(),dialog.get_width())
        finally:settings.set_property('gtk-font-name',font)
        with patch.object(self.app.core.files,'discard_plan') as discard:
            self.key(dialog,'Escape');discard.assert_called_once_with('reviewed-plan')
        self.assertEqual(1,launch.call_count)

    def test_delete_closed_during_preparation_discards_late_plan(self):
        dialog,launch,prepared=self.prepare_delete()
        self.key(dialog,'Escape')
        with patch.object(self.app.core.files,'discard_plan') as discard:
            prepared(self.preview());discard.assert_called_once_with('reviewed-plan')
        self.assertEqual(1,launch.call_count)

    def test_delete_replaced_client_cannot_submit(self):
        dialog,launch,prepared=self.prepare_delete();prepared(self.preview())
        self.app.client=Mock();dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(1,launch.call_count)
        self.assertIn('Connection changed',self.app.status_label.get_text())

    def test_paste_layout_actions_and_captured_plan(self):
        for answer,decision in ((Gtk.ResponseType.OK,'skip'),(Gtk.ResponseType.APPLY,'replace'),(Gtk.ResponseType.CANCEL,None)):
            with patch.object(self.app,'run_file_job') as launch, patch.object(self.app.core.files,'discard_plan') as discard, patch.object(self.app.core.files,'execute_copy') as execute:
                self.app.start_copy(True,self.app.local,('a',),False,'/USB1',self.client)
                launch.call_args.args[1](NS(state='succeeded',result=NS(conflicts=['p'*300]*40,replaceable=True,operation_count=1,plan_id='copy-plan')))
                dialog=next(w for w in Gtk.Window.get_toplevels() if w.get_title()=='Files already exist')
                self.layout(dialog)
                for width in (420,800):dialog.set_default_size(width,-1);self.settle(dialog)
                dialog.response(answer)
                if decision:
                    self.assertEqual(2,launch.call_count)
                    launch.call_args.args[0]();execute.assert_called_once_with('copy-plan',decision)
                else:
                    self.assertEqual(1,launch.call_count);discard.assert_called_once_with('copy-plan')

    def test_local_rename_refuses_overwrite(self):
        import tempfile
        from pathlib import Path
        from gi.repository import GLib
        with tempfile.TemporaryDirectory() as folder:
            self.app.local=Path(folder)
            (self.app.local/'source').write_text('source')
            (self.app.local/'existing').write_text('existing')
            with patch.object(self.app,'run') as run:
                self.app.rename_item(True,'source')
                dialog=next(w for w in Gtk.Window.get_toplevels() if w.get_title()=='Rename')
                entry=next(w for w in self.fixture.walk(dialog) if isinstance(w,Gtk.Entry))
                entry.set_text('existing');dialog.response(Gtk.ResponseType.OK)
                with self.assertRaises(GLib.Error):run.call_args.args[0]()
            self.assertEqual('source',(self.app.local/'source').read_text())
            self.assertEqual('existing',(self.app.local/'existing').read_text())

    def test_delete_duplicate_while_admitted_does_not_resubmit(self):
        dialog,launch,prepared=self.prepare_delete();prepared(self.preview())
        with patch.object(self.app.core.files,'discard_plan'):
            dialog.response(Gtk.ResponseType.OK)
            self.assertEqual(2,launch.call_count)
            # Real foreground admission synchronously sets busy before returning.
            self.app.busy=True
            try:dialog.response(Gtk.ResponseType.OK)
            finally:self.app.busy=False
            self.assertEqual(2,launch.call_count)

    def test_delete_window_close_before_preparation(self):
        dialog,launch,prepared=self.prepare_delete()
        dialog.close();self.fixture.drain_events()
        with patch.object(self.app.core.files,'discard_plan') as discard:
            prepared(self.preview());discard.assert_called_once_with('reviewed-plan')
        self.assertEqual(1,launch.call_count)

    def test_paste_stale_client_and_duplicate_busy_response(self):
        with patch.object(self.app,'run_file_job') as launch:
            self.app.start_copy(True,self.app.local,('a',),False,'/USB1',self.client)
            launch.call_args.args[1](NS(state='succeeded',result=NS(conflicts=['a'],replaceable=False,operation_count=1,plan_id='plan')))
            dialog=next(w for w in Gtk.Window.get_toplevels() if w.get_title()=='Files already exist')
            self.assertFalse(dialog.get_widget_for_response(Gtk.ResponseType.APPLY).get_sensitive())
            self.app.client=Mock();dialog.response(Gtk.ResponseType.OK)
            self.assertEqual(1,launch.call_count)
            self.app.client=self.client;self.app.busy=True
            try:dialog.response(Gtk.ResponseType.OK)
            finally:self.app.busy=False
            self.assertEqual(1,launch.call_count)

    def test_conflict_free_copy_does_not_open_dialog(self):
        with patch.object(self.app,'run_file_job') as launch, patch.object(self.app.core.files,'execute_copy') as execute:
            self.app.start_copy(True,self.app.local,('a',),False,'/USB1',self.client)
            launch.call_args.args[1](NS(state='succeeded',result=NS(conflicts=(),plan_id='clear-plan')))
            self.assertEqual(2,launch.call_count)
            launch.call_args.args[0]();execute.assert_called_once_with('clear-plan','skip')
            self.assertFalse(any(w.get_title()=='Files already exist' for w in Gtk.Window.get_toplevels()))

    def test_paste_keyboard_navigation_and_escape(self):
        with patch.object(self.app,'run_file_job') as launch, patch.object(self.app.core.files,'discard_plan') as discard:
            self.app.start_copy(True,self.app.local,('a',),False,'/USB1',self.client)
            launch.call_args.args[1](NS(state='succeeded',result=NS(conflicts=['long'*200],replaceable=True,operation_count=1,plan_id='cancel-plan')))
            dialog=next(w for w in Gtk.Window.get_toplevels() if w.get_title()=='Files already exist')
            self.key(dialog,'Tab')
            self.assertIsNotNone(dialog.get_focus())
            self.key(dialog,'Escape');discard.assert_called_once_with('cancel-plan')
            self.assertEqual(1,launch.call_count)

    def paste_review(self, launch):
        self.app.start_copy(True,self.app.local,('a',),False,'/USB1',self.client)
        launch.call_args.args[1](NS(state='succeeded',result=NS(conflicts=['a'],replaceable=True,operation_count=1,plan_id='paste-owned')))
        return next(w for w in Gtk.Window.get_toplevels() if w.get_title()=='Files already exist')

    def test_destroy_without_response_disposes_delete_and_paste(self):
        with patch.object(self.app.core.files,'discard_plan') as discard:
            dialog,launch,prepared=self.prepare_delete();prepared(self.preview())
            dialog.destroy();self.fixture.drain_events()
            discard.assert_called_once_with('reviewed-plan')
            discard.reset_mock()
            dialog=self.paste_review(launch);dialog.destroy();self.fixture.drain_events()
            discard.assert_called_once_with('paste-owned')
            self.assertFalse(self.app._file_reviews)

    def test_late_response_after_cancel_preserves_status(self):
        with patch.object(self.app.core.files,'discard_plan') as discard:
            dialog,launch,prepared=self.prepare_delete();prepared(self.preview())
            dialog.response(Gtk.ResponseType.CANCEL)
            self.app.status.set_text('New status')
            dialog.response(Gtk.ResponseType.OK)
            self.assertEqual('New status',self.app.status_label.get_text())
            self.assertEqual(1,launch.call_count)
            discard.assert_called_once_with('reviewed-plan')
            dialog=self.paste_review(launch)
            dialog.response(Gtk.ResponseType.CANCEL)
            count=launch.call_count;self.app.status.set_text('Another status')
            dialog.response(Gtk.ResponseType.APPLY)
            self.assertEqual(count,launch.call_count)
            self.assertEqual('Another status',self.app.status_label.get_text())

    def test_busy_then_late_response_cannot_revive_review(self):
        with patch.object(self.app.core.files,'discard_plan') as discard:
            dialog,launch,prepared=self.prepare_delete();prepared(self.preview())
            self.app.busy=True;dialog.response(Gtk.ResponseType.OK);self.app.busy=False
            dialog.response(Gtk.ResponseType.OK)
            self.assertEqual(1,launch.call_count);discard.assert_called_once_with('reviewed-plan')
            discard.reset_mock();dialog=self.paste_review(launch);count=launch.call_count
            self.app.busy=True;dialog.response(Gtk.ResponseType.APPLY);self.app.busy=False
            dialog.response(Gtk.ResponseType.APPLY)
            self.assertEqual(count,launch.call_count);discard.assert_called_once_with('paste-owned')

    def test_same_client_replaced_session_rejects_both_reviews(self):
        session=NS(device_id='device',session_id='one')
        with patch.object(self.app.core,'device_session',side_effect=lambda:session), patch.object(self.app.core.files,'discard_plan') as discard:
            dialog,launch,prepared=self.prepare_delete();prepared(self.preview())
            session=NS(device_id='device',session_id='two')
            dialog.response(Gtk.ResponseType.OK)
            self.assertEqual(1,launch.call_count);discard.assert_called_once_with('reviewed-plan')
            discard.reset_mock();dialog=self.paste_review(launch);count=launch.call_count
            session=NS(device_id='device',session_id='three')
            dialog.response(Gtk.ResponseType.APPLY)
            self.assertEqual(count,launch.call_count);discard.assert_called_once_with('paste-owned')

    def test_presentation_exception_disposes_exact_plan(self):
        dialog,launch,prepared=self.prepare_delete()
        with patch.object(self.app.core.files,'discard_plan') as discard:
            with patch('c64u_browser.gui.Gtk.Label.set_text',side_effect=ValueError('presentation')):
                with self.assertRaises(ValueError):prepared(self.preview())
            discard.assert_called_once_with('reviewed-plan')
            discard.reset_mock()
            self.app.start_copy(True,self.app.local,('a',),False,'/USB1',self.client)
            checked=launch.call_args.args[1]
            with patch('c64u_browser.gui.dialog_layout',side_effect=ValueError('layout')):
                with self.assertRaises(ValueError):checked(NS(state='succeeded',result=NS(plan_id='paste-error',conflicts=['a'],replaceable=True)))
            discard.assert_called_once_with('paste-error')
            self.assertFalse(self.app._file_reviews)

    def test_preparation_failure_has_no_authority_and_keeps_message(self):
        dialog,launch,prepared=self.prepare_delete()
        prepared(NS(state='failed',result=None,error=NS(message='fixture failure')))
        texts=[w.get_text() for w in self.fixture.walk(dialog) if isinstance(w,Gtk.Label)]
        self.assertTrue(any('Could not prepare deletion: fixture failure' in t for t in texts))
        self.assertFalse(dialog.get_widget_for_response(Gtk.ResponseType.OK).get_sensitive())
        dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(1,launch.call_count)

    def test_accepted_shutdown_discards_pending_review(self):
        dialog,launch,prepared=self.prepare_delete();prepared(self.preview())
        with patch.object(self.app.core.files,'discard_plan') as discard:
            self.assertFalse(self.app.close())
            discard.assert_called_once_with('reviewed-plan')
            dialog.response(Gtk.ResponseType.OK)
            self.assertEqual(1,launch.call_count)

    def test_busy_shutdown_veto_retains_preparation_owner(self):
        dialog,launch,prepared=self.prepare_delete()
        self.app.busy=True
        try:self.assertTrue(self.app.close())
        finally:self.app.busy=False
        self.assertEqual(1,len(self.app._file_reviews))
        with patch.object(self.app.core.files,'discard_plan') as discard:
            dialog.destroy();prepared(self.preview())
            discard.assert_called_once_with('reviewed-plan')

    def test_preparation_submission_error_preserves_disabled_error_dialog(self):
        def refuse(factory, done, **kwargs):
            kwargs['failed'](ValueError('submission error'))
            return False
        self.client.host='192.0.2.20'
        with patch.object(self.app,'run_file_job',side_effect=refuse), patch.object(self.app.core.files,'discard_plan') as discard:
            dialog=self.app.delete_dialog(False,['/USB1/a'],self.client)
            self.assertTrue(dialog.get_visible())
            self.assertFalse(dialog.get_widget_for_response(Gtk.ResponseType.OK).get_sensitive())
            self.assertTrue(any('submission error' in w.get_text() for w in self.fixture.walk(dialog) if isinstance(w,Gtk.Label)))
            dialog.response(Gtk.ResponseType.CANCEL)
            discard.assert_not_called()
            self.assertFalse(self.app._file_reviews)
