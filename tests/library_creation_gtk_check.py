"""Offline creation confirmation and visibility; no storage transport."""
from unittest.mock import Mock,patch
from types import SimpleNamespace as NS
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
import unittest
import managed_library_gtk_check as fixture
from c64u_browser.managed_library import LibraryState
from c64u_browser.library_creation import CreationTarget
from c64u_browser.picker_model import PickerMode,PickerSelection
from tests.test_managed_library import ID,PATH
from c0_gtk_input import pump


class CreationGtk(unittest.TestCase):
    def tearDown(self):fixture.ManagedViewGtk.tearDown(self)
    def setUp(self):
        fixture.ManagedViewGtk.setUp(self);self.app.window=self.window
        self.target=CreationTarget(ID,'device','one','/SD',PATH)
        self.core.prepare_library_creation=Mock(return_value=self.target)
        self.core.discard_library_creation=Mock();self.core.create_managed_library=Mock()
        self.selection=PickerSelection('c64u','/SD','SD','/SD','device','one','library-root','dir')
        self.patcher=patch('c64u_browser.file_picker.FilePicker')
        self.picker=self.patcher.start();self.addCleanup(self.patcher.stop)
    def test_create_visible_only_without_library(self):
        self.assertTrue(self.view.create_button.get_visible())
        for state in ('unavailable','multiple'):
            self.view.render(LibraryState(state,'state'))
            self.assertFalse(self.view.create_button.get_visible())
    def test_picker_cancel_never_prepares_or_creates(self):
        self.view.choose_creation()
        self.assertEqual(PickerMode.OPEN_FOLDER,self.picker.call_args.kwargs['mode'])
        self.assertEqual(('c64u',),self.picker.call_args.kwargs['scopes'])
        self.picker.call_args.args[1](None)
        self.core.prepare_library_creation.assert_not_called()
        self.core.create_managed_library.assert_not_called()
    def test_confirmation_captures_target_and_cancel_discards(self):
        self.view.choose_creation();self.picker.call_args.args[1]((self.selection,));pump()
        self.core.prepare_library_creation.assert_called_once_with(self.selection)
        self.core.create_managed_library.assert_not_called()
        dialog=self.view.confirmation
        label=dialog.get_content_area().get_first_child().get_text()
        self.assertIn(PATH,label);self.assertIn('device',label);self.assertIn('/SD',label)
        dialog.response(Gtk.ResponseType.CANCEL);pump()
        self.core.discard_library_creation.assert_called_once_with(ID)
        self.app.run_file_job.assert_not_called()
    def test_confirm_defers_to_foreground_and_reports_recovery(self):
        self.view.choose_creation();self.picker.call_args.args[1]((self.selection,))
        self.view.confirmation.response(Gtk.ResponseType.OK);pump()
        self.core.create_managed_library.assert_not_called()
        factory,done=self.app.run_file_job.call_args.args
        factory();self.core.create_managed_library.assert_called_once_with(self.target)
        done(NS(state='failed',result=NS(message='Recovery required at '+PATH)))
        self.assertEqual('unavailable',self.view.state.status)
        self.assertIn('Recovery required',self.view.message.get_text())
        self.assertFalse(self.view.create_button.get_visible())
