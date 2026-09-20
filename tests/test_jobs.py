# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

from c64u_browser.jobs import CoreJob, JobProgress


class JobTests(unittest.TestCase):
    def test_success_progress_events_and_serializable_snapshot(self):
        events=[]
        def task(job):
            job.report(JobProgress('copy',2,4,'files','Copied 2 of 4'))
            return {'paths':['a','b']}
        job=CoreJob('file.copy',task);job.add_listener(events.append)
        result=job.run()
        self.assertEqual('succeeded',result.state)
        self.assertEqual({'paths':['a','b']},result.result)
        self.assertEqual(['started','progress','finished'],[e.kind for e in events])
        self.assertEqual('Copied 2 of 4',result.progress.message)
        json.dumps(result.as_dict())

    def test_pending_cancellation_is_explicit(self):
        task_ran=[];job=CoreJob('file.copy',lambda _:task_ran.append(True))
        self.assertTrue(job.request_cancel())
        result=job.run()
        self.assertEqual('cancelled',result.state)
        self.assertEqual('cancelled',result.error.code)
        self.assertFalse(task_ran)
        self.assertFalse(job.request_cancel())

    def test_late_request_does_not_relabel_completed_consequence(self):
        def task(job):
            # Model a request arriving after an indivisible publication step.
            job.request_cancel()
            return {'published':True}
        result=CoreJob('file.publish',task).run()
        self.assertEqual('succeeded',result.state)
        self.assertEqual({'published':True},result.result)

    def test_unexpected_failure_is_sanitized(self):
        job=CoreJob('file.copy',lambda _:(_ for _ in ()).throw(
            RuntimeError('private implementation detail')))
        result=job.run()
        self.assertEqual('failed',result.state)
        self.assertEqual('internal',result.error.code)
        self.assertNotIn('private implementation',result.error.message)

    def test_broken_client_listener_cannot_change_job_outcome(self):
        job=CoreJob('file.copy',lambda _:'complete')
        job.add_listener(lambda _event:(_ for _ in ()).throw(RuntimeError('UI failed')))
        self.assertEqual('succeeded',job.run().state)


if __name__=='__main__':unittest.main()
