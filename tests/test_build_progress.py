from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from test_dashboard import WorkspaceFixture
from build_progress import observe_build, stage
import preview_dashboard as dashboard


class BuildProgressTests(WorkspaceFixture):
    def test_simultaneous_builds_report_only_their_own_progress(self):
        barrier = Barrier(2)
        def build(name):
            events = []
            with observe_build(lambda phase, message: events.append((phase, message))):
                barrier.wait()
                stage('research', name)
                stage('design', name)
            stage('validation', 'outside observer')
            return events
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(build, ['Alpha', 'Beta']))
        self.assertEqual(results, [[('research', 'Alpha'), ('design', 'Alpha')],
                                   [('research', 'Beta'), ('design', 'Beta')]])

    def test_failure_keeps_actual_stage_and_finish_time(self):
        def build(folder):
            stage('research', 'Researching reference websites')
            stage('copy', 'Writing copy')
            raise RuntimeError('Provider unavailable')
        with patch.object(dashboard, 'run_pipeline', side_effect=build):
            dashboard.run_landing_page('failed-stage', self.alpha)
        job = self.client.get('/landing-page-status?job_id=failed-stage').get_json()
        self.assertEqual((job['status'], job['phase']), ('error', 'copy'))
        self.assertGreaterEqual(job['finished_at'], job['started_at'])
