"""Production read migration with real control/data sockets and verified Core."""
from dataclasses import replace
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from c64u_ftp_server import FakeC64UFtp
from c64u_browser.api import UltimateClient, BrowserError, ConnectionFailure, Entry
from c64u_browser.core import ArgonautCore, CoreError
from c64u_browser.profiles import Profile, Preferences
from c64u_browser.ftp_reads import adapter_for, read_operation
from c64u_browser.native_files import read_remote, read_remote_game, MAX_GAME_BYTES
from c64u_browser.jobs import CoreJob, JobCancelled
from c64u_browser.usb_backup import UsbBackupService
from c64u_browser.c64u_ftp_types import CapabilityState as CS, FtpPolicy
from test_core import FakeCredentials, INFO

ROOT = {b'/':b'type=dir; USB1\r\n', b'/USB1':b'type=file;size=3; game.d64\r\n'}


class ReadMigrationTests(unittest.TestCase):
    def core(self, server, *, encoding='utf-8'):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        def factory(host,password,port,http_port):
            client=UltimateClient(host,password,port=port,http_port=http_port,encoding=encoding)
            client.test_connection=lambda:INFO
            return client
        core=ArgonautCore(preferences=Preferences(Path(temp.name)/'config.json'),
                          credentials=FakeCredentials(),client_factory=factory)
        self.addCleanup(core.close)
        profile=replace(Profile.new('fixture','127.0.0.1',device_id='ABC123'),ftp_port=server.port)
        return core,profile

    def connect(self,server,**kwargs):
        core,profile=self.core(server,**kwargs)
        core.connect(profile,remote_folder='/USB1')
        return core,profile

    def test_initial_directory_one_lease_and_health_does_not_change_epoch(self):
        with FakeC64UFtp(directories=ROOT) as server:
            with patch('ftplib.FTP',side_effect=AssertionError('legacy read')):
                core,profile=self.connect(server)
                epoch=core.device_session()
                self.assertEqual(1,server.connections)
                self.assertEqual(1,server.verbs.count(b'FEAT'))
                core.check_health()
                self.assertEqual(epoch,core.device_session())
                actual,entries=core.device_operations.list_directory('/USB1')
                self.assertEqual(('/USB1',[Entry('game.d64','file',3)]),(actual,entries))
                self.assertEqual(epoch,core.device_session())
                self.assertEqual(2,server.connections)
                self.assertEqual(0,core._ftp_manager.active_count)
                adapter=adapter_for(core._client)
                self.assertEqual(epoch.session_id,adapter.binding.core_session_id)
                self.assertEqual(CS.VERIFIED,adapter.capability_evidence.mlsd)
                self.assertEqual(CS.VERIFIED,adapter.capability_evidence.pasv)
                self.assertEqual(CS.UNKNOWN,adapter.capability_evidence.size)

    def test_sorted_presentation_strict_encoding_and_raw_identity(self):
        rows=(b'type=file;size=2; z  space\r\n'
              b'type=dir; Folder\r\ntype=file;size=1; A\r\n')
        with FakeC64UFtp(directories={**ROOT,b'/USB1':rows}) as server:
            core,_=self.connect(server)
            self.assertEqual(['Folder','A','z  space'],[e.name for e in core.device_operations.list_directory('/USB1')[1]])
            name=b'Schatzj\x84ger [Side 1] [Ariolasoft] [TWG].d64'
            server.directories[b'/USB1']=b'type=file;size=174848; '+name+b'\r\n'
            with self.assertRaisesRegex(BrowserError,'encoding'):core.device_operations.list_directory('/USB1')
            actual,entries=core._client.list_directory_identity(b'/USB1')
            self.assertEqual(b'/USB1',actual);self.assertEqual(name,entries[0].name)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_latin1_presentation_and_list_fallback(self):
        with FakeC64UFtp(directories=ROOT) as server:
            core,_=self.connect(server,encoding='latin-1')
            server.replies[b'MLSD']=b'502 unavailable\r\n'
            server.list_data=b'-rw-rw-rw- 1 user ftp 3 Sep 07 2026 Schatzj\x84ger.d64\r\n'
            with read_operation(core._client):
                a=core._client.list_directory('/USB1')
                b=core._client.list_directory_identity(b'/USB1')
            self.assertEqual('Schatzj\x84ger.d64',a[1][0].name)
            self.assertEqual(b'Schatzj\x84ger.d64',b[1][0].name)
            evidence=adapter_for(core._client).capability_evidence
            self.assertEqual(CS.UNSUPPORTED,evidence.mlsd)
            self.assertEqual('list',evidence.listing_dialect)
            self.assertEqual(2,server.connections)

    def test_fingerprint_exact_legacy_digest_with_one_connection(self):
        tree={**ROOT,b'/USB1':b'type=dir; sub\r\ntype=file;size=3; Schatzj\x84ger.d64\r\n',
              b'/USB1/sub':b'type=file;size=0; empty\r\n'}
        with FakeC64UFtp(directories=tree) as server:
            core,profile=self.core(server,encoding='latin-1')
            core.connect(profile,remote_folder='/')
            client=core._client
            before=server.connections
            new=UsbBackupService._volume_fingerprint(client,'/USB1')
            self.assertEqual(1,server.connections-before)
            legacy=UltimateClient('127.0.0.1',port=server.port)
            before=server.connections
            old=UsbBackupService._volume_fingerprint(legacy,'/USB1')
            self.assertEqual(2,server.connections-before)
            self.assertEqual(old,new)
            server.directories[b'/USB1/sub']=b'type=file;size=1; empty\r\n'
            self.assertNotEqual(new,UsbBackupService._volume_fingerprint(client,'/USB1'))

    def test_pwd_mismatch_and_bad_identity_never_become_empty(self):
        with FakeC64UFtp(directories=ROOT) as server:
            core,_=self.connect(server)
            server.replies[b'PWD']=b'257 "/USB2"\r\n'
            with self.assertRaisesRegex(BrowserError,'volume changed'):
                UsbBackupService._volume_fingerprint(core._client,'/USB1')
            del server.replies[b'PWD']
            for listing,code in ((b'type=file; a\r\ngarbage\r\n','listing-malformed'),
                                 (b'type=file; unfinished','listing-incomplete')):
                server.directories[b'/USB1']=listing
                with self.assertRaises(ConnectionFailure) as caught:
                    core._client.list_directory_identity(b'/USB1')
                self.assertEqual(code,caught.exception.ftp_code)
            self.assertNotIn(b'LIST',server.verbs)

    def test_bounded_read_before_after_size_same_lease_and_capability(self):
        data=bytes(range(256))*257
        with FakeC64UFtp(directories=ROOT,files={b'/USB1/a.sid':data}) as server:
            core,_=self.connect(server);progress=[]
            before=server.connections
            with patch('ftplib.FTP',side_effect=AssertionError('legacy')):
                value=read_remote_game(core.device_operations,'/USB1/a.sid',len(data),
                                       lambda n,total:progress.append((n,total)))
            self.assertEqual(data,value)
            self.assertEqual((len(data),len(data)),progress[-1])
            self.assertEqual(1,server.connections-before)
            self.assertEqual(2,server.verbs.count(b'SIZE'))
            self.assertEqual(1,server.verbs.count(b'RETR'))
            self.assertEqual(CS.VERIFIED,adapter_for(core._client).capability_evidence.size)

    def test_read_limit_and_allowed_game_boundary(self):
        with FakeC64UFtp(directories=ROOT,files={b'/USB1/game.crt':b'x'*1025}) as server:
            core,_=self.connect(server)
            with self.assertRaises(BrowserError):read_remote(core.device_operations,'/USB1/game.crt',1024)
            self.assertNotIn(b'RETR',server.verbs)
            with self.assertRaises(BrowserError):read_remote(core.device_operations,'/USB1/game.crt',MAX_GAME_BYTES)
            self.assertEqual(b'x'*1025,read_remote_game(core.device_operations,'/USB1/game.crt',MAX_GAME_BYTES))

    def test_unavailable_size_short_read_terminal_and_changed_size(self):
        with FakeC64UFtp(directories=ROOT,files={b'/USB1/a':b'abc'}) as server:
            core,_=self.connect(server)
            for response,expected in ((b'502 no\r\n','size-unavailable'),(b'213 4\r\n','size-mismatch')):
                server.replies[b'SIZE']=response
                with self.assertRaises(ConnectionFailure) as caught:read_remote(core.device_operations,'/USB1/a')
                self.assertEqual(expected,caught.exception.ftp_code)
            del server.replies[b'SIZE']
            server.completion=b'451 failed\r\n'
            with self.assertRaises(ConnectionFailure) as caught:read_remote(core.device_operations,'/USB1/a')
            self.assertEqual('completion-unknown',caught.exception.ftp_code)
            server.completion=b'226 OK\r\n'
            sizes=iter([b'213 3\r\n',b'213 4\r\n']);server.replies[b'SIZE']=lambda _:next(sizes)
            with self.assertRaisesRegex(BrowserError,'changed'):read_remote(core.device_operations,'/USB1/a')
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_job_cancellation_during_read_keeps_job_semantics(self):
        with FakeC64UFtp(directories=ROOT,files={b'/USB1/a':b'x'*50000}) as server:
            core,_=self.connect(server)
            def task(job):
                return read_remote_game(core.device_operations,'/USB1/a',50000,
                                        lambda *_:job.request_cancel())
            job=CoreJob('read',task);job.run()
            self.assertEqual('cancelled',job.snapshot().state)
            self.assertEqual(0,core._ftp_manager.active_count)
            self.assertEqual(1,server.verbs.count(b'RETR'))

    def test_fingerprint_cancellation_and_explicit_nested_reuse(self):
        tree={**ROOT,b'/USB1':b'type=dir; sub\r\n',b'/USB1/sub':b''}
        with FakeC64UFtp(directories=tree) as server:
            core,_=self.connect(server);cancel=[False]
            def check():
                if cancel[0]:raise JobCancelled()
            def progress(*_):cancel[0]=True
            with self.assertRaises(JobCancelled):
                UsbBackupService._volume_fingerprint(core._client,'/USB1',check,progress)
            self.assertEqual(0,core._ftp_manager.active_count)
            before=server.connections
            with read_operation(core._client):
                with read_operation(core._client):core._client.list_directory('/USB1')
                core._client.list_directory_identity(b'/USB1/sub')
            self.assertEqual(1,server.connections-before)

    def test_stale_old_adapter_after_reconnect_and_disconnect(self):
        with FakeC64UFtp(directories=ROOT) as server:
            core,profile=self.connect(server);old=core._client;epoch=core.device_session()
            core.reconnect('/USB1')
            self.assertNotEqual(epoch,core.device_session())
            before=server.connections
            with self.assertRaises(ConnectionFailure) as caught:old.list_directory('/USB1')
            self.assertEqual('session',caught.exception.kind)
            self.assertEqual(before,server.connections)
            current=core._client;core.disconnect()
            with self.assertRaises(ConnectionFailure):current.list_directory('/USB1')

    def test_preferred_missing_path_falls_back_on_new_clean_lease(self):
        with FakeC64UFtp(directories=ROOT) as server:
            core,profile=self.core(server)
            result=core.connect(profile,remote_folder='/USB1/missing')
            self.assertEqual('/USB1',result.remote_path)
            self.assertEqual(2,server.connections)

    def test_error_translation_keeps_auth_network_path_and_malformed_distinct(self):
        with FakeC64UFtp(directories=ROOT) as server:
            core,_=self.connect(server)
            cases=[(b'530 private\r\n','authentication','authentication-failed'),
                   (b'421 Too many FTP connections\r\n','network','session-limit'),
                   (b'550 missing\r\n','ftp','path-unavailable')]
            for reply,kind,detail in cases:
                server.replies[b'MLSD']=reply
                with self.assertRaises(ConnectionFailure) as caught:core.device_operations.list_directory('/USB1')
                self.assertEqual((kind,detail),(caught.exception.kind,caught.exception.ftp_code))
                self.assertNotIn('private',str(caught.exception))
            self.assertNotIn(b'LIST',server.verbs)

    def test_mutating_transport_factory_remains_legacy(self):
        with FakeC64UFtp(directories=ROOT) as server:
            core,_=self.connect(server)
            from c64u_browser.transfers import connect
            with patch('ftplib.FTP') as factory:
                ftp=connect(core.device_operations)
                self.assertIs(ftp,factory.return_value)
                factory.return_value.login.assert_called_once_with('anonymous','')

    def test_core_catalog_services_and_disk_image_use_socket_adapter(self):
        from c64u_browser.game_library import GameSource
        from c64u_browser.sid_jukebox import SidSource
        from tests.test_sid_format import sid_bytes
        from c64u_browser.disk_run import mount_and_run
        sid=sid_bytes();disk=(Path(__file__).parent/'fixtures'/'vice-1541-authentic.d64').read_bytes()
        with FakeC64UFtp(directories=ROOT,files={b'/USB1/a.sid':sid,b'/USB1/a.d64':disk}) as server:
            core,_=self.connect(server)
            identity=core.device_session().device_id
            with patch('ftplib.FTP',side_effect=AssertionError('legacy read')):
                tune=core.sid_catalog.add(SidSource.c64u(identity,'/USB1/a.sid')).wait(5)
                game=core.game_library.add(GameSource.c64u(identity,'/USB1/a.d64')).wait(5)
                self.assertEqual('succeeded',tune.state,tune.error)
                self.assertEqual('succeeded',game.state,game.error)
                with patch('c64u_browser.disk_run.run_image_bytes') as submit:
                    mount_and_run(core.device_operations,'/USB1/a.d64')
                    submit.assert_called_once_with(core.device_operations,disk)
            self.assertEqual(3,server.verbs.count(b'RETR'))
            self.assertEqual(6,server.verbs.count(b'SIZE'))

    def test_data_timeout_translation_and_subsequent_clean_read(self):
        with FakeC64UFtp(directories=ROOT,files={b'/USB1/a':b'abc'}) as server:
            core,_=self.connect(server)
            core._ftp_manager._policy=FtpPolicy(data_idle=.03)
            server.data_wait=threading.Event()
            with self.assertRaises(ConnectionFailure) as caught:
                read_remote(core.device_operations,'/USB1/a')
            self.assertEqual('network',caught.exception.kind)
            self.assertEqual('data-idle-timeout',caught.exception.ftp_code)
            self.assertEqual(0,core._ftp_manager.active_count)
            server.data_wait.set()
            self.assertEqual(b'abc',read_remote(core.device_operations,'/USB1/a'))

    def test_job_check_context_does_not_leak_and_switch_during_progress_rejects(self):
        from c64u_browser.jobs import check_current_job
        with FakeC64UFtp(directories=ROOT,files={b'/USB1/a':b'x'*50000}) as server:
            core,_=self.connect(server)
            job=CoreJob('cancel',lambda job:(job.request_cancel(),check_current_job()))
            job.run();self.assertEqual('cancelled',job.snapshot().state)
            check_current_job()
            def changed(*_):core.disconnect()
            with self.assertRaises(ConnectionFailure) as caught:
                read_remote_game(core.device_operations,'/USB1/a',50000,progress=changed)
            self.assertEqual('session',caught.exception.kind)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_wrong_reconnect_identity_stops_before_ftp(self):
        with FakeC64UFtp(directories=ROOT) as server:
            core,_=self.connect(server);before=server.connections
            original=core._client_factory
            def wrong(*args,**kwargs):
                client=original(*args,**kwargs)
                client.test_connection=lambda:{**INFO,'info':{**INFO['info'],'unique_id':'WRONG'}}
                return client
            core._client_factory=wrong
            with self.assertRaises(CoreError):core.reconnect('/USB1')
            self.assertEqual(before,server.connections)

if __name__=='__main__':unittest.main()
