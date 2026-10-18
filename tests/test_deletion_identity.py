"""Exact deletion directory identity; simulated and isolated loopback FTP only."""
from dataclasses import replace
from threading import Event
import unittest
from unittest.mock import patch
import test_partial_authority as recovery
from c64u_browser.api import BrowserError
from c64u_browser.file_service import FileLocation
from c64u_browser.files import DirectoryIdentityError, inspect, list_directory_exact
from c64u_browser.scheduler import DeviceSession


class StrictDeletionIdentity(unittest.TestCase):
    setUp=recovery.RecoveryAuthority.setUp
    issue=recovery.RecoveryAuthority.issue
    record=recovery.RecoveryAuthority.record
    review=recovery.RecoveryAuthority.review
    block_lane=recovery.RecoveryAuthority.block_lane

    def redirect(self, requested=b'/USB2', actual=b'/OTHER'):
        original=self.peer.list_directory
        def listing(path):
            result=original(path)
            return replace(result,actual_path=actual) if path==requested else result
        return patch.object(self.peer,'list_directory',side_effect=listing)

    def mutations(self):return [c for c in self.peer.calls if c[0] in ('delete','rmdir')]

    def prepare(self,path='/USB2/target'):
        return self.service.prepare_delete((FileLocation.c64u(path),)).wait(5)

    def test_matching_recursive_directory_success(self):
        self.peer.directories.add(b'/USB2/target');self.peer.files[b'/USB2/target/a']=b'data'
        preview=self.prepare();self.assertEqual('succeeded',preview.state)
        result=self.service.execute_delete(preview.result.plan_id).wait(5)
        self.assertEqual('succeeded',result.state)
        self.assertEqual(('/USB2/target/a','/USB2/target'),result.result.removed)

    def test_parent_mismatch_rejects_files_and_directories(self):
        for directory in (False,True):
            with self.subTest(directory=directory):
                if directory:self.peer.directories.add(b'/USB2/target');self.peer.files.clear()
                else:self.peer.files[b'/USB2/target']=b'data'
                with self.redirect():result=self.prepare()
                self.assertEqual('failed',result.state)
                self.assertEqual('directory-identity',result.error.code)
                self.assertFalse(result.error.retryable)
                self.assertFalse(self.service._delete_plans)
                self.assertFalse(self.mutations())

    def test_child_redirect_before_entries_are_used(self):
        self.peer.directories.add(b'/USB2/target');self.peer.files[b'/USB2/target/child']=b'keep'
        with self.redirect(b'/USB2/target'):
            result=self.prepare()
        self.assertEqual('failed',result.state)
        self.assertEqual('directory-identity',result.error.code)
        self.assertFalse(self.service._delete_plans)
        self.assertFalse(self.mutations())

    def test_case_alias_noncanonical_and_diagnostic_evidence(self):
        for actual in (b'/usb2',b'/ALIAS',b'/USB2/',b'/USB2/../USB2',b'/USB2//'):
            with self.subTest(actual=actual),self.redirect(actual=actual):
                with self.assertRaises(DirectoryIdentityError) as caught:list_directory_exact(self.client,'/USB2')
                self.assertEqual('/USB2',caught.exception.requested_directory)
                self.assertEqual(actual.decode(),caught.exception.reported_directory)
                self.assertFalse(caught.exception.retryable)
        self.assertFalse(self.mutations())

    def test_execution_redirect_consumes_plan_without_mutation(self):
        self.peer.files[b'/USB2/target']=b'data';preview=self.prepare()
        with self.redirect():result=self.service.execute_delete(preview.result.plan_id).wait(5)
        self.assertEqual('failed',result.state)
        self.assertEqual('Directory identity mismatch; deletion stopped.',result.result.failure)
        self.assertEqual((),result.result.removed)
        self.assertFalse(self.mutations())
        with self.assertRaises(BrowserError):self.service.execute_delete(preview.result.plan_id)

    def test_final_inspection_redirect(self):
        import c64u_browser.files as files
        self.peer.files[b'/USB2/target']=b'data';preview=self.prepare();original=files.inspect_exact
        def final(client,path):
            with self.redirect():return original(client,path)
        with patch.object(files,'inspect_exact',side_effect=final):
            result=self.service.execute_delete(preview.result.plan_id).wait(5)
        self.assertEqual('failed',result.state)
        self.assertIn('Directory identity mismatch',result.result.failure)
        self.assertFalse(self.mutations())

    def test_redirect_only_in_final_empty_folder_check(self):
        import c64u_browser.files as files
        self.peer.directories.add(b'/USB2/target');preview=self.prepare()
        original_inspect=files.inspect_exact;original_listing=self.peer.list_directory;final=[False]
        def inspect_target(*args):
            result=original_inspect(*args);final[0]=True;return result
        def listing(path):
            result=original_listing(path)
            return replace(result,actual_path=b'/OTHER/empty') if final[0] and path==b'/USB2/target' else result
        with patch.object(files,'inspect_exact',side_effect=inspect_target),patch.object(self.peer,'list_directory',side_effect=listing):
            result=self.service.execute_delete(preview.result.plan_id).wait(5)
        self.assertTrue(final[0]);self.assertEqual('failed',result.state)
        self.assertIn('Directory identity mismatch',result.result.failure)
        self.assertIn(b'/USB2/target',self.peer.directories);self.assertFalse(self.mutations())

    def test_completed_prefix_retained_when_later_listing_redirects(self):
        self.peer.directories.add(b'/USB2/target')
        for name in (b'a',b'b'):self.peer.files[b'/USB2/target/'+name]=b'keep'
        preview=self.prepare();original=self.peer.list_directory;after=[False]
        self.peer.before_mutation=lambda *_:after.__setitem__(0,True)
        def listing(path):
            result=original(path)
            return replace(result,actual_path=b'/OTHER') if after[0] else result
        with patch.object(self.peer,'list_directory',side_effect=listing):
            result=self.service.execute_delete(preview.result.plan_id).wait(5)
        self.assertEqual('failed',result.state)
        self.assertEqual(('/USB2/target/a',),result.result.removed)
        self.assertIn('/USB2/target/b',result.result.not_attempted)
        self.assertIsNone(result.result.mutation)
        self.assertEqual(1,len(self.mutations()))
        self.assertIn(b'/USB2/target/b',self.peer.files)

    def test_cancellation_during_listing(self):
        self.peer.files[b'/USB2/target']=b'keep';entered=Event();release=Event();original=self.peer.list_directory
        def listing(path):
            result=original(path);entered.set();self.assertTrue(release.wait(5));return result
        with patch.object(self.peer,'list_directory',side_effect=listing):
            job=self.service.prepare_delete((FileLocation.c64u('/USB2/target'),))
            self.assertTrue(entered.wait(5));job.request_cancel();release.set();result=job.wait(5)
        self.assertEqual('cancelled',result.state)
        self.assertFalse(self.service._delete_plans);self.assertFalse(self.mutations())

    def test_session_replacement_rejects_queued_execution(self):
        self.peer.files[b'/USB2/target']=b'keep';preview=self.prepare()
        release,blocker=self.block_lane();job=self.service.execute_delete(preview.result.plan_id)
        self.session=DeviceSession('fixture','replacement');release.set();blocker.wait(5)
        self.assertEqual('failed',job.wait(5).state);self.assertFalse(self.mutations())
        with self.assertRaises(BrowserError):self.service.execute_delete(preview.result.plan_id)

    def test_recovery_preparation_and_execution_require_identity(self):
        record=self.record()
        with self.redirect():failed=self.service.prepare_partial_delete(record).wait(5)
        self.assertEqual('directory-identity',failed.error.code)
        preview=self.review(record)  # Failed preparation releases reservation.
        with self.redirect():result=self.service.execute_delete(preview.plan_id).wait(5)
        self.assertEqual('failed',result.state);self.assertFalse(self.mutations())
        with self.assertRaises(BrowserError):self.service.prepare_partial_delete(record)

    def test_browsing_and_non_strict_inspection_unchanged(self):
        self.peer.files[b'/USB2/target']=b'keep'
        with self.redirect():
            actual,entries=self.client.list_directory('/USB2')
            self.assertEqual('/OTHER',actual);self.assertEqual('target',entries[0].name)
            self.assertEqual('target',inspect(self.client,'/USB2/target').name)


class DirectoryIdentityWire(unittest.TestCase):
    def test_real_pwd_redirect_preparation_and_execution(self):
        from test_ftp_uploads import server, UploadTests
        fixture=UploadTests();self.addCleanup(fixture.doCleanups)
        with server() as ftp:
            core,_=fixture.connect(ftp)
            ftp.replies[b'PWD']=b'257 "/OTHER"\r\n'
            rejected=core.files.prepare_delete((FileLocation.c64u('/USB1/existing'),)).wait(5)
            self.assertEqual('directory-identity',rejected.error.code)
            del ftp.replies[b'PWD']
            preview=core.files.prepare_delete((FileLocation.c64u('/USB1/existing'),)).wait(5)
            self.assertEqual('succeeded',preview.state)
            ftp.replies[b'PWD']=b'257 "/OTHER"\r\n'
            result=core.files.execute_delete(preview.result.plan_id).wait(5)
            self.assertEqual('failed',result.state)
            self.assertIn('Directory identity mismatch',result.result.failure)
            self.assertNotIn(b'DELE',ftp.verbs);self.assertNotIn(b'RMD',ftp.verbs)
            with self.assertRaises(BrowserError):core.files.execute_delete(preview.result.plan_id)
