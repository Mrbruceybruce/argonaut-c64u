"""3D review corrections: primary evidence and visible Core-formatted reports."""
import ast
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_ftp_replacements as replacement_tests
from test_ftp_replacements import server, F
from c64u_browser.jobs import JobCancelled
from c64u_browser.file_service import CopyResult
from c64u_browser.usb_backup import RestoreResult
from c64u_browser.managed_replacement import ReplacementFailure


class CorrectionTests(unittest.TestCase):
    core=replacement_tests.ReplacementTests.core
    connect=replacement_tests.ReplacementTests.connect
    source=replacement_tests.ReplacementTests.source
    run_replace=replacement_tests.ReplacementTests.run_replace

    def cleanup_failure(self):
        original=tempfile.TemporaryDirectory
        self.cleanup_attempts=0
        def factory(*args,**kwargs):
            resource=original(*args,**kwargs)
            def cleanup():
                self.cleanup_attempts+=1
                resource.cleanup()
                raise OSError('SECRET private local path')
            return SimpleNamespace(name=resource.name,cleanup=cleanup)
        return patch('c64u_browser.managed_replacement.tempfile.TemporaryDirectory',side_effect=factory)

    def secondary(self,e):
        self.assertEqual(1,self.cleanup_attempts)
        self.assertEqual(dict(attempted=True,status='failed',error_category='local-cleanup-failed'),e.local_cleanup)
        self.assertNotIn('SECRET',json.dumps(asdict(e)))
        self.assertIn('Local temporary cleanup',e.inspection_message())

    def test_unknown_final_publication_survives_cleanup_error(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            ftp.after_mutation[b'RNTO']=lambda p:None if p==F else b'250 Done\r\n'
            with self.cleanup_failure():exc=self.run_replace(core,ftp,source='/USB1/source/a',fail=True)
            e=exc.replacement_evidence;self.secondary(e)
            self.assertEqual('unknown',e.publication)
            self.assertEqual('completed',e.first_rename['outcome'])
            self.assertEqual('unknown',e.publication_rename['outcome'])
            self.assertEqual((e.staged,e.final),e.uncertain_paths)
            self.assertEqual(('mkdir','first_rename'),e.acknowledged)
            self.assertEqual('publication_rename',e.stopped)
            self.assertIsNotNone(e.transport_error);self.assertNotEqual('local-io',e.error_category)
            self.assertEqual(3,ftp.verbs.count(b'RNTO'));self.assertNotIn(b'DELE',ftp.verbs);self.assertNotIn(b'RMD',ftp.verbs)

    def test_nested_upload_uncertainty_survives_cleanup_error(self):
        with server() as ftp:
            core,_=self.connect(ftp);ftp.after_mutation[b'RNTO']=None
            with self.cleanup_failure():exc=self.run_replace(core,ftp,source='/USB1/source/a',fail=True)
            e=exc.replacement_evidence;self.secondary(e)
            self.assertEqual('location-unknown',e.upload.disposition)
            self.assertEqual((e.upload.staging,e.upload.destination),e.uncertain_paths)
            self.assertEqual('not-completed',e.publication);self.assertIsNone(e.first_rename)
            self.assertEqual(('mkdir',),e.acknowledged);self.assertEqual('staging',e.stopped)
            self.assertIsNotNone(e.upload.transport_error);self.assertEqual(1,ftp.verbs.count(b'RNTO'))
            self.assertNotIn(b'DELE',ftp.verbs);self.assertNotIn(b'RMD',ftp.verbs)

    def test_cancellation_survives_cleanup_error(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            def progress(n):raise JobCancelled()
            with self.cleanup_failure():exc=self.run_replace(core,ftp,source='/USB1/source/a',progress=progress,fail=True)
            self.assertIsInstance(exc,JobCancelled)
            e=exc.replacement_evidence;self.secondary(e)
            self.assertEqual('cancelled',e.error_category);self.assertTrue(e.cancellation_observed)
            self.assertEqual(('mkdir',),e.acknowledged);self.assertIsNotNone(e.original_before)
            self.assertEqual('not-completed',e.publication);self.assertIsNone(e.first_rename)
            self.assertNotIn(b'STOR',ftp.verbs);self.assertNotIn(b'DELE',ftp.verbs)

    def test_remote_success_then_local_cleanup_failure(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            with self.cleanup_failure():exc=self.run_replace(core,ftp,source='/USB1/source/a',fail=True)
            self.assertIsInstance(exc,ReplacementFailure)
            e=exc.replacement_evidence
            self.assertEqual(1,self.cleanup_attempts);self.assertEqual('failed',e.local_cleanup['status'])
            self.assertEqual('completed',e.publication);self.assertEqual('completed',e.cleanup)
            self.assertEqual('completed',e.backup_delete['outcome']);self.assertEqual('completed',e.directory_remove['outcome'])
            self.assertEqual('local-cleanup',e.stopped);self.assertEqual('local-io',e.error_category)
            self.assertIn('Publication and remote cleanup completed',str(exc))
            self.assertNotIn('SECRET',json.dumps(asdict(e)));self.assertEqual((),e.uncertain_paths)
            self.assertEqual(b'new',ftp.files[F]);self.assertEqual(3,ftp.verbs.count(b'RNTO'))
            self.assertEqual(1,ftp.verbs.count(b'DELE'));self.assertEqual(1,ftp.verbs.count(b'RMD'))

    def evidence(self,mode):
        with server() as ftp:
            core,_=self.connect(ftp)
            if mode=='unknown':ftp.after_mutation[b'RNTO']=lambda p:None if p==F else b'250 Done\r\n'
            elif mode=='refused':ftp.before_command=lambda v,p:b'550 refused\r\n' if v==b'RNTO' and p==F else None
            elif mode=='delete':ftp.replies[b'DELE']=b'550 refused\r\n'
            else:ftp.after_mutation[b'RMD']=None
            return self.run_replace(core,ftp,fail=True).replacement_evidence

    def check_summary(self,text,e,mode):
        self.assertIn(e.final,text);self.assertIn('Inspection only',text)
        self.assertIn('do not authorize replay, rollback or cleanup',text)
        self.assertIn('Fresh inspection and explicit review',text)
        self.assertIn(e.stopped,text)
        if mode in ('unknown','refused'):
            self.assertIn(e.staged,text);self.assertIn(e.backup,text)
            self.assertIn('Last acknowledged original location',text)
            self.assertIn('publication: '+('unknown' if mode=='unknown' else 'not-completed'),text)
            if mode=='unknown':self.assertIn('alternative locations (not confirmed)',text)
        else:
            self.assertIn('publication completed',text)
            self.assertIn('cleanup is incomplete or uncertain',text)
            self.assertIn(e.directory,text)
            if mode=='delete':self.assertIn(e.backup,text)
            else:self.assertNotIn(e.backup,text)

    def test_copy_details_show_unknown_refused_and_cleanup_states(self):
        for mode in ('unknown','refused','delete','rmdir'):
            with self.subTest(mode=mode):
                e=self.evidence(mode)
                result=CopyResult((),(),('a',),failure=str(ReplacementFailure(e)),replacements=(e,))
                self.check_summary(result.details(),e,mode)
                self.assertIsNone(result.partial_upload);self.assertIsNone(result.partial_path)

    def test_usb_restore_retains_core_consequence_details(self):
        for mode in ('unknown','refused','delete','rmdir'):
            with self.subTest(mode=mode):
                e=self.evidence(mode)
                result=RestoreResult((),(),(),(),(),('a',),0,failure=str(ReplacementFailure(e)),replacements=(e,))
                self.check_summary(result.details(),e,mode)
                self.assertIsNone(result.partial_upload)

    def test_ordinary_partial_upload_reporting_unchanged(self):
        copy=CopyResult((),(),('a',),partial_path='/USB1/partial')
        restore=RestoreResult((),(),(),(),(),('a',),0,partial_path='/USB1/partial')
        self.assertIn('Possible partial upload: /USB1/partial',copy.details())
        self.assertIn('Partial upload:\n/USB1/partial',restore.details())

    def test_copy_cancelled_completion_shows_replacement_report(self):
        tree=ast.parse(Path('c64u_browser/gui.py').read_text())
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='finished'
                    and any(isinstance(call,ast.Attribute) and call.attr=='copy_report' for call in ast.walk(n)))
        e=self.evidence('refused')
        result=CopyResult((),(),('a',),failure='Operation cancelled by request.',replacements=(e,))
        browser=SimpleNamespace(status=Mock(),copy_report=Mock(),refresh_local=Mock(),client=None)
        namespace=dict(self=browser,names=('a',),source_local=False,local=False,
                       completed_roots=lambda names,completed:())
        exec(compile(ast.Module(body=[method],type_ignores=[]),'gui.py','exec'),namespace)
        namespace['finished'](SimpleNamespace(result=result,state='cancelled'))
        browser.copy_report.assert_called_once_with(result)
        self.assertIn('Inspection only',result.details())

if __name__=='__main__':unittest.main()
