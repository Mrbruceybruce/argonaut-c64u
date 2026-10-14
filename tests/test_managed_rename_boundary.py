"""Independent boundary fault injection on real managed numeric-loopback FTP."""
import copy
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from c64u_browser.api import BrowserError
from c64u_browser.c64u_ftp import C64UFtpLeaseManager
from c64u_browser.c64u_ftp_types import ConnectionBinding, DeviceIdentity, FtpPolicy
from c64u_browser.ftp_reads import FtpReadAdapter
from c64u_browser.jobs import JobCancelled
from c64u_browser.managed_rename import RenameStopped
from c64u_browser.required_evidence import EvidenceDirectory, EvidenceReceipt, RequiredEvidence, encode_record
from c64u_ftp_server import FakeC64UFtp


class Sink:
    def __init__(self, fail=None, hook=None):
        self.fail, self.hook = fail, hook
        self.records = []
    def save(self, kind, value):
        if self.hook: self.hook(kind, value)
        if kind == self.fail: raise OSError('Injected required persistence failure')
        self.records.append((kind, value))
        return EvidenceReceipt(str(len(self.records)), hashlib.sha256(encode_record(dict(kind=kind, value=value))).hexdigest())


class RenameBoundaryTests(unittest.TestCase):
    def adapter(self, server, diagnostic=None):
        self.binding = ConnectionBinding(DeviceIdentity('fixture-device'), 'session-1', '127.0.0.1', server.port)
        self.current = self.binding
        manager = C64UFtpLeaseManager(lambda _: self.current, lambda _: '',
            policy=FtpPolicy(control_reply=.2), diagnostic=diagnostic)
        return FtpReadAdapter(manager, self.binding)

    def fixture(self, **kw):
        return FakeC64UFtp(files={b'/USB1/a': b'abc'}, directories={b'/USB1': b''}, mutation_tree=True, **kw)

    def mutations(self, server):
        return [v for v in server.verbs if v in (b'RNFR', b'RNTO', b'STOR', b'DELE', b'RMD', b'MKD')]

    def test_explicit_boundary_retains_both_exact_framed_replies(self):
        with self.fixture(split=True) as server:
            adapter = self.adapter(server); sink = Sink()
            with adapter.operation(reject_busy=True):
                owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', sink)
                self.assertEqual(self.mutations(server), [b'RNFR'])
                self.assertFalse(owner.verified)
                first, second = owner.continue_rename()
                self.assertEqual(first.request, b'RNFR /USB1/a\r\n')
                self.assertEqual(second.request, b'RNTO /USB1/b\r\n')
                self.assertEqual(first.reply, b'350 Continue\r\n')
                self.assertEqual(second.reply, b'250 Renamed\r\n')
                self.assertEqual(first.ftp_session_id, second.ftp_session_id)
                self.assertTrue(owner.verified)
                self.assertEqual(adapter.size('/USB1/b'), 3)
            self.assertEqual([k for k, v in sink.records], ['rnfr-intent', 'rnfr-outcome', 'rnto-intent', 'rnto-outcome'])
            self.assertEqual(server.connections, 1)
            self.assertEqual(self.mutations(server), [b'RNFR', b'RNTO'])

    def test_reentrant_outcome_sink_cannot_continue_before_receipt(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            def hook(kind, value):
                if kind == 'rnfr-outcome':
                    owner = next(iter(adapter._rename_owners.values()))
                    owner.continue_rename()
            with self.assertRaises(RenameStopped), adapter.operation():
                adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink(hook=hook))
            self.assertEqual(self.mutations(server), [b'RNFR'])
            self.assertTrue(adapter._evidence_blocked)

    def test_session_change_during_rnto_persistence_not_verified(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            def hook(kind, value):
                if kind == 'rnto-outcome':
                    self.current = replace(self.binding, core_session_id='changed')
            with self.assertRaises(BrowserError), adapter.operation():
                owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink(hook=hook))
                owner.continue_rename()
            self.assertFalse(owner.verified)
            self.assertTrue(owner.rnto.remote_effects_possible)
            self.assertEqual(self.mutations(server), [b'RNFR', b'RNTO'])

    def test_socket_invalidation_during_outcome_persistence_not_verified(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            def hook(kind, value):
                if kind == 'rnto-outcome':
                    adapter._context.get().client._invalidate()
            with self.assertRaises(RenameStopped), adapter.operation():
                owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink(hook=hook))
                owner.continue_rename()
            self.assertFalse(owner.verified)
            self.assertTrue(owner.rnto.remote_effects_possible)

    def test_buffered_surplus_reply_cannot_acknowledge_next_command(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with self.assertRaises(RenameStopped), adapter.operation():
                # Inject at the reply parser boundary, independent of TCP splitting.
                original = __import__('c64u_browser.c64u_ftp', fromlist=['C64UFtpClient']).C64UFtpClient._reply
                def reply(client, *args, **kwargs):
                    result = original(client, *args, **kwargs)
                    if kwargs.get('capture') is not None:
                        client._buffer.extend(b'250 Unsolicited\r\n')
                    return result
                with patch('c64u_browser.c64u_ftp.C64UFtpClient._reply', new=reply):
                    adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
            owner = next(iter(adapter._rename_owners.values()))
            self.assertFalse(owner.rnfr.accepted)
            self.assertEqual(owner.rnfr.reply, b'350 Continue\r\n250 Unsolicited\r\n')
            self.assertEqual(self.mutations(server), [b'RNFR'])

    def test_multiline_raw_framing_unchanged(self):
        reply = b'350-First line\r\n second line\r\n350 Last line\r\n'
        with self.fixture(after_mutation={b'RNFR': reply}) as server:
            adapter = self.adapter(server)
            with adapter.operation():
                owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                self.assertEqual(owner.rnfr.reply, reply)
                owner.continue_rename()

    def test_failure_at_each_required_write_has_exact_command_prefix(self):
        for kind, expected in [('rnfr-intent', []), ('rnfr-outcome', [b'RNFR']),
                               ('rnto-intent', [b'RNFR']), ('rnto-outcome', [b'RNFR', b'RNTO'])]:
            with self.subTest(kind=kind), self.fixture() as server:
                adapter = self.adapter(server)
                with self.assertRaises(OSError):
                    with adapter.operation():
                        owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink(fail=kind))
                        owner.continue_rename()
                self.assertEqual(self.mutations(server), expected)
                self.assertTrue(adapter._rename_owners)
                self.assertFalse(any(o.verified for o in adapter._rename_owners.values()))
                with self.assertRaises(BrowserError):
                    with adapter.operation(): adapter.size('/USB1/a')
                self.assertEqual(server.connections, 1)

    def test_no_rnto_before_durable_outcome_and_intent(self):
        with self.fixture() as server:
            adapter = self.adapter(server); phases = []
            def hook(kind, value):
                phases.append((kind, tuple(self.mutations(server))))
                if kind in ('rnfr-outcome', 'rnto-intent'):
                    self.assertEqual(self.mutations(server), [b'RNFR'])
            with adapter.operation():
                adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink(hook=hook)).continue_rename()
            self.assertEqual(len(phases), 4)

    def test_exact_reply_codes_only(self):
        for verb, reply in [(b'RNFR', b'331 Wrong positive\r\n'), (b'RNFR', b'250 Wrong positive\r\n'),
                            (b'RNTO', b'200 Wrong positive\r\n'), (b'RNTO', b'350 Wrong phase\r\n'),
                            (b'RNFR', b'550 Refused\r\n'), (b'RNTO', b'550 Refused\r\n')]:
            with self.subTest(verb=verb, reply=reply), self.fixture(after_mutation={verb: reply}) as server:
                adapter = self.adapter(server)
                with self.assertRaises(RenameStopped):
                    with adapter.operation():
                        adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink()).continue_rename()
                self.assertEqual(self.mutations(server), [b'RNFR'] if verb == b'RNFR' else [b'RNFR', b'RNTO'])

    def test_lost_replies_retain_unknown_consequences(self):
        for verb in (b'RNFR', b'RNTO'):
            with self.subTest(verb=verb), self.fixture(after_mutation={verb: None}) as server:
                adapter = self.adapter(server)
                with self.assertRaises(RenameStopped):
                    with adapter.operation():
                        adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink()).continue_rename()
                owner = next(iter(adapter._rename_owners.values()))
                evidence = owner.rnfr if verb == b'RNFR' else owner.rnto
                self.assertEqual(evidence.acknowledgment, 'unknown')
                self.assertEqual(evidence.remote_effects_possible, verb == b'RNTO')
                self.assertFalse(evidence.framing_complete)
                self.assertEqual(evidence.reply, b'')

    def test_malformed_reply_not_normalized(self):
        for raw in (b'350 malformed\n', b'garbage\r\n', b'350 partial'):
            with self.subTest(raw=raw), self.fixture(after_mutation={b'RNFR': raw}) as server:
                adapter = self.adapter(server)
                with self.assertRaises(RenameStopped):
                    with adapter.operation(): adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                owner = next(iter(adapter._rename_owners.values()))
                self.assertEqual(owner.rnfr.reply, raw)
                self.assertFalse(owner.rnfr.accepted)
                self.assertEqual(self.mutations(server), [b'RNFR'])

    def test_bounded_overlong_reply(self):
        with self.fixture(after_mutation={b'RNFR': b'350 ' + b'x'*5000 + b'\r\n'}) as server:
            adapter = self.adapter(server)
            with self.assertRaises(RenameStopped):
                with adapter.operation(): adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
            evidence = next(iter(adapter._rename_owners.values())).rnfr
            self.assertFalse(evidence.accepted)
            self.assertLessEqual(len(evidence.reply), 16384)

    def test_cancellation_between_commands(self):
        with self.fixture() as server:
            adapter = self.adapter(server); cancel = [False]
            def check():
                if cancel[0]: raise JobCancelled()
            with self.assertRaises(JobCancelled):
                with adapter.operation(check):
                    owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                    cancel[0] = True
                    owner.continue_rename()
            self.assertEqual(self.mutations(server), [b'RNFR'])

    def test_cancellation_after_rnto_does_not_erase_accepted_reply(self):
        with self.fixture() as server:
            adapter = self.adapter(server); cancel = [False]
            def check():
                if cancel[0]: raise JobCancelled()
            def hook(kind, value):
                if kind == 'rnto-outcome': cancel[0] = True
            with adapter.operation(check):
                owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink(hook=hook))
                owner.continue_rename()
                self.assertTrue(owner.verified)

    def test_session_change_prevents_continuation(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with self.assertRaises(Exception):
                with adapter.operation():
                    owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                    self.current = replace(self.binding, core_session_id='session-2')
                    owner.continue_rename()
            self.assertEqual(self.mutations(server), [b'RNFR'])

    def test_lease_invalidation_prevents_continuation(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with self.assertRaises(Exception):
                with adapter.operation():
                    owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                    adapter._manager.invalidate(self.binding.device.physical_id)
                    owner.continue_rename()
            self.assertEqual(self.mutations(server), [b'RNFR'])

    def test_replaced_lease_owner_prevents_continuation(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with self.assertRaises(RenameStopped):
                with adapter.operation():
                    owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                    adapter._manager._leases[self.binding.device.physical_id] = object()
                    owner.continue_rename()
            self.assertEqual(self.mutations(server), [b'RNFR'])

    def test_unrelated_command_and_second_begin_are_blocked(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with adapter.operation():
                owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                with self.assertRaises(BrowserError): adapter.size('/USB1/a')
                with self.assertRaises(BrowserError): adapter.begin_evidenced_rename('/USB1/a', '/USB1/c', Sink())
                owner.continue_rename()
            self.assertEqual(self.mutations(server), [b'RNFR', b'RNTO'])

    def test_no_alternate_target_parameter_or_serialized_capability(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with adapter.operation():
                owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                with self.assertRaises(TypeError): owner.continue_rename('/USB1/c')
                with self.assertRaises(TypeError): owner.continue_rename(source='/USB1/c')
                self.assertNotIn('token', json.dumps(owner.rnfr.private_record()))
                owner.continue_rename()

    def test_copied_owner_cannot_continue(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with adapter.operation():
                owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                with self.assertRaises(RenameStopped): copy.copy(owner).continue_rename()
            self.assertEqual(self.mutations(server), [b'RNFR'])

    def test_repeated_continuation_cannot_dispatch(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with adapter.operation():
                owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                owner.continue_rename()
                with self.assertRaises(RenameStopped): owner.continue_rename()
            self.assertEqual(self.mutations(server), [b'RNFR', b'RNTO'])

    def test_scope_exit_abandons_pending_rnfr_without_commands(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with adapter.operation(): owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
            with self.assertRaises(RenameStopped): owner.continue_rename()
            self.assertEqual(self.mutations(server), [b'RNFR'])
            self.assertTrue(server.closed.wait(1))

    def test_expired_owner_refuses(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with adapter.operation():
                owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                with patch('c64u_browser.managed_rename.time.monotonic', return_value=owner._expires+1):
                    with self.assertRaises(RenameStopped): owner.continue_rename()
            self.assertEqual(self.mutations(server), [b'RNFR'])

    def test_diagnostic_failure_remains_best_effort(self):
        def fail(event): raise OSError('diagnostic-only failure')
        with self.fixture() as server:
            adapter = self.adapter(server, fail)
            with adapter.operation():
                owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
                owner.continue_rename(); self.assertTrue(owner.verified)

    def test_original_rename_projection_unchanged(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with adapter.operation(): evidence = adapter.mutate_evidence('rename', '/USB1/a', '/USB1/b', strict_rename=True)
            self.assertEqual(evidence.reply_lines, (b'250 Renamed',))
            self.assertEqual(evidence.acknowledged, (('RNFR', 350), ('RNTO', 250)))
            self.assertNotIn('reply_lines', evidence.as_dict())

    def test_explicit_outer_operation_required(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            with self.assertRaises(BrowserError): adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', Sink())
            self.assertEqual(server.connections, 0)

    def test_invalid_paths_refuse_before_lease(self):
        with self.fixture() as server:
            adapter = self.adapter(server)
            for source, target in [('/USB1/a\r\nDELE x', '/USB1/b'), ('/USB1/a', '/USB1/a'), ('/USB1/a', '/'+'x'*2049)]:
                with adapter.operation():
                    with self.assertRaises(Exception): adapter.begin_evidenced_rename(source, target, Sink())
            self.assertEqual(server.connections, 0)

    def test_actual_fsync_failure_after_rnfr_prevents_rnto(self):
        with tempfile.TemporaryDirectory() as tmp, self.fixture() as server:
            store = EvidenceDirectory(Path(tmp)/'evidence'); self.addCleanup(store.close)
            adapter = self.adapter(server)
            with self.assertRaises(OSError):
                with adapter.operation():
                    owner = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', store)
                    with patch('c64u_browser.required_evidence.os.fsync', side_effect=OSError('disk failure')):
                        owner.continue_rename()
            self.assertEqual(self.mutations(server), [b'RNFR'])
            self.assertTrue(store.blocked)


if __name__ == '__main__': unittest.main()
