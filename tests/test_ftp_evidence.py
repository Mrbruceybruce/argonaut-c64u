"""Transport-derived evidence with real loopback replies and injected I/O faults."""
from dataclasses import replace
import io
import unittest
from unittest.mock import patch

from c64u_browser.c64u_ftp_types import FtpOperationError, Outcome, SessionState
from c64u_browser.ftp_reads import adapter_for
from c64u_ftp_server import FakeC64UFtp
import test_c64u_ftp as protocol
import test_ftp_reads as reads


def server(**kwargs):
    return FakeC64UFtp(directories={b'/':b'',b'/USB1':b''}, mutation_tree=True, **kwargs)


class Budget:
    def __init__(self, remaining):self.remaining=remaining;self.used=0
    def require(self, amount):
        if amount > self.remaining:raise ValueError('budget exhausted')
    def consume(self, amount):
        self.require(amount);self.remaining-=amount;self.used+=amount


class TransportEvidenceTests(unittest.TestCase):
    manager=protocol.ProtocolTests.manager

    def test_mkd_reply_and_exact_path_evidence(self):
        cases=[(b'257 "/USB1/new" created\r\n','matched'),
               (b'257 "/USB1/other" created\r\n','mismatch'),
               (b'257 "new" created\r\n','invalid'),
               (b'257 "/USB1/../new" created\r\n','invalid'),
               (b'257 "/USB1/new/" created\r\n','invalid'),
               (b'257 done\r\n','unavailable'),
               (b'257 /USB1/new\r\n','unavailable'),
               (b'257 "/USB1/new\r\n','unavailable'),
               (b'257 "/USB1/new" "/USB1/other"\r\n','unavailable'),
               (b'257-first\r\n257 "/USB1/new"\r\n','unavailable'),
               (b'299 "/USB1/new"\r\n','unavailable')]
        for reply,status in cases:
            with self.subTest(reply=reply),server(after_mutation={b'MKD':reply}) as ftp:
                events=[];manager=self.manager(ftp,events=events)
                with manager.lease(self.binding) as client:
                    evidence=client.mkdir(b'/USB1/new')
                    self.assertEqual(Outcome.COMPLETED,evidence.outcome) # legacy API
                    self.assertEqual(Outcome.UNKNOWN if reply.startswith(b'299') else Outcome.COMPLETED,evidence.acknowledgment)
                    self.assertEqual(tuple(reply.rstrip(b'\r\n').split(b'\r\n')),evidence.reply_lines)
                    self.assertEqual(b'/USB1/new',evidence.requested_path)
                    self.assertEqual(status,evidence.mkdir_path_status(b'/USB1/new'))
                    if status=='matched':self.assertEqual(b'/USB1/new',evidence.require_mkdir_path(b'/USB1/new'))
                    else:
                        with self.assertRaises(FtpOperationError):evidence.require_mkdir_path(b'/USB1/new')
                    self.assertNotIn('/USB1',repr(evidence));self.assertNotIn('/USB1',repr(evidence.as_dict()))
                self.assertNotIn('/USB1',repr(events));self.assertEqual(0,manager.active_count)
                self.assertEqual(1,ftp.connections);self.assertEqual(1,ftp.verbs.count(b'MKD'))
                self.assertNotIn(b'RMD',ftp.verbs)

    def test_quoted_path_escaping_exact_octets_and_requested_identity(self):
        path='/USB1/é"snow'.encode()
        reply=b'257 "'+path.replace(b'"',b'""')+b'" created\r\n'
        with server(after_mutation={b'MKD':reply}) as ftp:
            manager=self.manager(ftp)
            with manager.lease(self.binding) as client:
                e=client.mkdir(path);self.assertEqual(path,e.require_mkdir_path(path))
                self.assertEqual('mismatch',e.mkdir_path_status(b'/USB1/other'))
                self.assertEqual('mismatch',replace(e,requested_path=b'/USB1/other').mkdir_path_status(path))

    def test_mkd_rejected_lost_and_ambiguous_replies(self):
        for reply,ack in ((b'550 SECRET rejected\r\n',Outcome.REJECTED),
                          (b'421 closing\r\n',Outcome.UNKNOWN),(None,Outcome.UNKNOWN),
                          (b'350 later\r\n',Outcome.UNKNOWN),(b'bad\r\n',Outcome.UNKNOWN)):
            with self.subTest(reply=reply),server(after_mutation={b'MKD':reply}) as ftp:
                manager=self.manager(ftp)
                with manager.lease(self.binding) as client:
                    with self.assertRaises(FtpOperationError) as caught:client.mkdir(b'/USB1/new')
                    e=caught.exception.mutation
                    self.assertEqual(ack,e.acknowledgment);self.assertEqual('unavailable',e.mkdir_path_status(b'/USB1/new'))
                    if reply and reply.startswith(b'550'):
                        self.assertEqual(550,e.reply_code);self.assertEqual((reply[:-2],),e.reply_lines)
                    self.assertNotIn('SECRET',repr(caught.exception.as_dict()))
                # Even a negative reply is not proof of absence or cleanup.
                self.assertIn(b'/USB1/new',ftp.directories)
                self.assertEqual(1,ftp.connections);self.assertEqual(1,ftp.verbs.count(b'MKD'))
                self.assertEqual(0,manager.active_count);self.assertNotIn(b'RMD',ftp.verbs)

    def test_pre_submission_failure_has_no_consequence(self):
        with server() as ftp:
            manager=self.manager(ftp)
            with manager.lease(self.binding) as client:
                with patch.object(client,'_send',side_effect=OSError('before submission')):
                    with self.assertRaises(FtpOperationError) as caught:client.mkdir(b'/USB1/new')
                self.assertEqual(Outcome.NOT_STARTED,caught.exception.mutation.acknowledgment)
                self.assertNotIn(b'MKD',ftp.verbs)
            self.assertEqual(0,manager.active_count)

    def test_stor_final_ack_is_independent_of_sender_completion(self):
        for reply,ack in ((b'226 Complete\r\n',Outcome.COMPLETED),(b'250 Complete\r\n',Outcome.COMPLETED),
                          (None,Outcome.UNKNOWN),(b'550 Failed\r\n',Outcome.UNKNOWN),(b'200 unexpected\r\n',Outcome.UNKNOWN)):
            with self.subTest(reply=reply),server(completion=reply) as ftp:
                manager=self.manager(ftp);budget=Budget(17000)
                with manager.lease(self.binding) as client:
                    if ack==Outcome.COMPLETED:e=client.write_from(b'/USB1/new',io.BytesIO(b'x'*17000),expected_bytes=17000,budget=budget).transfer
                    else:
                        with self.assertRaises(FtpOperationError) as caught:client.write_from(b'/USB1/new',io.BytesIO(b'x'*17000),expected_bytes=17000,budget=budget)
                        e=caught.exception.transfer
                    self.assertEqual(ack,e.acknowledgment)
                    self.assertEqual((17000,17000,0),(e.attempted_bytes,e.confirmed_sender_bytes,e.uncertain_send_bytes))
                    self.assertEqual(17000,budget.used);self.assertEqual(0,budget.remaining)
                self.assertEqual(1,ftp.verbs.count(b'STOR'));self.assertEqual(1,ftp.connections)
                self.assertEqual(0,manager.active_count);self.assertNotIn(b'DELE',ftp.verbs)

    def test_stor_preliminary_rejection_has_no_payload_exposure(self):
        for reply,ack in ((b'550 SECRET refused\r\n',Outcome.REJECTED),(b'421 closing\r\n',Outcome.UNKNOWN),(None,Outcome.UNKNOWN)):
            with self.subTest(reply=reply),server(replies={b'STOR':reply}) as ftp:
                manager=self.manager(ftp)
                with manager.lease(self.binding) as client:
                    with self.assertRaises(FtpOperationError) as caught:client.write_from(b'/USB1/new',io.BytesIO(b'abc'),expected_bytes=3)
                    e=caught.exception.transfer;self.assertEqual(ack,e.acknowledgment)
                    self.assertEqual((0,0,0),(e.attempted_bytes,e.transferred,e.uncertain_send_bytes))
                self.assertEqual(1,ftp.verbs.count(b'STOR'));self.assertEqual(0,manager.active_count)

    def test_partial_send_failure_charges_entire_uncertain_block(self):
        for fail_block in (1,2,3):
            for partial in (0,17):
                with self.subTest(fail_block=fail_block,partial=partial),server() as ftp:
                    manager=self.manager(ftp);budget=Budget(17000)
                    with manager.lease(self.binding) as client:
                        original=client._state_to
                        def state(value):
                            original(value)
                            if value==SessionState.TRANSFERRING:
                                data=client._data
                                class Socket:
                                    calls=0
                                    def __getattr__(self,name):return getattr(data,name)
                                    def sendall(self,block):
                                        self.calls+=1
                                        if self.calls==fail_block:
                                            if partial:data.sendall(block[:partial])
                                            raise OSError('injected send loss')
                                        return data.sendall(block)
                                client._data=Socket()
                        with patch.object(client,'_state_to',side_effect=state):
                            with self.assertRaises(FtpOperationError) as caught:client.write_from(b'/USB1/new',io.BytesIO(b'x'*17000),expected_bytes=17000,budget=budget)
                        e=caught.exception.transfer
                        attempted=min(fail_block*8192,17000);confirmed=(fail_block-1)*8192
                        self.assertEqual((attempted,confirmed,attempted-confirmed),(e.attempted_bytes,e.confirmed_sender_bytes,e.uncertain_send_bytes))
                        self.assertEqual(attempted,budget.used);self.assertEqual(Outcome.UNKNOWN,e.acknowledgment)
                    self.assertEqual(0,manager.active_count);self.assertEqual(1,ftp.connections)
                    self.assertEqual(1,ftp.verbs.count(b'STOR'));self.assertNotIn(b'DELE',ftp.verbs)

    def test_failure_before_send_and_after_send_keeps_distinct_counts(self):
        for phase in ('source','timeout','progress'):
            with self.subTest(phase=phase),server() as ftp:
                manager=self.manager(ftp);budget=Budget(3)
                with manager.lease(self.binding) as client:
                    source=io.BytesIO(b'abc');original=client._state_to
                    if phase=='source':source=type('Source',(),{'read':lambda *_:(_ for _ in ()).throw(OSError('read failed'))})()
                    def state(value):
                        original(value)
                        if value==SessionState.TRANSFERRING and phase=='timeout':
                            data=client._data
                            class Socket:
                                def __getattr__(self,name):return getattr(data,name)
                                def settimeout(self,_):raise OSError('before send')
                            client._data=Socket()
                    def progress(_):
                        if phase=='progress':raise ValueError('stop after send')
                    with patch.object(client,'_state_to',side_effect=state):
                        with self.assertRaises(FtpOperationError) as caught:client.write_from(b'/USB1/new',source,expected_bytes=3,progress=progress,budget=budget)
                    e=caught.exception.transfer;count=3 if phase=='progress' else 0
                    self.assertEqual((count,count,0),(e.attempted_bytes,e.confirmed_sender_bytes,e.uncertain_send_bytes))
                    self.assertEqual(count,budget.used);self.assertEqual(Outcome.UNKNOWN,e.acknowledgment)
                self.assertEqual(0,manager.active_count)

    def test_upload_budget_before_command_and_between_blocks(self):
        for initial,after in ((2,None),(9000,0)):
            with self.subTest(initial=initial),server() as ftp:
                manager=self.manager(ftp);budget=Budget(initial);length=3 if after is None else 9000
                with manager.lease(self.binding) as client:
                    def progress(_):budget.remaining=0
                    with self.assertRaises(FtpOperationError) as caught:client.write_from(b'/USB1/new',io.BytesIO(b'x'*length),expected_bytes=length,budget=budget,progress=progress)
                    e=caught.exception.transfer;count=0 if after is None else 8192
                    self.assertEqual((count,count,0),(e.attempted_bytes,e.transferred,e.uncertain_send_bytes))
                    self.assertEqual(count,budget.used)
                    self.assertEqual(Outcome.NOT_STARTED if after is None else Outcome.UNKNOWN,e.acknowledgment)
                    self.assertEqual(0 if after is None else 1,ftp.verbs.count(b'STOR'))
                self.assertEqual(0,manager.active_count)

    def test_cancellation_before_submission_and_after_confirmed_chunk(self):
        for before in (True,False):
            with self.subTest(before=before),server() as ftp:
                pending=[False];manager=self.manager(ftp);budget=Budget(9000)
                with manager.lease(self.binding,cancelled=lambda:pending[0]) as client:
                    pending[0]=before
                    with self.assertRaises(FtpOperationError) as caught:
                        client.write_from(b'/USB1/new',io.BytesIO(b'x'*9000),expected_bytes=9000,
                            budget=budget,progress=lambda _:pending.__setitem__(0,True))
                    if before:
                        self.assertNotIn(b'STOR',ftp.verbs);self.assertEqual(0,budget.used)
                    else:
                        e=caught.exception.transfer
                        self.assertEqual((8192,8192,0),(e.attempted_bytes,e.transferred,e.uncertain_send_bytes))
                        self.assertEqual(8192,budget.used);self.assertEqual(Outcome.UNKNOWN,e.acknowledgment)
                self.assertEqual(0,manager.active_count);self.assertNotIn(b'DELE',ftp.verbs)

    def test_stor_command_send_failure_is_uncertain_without_payload(self):
        with server() as ftp:
            manager=self.manager(ftp)
            with manager.lease(self.binding) as client:
                control=client._control
                class Socket:
                    def __getattr__(self,name):return getattr(control,name)
                    def sendall(self,data):
                        if data.startswith(b'STOR '):raise OSError('command send loss')
                        return control.sendall(data)
                client._control=Socket()
                with self.assertRaises(FtpOperationError) as caught:
                    client.write_from(b'/USB1/new',io.BytesIO(b'abc'),expected_bytes=3)
                e=caught.exception.transfer
                self.assertTrue(e.submitted);self.assertEqual(Outcome.UNKNOWN,e.acknowledgment)
                self.assertEqual((0,0,0),(e.attempted_bytes,e.transferred,e.uncertain_send_bytes))
            self.assertEqual(1,ftp.connections);self.assertEqual(0,manager.active_count)

    def test_accepted_short_sender_stream_still_fails_upload(self):
        with server() as ftp:
            manager=self.manager(ftp)
            with manager.lease(self.binding) as client:
                with self.assertRaises(FtpOperationError) as caught:
                    client.write_from(b'/USB1/new',io.BytesIO(b'ab'),expected_bytes=3)
                e=caught.exception.transfer
                self.assertEqual('size-mismatch',caught.exception.code.value)
                self.assertEqual(Outcome.COMPLETED,e.acknowledgment)
                self.assertEqual('short',e.length_status)
                self.assertEqual((2,2,0),(e.attempted_bytes,e.transferred,e.uncertain_send_bytes))
                self.assertIsNone(e.sha256)

    def test_adapter_typed_budget_failure_and_private_mutation_evidence(self):
        with server(after_mutation={b'MKD':b'257 "/USB1/new" made\r\n'}) as ftp:
            core,_=reads.ReadMigrationTests.connect(self,ftp)
            adapter=adapter_for(core._client)
            evidence=adapter.mutate_evidence('mkdir','/USB1/new')
            self.assertEqual(b'/USB1/new',evidence.require_mkdir_path(b'/USB1/new'))
            with self.assertRaises(ValueError) as caught:adapter.write_from('/USB1/file',io.BytesIO(b'abc'),3,budget=Budget(2))
            self.assertEqual(Outcome.NOT_STARTED,caught.exception.ftp_error.transfer.acknowledgment)
            self.assertEqual(0,core._ftp_manager.active_count);self.assertNotIn(b'STOR',ftp.verbs)

    core=reads.ReadMigrationTests.core
