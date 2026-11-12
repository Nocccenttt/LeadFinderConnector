"""Current-file QA, explicit review, and honest download contracts."""
import json
from urllib.parse import quote
from unittest.mock import patch

import preview_dashboard as dashboard
from test_dashboard import WorkspaceFixture
from website_status import website_snapshot, website_status


def passing_report(folder):
    report = {'status': 'PASS', 'checks': {'html': {'status': 'PASS', 'issues': []}},
              'warnings': [], 'website_fingerprint': website_snapshot(folder)['fingerprint']}
    output = folder / 'quality_report.json'
    output.write_text(json.dumps(report), encoding='utf-8')
    return output


class WebsiteReviewTests(WorkspaceFixture):
    def post(self, endpoint, **extra):
        return self.client.post(endpoint, json={'priority': 'HIGH', 'name': self.alpha.name, **extra},
                                headers={'X-Workspace-Token': dashboard.settings_token})

    def approve(self):
        info = website_status(self.alpha)
        return self.post('/delivery-review', action='approve', fingerprint=info['fingerprint'],
                         qa_report_hash=info['qa_report_hash'])

    def test_files_and_legacy_qa_never_imply_review(self):
        info = website_status(self.alpha)
        self.assertEqual(info['state'], 'draft')
        self.assertTrue(info['can_download_draft'])
        self.assertFalse(info['can_review'])
        report = passing_report(self.alpha)
        data = json.loads(report.read_text())
        data.pop('website_fingerprint')
        report.write_text(json.dumps(data))
        info = website_status(self.alpha)
        self.assertEqual((info['state'], info['qa']['status']), ('draft', 'UNVERIFIED'))
        self.assertEqual(self.approve().status_code, 409)

    def test_review_is_explicit_persistent_revocable_and_bound_to_assets(self):
        passing_report(self.alpha)
        self.assertEqual(website_status(self.alpha)['state'], 'qa_passed')
        self.assertEqual(self.approve().get_json()['state'], 'approved')
        lead = next(item for item in self.client.get('/leads').get_json()['leads'] if item['client_id'] == self.alpha.name)
        self.assertEqual((lead['website_state'], lead['delivery_review']), ('approved', 'APPROVED'))
        self.assertIn('reviewed-website.zip', self.client.get(lead['approved_download_url']).headers['Content-Disposition'])
        (self.alpha / 'website' / 'script.js').write_text('console.log("changed")')
        info = website_status(self.alpha)
        self.assertEqual((info['state'], info['qa']['status']), ('draft', 'STALE'))
        self.assertEqual(self.client.get(lead['approved_download_url']).status_code, 409)
        passing_report(self.alpha)
        self.assertEqual(website_status(self.alpha)['state'], 'qa_passed')
        self.assertEqual(self.approve().status_code, 200)
        self.assertEqual(self.post('/delivery-review', action='revoke').get_json()['state'], 'qa_passed')
        self.assertFalse((self.alpha / 'DELIVERY.json').exists())

    def test_review_requires_the_same_qa_result_seen_by_reviewer(self):
        report = passing_report(self.alpha)
        original = website_status(self.alpha)
        data = json.loads(report.read_text())
        data['warnings'] = ['Human review still needed.']
        report.write_text(json.dumps(data))
        response = self.post('/delivery-review', action='approve', fingerprint=original['fingerprint'],
                             qa_report_hash=original['qa_report_hash'])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.approve().status_code, 200)
        data['warnings'] = []
        report.write_text(json.dumps(data))
        self.assertEqual(website_status(self.alpha)['state'], 'qa_passed')

    def test_false_pass_failed_build_and_busy_build_cannot_be_reviewed(self):
        report = passing_report(self.alpha)
        data = json.loads(report.read_text())
        data['checks']['html']['status'] = 'FAIL'
        report.write_text(json.dumps(data))
        self.assertFalse(website_status(self.alpha)['qa_passed'])
        passing_report(self.alpha)
        (self.alpha / 'STATUS.json').write_text('{"status":"FAILED"}')
        self.assertEqual(website_status(self.alpha)['state'], 'needs_attention')
        self.assertEqual(self.approve().status_code, 409)
        dashboard.jobs['busy'] = {'kind': 'website', 'status': 'running', 'client': str(self.alpha)}
        self.assertEqual(self.post('/validate-website').status_code, 409)
        self.assertEqual(self.approve().status_code, 409)
        self.assertEqual(self.client.get('/download-demo/HIGH/' + quote(self.alpha.name, safe='')).status_code, 409)

    def test_local_recheck_keeps_assets_and_requires_new_review(self):
        original = website_snapshot(self.alpha)['fingerprint']
        with patch.object(dashboard, 'validate', side_effect=passing_report) as validate:
            response = self.post('/validate-website')
        validate.assert_called_once_with(self.alpha)
        self.assertEqual(response.get_json()['state'], 'qa_passed')
        self.assertFalse(response.get_json()['approved'])
        self.assertEqual(website_snapshot(self.alpha)['fingerprint'], original)
        self.assertEqual(self.approve().status_code, 200)
        with patch.object(dashboard, 'validate', side_effect=OSError('disk failure')):
            self.assertEqual(self.post('/validate-website').status_code, 500)
        self.assertFalse(website_status(self.alpha)['approved'])
        self.assertEqual(website_snapshot(self.alpha)['fingerprint'], original)

    def test_drafts_download_honestly_while_reviewed_downloads_are_gated(self):
        with dashboard.app.test_request_context():
            info = dashboard.preview_info(self.alpha)
        response = self.client.get(info['download_url'])
        self.assertEqual(response.status_code, 200)
        self.assertIn('DRAFT-website.zip', response.headers['Content-Disposition'])
        self.assertEqual(self.client.get(info['download_url'].replace('kind=draft', 'kind=reviewed')).status_code, 409)
        (self.alpha / 'website' / 'script.js').unlink()
        self.assertFalse(website_status(self.alpha)['can_download_draft'])
        self.assertEqual(self.client.get(info['download_url']).status_code, 409)

    def test_recheck_and_review_require_workspace_token_and_valid_business(self):
        for endpoint in ('/validate-website', '/delivery-review'):
            self.assertEqual(self.client.post(endpoint, json={'priority': 'HIGH', 'name': self.alpha.name}).status_code, 403)
            self.assertEqual(self.post(endpoint, name='../outside').status_code, 404)
            self.assertEqual(self.client.post(endpoint, json=[], headers={'X-Workspace-Token': dashboard.settings_token}).status_code, 400)

    def test_actual_local_validator_records_current_files_without_paid_generation(self):
        response = self.post('/validate-website')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['state'], 'needs_attention')
        report = json.loads((self.alpha / 'quality_report.json').read_text())
        self.assertEqual(report['website_fingerprint'], website_snapshot(self.alpha)['fingerprint'])
        self.assertTrue(response.get_json()['can_download_draft'])
