import json
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from job_store import save_jobs, load_jobs
from preview_dashboard import write_lead_workflow
from test_dashboard import WorkspaceFixture
from unittest.mock import patch
import preview_dashboard as dashboard


class JobRecoveryTests(unittest.TestCase):
    def test_restart_restores_previous_website_and_keeps_interrupted_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'codex_handoffs/HIGH/Example'
            backup = folder / '.build-backup-test'
            (backup / 'website').mkdir(parents=True)
            (backup / 'website/index.html').write_text('Previous working website')
            (backup / 'checkpoint.json').write_text(json.dumps({'website': True, 'GENERATED_COPY.json': False}))
            (folder / 'website').mkdir()
            (folder / 'website/index.html').write_text('Interrupted partial build')
            save_jobs(root, {'build': {'kind': 'website', 'status': 'running', 'priority': 'HIGH', 'client_id': 'Example'}})
            self.assertTrue(load_jobs(root)['build']['interrupted'])
            self.assertEqual((folder / 'website/index.html').read_text(), 'Previous working website')
            self.assertEqual(next(backup.glob('interrupted-website-*/index.html')).read_text(), 'Interrupted partial build')
            load_jobs(root)
            self.assertEqual((folder / 'website/index.html').read_text(), 'Previous working website')

    def test_restart_marks_only_unfinished_work_interrupted_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_jobs(root, {'active': {'kind': 'website', 'status': 'running', 'client_id': 'Example',
                                      'priority': 'HIGH', 'api_key': 'private-key'},
                             'done': {'kind': 'leads', 'status': 'complete'},
                             'failed': {'kind': 'social', 'status': 'error'}})
            self.assertNotIn('private-key', (root / 'outputs/workspace-jobs.json').read_text())
            recovered = load_jobs(root)
            self.assertEqual(set(recovered), {'active', 'done', 'failed'})
            self.assertEqual(recovered['done']['status'], 'complete')
            self.assertNotIn('interrupted', recovered['failed'])
            self.assertEqual(recovered['active']['status'], 'error')
            self.assertTrue(recovered['active']['interrupted'])
            save_jobs(root, recovered)
            self.assertTrue(load_jobs(root)['active']['interrupted'])

    def test_simultaneous_followup_saves_are_complete_and_leave_no_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            drafts = [{'notes': str(index) * 100, 'status': 'NEW', 'follow_up_date': ''} for index in range(12)]
            with ThreadPoolExecutor(max_workers=6) as workers:
                list(workers.map(lambda draft: write_lead_workflow(folder, draft), drafts))
            self.assertIn(json.loads((folder / 'lead_workflow.json').read_text()), drafts)
            self.assertEqual([p.name for p in folder.iterdir()], ['lead_workflow.json'])


class BuildAdmissionTests(WorkspaceFixture):
    def test_third_build_waits_and_can_start_after_a_slot_finishes(self):
        with patch.object(dashboard, 'Thread') as thread:
            for folder in (self.alpha, self.beta):
                response = self.client.post('/generate-landing-page', json={'priority': folder.parent.name, 'name': folder.name})
                self.assertEqual(response.status_code, 200)
            response = self.client.post('/generate-landing-page', json={'priority': 'HIGH', 'name': self.gamma.name})
            self.assertEqual(response.status_code, 409)
            self.assertIn('Two website builds', response.get_json()['error'])
            self.assertEqual(thread.call_count, 2)
            next(iter(dashboard.jobs.values()))['status'] = 'complete'
            self.assertEqual(self.client.post('/generate-landing-page', json={'priority': 'HIGH', 'name': self.gamma.name}).status_code, 200)
