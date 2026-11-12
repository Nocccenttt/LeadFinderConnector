"""Removing saved leads uses temporary folders and never calls external services."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import preview_dashboard as dashboard


class LeadDeletionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.handoffs = self.root / 'codex_handoffs'
        for name, value in [('ROOT', self.root), ('HANDOFFS', self.handoffs), ('jobs', {})]:
            replacement = patch.object(dashboard, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.alpha = self.business('HIGH', 'Alpha #1 & Care')
        self.beta = self.business('MEDIUM', 'Beta Plumbing')
        self.low = self.business('LOW', 'Low score café')
        self.client = dashboard.app.test_client()
        self.headers = {'X-Workspace-Token': self.client.get('/session').get_json()['workspace_token']}

    def business(self, priority, name):
        folder = self.handoffs / priority / name
        (folder / 'website').mkdir(parents=True)
        (folder / 'business.json').write_text(json.dumps({'business_name': name, 'opportunity_score': 80}), encoding='utf-8')
        (folder / 'AI_HANDOFF.json').write_text('{}', encoding='utf-8')
        for name, content in [('index.html', '<h1>Saved website</h1>'), ('styles.css', 'body{}'), ('script.js', '// saved')]:
            (folder / 'website' / name).write_text(content, encoding='utf-8')
        return folder

    def identity(self, folder):
        return {'priority': folder.parent.name, 'name': folder.name}

    def delete(self, *folders):
        return self.client.post('/delete-leads', json={'leads': [self.identity(folder) for folder in folders]}, headers=self.headers)

    def listed(self):
        return {lead['name'] for lead in self.client.get('/leads').get_json()['leads']}

    def archived(self, folder):
        return list((self.root / 'outputs' / 'deleted_leads').glob(f'*/{folder.parent.name}/{folder.name}'))

    def test_removal_persists_on_refresh_and_keeps_website_files_and_other_data(self):
        before = {path.relative_to(self.alpha): path.read_bytes() for path in self.alpha.rglob('*') if path.is_file()}
        (self.root / 'outputs').mkdir()
        export = self.root / 'outputs' / 'previous-export.csv'
        export.write_text('previous export', encoding='utf-8')
        settings = self.root / '.env'
        settings.write_text('TEST_ONLY=dummy', encoding='utf-8')
        response = self.delete(self.alpha)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['deleted_count'], 1)
        self.assertEqual(response.get_json()['deleted'], [self.identity(self.alpha)])
        self.assertFalse(self.alpha.exists())
        self.assertEqual(self.listed(), {self.beta.name, self.low.name})
        archived = self.archived(self.alpha)
        self.assertEqual(len(archived), 1)
        self.assertEqual({path.relative_to(archived[0]): path.read_bytes() for path in archived[0].rglob('*') if path.is_file()}, before)
        self.assertEqual(export.read_text(encoding='utf-8'), 'previous export')
        self.assertEqual(settings.read_text(encoding='utf-8'), 'TEST_ONLY=dummy')
        with self.client.get('/export') as response:
            self.assertNotIn(self.alpha.name, response.get_data(as_text=True))
            self.assertIn(self.beta.name, response.get_data(as_text=True))
        with patch.object(dashboard, 'Thread') as thread:
            response = self.client.post('/generate-landing-page', json=self.identity(self.alpha))
        self.assertEqual(response.status_code, 404)
        thread.assert_not_called()

    def test_clear_list_removes_all_supplied_priorities(self):
        response = self.delete(self.alpha, self.beta, self.low)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['deleted_count'], 3)
        data = self.client.get('/leads').get_json()
        self.assertEqual({key: data[key] for key in ('total', 'ready', 'high', 'medium', 'low')}, dict.fromkeys(('total', 'ready', 'high', 'medium', 'low'), 0))
        for folder in (self.alpha, self.beta, self.low):
            self.assertEqual(len(self.archived(folder)), 1)

    def test_clear_snapshot_does_not_remove_new_or_unselected_businesses(self):
        snapshot = [self.identity(folder) for folder in (self.alpha, self.beta, self.low)]
        later = self.business('HIGH', 'Added after confirmation opened')
        response = self.client.post('/delete-leads', json={'leads': snapshot}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.listed(), {later.name})

    def test_requires_current_token_local_host_and_same_origin(self):
        payload = {'leads': [self.identity(self.alpha)]}
        attempts = [
            {},
            {'headers': {'X-Workspace-Token': 'stale-token'}},
            {'headers': self.headers, 'base_url': 'http://other-host.invalid'},
            {'headers': {**self.headers, 'Origin': 'https://other-origin.invalid'}},
            {'headers': {**self.headers, 'Origin': 'null'}},
        ]
        for options in attempts:
            with self.subTest(options=options):
                self.assertEqual(self.client.post('/delete-leads', json=payload, **options).status_code, 403)
                self.assertTrue(self.alpha.exists())
        response = self.client.post('/delete-leads', json=payload, headers={**self.headers, 'Origin': 'http://localhost'})
        self.assertEqual(response.status_code, 200)

    def test_session_token_is_not_cached(self):
        response = self.client.get('/session')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.get_json()['workspace_token'], self.headers['X-Workspace-Token'])

    def test_invalid_or_duplicate_batch_does_not_remove_valid_first_item(self):
        valid = self.identity(self.alpha)
        invalid = [None, {}, [], {'leads': []}, {'leads': 'all'},
                   {'leads': [valid, valid]}, {'leads': [valid, None]},
                   {'leads': [valid, {'priority': 'HIGH', 'name': '../Beta Plumbing'}]},
                   {'leads': [valid, {'priority': 'HIGH', 'name': 'folder\\child'}]},
                   {'leads': [valid, {'priority': 'HIGH', 'name': 'C:somewhere'}]},
                   {'leads': [valid, {'priority': 'HIGH', 'name': '\0'}]},
                   {'leads': [valid, {'priority': 'OTHER', 'name': 'Unknown'}]},
                   {'leads': [valid, {'priority': [], 'name': 'Unknown'}]}]
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.client.post('/delete-leads', json=payload, headers=self.headers)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(self.alpha.exists())
        self.assertFalse((self.root / 'outputs').exists())

    def test_stale_selection_aborts_entire_batch(self):
        response = self.client.post('/delete-leads', json={'leads': [self.identity(self.alpha), {'priority': 'HIGH', 'name': 'Missing'}]}, headers=self.headers)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(self.alpha.exists())
        self.assertFalse((self.root / 'outputs').exists())

    def test_active_search_blocks_deletion_for_all_priorities(self):
        for status in ('queued', 'running'):
            with self.subTest(status=status):
                dashboard.jobs['search'] = {'kind': 'leads', 'status': status}
                self.assertEqual(self.delete(self.alpha, self.low).status_code, 409)
                self.assertTrue(self.alpha.exists())
                self.assertTrue(self.low.exists())

    def test_active_target_build_blocks_entire_batch(self):
        with patch.object(dashboard, 'Thread'):
            self.assertEqual(self.client.post('/generate-landing-page', json=self.identity(self.beta)).status_code, 200)
        self.assertEqual(self.delete(self.alpha, self.beta).status_code, 409)
        self.assertTrue(self.alpha.exists())
        self.assertTrue(self.beta.exists())

    def test_other_business_build_does_not_block_removing_unrelated_lead(self):
        with patch.object(dashboard, 'Thread'):
            self.client.post('/generate-landing-page', json=self.identity(self.beta))
        self.assertEqual(self.delete(self.alpha).status_code, 200)
        self.assertTrue(self.beta.exists())

    def test_completed_or_failed_jobs_do_not_block_deletion(self):
        dashboard.jobs.update({'search': {'kind': 'leads', 'status': 'complete'},
                               'build': {'kind': 'website', 'status': 'error', 'client': str(self.alpha)}})
        self.assertEqual(self.delete(self.alpha).status_code, 200)

    def symlink(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'Directory symlinks are unavailable: {error}')

    def test_sibling_alias_and_outside_symlink_cannot_remove_their_targets(self):
        alias = self.alpha.parent / 'Alias'
        self.symlink(alias, self.alpha)
        outside = self.root / 'unrelated'
        outside.mkdir()
        (outside / 'business.json').write_text('{}', encoding='utf-8')
        outside_alias = self.alpha.parent / 'Outside alias'
        self.symlink(outside_alias, outside)
        for folder in (alias, outside_alias):
            with self.subTest(folder=folder.name):
                self.assertEqual(self.delete(folder).status_code, 404)
                self.assertTrue(self.alpha.exists())
                self.assertTrue(outside.exists())
        self.assertFalse((self.root / 'outputs').exists())

    def test_linked_priority_folder_cannot_remove_a_different_priority(self):
        empty = self.handoffs / 'LOW'
        self.low.rename(self.root / self.low.name)
        empty.rmdir()
        self.symlink(empty, self.handoffs / 'HIGH')
        self.assertEqual(self.delete(empty / self.alpha.name).status_code, 404)
        self.assertTrue(self.alpha.exists())

    def test_redirected_archive_directory_is_rejected(self):
        outside = self.root / 'unrelated'
        outside.mkdir()
        (self.root / 'outputs').mkdir()
        self.symlink(self.root / 'outputs' / 'deleted_leads', outside)
        self.assertEqual(self.delete(self.alpha).status_code, 409)
        self.assertTrue(self.alpha.exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_failed_move_restores_earlier_moves_and_keeps_all_files(self):
        rename = Path.rename
        def fail_second(folder, target):
            if folder == self.beta:
                raise PermissionError('simulated file in use')
            return rename(folder, target)
        with patch.object(Path, 'rename', fail_second):
            response = self.delete(self.alpha, self.beta)
        self.assertEqual(response.status_code, 500)
        self.assertIn('No businesses were removed', response.get_json()['error'])
        self.assertEqual(self.listed(), {self.alpha.name, self.beta.name, self.low.name})
        self.assertEqual((self.alpha / 'website' / 'index.html').read_text(), '<h1>Saved website</h1>')

    def test_rollback_failure_keeps_files_and_reports_partial_removal(self):
        rename = Path.rename
        def fail_second_and_restore(folder, target):
            if folder == self.beta or Path(target) == self.alpha:
                raise PermissionError('simulated file in use')
            return rename(folder, target)
        with patch.object(Path, 'rename', fail_second_and_restore):
            response = self.delete(self.alpha, self.beta)
        self.assertEqual(response.status_code, 500)
        self.assertIn('Some businesses remain in outputs/deleted_leads', response.get_json()['error'])
        self.assertTrue(self.beta.exists())
        self.assertEqual((self.archived(self.alpha)[0] / 'website' / 'index.html').read_text(), '<h1>Saved website</h1>')


if __name__ == '__main__':
    unittest.main()
