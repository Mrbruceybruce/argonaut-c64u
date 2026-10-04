"""R4 loopback contract. Every device socket is a local fixture."""
from dataclasses import asdict, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from c64u_ftp_server import FakeC64UFtp
import test_ftp_reads as reads
from c64u_browser.api import BrowserError
from c64u_browser.c64_ai_bridge_config import C64BridgeConfig, save_bridge_config, load_bridge_config
from c64u_browser.c64_ai_install import (ClientInstallResult, _build_legacy_c64_ai_client,
    build_c64_ai_client, install_and_pair_c64_ai)
from c64u_browser.c64_ai_operation import _ExactSink, EligibilityObservation
from c64u_browser.jobs import CoreJob
from c64u_browser.scheduler import JobBinding

CONFIG = C64BridgeConfig('gemma3:4b', '192.168.68.80', 6464, ('127.0.0.1',), 'A' * 64)
TARGET = b'/USB2/argonaut-ai.prg'
MUTATIONS = {b'STOR', b'MKD', b'RNFR', b'RNTO', b'DELE', b'RMD'}


def server(content=None):
    files = {b'/USB1/sentinel': b'keep'}
    if content is not None:files[TARGET] = content
    return FakeC64UFtp(files=files, directories={b'/': b'', b'/USB1': b'', b'/USB2': b'', b'/SD': b''},
                      mutation_tree=True)


class C64AIInstallTests(unittest.TestCase):
    core = reads.ReadMigrationTests.core
    connect = reads.ReadMigrationTests.connect

    def run_file(self, core, ftp, *, config=CONFIG, path=TARGET.decode()):
        before = ftp.connections
        epoch = core.device_session()
        ftp.commands.clear()
        with patch('ftplib.FTP', side_effect=AssertionError('raw FTP')):
            handle = core.ai.prepare(config, '127.0.0.1', path)
            snapshot = core.ai.execute(handle).wait(8)
        self.assertEqual(0, core._ftp_manager.active_count)
        self.assertEqual(epoch, core.device_session())
        self.assertLessEqual(ftp.connections - before, 1)
        with self.assertRaises(BrowserError):core.ai.execute(handle)
        self.assertIsNotNone(snapshot.result)
        self.assertEqual(len(build_c64_ai_client(config)), snapshot.result.size)
        self.assertEqual(sha256(build_c64_ai_client(config)).hexdigest(), snapshot.result.sha256)
        public = json.dumps(snapshot.as_dict())
        self.assertNotIn(config.token, public)
        self.assertNotIn('argonaut-ai-private-', public)
        return snapshot.result

    def test_built_in_tokenizer_matches_verified_petcat_fixture(self):
        config = replace(CONFIG, allowed_clients=('192.168.68.69',))
        program = build_c64_ai_client(config)
        self.assertEqual(len(program), 1532)
        self.assertEqual(sha256(program).hexdigest(), '03824eabf37ad745bdd21d5b27f3844249e926c42819d787880cd79d4f8a9c79')
        self.assertEqual(program[:2], b'\x01\x08')
        self.assertEqual(program[-2:], b'\x00\x00')

    def test_missing_client_is_generated_uploaded_and_verified(self):
        with server() as ftp:
            core, _ = self.connect(ftp)
            result = self.run_file(core, ftp)
            self.assertEqual('installed', result.action)
            self.assertTrue(result.permits_provisioning)
            self.assertEqual('published', result.upload.disposition)
            self.assertEqual(build_c64_ai_client(CONFIG), core._client._ftp_reads.read(TARGET.decode(), 4096))

    def test_identical_existing_client_is_kept(self):
        with server(build_c64_ai_client(CONFIG)) as ftp:
            core, _ = self.connect(ftp)
            result = self.run_file(core, ftp)
            self.assertEqual('verified-current', result.disposition)
            self.assertFalse(result.installed)
            self.assertTrue(result.permits_provisioning)
            self.assertFalse(MUTATIONS.intersection(ftp.verbs))
            self.assertEqual(2, ftp.verbs.count(b'SIZE'))

    def test_exact_ai1_client_is_safely_upgraded(self):
        with server(_build_legacy_c64_ai_client(CONFIG)) as ftp:
            core, _ = self.connect(ftp)
            result = self.run_file(core, ftp)
            self.assertEqual('upgraded', result.action)
            self.assertTrue(result.permits_provisioning)
            self.assertEqual(['full-byte-match'] * 2, [e.status for e in result.legacy_eligibility])
            self.assertEqual(3, sum(v == b'RETR' and p == TARGET for v, p in ftp.commands))
            self.assertEqual(build_c64_ai_client(CONFIG), core._client._ftp_reads.read(TARGET.decode(), 4096))

    def test_different_existing_client_is_never_overwritten(self):
        for content in (b'different', b'', _build_legacy_c64_ai_client(replace(CONFIG, token='B'*64))):
            with self.subTest(size=len(content)), server(content) as ftp:
                core, _ = self.connect(ftp)
                result = self.run_file(core, ftp)
                self.assertEqual('foreign', result.classification)
                self.assertFalse(result.permits_provisioning)
                self.assertFalse(MUTATIONS.intersection(ftp.verbs))
                self.assertEqual(content, ftp.files[TARGET])

    def test_provision_installs_then_pairs_without_exposing_token(self):
        with server() as ftp, tempfile.TemporaryDirectory() as directory:
            core, _ = self.connect(ftp)
            path = Path(directory)/'bridge.json'
            save_bridge_config(path, CONFIG)
            def paired(*args, **kwargs):
                self.assertEqual(0, core._ftp_manager.active_count)
                self.assertEqual(build_c64_ai_client(CONFIG), ftp.files[TARGET])
                return SimpleNamespace(state='ready')
            with patch('c64u_browser.c64_ai_preparation.pair_bridge_address', side_effect=paired) as pair:
                result = install_and_pair_c64_ai(core.ai, path, '127.0.0.1')
            pair.assert_called_once()
            self.assertEqual('ready', result.bridge_disposition)
            self.assertTrue(result.client.permits_provisioning)

    def test_non_file_directory_refuses(self):
        with server() as ftp:
            ftp.directories[TARGET] = b''
            core, _ = self.connect(ftp)
            result = self.run_file(core, ftp)
            self.assertEqual('non-file', result.classification)
            self.assertFalse(MUTATIONS.intersection(ftp.verbs))

    def test_explicit_storage_and_path_policy(self):
        with server() as ftp:
            core, _ = self.connect(ftp)
            self.assertTrue(self.run_file(core, ftp, path='/SD/controlled.prg').permits_provisioning)
            for path in ('/SD', '/USB2/../a', '/USB2/a\r\nDELE x', '/flash/a', '/SD/a/b'):
                with self.subTest(path=path):
                    try:handle = core.ai.prepare(CONFIG, '127.0.0.1', path)
                    except BrowserError:continue
                    self.assertFalse(core.ai.execute(handle).wait(8).result.permits_provisioning)

    def test_missing_occupied_before_publication(self):
        with server() as ftp:
            core, _ = self.connect(ftp)
            ftp.transfer_hook = lambda v, p: ftp.files.update({TARGET:b'occupant'}) if v == b'STOR' else None
            result = self.run_file(core, ftp)
            self.assertEqual('refused', result.action)
            self.assertEqual('staging-candidate', result.upload.disposition)
            self.assertNotIn(b'RNFR', ftp.verbs)
            self.assertEqual(b'occupant', ftp.files[TARGET])

    def test_current_changed_after_preparation(self):
        with server(build_c64_ai_client(CONFIG)) as ftp:
            core, _ = self.connect(ftp)
            handle = core.ai.prepare(CONFIG, '127.0.0.1')
            ftp.files[TARGET] = b'foreign'
            ftp.commands.clear()
            result = core.ai.execute(handle).wait(8).result
            self.assertEqual('foreign', result.classification)
            self.assertFalse(MUTATIONS.intersection(ftp.verbs))

    def authoritative_race(self, slot):
        old = _build_legacy_c64_ai_client(CONFIG)
        reached, release = threading.Event(), threading.Event()
        with server(old) as ftp:
            core, _ = self.connect(ftp)
            count = 0
            def barrier(v, p):
                nonlocal count
                if v == b'RETR' and p == TARGET:
                    count += 1
                    if count == slot:
                        reached.set()
                        if not release.wait(5):raise AssertionError('barrier timed out')
            ftp.before_command = barrier
            job = core.ai.execute(core.ai.prepare(CONFIG, '127.0.0.1'))
            self.assertTrue(reached.wait(5))
            ftp.files[TARGET] = b'X'*len(old)
            release.set()
            result = job.wait(8).result
            self.assertEqual('refused-unchanged', result.disposition)
            self.assertEqual('mismatch', result.legacy_eligibility[-1].status)
            self.assertIsNone(result.replacement.first_rename)
            self.assertEqual(b'X'*len(old), ftp.files[TARGET])
            self.assertEqual(0, core._ftp_manager.active_count)
            if slot == 2:
                self.assertNotIn(b'STOR', ftp.verbs)
                self.assertEqual(('mkdir',), result.replacement.acknowledged)
                self.assertEqual((result.replacement.directory,), result.replacement.candidates)
            return result

    def test_foreign_before_first_authoritative_read(self):self.authoritative_race(2)
    def test_foreign_before_second_authoritative_read(self):self.authoritative_race(3)

    def test_full_byte_predicate_not_digest_metadata(self):
        sink = _ExactSink(b'correct', EligibilityObservation('original-before', '/USB2/a', 'device', 'session', 'private-id'))
        self.assertEqual(7, sink.write(b'foreign'))
        metadata = SimpleNamespace(transferred=7, sha256=sha256(b'correct').hexdigest())
        self.assertEqual('unverified', sink.observation().status)
        self.assertEqual('mismatch', sink.observation(metadata).status)
        self.assertNotIn('correct', repr(sink))

    def test_sink_consumes_overflow_and_short_content(self):
        for chunks in ((b'cor', b'rect', b'overflow'), (b'cor',)):
            sink = _ExactSink(b'correct', EligibilityObservation('original-before', '/USB2/a', 'd', 's', 'i'))
            for chunk in chunks:self.assertEqual(len(chunk), sink.write(chunk))
            self.assertEqual('mismatch', sink.observation(SimpleNamespace(transferred=7, sha256='same')).status)

    def test_authoritative_failed_observations_unverified(self):
        old = _build_legacy_c64_ai_client(CONFIG)
        for mode in ('short', 'overlong', 'size-missing', 'size-change', 'interrupted'):
            with self.subTest(mode=mode), server(old) as ftp:
                core, _ = self.connect(ftp)
                reads_seen = 0
                def before(v,p):
                    nonlocal reads_seen
                    if v == b'RETR' and p == TARGET:reads_seen += 1
                    if mode == 'size-missing' and v == b'SIZE' and p == TARGET and b'MKD' in ftp.verbs:
                        return b'502 unavailable\r\n'
                    if mode == 'size-change' and v == b'SIZE' and p == TARGET and reads_seen == 2:
                        return b'213 1\r\n'
                ftp.before_command = before
                ftp.readback_data = lambda p,d: (d[:-1] if mode == 'short' else d+b'x') if p == TARGET and reads_seen == 2 and mode in ('short','overlong') else d
                ftp.transfer_completion = lambda v,p: b'426 interrupted\r\n' if mode == 'interrupted' and p == TARGET and reads_seen == 2 else b'226 Complete\r\n'
                result = self.run_file(core, ftp)
                self.assertEqual('unverified', result.legacy_eligibility[-1].status)
                self.assertFalse(result.permits_provisioning)
                self.assertNotIn(b'STOR', ftp.verbs)

    def test_wrong_address_and_unbound_identity(self):
        with server() as ftp:
            core, _ = self.connect(ftp)
            with self.assertRaises(BrowserError):core.ai.prepare(CONFIG, '127.0.0.2')
            core._active_profile = replace(core._active_profile, device_id='', device_mac='')
            with self.assertRaises(BrowserError):core.ai.prepare(CONFIG, '127.0.0.1')

    def queued(self, action):
        release, started = threading.Event(), threading.Event()
        with server() as ftp:
            core, profile = self.connect(ftp)
            blocker = CoreJob('barrier', lambda job: (started.set(), release.wait(5)))
            core.scheduler.submit(blocker, JobBinding.device(core.device_session()))
            self.assertTrue(started.wait(3))
            job = core.ai.execute(core.ai.prepare(CONFIG, '127.0.0.1'))
            if action == 'cancel':job.request_cancel()
            elif action == 'reconnect':core.connect(profile, remote_folder='/USB1')
            elif action == 'endpoint':core._client.host = '127.0.0.2'
            ftp.commands.clear()
            release.set()
            snapshot = job.wait(8)
            self.assertFalse(snapshot.result.permits_provisioning)
            self.assertEqual([], ftp.commands)
            self.assertEqual('cancelled' if action == 'cancel' else 'failed', snapshot.state)
            return snapshot

    def test_queued_cancellation_has_result(self):self.queued('cancel')
    def test_queued_same_device_reconnect(self):self.queued('reconnect')
    def test_queued_endpoint_change(self):self.queued('endpoint')

    def test_running_cancellation_and_session_field_invalidation(self):
        for action in ('cancel', 'session-field'):
            with self.subTest(action=action), server(build_c64_ai_client(CONFIG)) as ftp:
                core, profile = self.connect(ftp)
                reached, release = threading.Event(), threading.Event()
                def barrier(v,p):
                    if v == b'RETR' and p == TARGET:
                        reached.set();release.wait(5)
                ftp.before_command = barrier
                job = core.ai.execute(core.ai.prepare(CONFIG, '127.0.0.1'))
                self.assertTrue(reached.wait(3))
                if action == 'cancel':job.request_cancel()
                else:core._session_id = 'different-epoch'
                release.set()
                result = job.wait(8).result
                self.assertFalse(result.permits_provisioning)
                self.assertEqual(0, core._ftp_manager.active_count)
                self.assertFalse(MUTATIONS.intersection(ftp.verbs))

    def test_lost_publication_no_replay(self):
        with server() as ftp:
            core, _ = self.connect(ftp)
            ftp.after_mutation[b'RNTO'] = None
            result = self.run_file(core, ftp)
            self.assertEqual('uncertain', result.disposition)
            self.assertEqual('location-unknown', result.upload.disposition)
            self.assertFalse(result.permits_provisioning)
            self.assertEqual(1, ftp.verbs.count(b'STOR'))

    def test_replacement_cleanup_failure_preserves_publication(self):
        for verb in (b'DELE', b'RMD'):
            with self.subTest(verb=verb), server(_build_legacy_c64_ai_client(CONFIG)) as ftp:
                core, _ = self.connect(ftp)
                ftp.after_mutation[verb] = None
                result = self.run_file(core, ftp)
                self.assertEqual('published-cleanup-incomplete', result.disposition)
                self.assertTrue(result.installed)
                self.assertEqual('completed', result.replacement.publication)
                self.assertFalse(result.permits_provisioning)
                self.assertEqual(build_c64_ai_client(CONFIG), ftp.files[TARGET])

    def test_local_cleanup_failure_is_secondary_and_sanitized(self):
        import shutil
        original = shutil.rmtree
        seen = []
        def fail(path):
            seen.append(path)
            raise OSError('SECRET-TOKEN ' + str(path))
        with server() as ftp:
            core, _ = self.connect(ftp)
            try:
                with patch('c64u_browser.c64_ai_operation.shutil.rmtree', side_effect=fail):
                    result = self.run_file(core, ftp)
                self.assertEqual('installed', result.disposition)
                self.assertEqual('failed', result.local_cleanup)
                self.assertFalse(result.permits_provisioning)
                self.assertNotIn('SECRET', repr(result))
            finally:
                for path in seen:original(path)

    def test_cancellation_after_mutation_before_reply_keeps_file_success(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy), server(_build_legacy_c64_ai_client(CONFIG) if legacy else None) as ftp:
                core, _ = self.connect(ftp)
                handle = core.ai.prepare(CONFIG, '127.0.0.1')
                reached, release = threading.Event(), threading.Event()
                def hook(v,p):
                    if (v == b'RMD' if legacy else v == b'RNTO'):
                        reached.set();release.wait(5)
                ftp.mutation_hook = hook
                job = core.ai.execute(handle)
                self.assertTrue(reached.wait(3))
                job.request_cancel();release.set()
                snapshot = job.wait(8)
                self.assertEqual('succeeded', snapshot.state)
                self.assertEqual('upgraded' if legacy else 'installed', snapshot.result.action)
                self.assertFalse(snapshot.result.permits_provisioning)
                self.assertEqual(build_c64_ai_client(CONFIG), ftp.files[TARGET])

    def test_private_temporary_modes_and_closed_source(self):
        from c64u_browser.transfers import upload_managed
        with server() as ftp:
            core, _ = self.connect(ftp)
            paths=[]
            def upload(client, source, parent, progress):
                paths.append(source)
                self.assertEqual(0o600, source.stat().st_mode & 0o777)
                self.assertEqual(0o700, source.parent.stat().st_mode & 0o777)
                self.assertEqual(build_c64_ai_client(CONFIG), source.read_bytes())
                return upload_managed(client, source, parent, progress)
            with patch('c64u_browser.c64_ai_operation.upload_managed', side_effect=upload):
                self.run_file(core, ftp)
            self.assertFalse(paths[0].parent.exists())

    def test_handle_expiry_and_discard(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            from c64u_browser.c64_ai_operation import AIFileService
            clock=[0]
            service=AIFileService(core,clock=lambda:clock[0])
            handle=service.prepare(CONFIG,'127.0.0.1')
            clock[0]=301
            with self.assertRaises(BrowserError):service.execute(handle)
            handle=service.prepare(CONFIG,'127.0.0.1')
            service.discard(handle)
            with self.assertRaises(BrowserError):service.execute(handle)

    def test_static_ai_routes_have_no_raw_authority(self):
        import ast
        from c64u_browser import c64_ai_install, c64_ai_operation
        for module in (c64_ai_install,c64_ai_operation):
            tree=ast.parse(Path(module.__file__).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):
                    self.assertFalse(any(a.name in ('upload','download','replace_file','connect') for a in node.names))
                if isinstance(node,ast.Attribute):self.assertNotIn(node.attr,('open_ftp','device_operations'))

    def test_generic_equal_foreign_hashes_do_not_grant_ai_eligibility(self):
        from c64u_browser.managed_replacement import replace_managed, ReplacementFailure
        from c64u_browser.folder_copy import Step
        old=_build_legacy_c64_ai_client(CONFIG)
        for hooked in (False,True):
            with self.subTest(hooked=hooked),server(b'X'*len(old)) as ftp, tempfile.TemporaryDirectory() as directory:
                core,_=self.connect(ftp)
                path=Path(directory)/'argonaut-ai.prg';path.write_bytes(build_c64_ai_client(CONFIG))
                step=Step(path.name,path,TARGET.decode(),False,True,(path.name,len(old)))
                factory=lambda slot:_ExactSink(old,EligibilityObservation(slot,TARGET.decode(),'d','s','i'))
                if hooked:
                    with self.assertRaises(ReplacementFailure) as caught:
                        replace_managed(core._client,step,True,lambda n:None,original_validator_factory=factory)
                    self.assertEqual('mismatch',caught.exception.replacement_evidence.original_eligibility[0].status)
                    self.assertNotIn(b'STOR',ftp.verbs)
                else:
                    evidence=replace_managed(core._client,step,True,lambda n:None)
                    self.assertEqual(evidence.original_before,evidence.original_after)
                    self.assertEqual('completed',evidence.publication)
                    self.assertIsNone(evidence.original_eligibility)

    def test_unsupported_entry_and_case_collision(self):
        for rows in (b'type=OS.unix=slink;size=1; argonaut-ai.prg\r\n',
                     b'type=file;size=1; ARGONAUT-AI.PRG\r\ntype=file;size=1; argonaut-ai.prg\r\n'):
            with self.subTest(rows=rows),server() as ftp:
                core,_=self.connect(ftp)
                ftp.mutation_tree=False
                ftp.directories[b'/USB2']=rows
                result=self.run_file(core,ftp)
                self.assertFalse(result.permits_provisioning)
                self.assertFalse(MUTATIONS.intersection(ftp.verbs))

    def test_stale_during_client_resolution(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            client=core._client
            def resolve():
                core._session_id='new-session'
                return client
            with patch.object(core,'_require_client',side_effect=resolve):
                with self.assertRaises(BrowserError):core.ai.prepare(CONFIG,'127.0.0.1')

    def test_wrong_physical_identity_queued(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            handle=core.ai.prepare(CONFIG,'127.0.0.1')
            core._device_identity='id:another'
            ftp.commands.clear()
            snapshot=core.ai.execute(handle).wait(8)
            self.assertEqual('failed',snapshot.state)
            self.assertIsNotNone(snapshot.result)
            self.assertEqual([],ftp.commands)

    def test_running_staging_cancellation(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            reached,release=threading.Event(),threading.Event()
            def barrier(v,p):
                if v==b'STOR':reached.set();release.wait(5)
            ftp.before_command=barrier
            job=core.ai.execute(core.ai.prepare(CONFIG,'127.0.0.1'))
            self.assertTrue(reached.wait(3));job.request_cancel();release.set()
            snapshot=job.wait(8)
            self.assertEqual('cancelled',snapshot.state)
            self.assertFalse(snapshot.result.permits_provisioning)
            self.assertEqual(0,core._ftp_manager.active_count)
            self.assertNotIn(TARGET,ftp.files)

    def test_uncertain_replacement_exchange_no_replay(self):
        with server(_build_legacy_c64_ai_client(CONFIG)) as ftp:
            core,_=self.connect(ftp)
            count=0
            def reply(path):
                nonlocal count
                count+=1
                return None if count==3 else b'250 renamed\r\n'
            ftp.after_mutation[b'RNTO']=reply
            result=self.run_file(core,ftp)
            self.assertEqual('unknown',result.replacement.publication)
            self.assertEqual('uncertain',result.disposition)
            self.assertFalse(result.permits_provisioning)
            self.assertEqual(1,ftp.verbs.count(b'STOR'))
            self.assertNotIn(b'DELE',ftp.verbs)

    def test_public_snapshots_diagnostics_and_failure_chains_exclude_secrets(self):
        import logging
        from contextlib import nullcontext
        from c64u_browser.diagnostics import LOGGER, JsonEventFormatter
        for mode in ('callback','local','transport','success'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp)
                events=[];records=[]
                class Handler(logging.Handler):
                    def emit(self,record):records.append(JsonEventFormatter().format(record))
                handler=Handler();LOGGER.addHandler(handler)
                core._client.password='PASSWORDSENTINEL'
                core._ftp_manager._diagnostic=events.append
                if mode=='transport':ftp.replies[b'STOR']=b'550 '+CONFIG.token.encode()+b'\r\n'
                try:
                    with patch('c64u_browser.c64_ai_operation.os.chmod',side_effect=OSError('/private/SENTINEL '+CONFIG.token)) if mode=='local' else nullcontext():
                        if mode=='callback':
                            config_check=lambda:(_ for _ in ()).throw(RuntimeError(CONFIG.token+' /private/SENTINEL'))
                        else:config_check=None
                        job=core.ai.execute(core.ai.prepare(CONFIG,'127.0.0.1',config_check=config_check))
                        snapshots=[];job.add_listener(lambda e:snapshots.append(e.as_dict()))
                        snapshot=job.wait(8)
                    public=repr((snapshot.as_dict(),snapshots,events,records))
                    for secret in (CONFIG.token,'PASSWORDSENTINEL','/private/SENTINEL','argonaut-ai-private-',repr(build_c64_ai_client(CONFIG))):
                        self.assertNotIn(secret,public)
                finally:LOGGER.removeHandler(handler)
