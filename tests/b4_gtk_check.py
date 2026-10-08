"""Explicit offline B4 GTK qualification: run with a display; never silently skip."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import ast
import hashlib
import unittest
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib, GdkPixbuf
from c64u_browser.gui import Browser
from c64u_browser.core import CoreError
from c64u_browser.profiles import Profile
from c64u_browser.version import ASSETS
import test_core
import test_recovery
import test_preferences_ui


class HeaderGtkTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Gtk.init_check(), 'Offline GTK display required')
        self.fixture=test_preferences_ui.PreferencesUI()
        # Trap all Python socket connections; real GTK uses its own display IPC.
        self.trap=patch('socket.socket.connect',side_effect=AssertionError('Network forbidden'))
        self.trap.start();self.addCleanup(self.trap.stop)
        self.accessible=[]
        original=Gtk.Button.update_property
        def update(widget,properties,values):
            self.accessible.append((widget,properties,values))
            return original(widget,properties,values)
        with patch.object(Gtk.Button,'update_property',update):self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.app=self.fixture.app;self.fixture.pump()

    def buttons(self):
        result=[];child=self.app.connection_header.get_first_child()
        while child:
            if isinstance(child,Gtk.Button):result.append(child)
            child=child.get_next_sibling()
        return result

    def test_header_order_accessibility_icon_and_machine_retirement(self):
        buttons=self.buttons()
        self.assertEqual(buttons,[self.app.reconnect_button,self.app.disconnect_button,self.app.settings_button,self.app.power_button])
        self.assertEqual([b.get_label() for b in buttons[:3]],['Reconnect','Disconnect','Settings'])
        self.assertIsNone(buttons[-1].get_label())
        self.assertTrue(any(w is buttons[-1] and p==[Gtk.AccessibleProperty.LABEL] and v==['Ultimate Power'] for w,p,v in self.accessible))
        self.assertEqual(buttons[-1].get_tooltip_text(),'Ultimate Power\nPower, reset, and memory actions for the connected C64 Ultimate.')
        self.assertIsInstance(buttons[-1].get_child(),Gtk.Image)
        self.assertEqual(buttons[-1].get_child().get_pixel_size(),24)
        self.assertFalse(hasattr(self.app,'quick_connect_button'))
        labels=[self.app.tabs.get_tab_label_text(self.app.tabs.get_nth_page(i)) for i in range(self.app.tabs.get_n_pages())]
        self.assertNotIn('Machine',labels);self.assertIn('Test Lab',labels)
        self.assertFalse(self.app.reconnect_button.get_sensitive())

    def test_header_keyboard_order_and_small_widths(self):
        header=self.app.connection_header;self.app.controls.remove(header)
        window=Gtk.Window();window.set_child(header)
        self.addCleanup(window.destroy)
        for b in self.buttons():b.set_sensitive(True)
        self.app.connection_label.set_text('Connected · Synthetic device · Firmware 1.1.0 · API 0.1')
        for width in (640,740,900):
            window.set_default_size(width,100);window.present();self.fixture.pump()
            buttons=self.buttons()
            for a,b in zip(buttons,buttons[1:]):
                aa=a.get_allocation();bb=b.get_allocation()
                self.assertLessEqual(aa.x+aa.width,bb.x)
            last=buttons[-1].get_allocation()
            self.assertLessEqual(last.x+last.width,header.get_width())
            buttons[0].grab_focus()
            for expected in buttons[1:]:
                header.child_focus(Gtk.DirectionType.TAB_FORWARD)
                self.assertIs(window.get_focus(),expected)

    def test_settings_opens_existing_pages(self):
        self.app.settings_button.emit('clicked');self.fixture.pump()
        dialog=self.app.preferences_dialog
        self.assertEqual(dialog.get_title(),'Argonaut Settings')
        self.assertEqual([dialog.pages.get_tab_label_text(dialog.pages.get_nth_page(i)) for i in range(3)],['General','Device details','About'])
        dialog.response(Gtk.ResponseType.CLOSE);self.fixture.pump()

    def test_power_open_close_reopen_disconnected_and_keyboard(self):
        self.app.power_button.emit('clicked');self.fixture.pump()
        controller=self.app.ultimate_power;dialog=controller.dialog
        self.assertEqual(dialog.get_title(),'Ultimate Power')
        self.assertFalse(controller.actions.get_sensitive())
        self.assertIsNone(controller.command('reset'))
        dialog.response(Gtk.ResponseType.CLOSE);self.fixture.pump()
        self.assertIsNone(controller.dialog)
        self.app.power_button.emit('clicked');self.fixture.pump()
        self.assertIsNot(controller.dialog,dialog)
        controller.client=Mock(host='synthetic');controller.bind(controller.client)
        first=controller.actions.get_first_child();second=first.get_next_sibling()
        self.assertEqual([first.get_label(),second.get_label()],['Reset C64…','Reboot C64…'])
        first.grab_focus();controller.actions.child_focus(Gtk.DirectionType.TAB_FORWARD)
        self.assertIs(controller.dialog.get_focus(),second)
        controller.dialog.response(Gtk.ResponseType.CLOSE)

    def connect_synthetic_power(self):
        core=self.app.core
        core._client_factory=test_core.FakeClient
        profile=Profile.new('Synthetic','192.0.2.20',device_id='ABC123')
        core.connect(profile,initial_browse=False)
        client=core._require_client();client.machine_action=Mock(return_value={})
        self.app.ultimate_power.bind(core.device_operations)
        self.app.recovery.lost=Mock()
        self.app.power_button.emit('clicked');self.fixture.pump()
        return core,client

    def confirmation_from_button(self, action):
        box=self.app.ultimate_power.actions
        button=box.get_first_child()
        if action=='reboot':button=button.get_next_sibling()
        button.emit('clicked');self.fixture.pump()
        return next(w for w in Gtk.Window.list_toplevels() if
                    w.get_title()==action.title()+' C64')

    def test_power_buttons_cancel_and_execute_reviewed_commands(self):
        core,client=self.connect_synthetic_power()
        for action in ('reset','reboot'):
            self.confirmation_from_button(action).response(Gtk.ResponseType.CANCEL)
            self.fixture.pump();client.machine_action.assert_not_called()
            self.app.run=lambda task,done:done(task()) or True
            dialog=self.confirmation_from_button(action)
            dialog.response(Gtk.ResponseType.OK);self.fixture.pump()
            client.machine_action.assert_called_once_with(action)
            self.app.recovery.lost.assert_called_once()
            client.machine_action.reset_mock();self.app.recovery.lost.reset_mock()
        self.app.ultimate_power.dialog.response(Gtk.ResponseType.CLOSE)

    def test_power_ui_stale_session_refuses_both_commands(self):
        core,client=self.connect_synthetic_power()
        self.app.run=lambda task,done:done(task()) or True
        for action in ('reset','reboot'):
            dialog=self.confirmation_from_button(action)
            core.reconnect()
            new=core._require_client();new.machine_action=Mock()
            dialog.response(Gtk.ResponseType.OK);self.fixture.pump()
            client.machine_action.assert_not_called();new.machine_action.assert_not_called()
            self.assertEqual(self.app.status.get_text(),
                             'Connection changed. '+action.title()+' was not sent.')
            client=new
        self.app.recovery.lost.assert_not_called()
        self.app.ultimate_power.dialog.response(Gtk.ResponseType.CLOSE)

    def test_power_ui_submission_failure_discards_authorization(self):
        core,client=self.connect_synthetic_power()
        for action in ('reset','reboot'):
            dialog=self.confirmation_from_button(action)
            with patch.object(self.app.pool,'submit',side_effect=RuntimeError('synthetic refusal')) as submit:
                dialog.response(Gtk.ResponseType.OK);self.fixture.pump()
                self.assertFalse(core._machine_targets)
                submit.assert_called_once()
            # Emitting the old GTK response after failed handoff cannot resubmit.
            with patch.object(self.app.pool,'submit') as submit:
                dialog.response(Gtk.ResponseType.OK);self.fixture.pump()
                submit.assert_not_called()
        client.machine_action.assert_not_called();self.app.recovery.lost.assert_not_called()
        self.app.ultimate_power.dialog.response(Gtk.ResponseType.CLOSE)

    def check_restored_settings(self, pending, loss=False):
        app=self.app;core=app.core;clients=[]
        class SettingsClient(test_core.FakeClient):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                self.value='fresh-'+str(len(clients))
                self.apply_configuration=Mock()
                self.save_configuration=Mock()
                clients.append(self)
            def read_configuration(self,category=None):
                if category is None:return {'categories':['Synthetic settings']}
                if category=='Synthetic settings':
                    return {category:{'Value':{'current':self.value}}}
                return super().read_configuration(category)
        core._client_factory=SettingsClient
        app.run=lambda task,done:done(task()) or True
        result=core.connect(Profile.new('Synthetic','192.0.2.20',device_id='ABC123'))
        app.activate_connection(result)
        tab=app.settings_tab;tab.reload()
        key=('Synthetic settings','Value')
        setting=tab.all_settings[key[0]][0]
        self.assertEqual(setting.current,'fresh-0')
        if pending:tab.stage(key[0],setting,'retained draft')
        self.assertEqual(tab.apply_button.get_sensitive(),pending)
        self.assertEqual(tab.flash_button.get_sensitive(),not pending)
        drafts=dict(tab.drafts);edits=dict(tab.pending)
        session=core.device_session();profile=core.active_profile
        with patch.object(core,'reconnect',wraps=core.reconnect) as reconnect:
            if loss:
                app.recovery.lost('Synthetic connection loss')
                restored=core.reconnect(app.remote_root)
                app.recovery.accept(restored,was_offline=True)
            else:
                app.reconnect_button.emit('clicked')
            reconnect.assert_called_once()
        current=core.device_session()
        self.assertNotEqual(session,current)
        self.assertTrue(current.session_id)
        self.assertEqual(core.active_profile,profile)
        self.assertIs(core._require_client(),clients[-1])
        self.assertFalse(app.recovery.offline)
        self.assertFalse(app.recovery.inflight)
        self.assertFalse(app.recovery.paused)
        self.assertIsNone(app.offline_message)
        self.assertEqual(tab.pending,edits);self.assertEqual(tab.drafts,drafts)
        self.assertTrue(tab.requires_refresh)
        self.assertFalse(tab.rows.get_sensitive())
        self.assertFalse(tab.apply_button.get_sensitive())
        self.assertFalse(tab.flash_button.get_sensitive())
        self.assertIn('Reload',app.status.get_text())
        self.assertIn('Discard' if pending else 'Reload',tab.heading.get_text())
        with patch.object(tab,'confirm') as confirm, patch.object(tab,'request') as request:
            tab.stage(key[0],setting,'forbidden edit')
            tab.apply();tab.apply_reviewed(dict(edits));tab.save_to_flash()
            confirm.assert_not_called();request.assert_not_called()
        self.assertEqual(tab.pending,edits);self.assertEqual(tab.drafts,drafts)
        if pending:
            tab.reload()  # Retained drafts prevent implicit reload/discard.
            self.assertTrue(tab.requires_refresh);self.assertEqual(tab.pending,edits)
            tab.revert()
            self.assertTrue(tab.requires_refresh)
            self.assertFalse(tab.flash_button.get_sensitive())
        tab.reload()
        self.assertFalse(tab.requires_refresh)
        self.assertTrue(tab.loaded);self.assertTrue(tab.rows.get_sensitive())
        self.assertFalse(tab.pending);self.assertFalse(tab.drafts)
        self.assertFalse(tab.apply_button.get_sensitive())
        self.assertTrue(tab.flash_button.get_sensitive())
        fresh=tab.all_settings[key[0]][0]
        self.assertEqual(fresh.current,'fresh-1')
        tab.stage(key[0],fresh,'new deliberate draft')
        self.assertTrue(tab.apply_button.get_sensitive())
        self.assertEqual(core.device_session(),current)
        self.assertEqual(len(clients),2)
        for client in clients:
            client.apply_configuration.assert_not_called()
            client.save_configuration.assert_not_called()

    def test_connected_reconnect_retains_and_gates_pending_settings(self):
        self.check_restored_settings(pending=True)

    def test_connected_reconnect_gates_flash_without_pending_settings(self):
        self.check_restored_settings(pending=False)

    def test_loss_recovery_retains_and_gates_pending_settings(self):
        self.check_restored_settings(pending=True,loss=True)

    def test_loss_recovery_gates_flash_without_pending_settings(self):
        self.check_restored_settings(pending=False,loss=True)

    def check_flash_confirmation(self, restore=None, drafts=False):
        app=self.app;core=app.core;clients=[]
        class FlashClient(test_core.FakeClient):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                self.save_configuration=Mock(return_value={})
                clients.append(self)
            def read_configuration(self,category=None):
                if category is None:return {'categories':['Synthetic settings']}
                if category=='Synthetic settings':
                    return {category:{'Value':{'current':'baseline'}}}
                return super().read_configuration(category)
        core._client_factory=FlashClient
        app.run=lambda task,done:done(task()) or True
        app.activate_connection(core.connect(Profile.new('Synthetic','192.0.2.20',device_id='ABC123')))
        tab=app.settings_tab;tab.reload()
        self.assertTrue(tab.loaded);self.assertFalse(tab.requires_refresh)
        self.assertTrue(tab.flash_button.get_sensitive())
        dialog=tab.save_to_flash()
        self.assertIsInstance(dialog,Gtk.Dialog)
        self.addCleanup(dialog.destroy)
        if drafts:
            # Exercise retained local state while an older confirmation exists.
            tab.stage('Synthetic settings',tab.all_settings['Synthetic settings'][0],'draft')
        retained=dict(tab.drafts);pending=dict(tab.pending);baseline=tab.all_settings
        old=core.device_session()
        if restore=='loss':
            app.recovery.lost('Synthetic loss')
            app.recovery.accept(core.reconnect(app.remote_root),was_offline=True)
        elif restore=='reconnect':
            app.reconnect_button.emit('clicked')
        current=core.device_session();profile=core.active_profile
        if restore:
            self.assertNotEqual(current,old);self.assertTrue(current.session_id)
            self.assertTrue(tab.requires_refresh)
            self.assertFalse(tab.flash_button.get_sensitive())
            # Spy on real submission/confirmation paths without replacing them.
            with patch.object(app,'run',wraps=app.run) as run, patch.object(tab,'confirm',wraps=tab.confirm) as confirm:
                dialog.response(Gtk.ResponseType.OK)
                dialog.response(Gtk.ResponseType.OK)
                run.assert_not_called();confirm.assert_not_called()
            self.assertIn('Reload settings before saving to Flash',app.status.get_text())
            self.assertTrue(tab.requires_refresh)
            self.assertIs(tab.all_settings,baseline)
            self.assertEqual(tab.drafts,retained);self.assertEqual(tab.pending,pending)
            self.assertFalse(tab.rows.get_sensitive())
            for client in clients:client.save_configuration.assert_not_called()
        else:
            with patch.object(app,'run',wraps=app.run) as run:
                dialog.response(Gtk.ResponseType.OK)
                run.assert_called_once()
            clients[0].save_configuration.assert_called_once_with()
            self.assertFalse(tab.requires_refresh)
            self.assertEqual(app.status.get_text(),'C64U confirmed Save to Flash.')
        self.assertEqual(core.device_session(),current)
        self.assertEqual(core.active_profile,profile)
        self.assertIs(core._require_client(),clients[-1])
        self.assertFalse(app.recovery.offline);self.assertFalse(app.recovery.inflight)
        self.assertEqual(len(clients),2 if restore else 1)

    def test_old_flash_confirmation_refused_after_loss_recovery(self):
        self.check_flash_confirmation(restore='loss')

    def test_old_flash_confirmation_refused_after_connected_reconnect(self):
        self.check_flash_confirmation(restore='reconnect')

    def test_old_flash_confirmation_preserves_retained_drafts(self):
        self.check_flash_confirmation(restore='loss',drafts=True)

    def test_fresh_flash_confirmation_executes_once(self):
        self.check_flash_confirmation()

    def test_svg_original_bytes_colors_and_loader(self):
        data=(ASSETS/'commodore-c-equals.svg').read_bytes()
        self.assertEqual(len(data),454)
        self.assertEqual(hashlib.sha1(data).hexdigest(),'132e51b7e1acb7d04fc4fc8cd9fe30d2926c74c2')
        self.assertIn(b'#002255',data);self.assertIn(b'#ff0000',data)
        pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ASSETS/'commodore-c-equals.svg'),24,24,True)
        self.assertEqual(pixbuf.get_width(),24)
        self.assertGreater(pixbuf.get_height(),20)
        attribution=(ASSETS/'COMMODORE-ATTRIBUTION.txt').read_text()
        self.assertIn('Alien426',attribution);self.assertIn('trademark',attribution)


if __name__=='__main__':unittest.main()
