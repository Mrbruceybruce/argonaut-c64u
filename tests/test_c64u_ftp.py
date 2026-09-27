"""Headless real-wire compatibility tests; synthetic content, loopback only."""
from dataclasses import replace
import hashlib
import io
import json
import socket
import threading
import unittest
from unittest.mock import patch

from c64u_browser.c64u_ftp import C64UFtpLeaseManager
from c64u_browser.c64u_ftp_types import (
    CapabilityState as CS, ContainerPresentation as Mode, ConnectionBinding,
    DeviceIdentity, ErrorCode as EC, FtpOperationError, FtpPolicy,
    ListingLimits, ListingParser, Outcome, SessionState,
    checked_path, parse_mlsd_line,
)
from c64u_ftp_server import FakeC64UFtp


class ProtocolTests(unittest.TestCase):
    def manager(self, server, password='', policy=None, events=None):
        self.binding = ConnectionBinding(DeviceIdentity('fixture-device', 'C64 Ultimate',
                                                        'fixture-fw', 'v1'),
                                         'core-session', '127.0.0.1', server.port)
        self.current = self.binding
        return C64UFtpLeaseManager(lambda _: self.current, lambda _: password,
                                  policy=policy, diagnostic=None if events is None else events.append)

    def assertCode(self, code, call):
        with self.assertRaises(FtpOperationError) as caught:call()
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    def test_literal_passwords_and_private_diagnostics(self):
        for password in ('', '-', '  with spaces  ', 'secret-token-123', 'caf\u00e9'):
            with self.subTest(password_kind=len(password)), FakeC64UFtp() as server:
                events = []
                manager = self.manager(server, password, events=events)
                with manager.lease(self.binding) as client:
                    self.assertEqual(SessionState.READY, client.state)
                    self.assertEqual([(b'USER',b'anonymous'),(b'PASS',password.encode()),
                                      (b'FEAT',b''),(b'TYPE',b'I')], server.commands)
                    self.assertNotIn('password', repr(client.capabilities).lower())
                    self.assertNotIn('password', repr(client).lower())
                serialized = json.dumps(events)
                self.assertNotIn('PASS', serialized)
                self.assertNotIn('secret-token-123', serialized)
                self.assertEqual(0, manager.active_count)
                self.assertTrue(server.closed.wait(1))
                self.assertEqual(0, server.live)

    def test_password_controls_rejected_before_connect(self):
        with FakeC64UFtp() as server:
            for password in ('a\r\nSTOR x', '\x00', 'a\t', '\x7f', '\ud800'):
                manager = self.manager(server,password)
                def run():
                    with manager.lease(self.binding):pass
                self.assertCode(EC.INVALID_ARGUMENT,run)
                self.assertEqual(0,manager.active_count)
            self.assertEqual(0,server.connections)

    def test_modes_only_affect_wire_identity(self):
        with FakeC64UFtp() as server:
            manager = self.manager(server)
            for mode,user in ((Mode.FILES,b'anonymous'),(Mode.DIRECTORIES,b'dirs'),(Mode.BOTH,b'both')):
                with manager.lease(self.binding,presentation=mode) as client:
                    self.assertEqual(mode,client.capabilities.presentation)
                    self.assertEqual(user, [a for v,a in server.commands if v==b'USER'][-1])
            self.assertEqual(3,server.verbs.count(b'FEAT'))

    def test_capability_advertised_not_verified_omission_not_unsupported(self):
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                self.assertEqual(CS.ADVERTISED,client.capabilities.mlsd)
                self.assertEqual(CS.ADVERTISED,client.capabilities.mlst)
                self.assertEqual(CS.UNKNOWN,client.capabilities.size)
                self.assertEqual(CS.UNKNOWN,client.capabilities.pasv)
                first=client.identity
                client.list_directory(b'/USB1');client.list_directory(b'/USB1')
                self.assertEqual(3,client.size(b'/file'))
                self.assertEqual(CS.VERIFIED,client.capabilities.size)
                self.assertEqual(CS.VERIFIED,client.capabilities.mlsd)
                self.assertEqual(CS.VERIFIED,client.capabilities.pasv)
                self.assertEqual(1,server.verbs.count(b'FEAT'))
            with manager.lease(self.binding) as other:
                self.assertNotEqual(first.ftp_session_id,other.identity.ftp_session_id)
                self.assertEqual(first.core_session_id,other.identity.core_session_id)

    def test_binary_order_pasv_only_and_real_round_trip(self):
        data=bytes(range(256))*2+b'\x00\r\n\xff'
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                client.list_directory(b'/USB1')
                sent=client.write_from(b'/new',io.BytesIO(data),expected_bytes=len(data))
                self.assertEqual(data,server.files[b'/new'])
                self.assertEqual(len(data),client.size(b'/new'))
                sink=io.BytesIO()
                got=client.read_into(b'/new',sink,max_bytes=1000,expected_bytes=len(data))
                self.assertEqual(data,sink.getvalue())
                self.assertEqual(hashlib.sha256(data).hexdigest(),got.sha256)
                self.assertEqual(sent,got)
                client.list_directory(b'/USB1')
            for index,(verb,arg) in enumerate(server.commands):
                if verb==b'PASV':self.assertEqual((b'TYPE',b'I'),server.commands[index-1])
                if verb==b'TYPE':self.assertEqual(b'I',arg)
            self.assertFalse(set(server.verbs)&{b'EPSV',b'EPRT',b'PORT',b'REST',b'APPE',b'MDTM',b'AUTH',b'ABOR'})

    def test_zero_byte_transfer(self):
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                self.assertEqual(0,client.write_from(b'/empty',io.BytesIO(),expected_bytes=0).transferred)
                self.assertEqual(0,client.read_into(b'/empty',io.BytesIO(),max_bytes=0).transferred)

    def test_split_and_coalesced_control_replies(self):
        for opts in ({'split':True},{'coalesced':True}):
            with self.subTest(opts=opts),FakeC64UFtp(**opts) as server:
                manager=self.manager(server)
                with manager.lease(self.binding) as client:
                    self.assertEqual(1,len(client.list_directory(b'/USB1').entries))
                    self.assertEqual(3,client.size(b'/file'))

    def test_feat_unsupported_or_omitted_still_probes_mlsd(self):
        for feat in (b'502 No FEAT\r\n',b'211-Features\r\n211 End\r\n',b'211 No features\r\n'):
            with self.subTest(feat=feat),FakeC64UFtp(feat=feat) as server:
                manager=self.manager(server)
                with manager.lease(self.binding) as client:
                    self.assertEqual(CS.UNKNOWN,client.capabilities.mlsd)
                    client.list_directory(b'/USB1')
                    self.assertEqual(CS.VERIFIED,client.capabilities.mlsd)

    def test_feat_malformed_and_all_control_bounds(self):
        cases=[(b'211-Features\r\n \xff\r\n211 End\r\n',FtpPolicy()),
               (b'not a reply\r\n',FtpPolicy()),
               (b'211-'+b'x'*100+b'\r\n211 End\r\n',FtpPolicy(reply_line_bytes=64)),
               (b'211-Features\r\n MLSD\r\n SIZE\r\n211 End\r\n',FtpPolicy(reply_lines=3)),
               (b'211-Features\r\n MLSD\r\n211 End\r\n',FtpPolicy(reply_bytes=25))]
        for feat,policy in cases:
            with self.subTest(feat=feat),FakeC64UFtp(feat=feat) as server:
                manager=self.manager(server,policy=policy)
                def run():
                    with manager.lease(self.binding):pass
                self.assertCode(EC.PROTOCOL,run)
                self.assertEqual(0,manager.active_count)

    def test_incomplete_multiline_feat_times_out(self):
        with FakeC64UFtp(feat=b'211-Features\r\n MLSD\r\n') as server:
            manager=self.manager(server,policy=FtpPolicy(control_reply=.05))
            def run():
                with manager.lease(self.binding):pass
            self.assertCode(EC.CONTROL_TIMEOUT,run)

    def test_unsupported_mlsd_fallback_and_cached_decision(self):
        for reply in (b'500 Bad command\r\n',b'502 Unsupported\r\n',b'504 Unsupported\r\n'):
            with self.subTest(reply=reply),FakeC64UFtp(replies={b'MLSD':reply}) as server:
                manager=self.manager(server)
                with manager.lease(self.binding) as client:
                    for _ in range(2):
                        result=client.list_directory(b'/USB1')
                        self.assertEqual('list',result.dialect)
                        self.assertEqual(b'game.d64',result.entries[0].name)
                    self.assertEqual(CS.UNSUPPORTED,client.capabilities.mlsd)
                self.assertEqual(1,server.verbs.count(b'MLSD'))
                self.assertEqual(2,server.verbs.count(b'LIST'))

    def test_known_broken_profile_skips_mlsd_without_guessing(self):
        with FakeC64UFtp() as server:
            events=[];manager=self.manager(server,policy=FtpPolicy(known_broken_mlsd=True),events=events)
            with manager.lease(self.binding) as client:
                self.assertEqual('list',client.list_directory(b'/USB1').dialect)
                self.assertEqual(CS.BROKEN,client.capabilities.mlsd)
            self.assertNotIn(b'MLSD',server.verbs)
            self.assertTrue(any(e.get('reason')=='broken' for e in events))

    def test_no_fallback_on_auth_path_or_service_failure(self):
        for reply,code in ((b'530 Secret peer text\r\n',EC.AUTHENTICATION),
                           (b'550 Missing\r\n',EC.LISTING),
                           (b'421 Unavailable\r\n',EC.SERVICE_UNAVAILABLE)):
            with self.subTest(reply=reply),FakeC64UFtp(replies={b'MLSD':reply}) as server:
                manager=self.manager(server)
                with manager.lease(self.binding) as client:
                    error=self.assertCode(code,lambda:client.list_directory(b'/USB1'))
                    self.assertNotIn('Secret',str(error))
                self.assertNotIn(b'LIST',server.verbs)

    def test_no_fallback_on_malformed_partial_or_bounds_or_truncation(self):
        cases=[(b'type=file;size=1; good\r\ngarbage\r\n',ListingLimits(),EC.MALFORMED_LISTING),
               (b'type=file; a',ListingLimits(),EC.INCOMPLETE_LISTING),
               (b'type=file; a\r\n',ListingLimits(total_bytes=2),EC.LISTING_BOUNDS),
               (b'type=file; a\r\n',ListingLimits(line_bytes=2),EC.LISTING_BOUNDS),
               (b'type=file; a\r\ntype=file; b\r\n',ListingLimits(entries=1),EC.LISTING_BOUNDS)]
        for listing,limits,code in cases:
            with self.subTest(code=code),FakeC64UFtp(listing=listing) as server:
                manager=self.manager(server)
                with manager.lease(self.binding) as client:
                    self.assertCode(code,lambda:client.list_directory(b'/USB1',limits=limits))
                    self.assertEqual(SessionState.FAILED,client.state)
                self.assertNotIn(b'LIST',server.verbs)

    def test_octet_identity_and_sorting_repeated_listings(self):
        name=b'Schatzj\x84ger [Side 1] [Ariolasoft] [TWG].d64'
        listing=(b'type=file;size=174848; '+name+b'\r\n'
                 b'type=cdir; .\r\ntype=pdir; ..\r\n'
                 b'TYPE=file;SIZE=2;modify=20260927010203.5;x.custom=thing; A  B\r\n')
        with FakeC64UFtp(listing=listing) as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                a=client.list_directory(b'/USB1');b=client.list_directory(b'/USB1')
                self.assertEqual(a,b)
                self.assertEqual(b'/USB1',a.actual_path)
                self.assertEqual([b'A  B',name],[e.name for e in a.entries])
                self.assertIn('\\x84',a.entries[1].display_name)
                self.assertEqual('20260927010203.5',a.entries[0].modify)
                self.assertIn(('x.custom',b'thing'),a.entries[0].facts)

    def test_authentication_and_contextual_421_release_slot(self):
        cases=[({b'PASS':b'530 no\r\n'},b'220 ok\r\n',EC.AUTHENTICATION),
               ({},b'421 Too many FTP connections, try again later.\r\n',EC.SESSION_LIMIT),
               ({},b'421 Service unavailable\r\n',EC.SERVICE_UNAVAILABLE)]
        for replies,welcome,code in cases:
            with self.subTest(code=code),FakeC64UFtp(replies=replies,welcome=welcome) as server:
                manager=self.manager(server)
                def run():
                    with manager.lease(self.binding):pass
                error=self.assertCode(code,run)
                self.assertEqual(int(welcome[:3]) if not replies else 530,error.reply_code)
                self.assertEqual(0,manager.active_count)

    def test_ipv6_and_invalid_paths_fail_explicitly(self):
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            self.current=replace(self.binding,host='::1')
            def run():
                with manager.lease(self.current):pass
            self.assertCode(EC.INVALID_ARGUMENT,run)
            self.assertEqual(0,server.connections)
        for path in ('/USB1',b'/USB1/../a',b'/USB1\r\nDELE b',b'/a//b',b'/a/./b',b'/a\\b',b'/a\x00'):
            self.assertCode(EC.INVALID_ARGUMENT,lambda:checked_path(path))

    def test_lease_busy_sequential_reuse_and_stale_binding(self):
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                def nested():
                    with manager.lease(self.binding):pass
                self.assertCode(EC.BUSY,nested)
                self.assertEqual(1,manager.active_count)
                for _ in range(3):self.assertEqual(3,client.size(b'/file'))
                self.assertEqual(1,server.connections)
                self.current=replace(self.binding,core_session_id='new-session')
                before=len(server.commands)
                self.assertCode(EC.STALE,lambda:client.size(b'/file'))
                self.assertEqual(before,len(server.commands))
            self.assertEqual(0,manager.active_count)

    def test_recovery_invalidation_and_fresh_session(self):
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                old=client.identity
                manager.invalidate('fixture-device',recovering=True)
                self.assertEqual(SessionState.RECOVERING,client.state)
                self.assertCode(EC.RECOVERING,lambda:client.size(b'/file'))
            def run():
                with manager.lease(self.binding):pass
            self.assertCode(EC.RECOVERING,run)
            manager.recovery_complete('fixture-device')
            self.current=replace(self.binding,core_session_id='after-reconnect')
            with manager.lease(self.current) as client:
                self.assertNotEqual(old,client.identity)

    def test_cancellation_before_open_and_during_transfer(self):
        with FakeC64UFtp(files={b'/file':b'x'*20000}) as server:
            manager=self.manager(server);cancelled=[True]
            def run():
                with manager.lease(self.binding,cancelled=lambda:cancelled[0]):pass
            self.assertCode(EC.CANCELLED,run)
            self.assertEqual(0,server.connections)
            cancelled[0]=False
            with manager.lease(self.binding,cancelled=lambda:cancelled[0]) as client:
                def progress(_):cancelled[0]=True
                error=self.assertCode(EC.CANCELLED,lambda:client.read_into(
                    b'/file',io.BytesIO(),max_bytes=20000,progress=progress))
                self.assertGreater(error.transferred,0)
                self.assertEqual(SessionState.FAILED,client.state)
                self.assertCode(EC.STALE,lambda:client.size(b'/file'))
            self.assertEqual(1,server.verbs.count(b'RETR'))

    def test_short_retr_and_size_unavailable(self):
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                self.assertCode(EC.SIZE_MISMATCH,lambda:client.read_into(
                    b'/file',io.BytesIO(),max_bytes=4,expected_bytes=4))
        with FakeC64UFtp(replies={b'SIZE':b'502 unsupported\r\n'}) as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                self.assertCode(EC.SIZE_UNAVAILABLE,lambda:client.size(b'/file'))
                self.assertEqual(CS.UNSUPPORTED,client.capabilities.size)

    def test_delayed_failing_or_lost_completion_poison_and_never_retry_stor(self):
        cases=[dict(completion=b'451 failed\r\n'),dict(completion=b'malformed\r\n'),dict(completion=None),
               dict(completion_wait=threading.Event())]
        for opts in cases:
            with self.subTest(opts=list(opts)),FakeC64UFtp(**opts) as server:
                manager=self.manager(server,policy=FtpPolicy(final_reply=.05))
                with manager.lease(self.binding) as client:
                    error=self.assertCode(EC.COMPLETION_UNKNOWN,lambda:client.write_from(
                        b'/new',io.BytesIO(b'abc'),expected_bytes=3))
                    self.assertEqual(Outcome.UNKNOWN,error.outcome)
                    self.assertEqual(3,error.transferred)
                    self.assertEqual(SessionState.FAILED,client.state)
                self.assertEqual(1,server.verbs.count(b'STOR'))
                self.assertEqual(b'abc',server.files[b'/new'])

    def test_data_idle_timeout_no_listing_fallback(self):
        with FakeC64UFtp(data_wait=threading.Event()) as server:
            manager=self.manager(server,policy=FtpPolicy(data_idle=.05))
            with manager.lease(self.binding) as client:
                self.assertCode(EC.DATA_IDLE_TIMEOUT,lambda:client.list_directory(b'/USB1'))
            self.assertNotIn(b'LIST',server.verbs)

    def test_data_connect_timeout_fault_at_socket_boundary(self):
        # TCP blackholes are nondeterministic across OSes. Keep real control/PASV
        # sockets and inject only the connect timeout at the data socket boundary.
        original=socket.socket
        class TimeoutDataSocket(original):
            def connect(sock,address):
                if address[1] in server.pasv_ports:raise TimeoutError()
                return super().connect(address)
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client,patch('socket.socket',TimeoutDataSocket):
                error=self.assertCode(EC.DATA_CONNECT_TIMEOUT,lambda:client.list_directory(b'/USB1'))
                self.assertEqual('data-connect',error.phase)
                self.assertEqual(Outcome.NOT_STARTED,error.outcome)
            self.assertNotIn(b'MLSD',server.verbs)

    def test_transfer_rejections_and_connection_loss(self):
        for verb,code in ((b'STOR',EC.STOR),(b'RETR',EC.RETR)):
            with FakeC64UFtp(replies={verb:b'550 refused\r\n'}) as server:
                manager=self.manager(server)
                with manager.lease(self.binding) as client:
                    call=(lambda:client.write_from(b'/new',io.BytesIO(b'a'),expected_bytes=1)) if verb==b'STOR' else (
                        lambda:client.read_into(b'/file',io.BytesIO(),max_bytes=10))
                    error=self.assertCode(code,call)
                    self.assertEqual(Outcome.REJECTED,error.outcome)
        with FakeC64UFtp(replies={b'MLSD':None}) as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                self.assertCode(EC.INCOMPLETE_LISTING,lambda:client.list_directory(b'/USB1'))
            self.assertNotIn(b'LIST',server.verbs)

    def test_local_sink_failure_invalidates_and_sanitizes(self):
        class Sink:
            def write(self,_):raise OSError('private path and secret')
        with FakeC64UFtp() as server:
            events=[];manager=self.manager(server,events=events)
            with manager.lease(self.binding) as client:
                error=self.assertCode(EC.LOCAL_IO,lambda:client.read_into(b'/file',Sink(),max_bytes=4))
                self.assertNotIn('secret',str(error))
            self.assertNotIn('private path',json.dumps(events))

    def test_late_cancel_after_terminal_acceptance_keeps_completed_result(self):
        cancelled=[False]
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            def event(event):
                if event['kind']=='transfer-complete':cancelled[0]=True
            manager._diagnostic=event
            with manager.lease(self.binding,cancelled=lambda:cancelled[0]) as client:
                result=client.write_from(b'/new',io.BytesIO(b'a'),expected_bytes=1)
                self.assertEqual(Outcome.COMPLETED,result.outcome)

    def test_diagnostic_sink_failure_does_not_resend_or_abort_command(self):
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            def broken(_):raise RuntimeError('sink unavailable')
            manager._diagnostic=broken
            with manager.lease(self.binding) as client:
                client.write_from(b'/new',io.BytesIO(b'a'),expected_bytes=1)
            self.assertEqual(1,server.verbs.count(b'STOR'))

    def test_dns_network_refused_and_control_timeout_categories(self):
        import errno
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            def run():
                with manager.lease(self.binding):pass
            with patch('socket.getaddrinfo',side_effect=socket.gaierror()):
                self.assertCode(EC.DNS,run)
            original=socket.socket
            for exception,code in ((ConnectionRefusedError(),EC.CONTROL_REFUSED),
                                   (OSError(errno.ENETUNREACH,'private'),EC.NETWORK),
                                   (TimeoutError(),EC.CONTROL_TIMEOUT)):
                class FailureSocket(original):
                    def connect(sock,address):raise exception
                with patch('socket.socket',FailureSocket):
                    self.assertCode(code,run)
                self.assertEqual(0,manager.active_count)

    def test_session_change_mid_read_and_no_following_command(self):
        with FakeC64UFtp(files={b'/file':b'x'*20000}) as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                def changed(_):self.current=replace(self.binding,core_session_id='new')
                self.assertCode(EC.STALE,lambda:client.read_into(
                    b'/file',io.BytesIO(),max_bytes=20000,progress=changed))
                self.assertEqual(SessionState.FAILED,client.state)
            self.assertEqual(1,server.verbs.count(b'RETR'))

    def test_concurrent_transfer_fails_busy_without_poisoning_owner(self):
        release=threading.Event()
        with FakeC64UFtp(data_wait=release) as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                results=[]
                def read():
                    try:results.append(client.read_into(b'/file',io.BytesIO(),max_bytes=3))
                    except Exception as exc:results.append(exc)
                thread=threading.Thread(target=read)
                thread.start()
                try:
                    self.assertTrue(server.data_started.wait(1))
                    self.assertCode(EC.BUSY,lambda:client.size(b'/file'))
                finally:
                    release.set();thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(3,results[0].transferred)
                self.assertEqual(3,client.size(b'/file'))

    def test_manager_invalidation_interrupts_live_socket(self):
        release=threading.Event()
        with FakeC64UFtp(data_wait=release) as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                failures=[]
                def read():
                    try:client.read_into(b'/file',io.BytesIO(),max_bytes=3)
                    except FtpOperationError as exc:failures.append(exc)
                thread=threading.Thread(target=read);thread.start()
                try:
                    self.assertTrue(server.data_started.wait(1))
                    manager.invalidate('fixture-device',recovering=True)
                    thread.join(1)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(EC.RECOVERING,failures[0].code)
                finally:
                    release.set();thread.join(2)

    def test_two_devices_have_independent_single_leases(self):
        with FakeC64UFtp() as first, FakeC64UFtp() as second:
            manager=self.manager(first)
            other=replace(self.binding,device=DeviceIdentity('other'),port=second.port)
            bindings={'fixture-device':self.binding,'other':other}
            manager._binding_provider=bindings.get
            with manager.lease(self.binding) as one,manager.lease(other) as two:
                self.assertEqual(2,manager.active_count)
                self.assertEqual(3,one.size(b'/file'))
                self.assertEqual(3,two.size(b'/file'))
            self.assertEqual(0,manager.active_count)

    def test_cancelled_upload_preserves_uncertain_partial_and_no_cleanup(self):
        cancelled=[False]
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            with manager.lease(self.binding,cancelled=lambda:cancelled[0]) as client:
                def cancel(_):cancelled[0]=True
                error=self.assertCode(EC.CANCELLED,lambda:client.write_from(
                    b'/part',io.BytesIO(b'x'*20000),expected_bytes=20000,progress=cancel))
                self.assertEqual(Outcome.UNKNOWN,error.outcome)
            self.assertEqual(1,server.verbs.count(b'STOR'))
            self.assertFalse(set(server.verbs)&{b'DELE',b'ABOR',b'RNTO'})

    def test_stor_length_mismatch_never_reported_success(self):
        for data,expected in ((b'abc',2),(b'a',2)):
            with self.subTest(expected=expected),FakeC64UFtp() as server:
                manager=self.manager(server)
                with manager.lease(self.binding) as client:
                    self.assertCode(EC.SIZE_MISMATCH,lambda:client.write_from(
                        b'/new',io.BytesIO(data),expected_bytes=expected))
                    self.assertEqual(SessionState.FAILED,client.state)

    def test_fallback_preserves_octets_and_rejects_unknown_dialect(self):
        for data,valid in ((b'-rw-rw-rw- 1 user ftp 1 Sep 07 2026 Schatzj\x84ger.d64\r\n',True),
                           (b'garbage\r\n',False)):
            with FakeC64UFtp(replies={b'MLSD':b'502 No\r\n'},list_data=data) as server:
                manager=self.manager(server)
                with manager.lease(self.binding) as client:
                    if valid:
                        self.assertEqual(b'Schatzj\x84ger.d64',client.list_directory(b'/USB1').entries[0].name)
                    else:self.assertCode(EC.MALFORMED_LISTING,lambda:client.list_directory(b'/USB1'))
                self.assertNotIn(b'NLST',server.verbs)

    def test_phase_resets_after_successful_transfer(self):
        with FakeC64UFtp() as server:
            manager=self.manager(server,policy=FtpPolicy(control_reply=.05))
            with manager.lease(self.binding) as client:
                client.list_directory(b'/USB1')
                server.replies[b'TYPE']=b'200-Incomplete\r\n'
                error=self.assertCode(EC.CONTROL_TIMEOUT,lambda:client.size(b'/file'))
                self.assertEqual('control-reply',error.phase)
                self.assertEqual(Outcome.NOT_STARTED,error.outcome)

    def test_callback_exceptions_never_leak_payload_or_credentials(self):
        with FakeC64UFtp() as server:
            events=[];manager=self.manager(server,password='top-secret',events=events)
            with manager.lease(self.binding) as client:
                def progress(_):raise ValueError('top-secret')
                error=self.assertCode(EC.LOCAL_IO,lambda:client.read_into(
                    b'/file',io.BytesIO(),max_bytes=3,progress=progress))
                self.assertNotIn('top-secret',str(error))
            self.assertNotIn('top-secret',json.dumps(events))

    def test_lifecycle_and_diagnostic_correlation(self):
        with FakeC64UFtp() as server:
            events=[];manager=self.manager(server,events=events)
            with manager.lease(self.binding) as client:
                client.list_directory(b'/USB1')
                identity=client.identity
            states=[e['state'] for e in events if e['kind']=='lifecycle']
            self.assertEqual(['connecting','authenticating','negotiating','ready',
                              'transferring','ready','disconnected'],states)
            self.assertTrue(all(e['schema']==1 and e['core_session_id']=='core-session'
                                and e['ftp_session_id']==identity.ftp_session_id for e in events))
            self.assertTrue(any(e.get('entries')==1 for e in events))
            self.assertTrue(any('duration_ms' in e for e in events))

    def test_actual_path_preserves_raw_octets_for_service_revalidation(self):
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                path=b'/USB1/quote"-\x84'
                self.assertEqual(path,client.list_directory(path).actual_path)
        with FakeC64UFtp(replies={b'PWD':b'257 "/OTHER"\r\n'}) as server:
            manager=self.manager(server)
            with manager.lease(self.binding) as client:
                self.assertEqual(b'/OTHER',client.list_directory(b'/USB1').actual_path)

    def test_invalid_pwd_and_cwd_failure_do_not_fallback(self):
        for verb,reply,code in ((b'CWD',b'550 missing\r\n',EC.LISTING),
                                (b'PWD',b'257 unquoted\r\n',EC.PROTOCOL)):
            with FakeC64UFtp(replies={verb:reply}) as server:
                manager=self.manager(server)
                with manager.lease(self.binding) as client:
                    self.assertCode(code,lambda:client.list_directory(b'/USB1'))
                self.assertNotIn(b'LIST',server.verbs)
                self.assertNotIn(b'MLSD',server.verbs)

    def test_control_line_at_bound_with_split_crlf(self):
        with FakeC64UFtp(welcome=b'220 '+b'x'*61+b'\r\n',split=True) as server:
            manager=self.manager(server,policy=FtpPolicy(reply_line_bytes=65))
            with manager.lease(self.binding) as client:
                self.assertEqual(SessionState.READY,client.state)

    def test_cancel_before_consequential_command_reports_not_started(self):
        cancelled=[False]
        with FakeC64UFtp() as server:
            manager=self.manager(server)
            original=socket.socket
            class CancelAfterDataConnect(original):
                def connect(sock,address):
                    result=super().connect(address)
                    if address[1] in server.pasv_ports:cancelled[0]=True
                    return result
            with manager.lease(self.binding,cancelled=lambda:cancelled[0]) as client:
                with patch('socket.socket',CancelAfterDataConnect):
                    error=self.assertCode(EC.CANCELLED,lambda:client.write_from(
                        b'/new',io.BytesIO(b'a'),expected_bytes=1))
                    self.assertEqual(Outcome.NOT_STARTED,error.outcome)
            self.assertNotIn(b'STOR',server.verbs)


class ParserTests(unittest.TestCase):
    def test_malformed_records_fail_closed(self):
        rows=(b'type=file;size=-1; x',b'type=file;size=no; x',b'type=file;TYPE=dir; x',
              b'size=3; x',b'type=symlink; x',b'type=file x',b'type=file; ',
              b'type=file; /escape',b'type=file; ..',b'type=file;size=; x',
              b'type=file;modify=20261301000000; x',b'type=file;modify=garbage; x',
              b'type=file; x\x00',b'type=file;bad; x')
        for row in rows:
            with self.subTest(row=row),self.assertRaises(FtpOperationError):parse_mlsd_line(row)

    def test_incremental_parser_and_duplicate_identity(self):
        parser=ListingParser('mlsd',ListingLimits())
        for byte in b'type=file;size=0;  leading  space\r\n':parser.feed(bytes([byte]))
        self.assertEqual(b' leading  space',parser.finish()[0].name)
        with self.assertRaises(FtpOperationError):parser.feed(b'type=file;  leading  space\r\n')

    def test_raw_byte_order_independent_of_wire_order(self):
        rows=[b'type=file; Z\r\n',b'type=file; \x84\r\n',b'type=dir; a\r\n']
        def parse(rows):
            parser=ListingParser('mlsd',ListingLimits());parser.feed(b''.join(rows));return parser.finish()
        self.assertEqual(parse(rows),parse(reversed(rows)))

    def test_bound_configuration_and_error_serialization(self):
        for values in ({'data_idle':0},{'data_connect':float('nan')},{'reply_lines':0}):
            with self.assertRaises(ValueError):FtpPolicy(**values)
        with self.assertRaises(ValueError):ListingLimits(entries=0)
        for code in EC:
            error=FtpOperationError(code,'phase',outcome=Outcome.UNKNOWN)
            self.assertEqual(code.value,json.loads(json.dumps(error.as_dict()))['code'])

    def test_no_production_imports_and_headless_boundary(self):
        import ast
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]/'c64u_browser'
        for path in root.glob('*.py'):
            if path.name.startswith('c64u_ftp'):continue
            tree=ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):
                    self.assertNotIn('c64u_ftp',node.module or '')
                if isinstance(node,ast.Import):
                    self.assertFalse(any('c64u_ftp' in a.name for a in node.names))
        for name in ('c64u_ftp.py','c64u_ftp_types.py'):
            tree=ast.parse((root/name).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):
                    self.assertFalse(any(a.name in ('gi','ftplib') for a in node.names))
        from c64u_browser.c64u_ftp import C64UFtpClient
        for name in ('sendcmd','socket','ftp','password','client','credentials'):
            self.assertFalse(hasattr(C64UFtpClient,name))


if __name__=='__main__':unittest.main()
