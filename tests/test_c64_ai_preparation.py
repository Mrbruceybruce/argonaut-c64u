"""R4 file-before-bridge and private configuration revision gates."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from c64u_browser.api import BrowserError
from c64u_browser.c64_ai_bridge_config import (configuration_guard, configuration_revision,
    load_bridge_config, save_bridge_config)
from c64u_browser.c64_ai_bridge_control import SERVICE, HEALTH_TIMER
from c64u_browser.c64_ai_preparation import prepare_bridge
from c64u_browser.c64_ai_install import install_and_pair_c64_ai, build_c64_ai_client, _build_legacy_c64_ai_client
from c64u_browser.jobs import CoreJob
from c64u_browser.scheduler import JobBinding
from test_c64_ai_install import CONFIG, TARGET, server
import test_ftp_reads as reads


class PreparationTests(unittest.TestCase):
    core = reads.ReadMigrationTests.core
    connect = reads.ReadMigrationTests.connect

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)/'active.json'
        patcher=patch('c64u_browser.c64_ai_preparation.local_bridge_host', return_value=CONFIG.host)
        patcher.start();self.addCleanup(patcher.stop)

    def prepared(self):
        return prepare_bridge(self.path, CONFIG.model, '127.0.0.1', token_factory=lambda n:CONFIG.token)

    def run_prepared(self, core, prepared, **kwargs):
        with patch('c64u_browser.c64_ai_preparation.prepare_bridge', return_value=prepared):
            return install_and_pair_c64_ai(core.ai, self.path, '127.0.0.1', **kwargs)

    def test_pending_private_permissions_no_active_or_service_effects(self):
        prepared=self.prepared()
        self.assertFalse(self.path.exists())
        self.assertEqual(CONFIG, load_bridge_config(prepared.pending))
        self.assertEqual(0o700,prepared.pending.parent.stat().st_mode & 0o777)
        self.assertEqual(0o600,prepared.pending.stat().st_mode & 0o777)
        self.assertNotIn(CONFIG.token,repr(prepared))
        self.assertNotIn(str(prepared.pending),repr(prepared))

    def test_first_setup_nonpermitting_results_have_zero_bridge_effects(self):
        for mode in ('foreign','failed','cancelled','uncertain'):
            with self.subTest(mode=mode),server(b'foreign' if mode=='foreign' else None) as ftp:
                core,_=self.connect(ftp)
                prepared=self.prepared()
                runner=Mock(side_effect=AssertionError('bridge consequence'))
                if mode=='failed':ftp.replies[b'STOR']=b'550 rejected\r\n'
                if mode=='uncertain':ftp.after_mutation[b'RNTO']=None
                result=self.run_prepared(core,prepared,runner=runner,cancelled=lambda:mode=='cancelled')
                self.assertEqual('held',result.bridge_disposition)
                self.assertFalse(self.path.exists())
                self.assertTrue(prepared.pending.exists())
                self.assertEqual(CONFIG,load_bridge_config(prepared.pending))
                runner.assert_not_called()
                if mode == 'cancelled':
                    self.assertTrue(result.client.cancellation_observed)
                    self.assertNotIn(b'STOR', ftp.verbs)

    def test_existing_configuration_untouched_on_file_failure(self):
        save_bridge_config(self.path,CONFIG)
        original=self.path.read_bytes()
        with server(b'foreign') as ftp:
            core,_=self.connect(ftp)
            runner=Mock(side_effect=AssertionError('bridge consequence'))
            result=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',runner)
            self.assertEqual('held',result.bridge_disposition)
            self.assertEqual(original,self.path.read_bytes())
            runner.assert_not_called()

    def test_current_install_upgrade_finalize_only_after_released_ftp(self):
        for mode in ('current','install','upgrade'):
            content={'current':build_c64_ai_client(CONFIG),'install':None,'upgrade':_build_legacy_c64_ai_client(CONFIG)}[mode]
            with self.subTest(mode=mode),server(content) as ftp:
                self.path.unlink(missing_ok=True)
                core,_=self.connect(ftp)
                prepared=self.prepared()
                commands=[]
                def runner(args,**kwargs):
                    self.assertEqual(0,core._ftp_manager.active_count)
                    self.assertEqual(build_c64_ai_client(CONFIG),ftp.files[TARGET])
                    self.assertEqual(CONFIG,load_bridge_config(self.path))
                    commands.append(args)
                    return SimpleNamespace(returncode=0,stdout='active\n' if args[2]=='is-active' else 'enabled\n')
                result=self.run_prepared(core,prepared,runner=runner)
                self.assertEqual('ready',result.bridge_disposition)
                self.assertTrue(commands)
                self.assertFalse(prepared.pending.parent.exists())
                self.assertIsNone(result.pending_id)
                self.assertEqual(CONFIG.token,load_bridge_config(self.path).token)

    def test_bridge_failure_rolls_back_but_retains_file_and_pending(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            prepared=self.prepared()
            runner=Mock(return_value=SimpleNamespace(returncode=1,stdout=''))
            result=self.run_prepared(core,prepared,runner=runner)
            self.assertEqual('failed',result.bridge_disposition)
            self.assertEqual('installed',result.client.disposition)
            self.assertTrue(prepared.pending.exists())
            self.assertFalse(self.path.exists())
            self.assertEqual(build_c64_ai_client(CONFIG),ftp.files[TARGET])
            ftp.commands.clear()
            result=self.run_prepared(core,self.prepared(),runner=runner)
            self.assertEqual('verified-current',result.client.disposition)
            self.assertFalse({b'STOR',b'MKD',b'RNFR',b'RNTO'}.intersection(ftp.verbs))

    def test_pending_and_active_revision_mismatch(self):
        prepared=self.prepared()
        save_bridge_config(prepared.pending,replace(CONFIG,model='other'))
        with self.assertRaises(BrowserError):prepared.validate()
        save_bridge_config(self.path,CONFIG)
        with self.assertRaises(BrowserError):prepared.validate()

    def test_same_content_supported_write_changes_revision(self):
        save_bridge_config(self.path,CONFIG)
        prepared=self.prepared()
        save_bridge_config(self.path,CONFIG)
        with self.assertRaises(BrowserError):prepared.validate()

    def test_configuration_change_during_generation_stops_before_ftp(self):
        save_bridge_config(self.path,CONFIG)
        with server() as ftp:
            core,_=self.connect(ftp)
            ftp.commands.clear()
            def generate(config):
                save_bridge_config(self.path,replace(CONFIG,token='B'*64))
                return build_c64_ai_client(config)
            with patch('c64u_browser.c64_ai_operation.build_c64_ai_client',side_effect=generate):
                with self.assertRaises(BrowserError):install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1')
            self.assertEqual([],ftp.commands)

    def test_configuration_change_while_queued_stops_before_ftp(self):
        save_bridge_config(self.path,CONFIG)
        with server() as ftp:
            core,_=self.connect(ftp)
            prepared=self.prepared()
            reached,release=threading.Event(),threading.Event()
            core.scheduler.submit(CoreJob('barrier',lambda job:(reached.set(),release.wait(5))),JobBinding.device(core.device_session()))
            self.assertTrue(reached.wait(3))
            handle=core.ai.prepare(CONFIG,'127.0.0.1',config_check=prepared.validate)
            job=core.ai.execute(handle)
            save_bridge_config(self.path,replace(CONFIG,model='other'))
            ftp.commands.clear();release.set()
            result=job.wait(8).result
            self.assertFalse(result.permits_provisioning)
            self.assertEqual([],ftp.commands)

    def test_configuration_change_after_publication_blocks_pair(self):
        save_bridge_config(self.path,CONFIG)
        with server() as ftp:
            core,_=self.connect(ftp)
            ftp.mutation_hook=lambda v,p:save_bridge_config(self.path,replace(CONFIG,model='other')) if v==b'RNTO' else None
            runner=Mock(side_effect=AssertionError('bridge effect'))
            result=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',runner)
            self.assertEqual('installed',result.client.disposition)
            self.assertEqual('failed',result.bridge_disposition)
            runner.assert_not_called()

    def test_external_change_at_commit_detected(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            prepared=self.prepared()
            from c64u_browser import c64_ai_bridge_control as control
            def change(path,config,**kwargs):
                save_bridge_config(path,config,**kwargs)
                save_bridge_config(path,replace(config,model='other'))
            runner=Mock(side_effect=AssertionError('activation'))
            with patch.object(control,'save_bridge_config',side_effect=change):
                result=self.run_prepared(core,prepared,runner=runner)
            self.assertEqual('failed',result.bridge_disposition)
            self.assertEqual('installed',result.client.disposition)
            self.assertTrue(prepared.pending.exists())
            self.assertEqual('other', load_bridge_config(self.path).model)
            self.assertEqual([('stop',SERVICE)], [tuple(call.args[0][2:]) for call in runner.call_args_list])

    def test_supported_writers_serialize(self):
        save_bridge_config(self.path,CONFIG)
        entered,finished=threading.Event(),threading.Event()
        def writer():
            entered.set()
            save_bridge_config(self.path,replace(CONFIG,model='other'))
            finished.set()
        with configuration_guard(self.path):
            thread=threading.Thread(target=writer);thread.start()
            self.assertTrue(entered.wait(3))
            self.assertFalse(finished.wait(.05))
            self.assertEqual(CONFIG,load_bridge_config(self.path))
        thread.join(3)
        self.assertTrue(finished.is_set())

    def test_invalid_capacity_stops_before_ftp(self):
        config=replace(CONFIG,allowed_clients=('192.0.2.1','192.0.2.2','192.0.2.3','192.0.2.4'))
        save_bridge_config(self.path,config)
        with server() as ftp:
            core,_=self.connect(ftp);ftp.commands.clear()
            with self.assertRaises(BrowserError):install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1')
            self.assertEqual([],ftp.commands)

    def test_private_io_exception_chain_is_sanitized(self):
        with patch('c64u_browser.c64_ai_preparation.save_bridge_config',side_effect=OSError(CONFIG.token+' /private/secret')):
            with self.assertRaises(BrowserError) as caught:self.prepared()
        self.assertIsNone(caught.exception.__context__)
        self.assertIsNone(caught.exception.__cause__)
        self.assertNotIn(CONFIG.token,str(caught.exception))

    def test_gui_pair_entry_uses_core_and_never_setup_or_facade(self):
        import ast
        source=Path('c64u_browser/test_lab_tab.py').read_text()
        tree=ast.parse(source)
        method=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='pair_connected_c64')
        text=ast.unparse(method)
        self.assertIn('self.app.core.ai',text)
        self.assertNotIn('setup_bridge',text)
        self.assertNotIn('self.app.client',text)
        self.assertNotIn('test_connection',text)


    def test_edit_after_publish_before_enable_holds_activation(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            prepared=self.prepared()
            commands=[]
            def runner(args,**kwargs):
                commands.append(args[2])
                if args[2]=='daemon-reload':
                    save_bridge_config(self.path,replace(CONFIG,model='other'))
                return SimpleNamespace(returncode=0,stdout='enabled\n')
            result=self.run_prepared(core,prepared,runner=runner)
            self.assertEqual('installed',result.client.disposition)
            self.assertEqual('failed',result.bridge_disposition)
            self.assertEqual(['daemon-reload','is-enabled','stop'],commands)
            self.assertEqual('other',load_bridge_config(self.path).model)
            self.assertTrue(prepared.pending.exists())

    def ready_runner(self, calls, hook=lambda args: None):
        def run(args, **kwargs):
            calls.append(tuple(args[2:]))
            hook(args)
            return SimpleNamespace(returncode=0, stdout='active\n' if args[2]=='is-active' else 'enabled\n')
        return run

    def test_existing_status_edit_blocks_restart(self):
        for change in ('token', 'same-content'):
            with self.subTest(change=change), server() as ftp:
                save_bridge_config(self.path, CONFIG)
                core,_=self.connect(ftp)
                calls=[]
                def run(args, **kwargs):
                    calls.append(tuple(args[2:]))
                    if args[2]=='is-active':
                        save_bridge_config(self.path, replace(CONFIG, token='B'*64) if change=='token' else CONFIG)
                    return SimpleNamespace(returncode=3, stdout='inactive\n')
                with patch('c64u_browser.c64_ai_bridge_control.local_address_available', return_value=True):
                    result=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',run)
                self.assertEqual('installed',result.client.disposition)
                self.assertEqual('failed',result.bridge_disposition)
                self.assertEqual([('is-active',SERVICE),('is-enabled',SERVICE)],calls)
                self.assertEqual((),result.bridge_commands)

    def test_existing_activation_each_internal_boundary_stops_next_command(self):
        from c64u_browser.c64_ai_bridge_control import activate_bridge
        from c64u_browser.jobs import JobCancelled
        for boundary in ('restart','daemon-reload'):
            for invalidation in ('cancel','session'):
                with self.subTest(boundary=boundary,invalidation=invalidation):
                    save_bridge_config(self.path,CONFIG)
                    prepared=self.prepared()
                    calls=[];invalid=[False]
                    def check():
                        prepared.validate()
                        if invalid[0]:
                            if invalidation=='cancel':raise JobCancelled()
                            raise BrowserError('Stale session')
                    def run(args,**kwargs):
                        calls.append(tuple(args[2:]))
                        if args[2]==boundary:invalid[0]=True
                        return SimpleNamespace(returncode=1,stdout='')
                    with self.assertRaises(BrowserError if invalidation=='session' else JobCancelled):
                        activate_bridge(self.path,run,consequence_check=check)
                    expected=[('restart',SERVICE)]
                    if boundary=='daemon-reload':expected.append(('daemon-reload',))
                    self.assertEqual(expected,calls)

    def test_first_time_activation_cancellation_preserves_completed_command(self):
        for boundary in ('enable','restart'):
            with self.subTest(boundary=boundary),server() as ftp:
                core,_=self.connect(ftp)
                calls=[];cancel=[False]
                def hook(args):
                    if args[2]==boundary:cancel[0]=True
                result=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',
                    self.ready_runner(calls,hook),cancelled=lambda:cancel[0])
                self.assertEqual('installed',result.client.disposition)
                self.assertEqual('cancelled',result.bridge_disposition)
                expected=[('daemon-reload',),('is-enabled',SERVICE),('enable',SERVICE)]
                if boundary=='restart':expected += [('restart',SERVICE),('is-active',SERVICE),('is-enabled',SERVICE)]
                expected += [('stop',SERVICE)] # Existing setup rollback, never a file rollback.
                self.assertEqual(expected,calls)
                self.assertIn((boundary,'bridge','completed'),result.bridge_commands)
                self.assertEqual(1,ftp.verbs.count(b'STOR'))
                self.assertFalse(self.path.exists())

    def test_first_time_activation_retry_context_gates(self):
        for boundary in ('restart','daemon-reload'):
            with self.subTest(boundary=boundary),server() as ftp:
                core,_=self.connect(ftp)
                calls=[];restarting=[False]
                def run(args,**kwargs):
                    command=args[2];calls.append(tuple(args[2:]))
                    if command=='restart':restarting[0]=True
                    if restarting[0] and command==boundary:core._session_id='invalidated'
                    return SimpleNamespace(returncode=1 if command=='restart' else 0,
                                           stdout='enabled\n')
                result=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',run)
                self.assertEqual('stale-context',result.reason)
                expected=[('daemon-reload',),('is-enabled',SERVICE),('enable',SERVICE),('restart',SERVICE)]
                if boundary=='daemon-reload':expected.append(('daemon-reload',))
                expected.append(('stop',SERVICE))
                self.assertEqual(expected,calls)
                self.assertEqual('installed',result.client.disposition)

    def test_health_reload_cancellation_or_context_blocks_enable_now(self):
        for invalidation in ('cancel','session','pending'):
            with self.subTest(invalidation=invalidation),server() as ftp:
                core,_=self.connect(ftp)
                # A separate local setting per subcase avoids deliberate stale retained state.
                path=self.path.parent/(invalidation+'.json')
                path.parent.mkdir(exist_ok=True)
                if invalidation!='cancel':
                    path=self.path.parent/invalidation/'active.json'
                    path.parent.mkdir()
                calls=[];reloads=[0];cancel=[False]
                def hook(args):
                    if args[2]=='daemon-reload':
                        reloads[0]+=1
                        if reloads[0]==2:
                            if invalidation=='cancel':cancel[0]=True
                            elif invalidation=='session':core._session_id='invalidated'
                            else:
                                pending=next((path.parent/'.c64-ai-pending').glob('*/configuration.json'))
                                save_bridge_config(pending,replace(load_bridge_config(pending),model='other'))
                result=install_and_pair_c64_ai(core.ai,path,'127.0.0.1',
                    self.ready_runner(calls,hook),cancelled=lambda:cancel[0])
                self.assertEqual('installed',result.client.disposition)
                self.assertNotEqual('ready',result.bridge_disposition)
                self.assertEqual([('daemon-reload',),('is-enabled',SERVICE),('enable',SERVICE),
                    ('restart',SERVICE),('is-active',SERVICE),('is-enabled',SERVICE),
                    ('is-enabled',HEALTH_TIMER),('daemon-reload',),('stop',SERVICE)],calls)
                self.assertEqual(2,result.bridge_commands.count(('daemon-reload','bridge','completed')))

    def test_existing_pair_write_context_and_status_revision_gates(self):
        for boundary in ('before-write','during-status'):
            with self.subTest(boundary=boundary),server() as ftp:
                config=replace(CONFIG,allowed_clients=('192.0.2.1',))
                save_bridge_config(self.path,config)
                core,_=self.connect(ftp);calls=[]
                if boundary=='before-write':
                    from c64u_browser.c64_ai_bridge_control import pair_bridge_address
                    def pair(*args,context_check,**kwargs):
                        checks=[0]
                        def check():
                            checks[0]+=1
                            context_check()
                            if checks[0]==2:raise BrowserError('context stopped')
                        return pair_bridge_address(*args,context_check=check,**kwargs)
                    guard=patch('c64u_browser.c64_ai_preparation.pair_bridge_address',side_effect=pair)
                else:
                    from contextlib import nullcontext
                    guard=nullcontext()
                def hook(args):
                    if boundary=='during-status' and args[2]=='is-active':
                        save_bridge_config(self.path,replace(load_bridge_config(self.path),token='B'*64))
                with guard:
                    result=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',self.ready_runner(calls,hook))
                self.assertEqual('failed',result.bridge_disposition)
                if boundary=='before-write':
                    self.assertEqual([],calls)
                    self.assertEqual(config,load_bridge_config(self.path))
                else:
                    self.assertEqual([('restart',SERVICE),('is-active',SERVICE),('is-enabled',SERVICE)],calls)
                    self.assertIn(('restart','bridge','completed'),result.bridge_commands)

    def test_public_post_generation_revision_errors_hide_active_and_pending_paths(self):
        import logging
        from c64u_browser import c64_ai_preparation as preparation
        from c64u_browser.diagnostics import LOGGER, JsonEventFormatter
        for active in (False,True):
            with self.subTest(active=active),server() as ftp:
                # Isolate pending history from active case.
                path=self.path.parent/str(active)/'PRIVATE-ACTIVE.json'
                if active:save_bridge_config(path,CONFIG)
                core,_=self.connect(ftp);ftp.commands.clear()
                events=[];records=[];handles=[];generated=[False];secret_paths=[]
                class Handler(logging.Handler):
                    def emit(self,record):records.append(JsonEventFormatter().format(record))
                handler=Handler();LOGGER.addHandler(handler)
                core._ftp_manager._diagnostic=events.append
                original_revision=preparation.configuration_revision
                original_prepare=core.ai.prepare
                def capture(*args,**kwargs):
                    handle=original_prepare(*args,**kwargs);handles.append(handle)
                    generated[0]=True
                    return handle
                def revision(candidate):
                    if generated[0] and (active or Path(candidate).name=='configuration.json'):
                        secret_paths.append(str(candidate))
                        raise PermissionError(13,'TOKEN-SENTINEL PROGRAM-SENTINEL PASSWORD-SENTINEL',str(candidate))
                    return original_revision(candidate)
                calls=[]
                try:
                    with patch.object(core.ai,'prepare',side_effect=capture),patch.object(preparation,'configuration_revision',side_effect=revision):
                        with self.assertRaises(BrowserError) as caught:
                            install_and_pair_c64_ai(core.ai,path,'127.0.0.1',self.ready_runner(calls))
                    exc=caught.exception
                    self.assertIsNone(exc.__cause__);self.assertIsNone(exc.__context__)
                    public=repr((str(exc),exc,events,records))
                    for marker in secret_paths+['TOKEN-SENTINEL','PROGRAM-SENTINEL','PASSWORD-SENTINEL',CONFIG.token,repr(build_c64_ai_client(CONFIG))]:
                        self.assertNotIn(marker,public)
                    self.assertTrue(secret_paths);self.assertEqual([],calls);self.assertEqual([],ftp.commands)
                    self.assertEqual(1,len(handles))
                    with self.assertRaises(BrowserError):core.ai.execute(handles[0])
                finally:LOGGER.removeHandler(handler)

    def test_public_preparation_generation_and_submission_failures_are_sanitized(self):
        for phase in ('prepare_bridge','generation','timer','submission'):
            with self.subTest(phase=phase),server() as ftp:
                path=self.path.parent/phase/'PRIVATE.json'
                core,_=self.connect(ftp);ftp.commands.clear()
                target={'prepare_bridge':'c64u_browser.c64_ai_preparation.configuration_revision',
                    'generation':'c64u_browser.c64_ai_operation.build_c64_ai_client',
                    'timer':'c64u_browser.c64_ai_operation.Timer.start'}
                error=OSError('TOKEN PROGRAM /private/SENTINEL')
                blocker=(patch.object(core.scheduler,'submit',side_effect=error) if phase=='submission'
                         else patch(target[phase],side_effect=error))
                with blocker:
                    with self.assertRaises(BrowserError) as caught:
                        install_and_pair_c64_ai(core.ai,path,'127.0.0.1')
                exc=caught.exception
                self.assertIsNone(exc.__context__);self.assertIsNone(exc.__cause__)
                for marker in ('TOKEN','PROGRAM','/private/SENTINEL'):self.assertNotIn(marker,repr(exc))
                self.assertEqual({},core.ai._AIFileService__plans)
                self.assertEqual([],ftp.commands)

    def test_ordinary_retry_reuses_retained_token_and_fresh_core_classification(self):
        import secrets
        with server() as ftp:
            core,_=self.connect(ftp);calls=[];tokens=[]
            real_prepare=prepare_bridge
            def token(n):
                value=secrets.token_hex(n);tokens.append(value);return value
            def ordinary(*args,**kwargs):return real_prepare(*args,**kwargs,token_factory=token)
            with patch('c64u_browser.c64_ai_preparation.prepare_bridge',side_effect=ordinary):
                first=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',
                    lambda *a,**kw:SimpleNamespace(returncode=1,stdout=''))
                self.assertEqual('installed',first.client.disposition)
                self.assertFalse(self.path.exists())
                pending=next((self.path.parent/'.c64-ai-pending').glob('*/configuration.json'))
                retained=load_bridge_config(pending)
                self.assertEqual(build_c64_ai_client(retained),ftp.files[TARGET])
                ftp.commands.clear()
                second=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',self.ready_runner(calls))
            self.assertEqual(1,len(tokens))
            self.assertEqual('ready',second.bridge_disposition)
            self.assertEqual('verified-current',second.client.disposition)
            self.assertEqual(first.pending_id,second.client.config_id)
            self.assertNotEqual(first.client.preparation_id,second.client.preparation_id)
            self.assertEqual(retained,load_bridge_config(self.path))
            self.assertFalse(pending.parent.exists());self.assertIsNone(second.pending_id)
            self.assertFalse({b'STOR',b'MKD',b'RNFR',b'RNTO',b'DELE',b'RMD'}.intersection(ftp.verbs))
            self.assertEqual(1,ftp.verbs.count(b'RETR'));self.assertEqual(2,ftp.verbs.count(b'SIZE'))
            self.assertEqual([('daemon-reload',),('is-enabled',SERVICE),('enable',SERVICE),
                ('restart',SERVICE),('is-active',SERVICE),('is-enabled',SERVICE),
                ('is-enabled',HEALTH_TIMER),('daemon-reload',),('enable','--now',HEALTH_TIMER),
                ('is-enabled',HEALTH_TIMER),('is-active',HEALTH_TIMER)],calls)

    def test_ineligible_retained_config_refuses_without_token_or_consequence(self):
        import json, os, shutil
        from c64u_browser import c64_ai_preparation as preparation
        for defect in ('corrupt','stale','address','model','host','device','permissions','owner',
                       'symlink','provenance','multiple','active-conflict','schema','port','model-field'):
            with self.subTest(defect=defect),server() as ftp:
                path=self.path.parent/defect/'active.json'
                core,_=self.connect(ftp)
                prepared=prepare_bridge(path,CONFIG.model,'127.0.0.1',device_id=core.device_session().device_id)
                pending=prepared.pending
                if defect in ('schema','port','model-field'):
                    content=json.loads(pending.read_text())
                    key='model' if defect=='model-field' else defect
                    content[key]={'schema':2,'port':80,'model-field':'model:cloud'}[defect]
                    pending.write_text(json.dumps(content))
                    metadata=json.loads(prepared.provenance.read_text())
                    metadata['revision']=preparation._fingerprint(pending)
                    prepared.provenance.write_text(json.dumps(metadata))
                elif defect=='corrupt':pending.write_text('invalid')
                elif defect=='stale':save_bridge_config(pending,load_bridge_config(pending))
                elif defect=='address':
                    data=json.loads(prepared.provenance.read_text());data['address']='192.0.2.4'
                    prepared.provenance.write_text(json.dumps(data))
                elif defect=='device':
                    data=json.loads(prepared.provenance.read_text());data['device']='other'
                    prepared.provenance.write_text(json.dumps(data))
                elif defect=='permissions':pending.chmod(0o644)
                elif defect=='symlink':
                    copy=pending.parent/'copy';pending.rename(copy);pending.symlink_to(copy)
                elif defect=='provenance':prepared.provenance.unlink()
                elif defect=='multiple':shutil.copytree(pending.parent,pending.parent.parent/('b'*32))
                elif defect=='active-conflict':save_bridge_config(path,prepared.config)
                ftp.commands.clear();calls=[]
                from contextlib import nullcontext
                host=patch.object(preparation,'local_bridge_host',return_value='192.0.2.2') if defect=='host' else nullcontext()
                owner=patch.object(preparation.os,'getuid',return_value=-1) if defect=='owner' else nullcontext()
                tokens=Mock(side_effect=AssertionError('token must not be generated'))
                original=prepare_bridge
                def ordinary(*args,**kwargs):return original(*args,**kwargs,token_factory=tokens)
                with host,owner,patch.object(preparation,'prepare_bridge',side_effect=ordinary):
                    with self.assertRaises(BrowserError) as caught:
                        install_and_pair_c64_ai(core.ai,path,'127.0.0.1',self.ready_runner(calls),
                                                model='other' if defect=='model' else CONFIG.model)
                self.assertIn('review',str(caught.exception))
                self.assertNotIn(str(path),str(caught.exception))
                tokens.assert_not_called();self.assertEqual([],calls);self.assertEqual([],ftp.commands)
                self.assertTrue(pending.exists())

    def test_retained_reentry_reconnect_is_fresh_but_old_handle_cannot_continue(self):
        with server() as ftp:
            core,profile=self.connect(ftp)
            first=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',
                lambda *a,**kw:SimpleNamespace(returncode=1,stdout=''))
            pending=next((self.path.parent/'.c64-ai-pending').glob('*/configuration.json'))
            retained=load_bridge_config(pending)
            old=core.ai.prepare(retained,'127.0.0.1')
            core.connect(profile,remote_folder='/USB1') # Actual Core reconnect.
            ftp.commands.clear()
            snapshot=core.ai.execute(old).wait(8)
            self.assertEqual('failed',snapshot.state);self.assertEqual([],ftp.commands)
            result=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',self.ready_runner([]))
            self.assertEqual('verified-current',result.client.disposition)
            self.assertNotEqual(first.client.session_id,result.client.session_id)
            self.assertEqual(first.pending_id,result.client.config_id)
            self.assertFalse({b'STOR',b'MKD',b'RNFR',b'RNTO'}.intersection(ftp.verbs))

    def test_context_change_during_pending_preparation_prevents_fresh_plan(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            original=prepare_bridge
            def changed(*args,**kwargs):
                prepared=original(*args,**kwargs)
                core._session_id='invalidated'
                return prepared
            ftp.commands.clear()
            with patch('c64u_browser.c64_ai_preparation.prepare_bridge',side_effect=changed):
                with self.assertRaises(BrowserError):install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1')
            self.assertEqual([],ftp.commands)
            self.assertEqual({},core.ai._AIFileService__plans)

    def test_after_acknowledged_file_success_cancellation_only_holds_bridge(self):
        from c64u_browser import c64_ai_operation as operation
        for legacy in (False,True):
            with self.subTest(legacy=legacy),server(_build_legacy_c64_ai_client(CONFIG) if legacy else None) as ftp:
                save_bridge_config(self.path,CONFIG)
                core,_=self.connect(ftp);cancel=[False];snapshots=[];calls=[]
                name='replace_managed' if legacy else 'upload_managed'
                primitive=getattr(operation,name)
                def acknowledged(*args,**kwargs):
                    evidence=primitive(*args,**kwargs)
                    if legacy:
                        self.assertEqual('completed',evidence.publication)
                        self.assertEqual('completed',evidence.cleanup)
                    else:self.assertEqual('completed',evidence['upload'].publication['outcome'])
                    # Client has consumed successful replies and the composite has returned.
                    cancel[0]=True
                    return evidence
                reached,release=threading.Event(),threading.Event()
                original_acknowledged=acknowledged
                def barrier(*args,**kwargs):
                    evidence=original_acknowledged(*args,**kwargs)
                    reached.set()
                    if not release.wait(5):raise AssertionError('ack barrier timed out')
                    return evidence
                execute=core.ai.execute
                def capture(*args,**kwargs):
                    job=execute(*args,**kwargs)
                    job.add_listener(lambda event:snapshots.append(event.job))
                    self.assertTrue(reached.wait(5))
                    job.request_cancel()
                    release.set()
                    return job
                with patch.object(operation,name,side_effect=barrier),patch.object(core.ai,'execute',side_effect=capture):
                    result=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',
                        self.ready_runner(calls),cancelled=lambda:cancel[0])
                self.assertEqual('upgraded' if legacy else 'installed',result.client.disposition)
                self.assertEqual('held',result.bridge_disposition)
                self.assertTrue(result.client.cancellation_requested)
                self.assertEqual('succeeded',snapshots[-1].state)
                self.assertEqual([],calls);self.assertEqual(1,ftp.verbs.count(b'STOR'))
                self.assertEqual(build_c64_ai_client(CONFIG),ftp.files[TARGET])

    def test_existing_stopped_activation_cancellation_and_session_gates(self):
        for boundary in ('restart','daemon-reload'):
            for invalidate in ('cancel','session'):
                with self.subTest(boundary=boundary,invalidate=invalidate),server() as ftp:
                    save_bridge_config(self.path,CONFIG)
                    core,_=self.connect(ftp);calls=[];cancel=[False]
                    def run(args,**kwargs):
                        calls.append(tuple(args[2:]))
                        if args[2]==boundary:
                            if invalidate=='cancel':cancel[0]=True
                            else:core._session_id='invalidated'
                        return SimpleNamespace(returncode=1,stdout='inactive\n')
                    with patch('c64u_browser.c64_ai_bridge_control.local_address_available',return_value=True):
                        result=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',run,cancelled=lambda:cancel[0])
                    self.assertEqual('installed',result.client.disposition)
                    self.assertEqual('cancelled' if invalidate=='cancel' else 'failed',result.bridge_disposition)
                    expected=[('is-active',SERVICE),('is-enabled',SERVICE),('restart',SERVICE)]
                    if boundary=='daemon-reload':expected.append(('daemon-reload',))
                    self.assertEqual(expected,calls)
                    self.assertIn(('restart','bridge','failed'),result.bridge_commands)
                    self.assertEqual(CONFIG,load_bridge_config(self.path))

    def test_pending_cleanup_failure_is_safe_and_preserves_committed_active_and_file(self):
        with server() as ftp:
            core,_=self.connect(ftp);calls=[]
            unlink=Path.unlink
            def fail_pending(path,*args,**kwargs):
                if path.name=='configuration.json':raise PermissionError('TOKEN /private/SENTINEL')
                return unlink(path,*args,**kwargs)
            with patch.object(Path,'unlink',fail_pending):
                result=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',self.ready_runner(calls))
            self.assertEqual('installed',result.client.disposition)
            self.assertEqual('failed',result.bridge_disposition)
            self.assertNotIn('TOKEN',repr(result));self.assertNotIn('/private/SENTINEL',repr(result))
            pending=next((self.path.parent/'.c64-ai-pending').glob('*/configuration.json'))
            self.assertEqual(load_bridge_config(pending),load_bridge_config(self.path))
            self.assertNotIn(('stop',SERVICE),calls)
            ftp.commands.clear()
            with self.assertRaises(BrowserError):
                install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',self.ready_runner([]))
            self.assertEqual([],ftp.commands) # Conflicting active/pending needs explicit local review.

    def test_retained_retry_fresh_classification_refuses_changed_remote_without_replay(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            first=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',
                lambda *a,**kw:SimpleNamespace(returncode=1,stdout=''))
            ftp.files[TARGET]=b'foreign';ftp.commands.clear();calls=[]
            second=install_and_pair_c64_ai(core.ai,self.path,'127.0.0.1',self.ready_runner(calls))
            self.assertEqual(first.pending_id,second.pending_id)
            self.assertEqual('foreign',second.client.classification)
            self.assertEqual('held',second.bridge_disposition)
            self.assertEqual([],calls)
            self.assertFalse({b'STOR',b'MKD',b'RNFR',b'RNTO',b'DELE',b'RMD'}.intersection(ftp.verbs))
            self.assertEqual(b'foreign',ftp.files[TARGET])


    def test_active_publish_rechecks_after_temporary_write(self):
        import os
        for active in (False,True):
            for invalidation in ('cancel','revision'):
                with self.subTest(active=active,invalidation=invalidation),server() as ftp:
                    path=self.path.parent/(str(active)+invalidation)/'active.json'
                    config=replace(CONFIG,allowed_clients=('192.0.2.1',))
                    if active:save_bridge_config(path,config)
                    core,_=self.connect(ftp)
                    prepared=prepare_bridge(path,CONFIG.model,'127.0.0.1',device_id=core.device_session().device_id)
                    original=path.read_bytes() if active else None
                    cancel=[False];calls=[];fsync=os.fsync
                    def changed(fd):
                        fsync(fd)
                        if invalidation=='cancel':cancel[0]=True
                        else:
                            # Detectable external edit while the unpublished temp file is flushed.
                            path.write_text('external revision')
                    with patch('c64u_browser.c64_ai_preparation.prepare_bridge',return_value=prepared), \
                         patch('c64u_browser.c64_ai_bridge_config.os.fsync',side_effect=changed):
                        result=install_and_pair_c64_ai(core.ai,path,'127.0.0.1',self.ready_runner(calls),
                                                       cancelled=lambda:cancel[0])
                    self.assertEqual('installed',result.client.disposition)
                    self.assertEqual('cancelled' if invalidation=='cancel' else 'failed',result.bridge_disposition)
                    self.assertEqual([],calls)
                    if invalidation=='revision':self.assertEqual('external revision',path.read_text())
                    elif active:self.assertEqual(original,path.read_bytes())
                    else:self.assertFalse(path.exists())
                    self.assertEqual([],[entry for entry in path.parent.glob('.c64-ai-*') if entry.is_file()])
