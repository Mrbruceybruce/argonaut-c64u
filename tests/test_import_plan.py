"""Read-only planner checks; injected transports expose no mutation API."""
from dataclasses import FrozenInstanceError, replace
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace as E
import unittest
from unittest.mock import patch

from c64u_browser.import_plan import ImportPlanner, validate_selections
from c64u_browser.jobs import JobCancelled
from c64u_browser.managed_library import LibraryError, parse_manifest
from c64u_browser.picker_model import PickerSelection
from c64u_browser.scheduler import DeviceSession
from tests.test_game_library import crt_bytes, D64_FIXTURE
from tests.test_managed_library import manifest, game, PATH


class ImportPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.session = DeviceSession('device', 'one')
        self.data = {PATH+'/manifest.json': manifest()}
        self.entries = [];self.progress = [];self.calls = [];self.cancel = False
        self.library = parse_manifest(manifest(), 'device', PATH)
        self.planner = ImportPlanner(self.listing, self.read, self.session, self.check, self.progress.append)

    def check(self):
        if self.cancel:raise JobCancelled()

    def listing(self, path):
        self.calls.append(('list', path))
        return path, ([E(name='manifest.json', kind='file')] +
                      [E(name=n, kind='dir') for n in ('games','metadata','artwork')]
                      if path == PATH else list(self.entries))

    def read(self, path, limit, progress, *, budget=None):
        self.calls.append(('read', path))
        if path not in self.data:raise LibraryError('Missing content')
        data = self.data[path]
        if budget is not None:budget.require(len(data));budget.consume(len(data))
        progress(len(data));return data

    def source(self, name='a.crt', data=None, remote=False):
        data = crt_bytes() if data is None else data
        path = '/USB1/'+name if remote else str(self.root/name)
        if remote:self.data[path] = data
        else:Path(path).write_bytes(data)
        return PickerSelection('c64u' if remote else 'core-host',path,name,
            '/USB1' if remote else '', 'device' if remote else '', 'one' if remote else '', 'games', 'file')

    def prepare(self, *sources):
        return self.planner.prepare(sources, self.library.identity, 0)

    def existing(self, name='a.crt', data=None, present=True):
        data = crt_bytes() if data is None else data
        entry = game(path='games/'+name, size=len(data), sha256=hashlib.sha256(data).hexdigest())
        self.data[PATH+'/manifest.json'] = manifest(games=[entry])
        if present:
            self.data[PATH+'/games/'+name] = data
            self.entries.append(E(name=name, kind='file'))

    def test_local_hash_validation_workload_and_immutability(self):
        source = self.source();before = Path(source.path).read_bytes()
        plan = self.prepare(source)
        self.assertEqual('new', plan.items[0].classification)
        self.assertEqual(hashlib.sha256(before).hexdigest(),plan.items[0].sha256)
        self.assertEqual(len(before),plan.transfer_bytes)
        self.assertEqual(before,Path(source.path).read_bytes())
        self.assertEqual(1,dict(plan.counts)['new'])
        self.assertGreaterEqual(plan.bytes_read,2*len(before))
        self.assertEqual('complete',self.progress[-1].phase)
        with self.assertRaises(FrozenInstanceError):plan.revision=99
        with self.assertRaises(FrozenInstanceError):plan.items[0].size=1
        self.assertTrue(all(verb in ('read','list') for verb,_ in self.calls))

    def test_remote_typed_context_and_hash(self):
        source=self.source(remote=True);plan=self.prepare(source)
        self.assertEqual(source,plan.items[0].source)
        self.assertEqual('one',plan.session_id)
        self.assertEqual(2,self.calls.count(('read',source.path)))

    def test_stale_session_and_forbidden_roots(self):
        source=self.source(remote=True)
        for candidate in (replace(source,session_id='two'),replace(source,device_id='other'),
                          replace(source,path='/Flash/a.crt',storage_root='/Flash'),
                          replace(source,path='/Temp/a.crt',storage_root='/Temp'),
                          replace(source,path='/USB1/../a.crt')):
            with self.subTest(candidate=candidate),self.assertRaises((ValueError,LibraryError)):
                self.prepare(candidate)
        self.assertEqual([],self.calls)

    def test_typed_kind_category_and_local_context(self):
        source=self.source()
        for candidate in (replace(source,kind='dir'),replace(source,category='sid'),
                          replace(source,device_id='device'),replace(source,filename='b.crt')):
            with self.assertRaises(LibraryError):validate_selections((candidate,),self.session)

    def test_d64_and_invalid_formats(self):
        sources=(self.source('disk.d64',D64_FIXTURE.read_bytes()),self.source('bad.crt',b'bad'),
                 self.source('bad.d64',b'bad'),self.source('no.sid',b'bad'))
        plan=self.prepare(*sources)
        self.assertEqual(['new','invalid','invalid','invalid'],[i.classification for i in plan.items])

    def test_confirmed_same_name_duplicate(self):
        self.existing();plan=self.prepare(self.source())
        self.assertEqual('same-name-duplicate',plan.items[0].classification)
        self.assertEqual('verified',plan.content[0].status)
        self.assertEqual(0,plan.transfer_bytes)

    def test_confirmed_different_name_duplicate(self):
        self.existing();plan=self.prepare(self.source('b.crt'))
        self.assertEqual('content-duplicate',plan.items[0].classification)

    def test_filename_conflict_and_no_silent_rename(self):
        self.existing();plan=self.prepare(self.source(data=crt_bytes(name='DIFFERENT')))
        self.assertEqual('conflict',plan.items[0].classification)
        self.assertEqual('games/a.crt',plan.items[0].relative_destination)

    def test_duplicate_batch_deterministic(self):
        first=self.source();second=self.source('b.crt')
        plan=self.prepare(first,second,first)
        self.assertEqual(['new','batch-duplicate','batch-duplicate'],[i.classification for i in plan.items])
        self.assertEqual(len(crt_bytes()),plan.transfer_bytes)

    def test_batch_same_name_different_content_blocks_both(self):
        first=self.source('a.crt');second=self.source('A.crt',crt_bytes(name='DIFFERENT'))
        plan=self.prepare(first,second)
        self.assertEqual(['conflict','conflict'],[i.classification for i in plan.items])

    def test_missing_and_changed_catalog_content_block_duplicates(self):
        self.existing(present=False);source=self.source()
        plan=self.prepare(source)
        self.assertEqual('unverified',plan.items[0].classification)
        self.assertEqual('unavailable',plan.content[0].status)
        self.data[PATH+'/games/a.crt']=crt_bytes(name='CHANGED')
        plan=self.prepare(source)
        self.assertEqual('unverified',plan.items[0].classification)
        self.assertEqual('mismatch',plan.content[0].status)

    def test_nonrelevant_catalog_evidence_is_manifest_only(self):
        self.existing(present=False)
        plan=self.prepare(self.source('other.crt',crt_bytes(name='OTHER')))
        self.assertEqual('manifest-only',plan.content[0].status)
        self.assertNotIn(('read',PATH+'/games/a.crt'),self.calls)

    def test_uncataloged_destination_blocks(self):
        self.entries=[E(name='A.crt',kind='file')]
        self.assertEqual('conflict',self.prepare(self.source()).items[0].classification)

    def test_source_change_during_planning_rejects_complete_result(self):
        source=self.source();original=self.planner.source;count=0
        def changed(*args):
            nonlocal count
            count+=1
            if count==2:Path(source.path).write_bytes(crt_bytes(name='CHANGED'))
            return original(*args)
        self.planner.source=changed
        with self.assertRaisesRegex(LibraryError,'changed'):self.prepare(source)
        self.assertNotEqual('complete',self.progress[-1].phase)

    def test_remote_same_size_change_rejected(self):
        source=self.source(remote=True);read=self.planner.read;count=0
        def changed(path,*args,**kwargs):
            nonlocal count
            if path==source.path:
                count+=1
                if count==2:self.data[path]=crt_bytes(name='CHANGED')
            return read(path,*args,**kwargs)
        self.planner.read=changed
        with self.assertRaisesRegex(LibraryError,'changed'):self.prepare(source)

    def test_manifest_revision_and_same_revision_byte_change_rejected(self):
        for changed in (manifest(revision=1),manifest(created_at='2026-10-11T10:00:00Z')):
            self.setUp();source=self.source();read=self.planner.read;count=0
            def mutate(path,*args,**kwargs):
                nonlocal count
                if path.endswith('manifest.json'):
                    count+=1
                    if count==2:self.data[path]=changed
                return read(path,*args,**kwargs)
            self.planner.read=mutate
            with self.assertRaisesRegex(LibraryError,'evidence changed'):self.prepare(source)

    def test_destination_listing_change_rejected(self):
        source=self.source();listing=self.planner.listing;count=0
        def changed(path):
            nonlocal count
            if path.endswith('/games'):
                count+=1
                if count==2:self.entries.append(E(name='a.crt',kind='file'))
            return listing(path)
        self.planner.listing=changed
        with self.assertRaisesRegex(LibraryError,'evidence changed'):self.prepare(source)

    def test_cancel_during_read_propagates_and_no_complete_plan(self):
        source=self.source(remote=True)
        def cancel(progress):self.progress.append(progress);self.cancel=True
        self.planner.report=cancel
        with self.assertRaises(JobCancelled):self.prepare(source)
        self.assertFalse(any(p.phase=='complete' for p in self.progress))

    def test_symlink_refused(self):
        source=self.source();link=self.root/'link.crt';link.symlink_to(source.path)
        plan=self.prepare(replace(source,path=str(link),filename=link.name))
        self.assertEqual('invalid',plan.items[0].classification)

    def test_bounded_items_and_source_budget(self):
        source=self.source()
        with self.assertRaises(LibraryError):self.prepare(*([source]*65))
        self.planner.source_budget.limit=1
        with patch('c64u_browser.import_plan.MAX_SOURCE_BYTES',1):
            with self.assertRaisesRegex(LibraryError,'budget'):self.prepare(source)

    def test_relevant_catalog_work_is_bounded(self):
        self.existing();source=self.source()
        with patch('c64u_browser.import_plan.MAX_RELEVANT_GAMES',0):
            with self.assertRaisesRegex(LibraryError,'Too many'):self.prepare(source)

    def test_catalog_path_wrong_type_blocks_even_with_readable_bytes(self):
        self.existing();self.entries=[E(name='a.crt',kind='dir')]
        self.assertEqual('unverified',self.prepare(self.source()).items[0].classification)

    def test_progress_counts_and_names(self):
        source=self.source();self.prepare(source)
        self.assertTrue(any(dict(p.details).get('current_file')==source.path for p in self.progress))
        amounts=[dict(p.details)['bytes_read'] for p in self.progress]
        self.assertEqual(sorted(amounts),amounts)
        self.assertEqual((1,1),(self.progress[-1].completed,self.progress[-1].total))


class ImportCoreTests(unittest.TestCase):
    def setUp(self):
        from tests.test_core import CoreTests
        self.fixture=CoreTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.core=self.fixture.core;self.core.connect(self.fixture.profile)
        self.client=self.fixture.created[-1];self.session=self.core.device_session()
        self.library=parse_manifest(manifest(),self.session.device_id,PATH)
        self.core.configure_game_library(PATH,identity=self.library.identity,expected_session=self.session)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        path=Path(self.temp.name)/'a.crt';path.write_bytes(crt_bytes())
        self.source=PickerSelection('core-host',str(path),path.name,'','','','games','file')
        self.calls=[]
        def listing(path):
            self.calls.append(path)
            return path, ([] if path.endswith('/games') else
                [E(name='manifest.json',kind='file')]+[E(name=n,kind='dir') for n in ('games','metadata','artwork')])
        self.client.list_directory=listing
        self.patch=patch('c64u_browser.native_files.read_remote_game',return_value=manifest())
        self.read=self.patch.start();self.addCleanup(self.patch.stop)

    def run_plan(self,**kwargs):
        return self.core.prepare_managed_import((self.source,),self.library,self.session,**kwargs).wait(5)

    def test_core_success_and_readonly_revalidation_no_catalog_or_preferences_write(self):
        before=self.core.preferences.path.read_bytes()
        result=self.run_plan();self.assertEqual('succeeded',result.state,result.error)
        second=self.run_plan(previous=result.result)
        self.assertEqual('succeeded',second.state,second.error)
        self.assertEqual(before,self.core.preferences.path.read_bytes())
        self.assertFalse(self.core.game_library.path.exists())
        self.assertEqual(0,self.library.revision)

    def test_core_revalidation_rejects_changed_source(self):
        result=self.run_plan();Path(self.source.path).write_bytes(crt_bytes(name='CHANGED'))
        later=self.run_plan(previous=result.result)
        self.assertEqual('failed',later.state)
        self.assertEqual('plan',later.error.code)

    def test_reconnect_rejects_captured_session_before_reads(self):
        self.core.connect(self.fixture.profile)
        with self.assertRaisesRegex(Exception,'intended'):self.run_plan()
        self.read.assert_not_called()

    def test_changed_selected_library_refused(self):
        self.core.configure_game_library('')
        with self.assertRaisesRegex(Exception,'intended'):self.run_plan()
        self.assertEqual([],self.calls)

    def test_session_replacement_during_read_discards_result(self):
        def changed(*args,**kwargs):
            self.core.connect(self.fixture.profile)
            return manifest()
        self.read.side_effect=changed
        result=self.run_plan()
        self.assertEqual('failed',result.state)
        self.assertEqual('session',result.error.code)
        self.assertIsNone(result.result)

    def test_location_change_during_read_discards_result(self):
        def changed(*args,**kwargs):
            self.core.configure_game_library('');return manifest()
        self.read.side_effect=changed
        result=self.run_plan()
        self.assertEqual('failed',result.state)
        self.assertEqual('location',result.error.code)

    def test_revision_changed_before_preparation_fails(self):
        self.read.return_value=manifest(revision=1)
        result=self.run_plan()
        self.assertEqual('failed',result.state)
        self.assertIn('revision changed',result.error.message)


class ImportWireTests(unittest.TestCase):
    def test_actual_managed_reads_hash_remote_source_without_mutation(self):
        from c64u_ftp_server import FakeC64UFtp
        import test_ftp_reads as reads
        fixture=reads.ReadMigrationTests();self.addCleanup(fixture.doCleanups)
        root=PATH.encode()
        directories={b'/':b'type=dir; SD\r\ntype=dir; USB1\r\n',
            b'/SD':b'type=dir; ARGONAUT_LIBRARY\r\n',b'/USB1':b'type=file; a.crt\r\n',
            root:b'type=file; manifest.json\r\ntype=dir; games\r\ntype=dir; metadata\r\ntype=dir; artwork\r\n',
            root+b'/games':b'',root+b'/metadata':b'',root+b'/artwork':b''}
        files={root+b'/manifest.json':manifest(),b'/USB1/a.crt':crt_bytes()}
        with FakeC64UFtp(directories=directories,files=files) as server:
            with patch('ftplib.FTP',side_effect=AssertionError('Legacy FTP forbidden')):
                core,_=fixture.connect(server);session=core.device_session()
                library=parse_manifest(manifest(),session.device_id,PATH)
                core.configure_game_library(PATH,identity=library.identity,expected_session=session)
                source=PickerSelection('c64u','/USB1/a.crt','a.crt','/USB1',session.device_id,session.session_id,'games','file')
                result=core.prepare_managed_import((source,),library,session).wait(10)
                self.assertEqual('succeeded',result.state,result.error)
                self.assertEqual(hashlib.sha256(crt_bytes()).hexdigest(),result.result.items[0].sha256)
                self.assertEqual(0,core._ftp_manager.active_count)
                self.assertFalse({b'STOR',b'MKD',b'DELE',b'RMD',b'RNFR',b'RNTO'} & set(server.verbs))
                self.assertEqual(files,server.files)
                self.assertFalse(core.game_library.path.exists())


class SourceBudgetTests(unittest.TestCase):
    def setUp(self):
        from c64u_browser.import_plan import SourceBudget
        self.f=ImportPlanTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.budget=SourceBudget(100)
        self.f.planner.source_budget=self.budget

    def test_explicit_production_limit_and_oversized_sparse_source_preflight(self):
        from c64u_browser.import_plan import SourceBudget,SourceBudgetError
        self.assertEqual(268435456,SourceBudget().limit)
        source=self.f.source()
        with open(source.path,'wb') as stream:stream.truncate(268435457)
        self.f.planner.source_budget=SourceBudget()
        with self.assertRaises(SourceBudgetError):self.f.prepare(source)
        self.assertEqual(0,self.f.planner.source_budget.consumed)
        self.assertFalse(any(p.phase=='complete' for p in self.f.progress))

    def test_multiple_sources_reject_next_before_read(self):
        from c64u_browser.import_plan import SourceBudgetError
        a=self.f.source('a.crt');b=self.f.source('b.crt',crt_bytes(name='B'))
        self.budget.limit=len(crt_bytes())+1
        self.f.planner.source(a,'CRT')
        with self.assertRaises(SourceBudgetError):self.f.planner.source(b,'CRT')
        self.assertEqual(len(crt_bytes()),self.budget.consumed)

    def test_failed_source_bytes_persist_and_next_source_is_refused(self):
        from c64u_browser.import_plan import SourceBudgetError
        a=self.f.source('a.crt',remote=True);b=self.f.source('b.crt',remote=True)
        original=self.f.planner.read;attempts=[]
        def read(path,limit,progress,*,budget=None):
            if path==a.path:
                attempts.append(path);budget.consume(90);progress(90)
                raise LibraryError('Read failed after payload arrived.')
            return original(path,limit,progress,budget=budget)
        self.f.planner.read=read
        with self.assertRaises(SourceBudgetError):self.f.prepare(a,b)
        self.assertEqual(90,self.budget.consumed)
        self.assertEqual([a.path],attempts)
        self.assertFalse(any(p.phase=='complete' for p in self.f.progress))

    def test_failed_source_followed_by_valid_source_preserves_charges(self):
        a=self.f.source('bad.crt',remote=True);b=self.f.source('good.crt',remote=True)
        original=self.f.planner.read;size=len(crt_bytes());self.budget.limit=7+size*2
        def read(path,limit,progress,*,budget=None):
            if path==a.path:
                budget.consume(7);progress(7);raise LibraryError('Rejected after reading')
            return original(path,limit,progress,budget=budget)
        self.f.planner.read=read;plan=self.f.prepare(a,b)
        self.assertEqual(['invalid','new'],[i.classification for i in plan.items])
        self.assertEqual(7+2*size,plan.source_bytes_read)

    def test_repeated_verification_must_fit_and_exact_limit_succeeds(self):
        from c64u_browser.import_plan import SourceBudget,SourceBudgetError
        source=self.f.source();size=len(crt_bytes())
        self.budget.limit=2*size-1
        with self.assertRaises(SourceBudgetError):self.f.prepare(source)
        self.assertEqual(size,self.budget.consumed)
        self.f.planner.source_budget=SourceBudget(2*size)
        plan=self.f.prepare(source)
        self.assertEqual(2*size,plan.source_bytes_read)
        self.assertEqual(0,self.f.planner.source_budget.remaining)

    def test_local_growth_cannot_read_past_remaining_budget(self):
        from c64u_browser.import_plan import SourceBudgetError
        source=self.f.source();size=len(crt_bytes());self.budget.limit=size
        report=self.f.planner.report
        def grow(progress):
            if dict(progress.details).get('current_file')==source.path:
                with open(source.path,'ab') as stream:stream.write(b'extra')
            report(progress)
        self.f.planner.report=grow
        with self.assertRaises(SourceBudgetError):self.f.prepare(source)
        self.assertEqual(size,self.budget.consumed)
        self.assertFalse(any(p.phase=='complete' for p in self.f.progress))


class SourceBudgetWireTests(unittest.TestCase):
    def run_read(self, *, payload=b'abcdefgh', hint=None, allowance=8, cancel=False):
        from c64u_ftp_server import FakeC64UFtp
        import test_ftp_reads as reads
        from c64u_browser.import_plan import SourceBudget,SourceBudgetError
        from c64u_browser.native_files import read_remote_game
        fixture=reads.ReadMigrationTests();self.addCleanup(fixture.doCleanups)
        budget=SourceBudget(allowance)
        if cancel:
            consume=budget.consume
            def canceled(amount):consume(amount);raise JobCancelled()
            budget.consume=canceled
        directories={b'/':b'type=dir; USB1\r\n',b'/USB1':b'type=file; a.crt\r\n'}
        def override(verb,path):
            if hint is not None and verb==b'SIZE' and path==b'/USB1/a.crt':
                return b'213 '+str(hint).encode()+b'\r\n'
        files={b'/USB1/a.crt':payload}
        with FakeC64UFtp(files=files,directories=directories,before_command=override) as server:
            core,_=fixture.connect(server)
            try:
                result=read_remote_game(core._client,'/USB1/a.crt',64*1024*1024,budget=budget)
                error=None
            except Exception as exc:result=None;error=exc
            self.assertEqual(0,core._ftp_manager.active_count)
            self.assertFalse({b'STOR',b'MKD',b'DELE',b'RMD',b'RNFR',b'RNTO'} & set(server.verbs))
            self.assertEqual(files,server.files)
            self.assertFalse(core.game_library.path.exists())
            return budget,result,error,tuple(server.verbs)

    def test_known_remote_size_rejected_before_retr(self):
        from c64u_browser.import_plan import SourceBudgetError
        budget,result,error,verbs=self.run_read(allowance=7)
        self.assertIsInstance(error,SourceBudgetError);self.assertIsNone(result)
        self.assertNotIn(b'RETR',verbs);self.assertEqual(0,budget.consumed)

    def test_underreported_remote_size_stops_at_budget_without_full_buffer(self):
        from c64u_browser.import_plan import SourceBudgetError
        budget,result,error,verbs=self.run_read(payload=b'x'*32768,hint=1,allowance=10)
        self.assertIsInstance(error,SourceBudgetError);self.assertIsNone(result)
        self.assertEqual(10,budget.consumed)
        self.assertEqual('import-source-budget',error.code)

    def test_underreported_size_failure_still_charges_payload(self):
        budget,result,error,verbs=self.run_read(hint=1,allowance=100)
        self.assertIsNotNone(error);self.assertIsNone(result)
        self.assertEqual(8,budget.consumed)

    def test_exact_remote_limit_and_eof_succeed(self):
        budget,result,error,verbs=self.run_read()
        self.assertIsNone(error);self.assertEqual(b'abcdefgh',result)
        self.assertEqual(8,budget.consumed)

    def test_cancellation_during_budgeted_payload_releases_lease(self):
        budget,result,error,verbs=self.run_read(cancel=True)
        self.assertIsInstance(error,JobCancelled);self.assertIsNone(result)
        self.assertEqual(8,budget.consumed)

    def test_core_budget_failure_has_no_partial_plan_or_catalog_changes(self):
        f=ImportCoreTests();f.setUp();self.addCleanup(f.doCleanups)
        before=f.core.preferences.path.read_bytes()
        with patch('c64u_browser.import_plan.MAX_SOURCE_BYTES',len(crt_bytes())*2-1):
            result=f.run_plan()
        self.assertEqual('failed',result.state)
        self.assertEqual('import-source-budget',result.error.code)
        self.assertIsNone(result.result)
        self.assertEqual(before,f.core.preferences.path.read_bytes())
        self.assertFalse(f.core.game_library.path.exists())

    def test_core_remote_stream_budget_failure_has_no_ready_plan(self):
        from c64u_ftp_server import FakeC64UFtp
        import test_ftp_reads as reads
        fixture=reads.ReadMigrationTests();self.addCleanup(fixture.doCleanups)
        root=PATH.encode()
        directories={b'/':b'type=dir; SD\r\ntype=dir; USB1\r\n',
            b'/SD':b'type=dir; ARGONAUT_LIBRARY\r\n',b'/USB1':b'type=file; a.crt\r\n',
            root:b'type=file; manifest.json\r\ntype=dir; games\r\ntype=dir; metadata\r\ntype=dir; artwork\r\n',
            root+b'/games':b'',root+b'/metadata':b'',root+b'/artwork':b''}
        files={root+b'/manifest.json':manifest(),b'/USB1/a.crt':crt_bytes()}
        def hint(verb,path):
            if verb==b'SIZE' and path==b'/USB1/a.crt':return b'213 1\r\n'
        with FakeC64UFtp(files=files,directories=directories,before_command=hint) as server:
            core,_=fixture.connect(server);session=core.device_session()
            library=parse_manifest(manifest(),session.device_id,PATH)
            core.configure_game_library(PATH,identity=library.identity,expected_session=session)
            before=core.preferences.path.read_bytes()
            source=PickerSelection('c64u','/USB1/a.crt','a.crt','/USB1',session.device_id,session.session_id,'games','file')
            with patch('c64u_browser.import_plan.MAX_SOURCE_BYTES',10):
                result=core.prepare_managed_import((source,),library,session).wait(5)
            self.assertEqual('failed',result.state)
            self.assertEqual('import-source-budget',result.error.code)
            self.assertIn('10 of 10 bytes consumed',result.error.message)
            self.assertIsNone(result.result)
            self.assertEqual(0,core._ftp_manager.active_count)
            self.assertEqual(files,server.files)
            self.assertFalse({b'STOR',b'MKD',b'DELE',b'RMD',b'RNFR',b'RNTO'} & set(server.verbs))
            self.assertEqual(before,core.preferences.path.read_bytes())
            self.assertFalse(core.game_library.path.exists())
