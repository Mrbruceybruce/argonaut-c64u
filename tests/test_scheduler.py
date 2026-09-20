# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
import time
import unittest

from c64u_browser.api import BrowserError
from c64u_browser.jobs import CoreJob, JobProgress
from c64u_browser.scheduler import CoreScheduler, DeviceSession, JobBinding


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.session=DeviceSession('device-a','session-1')
        self.scheduler=CoreScheduler(lambda:self.session)
        self.addCleanup(self.scheduler.close)

    def device(self):return JobBinding.device(self.session)

    def test_conflicting_jobs_are_fifo_and_failure_does_not_corrupt_lane(self):
        gate=Event();started=Event();order=[]
        def first(_):
            order.append('first-start');started.set();gate.wait(2)
            order.append('first-end');raise RuntimeError('private')
        one=self.scheduler.submit(CoreJob('one',first),self.device())
        self.assertTrue(started.wait(1))
        two=self.scheduler.submit(CoreJob('two',lambda _:order.append('two')),self.device())
        self.assertEqual('queued',two.snapshot().state)
        self.assertEqual('device-a',two.snapshot().device_id)
        self.assertEqual('session-1',two.snapshot().session_id)
        gate.set()
        self.assertEqual('failed',one.wait(2).state)
        self.assertEqual('succeeded',two.wait(2).state)
        self.assertEqual(['first-start','first-end','two'],order)

    def test_queued_cancellation_never_runs_task(self):
        gate=Event();started=Event();ran=[]
        first=self.scheduler.submit(CoreJob('first',lambda _:(started.set(),gate.wait(2))),self.device())
        self.assertTrue(started.wait(1))
        second=self.scheduler.submit(CoreJob('second',lambda _:ran.append(True)),self.device())
        self.assertTrue(self.scheduler.cancel(second.id));gate.set();first.wait(2)
        self.assertEqual('cancelled',second.wait(2).state);self.assertFalse(ran)

    def test_running_and_late_cancellation_semantics(self):
        entered=Event();release=Event()
        def cooperative(job):
            entered.set();release.wait(2);job.check_cancel()
        running=self.scheduler.submit(CoreJob('running',cooperative),self.device())
        self.assertTrue(entered.wait(1));self.assertTrue(self.scheduler.cancel(running.id))
        release.set();self.assertEqual('cancelled',running.wait(2).state)

        def consequential(job):
            result={'published':True};job.request_cancel();return result
        late=self.scheduler.submit(CoreJob('late',consequential),self.device()).wait(2)
        self.assertEqual('succeeded',late.state)
        self.assertEqual({'published':True},late.result)

    def test_session_or_device_change_rejects_queued_work_and_new_session_runs(self):
        gate=Event();entered=Event();ran=[]
        old=self.device()
        first=self.scheduler.submit(CoreJob('first',lambda _:(entered.set(),gate.wait(2))),old)
        self.assertTrue(entered.wait(1))
        stale=self.scheduler.submit(CoreJob('stale',lambda _:ran.append('stale')),old)
        self.session=DeviceSession('device-a','session-2')
        fresh=self.scheduler.submit(CoreJob('fresh',lambda _:ran.append('fresh')),self.device())
        gate.set();first.wait(2)
        self.assertEqual('failed',stale.wait(2).state)
        self.assertEqual('session',stale.snapshot().error.code)
        self.assertEqual('succeeded',fresh.wait(2).state)
        self.assertEqual(['fresh'],ran)

        gate=Event();entered=Event();self.session=DeviceSession('device-a','session-3')
        first=self.scheduler.submit(CoreJob('first',lambda _:(entered.set(),gate.wait(2))),self.device())
        self.assertTrue(entered.wait(1));bound=self.scheduler.submit(
            CoreJob('bound',lambda _:ran.append('wrong-device')),self.device())
        self.session=DeviceSession('device-b','session-4');gate.set();first.wait(2)
        self.assertEqual('failed',bound.wait(2).state)
        self.assertEqual('device',bound.snapshot().error.code)

    def test_structured_events_and_bounded_completed_retention(self):
        now=[time.time()]
        scheduler=CoreScheduler(lambda:self.session,completed_limit=2,
                                completed_ttl=5,clock=lambda:now[0])
        self.addCleanup(scheduler.close);events=[];jobs=[]
        for number in range(3):
            job=CoreJob('local',lambda current,n=number:(
                current.report(JobProgress('work',n,3)),{'number':n})[1])
            job.add_listener(events.append)
            jobs.append(scheduler.submit(job,JobBinding.core_host()))
            job.wait(2)
        scheduler.cleanup()
        with self.assertRaises(BrowserError):scheduler.job(jobs[0].id)
        json.dumps(events[-1].as_dict())
        self.assertEqual('core-host',jobs[-1].snapshot().lane)
        now[0]+=6;scheduler.cleanup()
        with self.assertRaises(BrowserError):scheduler.job(jobs[-1].id)

    def test_cleanup_never_removes_active_work(self):
        scheduler=CoreScheduler(lambda:self.session,completed_limit=0,
                                completed_ttl=0)
        self.addCleanup(scheduler.close);gate=Event();entered=Event()
        running=scheduler.submit(CoreJob('active',lambda _:(entered.set(),gate.wait(2))),self.device())
        self.assertTrue(entered.wait(1))
        queued=scheduler.submit(CoreJob('queued',lambda _:'done'),self.device())
        scheduler.cleanup()
        self.assertEqual('running',scheduler.job(running.id).state)
        self.assertEqual('queued',scheduler.job(queued.id).state)
        gate.set();running.wait(2);queued.wait(2)

    def test_import_is_headless(self):
        root=str(Path(__file__).resolve().parents[1]);env=dict(os.environ)
        env.pop('DISPLAY',None);env.pop('WAYLAND_DISPLAY',None)
        code=("import sys; import c64u_browser.scheduler, c64u_browser.file_service; "
              "assert 'gi.repository.Gtk' not in sys.modules")
        result=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,
                              capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr)


if __name__=='__main__':unittest.main()
