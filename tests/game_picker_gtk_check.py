"""Game Add/Relink handoff with actual GTK and offline source fixtures."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
from c64u_browser.game_library_tab import GameLibraryTab
from c64u_browser.game_library_client import GameLibraryClient
from c64u_browser.game_library import GameLibraryService, GameSource
from c64u_browser.picker_model import PickerMode, PickerEntry, PickerSelection
from tests.test_game_library import crt_bytes
from picker_gtk_check import Host
from c0_gtk_input import Input, pump


class GamePickerGtk(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        for name in ('a.crt','z.crt'):(self.folder/name).write_bytes(crt_bytes())
        (self.folder/'invalid.crt').write_bytes(b'bad content')
        (self.folder/'hidden.sid').write_bytes(b'not a game')
        self.host=Host();self.host.local=self.folder
        self.host.core.list_directory=lambda path:NS(state='succeeded',error=None,
            result=(path,[PickerEntry('SD','dir')] if path=='/' else [PickerEntry('game.crt','file')]),
            device_id=self.host.session.device_id,session_id=self.host.session.session_id)
        self.service=GameLibraryService(self.folder/'catalog.json',
            session_provider=lambda:self.host.session,
            remote_reader=lambda source:crt_bytes()).load()
        # The real Core supplies DeviceSession, as must this fixture.
        from c64u_browser.scheduler import DeviceSession
        self.host.session=DeviceSession('founders','session-1')
        self.addCleanup(self.service.close)
        self.launcher=Mock()
        self.tab=GameLibraryTab.__new__(GameLibraryTab)
        self.tab.app=self.host;self.tab.chooser=None
        self.tab.client=GameLibraryClient(self.service,self.launcher)
        self.tab.refresh=Mock();self.tab._show=Mock();self.tab._relink_prepared=Mock()
        self.submissions=[];self.deferred=False
        def run(factory,done,**kwargs):
            self.submissions.append(factory)
            if not self.deferred:
                try:done(factory().wait(5))
                except Exception as exc:
                    if 'failed' in kwargs:kwargs['failed'](exc)
                    else:raise
        self.tab._run_job=run
        self.input=None
        self.trap=patch('socket.socket.connect',side_effect=AssertionError('No device contact'))
        self.trap.start();self.addCleanup(self.trap.stop)

    def tearDown(self):
        if self.input:self.input.close()
        if self.tab.chooser:self.tab.chooser.response(None,Gtk.ResponseType.CANCEL)
        self.host.window.destroy();pump()

    def row(self,picker,name):
        row=picker.listing.get_first_child()
        while row is not None:
            if row.item[0]==name:return row
            row=row.get_next_sibling()
        self.fail('Missing row '+name)

    def test_real_local_multi_selection_consumes_display_order(self):
        self.tab.add_local();p=self.tab.chooser;pump()
        self.assertEqual(PickerMode.OPEN_FILES,p.model.mode)
        self.assertEqual(('core-host','c64u'),p.model.scopes)
        self.assertNotIn('hidden.sid',[e.name for e in p.model.entries])
        self.input=Input(p.dialog)
        self.input.click(self.row(p,'z.crt'))
        self.input.click(self.row(p,'a.crt'),modifier='Control_L')
        p.response(None,Gtk.ResponseType.ACCEPT)
        self.assertEqual(2,len(self.submissions))
        self.assertEqual('a.crt',Path(self.service.list()[0].source.path).name)
        self.assertEqual(1,len(self.service.list()))
        self.assertEqual([],self.launcher.mock_calls)

    def test_remote_add_browses_and_validates_without_files_state(self):
        self.tab.add_c64u();p=self.tab.chooser;p.navigate('c64u','/SD');pump()
        p.listing.select_row(self.row(p,'game.crt'));p.response(None,Gtk.ResponseType.ACCEPT)
        self.assertEqual('/SD/game.crt',self.service.list()[0].source.path)
        self.assertEqual([],self.launcher.mock_calls)

    def test_cancel_add_and_relink_submit_nothing(self):
        self.tab.add_local();self.tab.chooser.response(None,Gtk.ResponseType.CANCEL)
        self.assertEqual([],self.submissions);self.assertEqual((),self.service.list())
        result=self.service.add(GameSource.core_host(self.folder/'a.crt')).wait(5)
        self.tab.client.select(result.result.record.id)
        self.tab.relink();p=self.tab.chooser
        self.assertEqual(PickerMode.OPEN_FILE,p.model.mode)
        self.assertEqual(('core-host',),p.model.scopes)
        p.response(None,Gtk.ResponseType.CANCEL)
        self.assertEqual([],self.submissions);self.tab._relink_prepared.assert_not_called()

    def test_deferred_remote_selection_rejects_reconnect(self):
        from c64u_browser.scheduler import DeviceSession
        self.deferred=True
        self.tab.add_c64u();p=self.tab.chooser;p.navigate('c64u','/SD');pump()
        p.listing.select_row(self.row(p,'game.crt'));p.response(None,Gtk.ResponseType.ACCEPT)
        self.host.session=DeviceSession('founders','new')
        with self.assertRaises(ValueError):self.submissions[0]()
        self.assertEqual((),self.service.list())

    def test_invalid_content_rejected_after_picker_selection(self):
        self.tab.add_local();p=self.tab.chooser;pump()
        p.listing.select_row(self.row(p,'invalid.crt'));p.response(None,Gtk.ResponseType.ACCEPT)
        self.assertEqual((),self.service.list())
        self.assertIn('Validation rejected',self.tab._show.call_args.args[0])

    def test_relink_retains_record_when_catalog_selection_changes(self):
        from c64u_browser.game_library import GameSource
        first=self.service.add(GameSource.core_host(self.folder/'a.crt')).wait(5).result.record
        self.tab.client.select(first.id);self.tab.relink();p=self.tab.chooser;pump()
        self.tab.client.selected_id=None
        p.listing.select_row(self.row(p,'z.crt'));p.response(None,Gtk.ResponseType.ACCEPT)
        result=self.tab._relink_prepared.call_args.args[0]
        self.assertEqual('succeeded',result.state,result.error)
        self.assertEqual(first.id,result.result.record_id)
        self.assertTrue(result.result.content_matches)
        self.assertEqual(first,self.service.get(first.id))

    def test_relink_review_cancel_does_not_execute(self):
        first=self.service.add(GameSource.core_host(self.folder/'a.crt')).wait(5).result.record
        result=self.service.prepare_relink(first.id,GameSource.core_host(self.folder/'z.crt')).wait(5)
        GameLibraryTab._relink_prepared(self.tab,result);pump()
        dialogs=[w for w in Gtk.Window.list_toplevels() if w.get_title()=='Review Locate/Relink']
        self.assertEqual(1,len(dialogs))
        dialogs[0].response(Gtk.ResponseType.CANCEL);pump()
        self.assertEqual([],self.submissions)
        self.assertEqual(first,self.service.get(first.id))

    def test_remote_multi_defers_typed_preview_and_rechecks_session(self):
        from c64u_browser.scheduler import DeviceSession
        from dataclasses import replace
        a=PickerSelection('c64u','/SD/a.crt','a.crt','/SD','founders','session-1','games','file')
        self.tab._start_bulk_scan=Mock()
        self.tab.add_selections((a,replace(a,path='/SD/b.crt',filename='b.crt')))
        self.assertEqual([],self.submissions)
        self.host.session=DeviceSession('founders','two')
        with self.assertRaises(ValueError):self.tab._start_bulk_scan.call_args.args[0]()
        self.assertEqual((),self.service.list())

    def test_files_add_shortcut_captures_paths_and_session(self):
        import ast
        import posixpath
        from c64u_browser import gui
        # Execute the actual menu branch; no copied callback implementation.
        tree=ast.parse(Path(gui.__file__).read_text())
        branch=next(node for node in ast.walk(tree) if isinstance(node,ast.If)
            and ast.dump(node.test)==ast.dump(ast.parse("not local and not directory and not hasattr(self,'managed_library_view')",mode='eval').body))
        callbacks=[]
        app=NS(core=self.host.core,remote='/SD',game_library_tab=NS(add_selections=Mock()),
            button=lambda box,label,callback:callbacks.append(callback))
        listing=NS(get_selected_rows=lambda:[NS(item=('a.crt',False)),NS(item=('b.crt',False))])
        env=dict(__name__="c64u_browser.gui",__package__="c64u_browser",self=app,local=False,directory=False,listing=listing,box=None,
            action=lambda callback:callback(),posixpath=posixpath)
        exec(compile(ast.Module(body=[branch],type_ignores=[]),'Files game menu','exec'),env)
        app.remote='/USB0';listing.get_selected_rows=lambda:[]
        from c64u_browser.scheduler import DeviceSession
        self.host.session=DeviceSession('replacement','two')
        callbacks[0]()
        selected=app.game_library_tab.add_selections.call_args.args[0]
        self.assertEqual(['/SD/a.crt','/SD/b.crt'],[s.path for s in selected])
        self.assertEqual({'session-1'},{s.session_id for s in selected})
        self.tab.add_selections(selected)
        self.assertEqual([],self.submissions)
        self.assertEqual((),self.service.list())
