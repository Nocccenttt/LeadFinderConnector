"""Workspace contracts and browser flows; builds/searches never call paid services."""
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import preview_dashboard as dashboard


class WorkspaceFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.handoffs = self.root / 'codex_handoffs'
        for key, value in [('ROOT', self.root), ('HANDOFFS', self.handoffs), ('jobs', {})]:
            replacement = patch.object(dashboard, key, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.alpha = self.business('HIGH', 'Alpha #1 & Care', ready=True)
        self.beta = self.business('MEDIUM', 'Beta Plumbing')
        self.gamma = self.business('HIGH', 'Gamma Roofing')
        self.low = self.business('LOW', 'Delta Cafe')
        self.client = dashboard.app.test_client()

    def business(self, priority, name, ready=False):
        folder = self.handoffs / priority / name
        folder.mkdir(parents=True)
        (folder / 'business.json').write_text(json.dumps({'business_name': name,
            'address': '123 Main Street', 'phone': '+1 (919) 555-0100', 'opportunity_score': 90,
            'opportunity_reasons': ['Website needs improvement']}), encoding='utf-8')
        (folder / 'AI_HANDOFF.json').write_text('{}', encoding='utf-8')
        if ready:
            self.website(folder)
        return folder

    def website(self, folder):
        website = folder / 'website'
        website.mkdir(exist_ok=True)
        for name, content in {'index.html': f'<!doctype html><link rel="stylesheet" href="styles.css"><h1>{folder.name}</h1><p>Real saved website content.</p><script src="script.js"></script>',
                              'styles.css': 'body{background:#fff;color:#243c30}h1{font-size:48px}',
                              'script.js': 'document.body.dataset.loaded="yes";'}.items():
            (website / name).write_text(content, encoding='utf-8')


class DashboardContractTests(WorkspaceFixture):
    def test_launcher_can_identify_its_own_workspace(self):
        self.assertEqual(self.client.get('/health').get_json(), {'app': 'leadfinder', 'root': str(self.root.resolve())})

    def info(self, folder):
        return self.client.get('/preview-status', query_string={'priority': folder.parent.name, 'name': folder.name})

    def test_preview_distinguishes_missing_incomplete_ready_and_failed(self):
        info = self.info(self.beta).get_json()
        self.assertEqual((info['state'], info['available']), ('missing', False))
        (self.beta / 'website').mkdir()
        (self.beta / 'website' / 'index.html').write_text('<h1>Partial</h1>')
        info = self.info(self.beta).get_json()
        self.assertEqual((info['state'], info['available']), ('incomplete', False))
        self.assertEqual(set(info['missing_assets']), {'styles.css', 'script.js'})
        self.website(self.beta)
        info = self.info(self.beta).get_json()
        self.assertEqual((info['state'], info['available']), ('draft', True))
        self.assertEqual(info['qa'], {'status': 'NOT RUN', 'checks_passed': 0, 'checks_total': 0, 'issues': []})
        (self.beta / 'quality_report.json').write_text(json.dumps({
            'status': 'PASS',
            'website_fingerprint': dashboard.website_status(self.beta)['fingerprint'],
            'checks': {
                'index.html': 'PASS',
                'html': {'status': 'PASS', 'issues': []},
                'seo': {'status': 'PASS', 'issues': [], 'warnings': []},
            },
            'warnings': [],
        }), encoding='utf-8')
        info = self.info(self.beta).get_json()
        self.assertEqual(info['qa']['status'], 'PASS')
        self.assertEqual((info['qa']['checks_passed'], info['qa']['checks_total']), (3, 3))
        with self.client.get(info['preview_url']) as response:
            self.assertEqual(response.status_code, 200)
        (self.beta / 'STATUS.json').write_text('{"status":"FAILED"}')
        self.assertEqual(self.info(self.beta).get_json()['state'], 'needs_attention')
        (self.beta / 'website' / 'script.js').write_text('')
        self.assertFalse(self.info(self.beta).get_json()['available'])
        self.assertEqual(self.client.get('/preview-status?priority=HIGH&name=../outside').status_code, 404)

    def test_list_reports_build_eligibility_and_complete_packages(self):
        leads = self.client.get('/leads').get_json()
        self.assertEqual((leads['total'], leads['ready'], leads['low']), (4, 0, 1))
        by_name = {lead['name']: lead for lead in leads['leads']}
        self.assertTrue(by_name[self.beta.name]['can_generate'])
        self.assertFalse(by_name[self.low.name]['can_generate'])
        self.assertFalse(by_name[self.beta.name]['demo_ready'])
        with self.client.get(by_name[self.alpha.name]['download_url']) as response:
            with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                self.assertEqual(set(archive.namelist()), {'index.html', 'styles.css', 'script.js'})

    def test_lead_workflow_persists_without_changing_business_source_data(self):
        token = dashboard.settings_token
        original = json.loads((self.beta / 'business.json').read_text(encoding='utf-8'))
        response = self.client.post('/lead-workflow', json={
            'priority': 'MEDIUM',
            'name': self.beta.name,
            'status': 'FOLLOW_UP',
            'follow_up_date': '2026-11-18',
            'notes': 'Called owner. Send redesigned homepage and follow up next week.',
        }, headers={'X-Workspace-Token': token})
        self.assertEqual(response.status_code, 200)
        workflow = response.get_json()['workflow']
        self.assertEqual(workflow['status'], 'FOLLOW_UP')
        self.assertEqual(workflow['follow_up_date'], '2026-11-18')
        self.assertIn('Called owner', workflow['notes'])
        self.assertEqual(json.loads((self.beta / 'business.json').read_text(encoding='utf-8')), original)
        self.assertEqual(json.loads((self.beta / 'lead_workflow.json').read_text(encoding='utf-8')), workflow)
        lead = next(item for item in self.client.get('/leads').get_json()['leads'] if item['name'] == self.beta.name)
        self.assertEqual(lead['workflow'], workflow)

        invalid_status = self.client.post('/lead-workflow', json={
            'priority': 'MEDIUM', 'name': self.beta.name, 'status': 'WON',
        }, headers={'X-Workspace-Token': token})
        self.assertEqual(invalid_status.status_code, 400)
        invalid_date = self.client.post('/lead-workflow', json={
            'priority': 'MEDIUM', 'name': self.beta.name, 'status': 'CONTACTED', 'follow_up_date': 'tomorrow',
        }, headers={'X-Workspace-Token': token})
        self.assertEqual(invalid_date.status_code, 400)
        too_long = self.client.post('/lead-workflow', json={
            'priority': 'MEDIUM', 'name': self.beta.name, 'status': 'NEW', 'notes': 'x' * 5001,
        }, headers={'X-Workspace-Token': token})
        self.assertEqual(too_long.status_code, 400)

    def test_incomplete_build_does_not_report_success(self):
        with patch.object(dashboard, 'run_pipeline', return_value='PASS'):
            dashboard.run_landing_page('incomplete', self.beta)
        response = self.client.get('/landing-page-status?job_id=incomplete').get_json()
        self.assertEqual(response['status'], 'error')
        self.assertNotIn('preview_url', response)

    def test_session_exposes_resumable_jobs_without_credentials(self):
        with patch.object(dashboard, 'Thread'), patch.dict(os.environ, {'GOOGLE_MAPS_API_KEY': 'secret-maps', 'DEEPSEEK_API_KEY': 'secret-model'}):
            website = self.client.post('/generate-landing-page', json={'priority': 'HIGH', 'name': self.alpha.name}).get_json()
            response = self.client.get('/session')
            session = response.get_json()
            jobs = {job['job_id']: job for job in session['active_jobs']}
            self.assertEqual(jobs[website['job_id']]['client_id'], self.alpha.name)
            self.assertEqual(jobs[website['job_id']]['kind'], 'website')
            self.assertNotIn('secret-', response.get_data(as_text=True))
            with dashboard.jobs_lock:
                dashboard.jobs[website['job_id']]['status'] = 'complete'
            search = self.client.post('/generate', json={'niche': 'Roofing', 'area': 'Raleigh'}).get_json()
            response = self.client.get('/session')
            self.assertEqual(response.get_json()['active_jobs'][0]['job_id'], search['job_id'])
            self.assertEqual(response.get_json()['active_jobs'][0]['kind'], 'leads')
        self.assertEqual(session['capabilities'], {'search_configured': True, 'website_configured': True})
        self.assertNotIn('secret-', response.get_data(as_text=True))
        self.assertEqual(session['workspace_id'], self.client.get('/session').get_json()['workspace_id'])

    def test_dashboard_serves_template_script_style_and_local_font(self):
        for url, expected in [('/', b'Find businesses'), ('/static/dashboard.js', b'loadPreview'),
                              ('/static/dashboard.css', b'font-face'), ('/dashboard-font', b'')]:
            with self.client.get(url) as response:
                self.assertEqual(response.status_code, 200, url)
                self.assertIn(expected, response.data)
                self.assertGreater(len(response.data), 100)


@unittest.skipUnless(os.getenv('RUN_BROWSER_TESTS') == '1', 'Enable RUN_BROWSER_TESTS for dashboard browser flows')
class DashboardBrowserTests(WorkspaceFixture):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.runtime = sync_playwright().start()
        cls.browser = cls.runtime.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.runtime.stop()

    def setUp(self):
        super().setUp()
        from werkzeug.serving import make_server, WSGIRequestHandler
        class QuietHandler(WSGIRequestHandler):
            def log_request(self, *args, **kwargs):
                pass
        self.server = make_server('127.0.0.1', 0, dashboard.app, threaded=True, request_handler=QuietHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1000})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.set_default_timeout(6000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.builds, self.statuses = [], {}
        self.page.route('**/session', lambda route: route.fulfill(json={'workspace_id': 'test-workspace',
            'capabilities': {'search_configured': True, 'website_configured': True}, 'active_jobs': []}))
        def build(route):
            payload = route.request.post_data_json
            self.builds.append(payload)
            job_id = str(len(self.builds))
            self.statuses[job_id] = {'status': 'running', 'message': 'Building this business website.'}
            route.fulfill(json={'job_id': job_id})
        def status(route):
            job_id = parse_qs(urlparse(route.request.url).query)['job_id'][0]
            result = self.statuses.get(job_id)
            if result and job_id in dashboard.jobs:
                with dashboard.jobs_lock:
                    dashboard.jobs[job_id]['status'] = result['status']
            if result and job_id.isdigit() and result['status'] in ('complete', 'error'):
                payload = self.builds[int(job_id) - 1]
                folder = self.handoffs / payload['priority'] / payload['name']
                (folder / 'STATUS.json').write_text(json.dumps({'status': 'PASS' if result['status'] == 'complete' else 'FAILED'}))
            route.fulfill(status=200 if result else 404, json=result or {'message': 'Job not found.'})
        self.page.route('**/generate-landing-page', build)
        self.page.route('**/landing-page-status?**', status)
        self.page.goto(f'http://127.0.0.1:{self.server.server_port}')
        self.page.locator('.lead-row').first.wait_for()

    def select(self, folder):
        self.page.locator('.lead-row').filter(has_text=folder.name).click()

    def open_section(self, section):
        summary = self.page.locator(f'#{section}:not([open]) > summary')
        if summary.count():
            summary.click()

    def test_api_settings_can_test_and_replace_keys_without_restart(self):
        import api_settings
        from unittest.mock import Mock
        from playwright.sync_api import expect
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': '', 'GOOGLE_MAPS_API_KEY': '', 'PEXELS_API_KEY': ''}):
            self.page.unroute('**/session')
            self.page.locator('#refresh-button').click()
            self.select(self.beta)
            expect(self.page.locator('#build-button')).to_be_disabled()
            self.page.get_by_role('button', name='API keys', exact=True).click()
            expect(self.page.locator('#save-settings')).to_be_enabled()
            expect(self.page.locator('#key-deepseek')).to_have_attribute('type', 'password')
            self.page.locator('#key-deepseek').fill('test-replacement-1234')
            with patch.object(api_settings.requests, 'request', return_value=Mock(status_code=401)):
                self.page.locator('#test-deepseek').click()
                expect(self.page.locator('#key-result-deepseek')).to_contain_text('rejected this key')
            with patch.object(api_settings.requests, 'request', return_value=Mock(status_code=200, json=lambda: {'data': []})):
                self.page.locator('#test-deepseek').click()
                expect(self.page.locator('#key-result-deepseek')).to_contain_text('accepted this key')
            self.assertFalse((self.root / '.env').exists())
            self.page.locator('#save-settings').click()
            expect(self.page.locator('#settings-message')).to_contain_text('API keys saved')
            expect(self.page.locator('#key-deepseek')).to_have_value('')
            expect(self.page.locator('#key-status-deepseek')).to_contain_text('1234')
            self.page.get_by_role('button', name='Close API settings').click()
            expect(self.page.locator('#build-button')).to_be_enabled()
            self.assertEqual(os.getenv('DEEPSEEK_API_KEY'), 'test-replacement-1234')
            self.page.get_by_role('button', name='API keys', exact=True).click()
            expect(self.page.locator('#key-status-deepseek')).to_contain_text('1234')
            expect(self.page.locator('#key-deepseek')).to_have_value('')
            self.assertNotIn('test-replacement-1234', self.page.locator('body').inner_text())
        self.assertEqual(self.errors, [])

    def test_api_settings_mobile_and_cancel_preserve_saved_keys(self):
        from playwright.sync_api import expect
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-saved-5736'}):
            for width in (800, 390, 320):
                self.page.set_viewport_size({'width': width, 'height': 844})
                self.assertLessEqual(self.page.locator('html').evaluate('(el)=>el.scrollWidth'), width)
                self.page.get_by_role('button', name='API keys', exact=True).click()
                expect(self.page.locator('#key-status-deepseek')).to_contain_text('5736')
                self.page.locator('#key-deepseek').fill('test-unsaved-1234')
                self.page.keyboard.press('Escape')
                expect(self.page.locator('#settings-dialog')).to_be_hidden()
                self.assertEqual(os.getenv('DEEPSEEK_API_KEY'), 'test-saved-5736')
            self.assertFalse((self.root / '.env').exists())

    def test_saved_preview_device_switch_download_filters_and_keyboard(self):
        from playwright.sync_api import expect
        self.select(self.alpha)
        expect(self.page.locator('#frame-stage')).to_be_visible()
        frame = self.page.frame_locator('#preview-frame')
        expect(frame.locator('h1')).to_have_text(self.alpha.name)
        self.assertEqual(frame.locator('html').evaluate('() => innerWidth'), 1440)
        self.page.get_by_role('button', name='Mobile', exact=True).click()
        self.assertEqual(frame.locator('html').evaluate('() => innerWidth'), 390)
        expect(self.page.locator('#contact-links a').first).to_have_attribute('href', 'tel:+19195550100')
        expect(self.page.locator('#selected-reason')).to_contain_text('Website needs improvement')
        with self.page.expect_download() as download:
            self.page.locator('#download-button').click()
        self.assertTrue(download.value.suggested_filename.endswith('.zip'))
        with self.page.expect_download() as export:
            self.page.locator('#export-button').click()
        self.assertEqual(export.value.suggested_filename, 'leadfinder_leads.csv')
        self.assertIn(self.alpha.name, Path(export.value.path()).read_text(encoding='utf-8'))
        self.page.get_by_role('searchbox').fill('Plumbing')
        expect(self.page.locator('.lead-row')).to_have_count(1)
        self.select(self.beta)
        expect(self.page.locator('#preview-title')).to_have_text('No website yet.')
        expect(self.page.locator('#frame-stage')).to_be_hidden()
        expect(self.page.locator('#build-button')).to_be_enabled()
        self.page.get_by_role('searchbox').fill('')
        self.page.locator('.lead-row').first.focus()
        self.page.keyboard.press('End')
        expect(self.page.locator('#selected-name')).to_have_text(self.low.name)
        expect(self.page.locator('#build-button')).to_be_disabled()
        self.assertEqual(self.errors, [])

    def test_website_actions_and_preview_are_visible_before_secondary_details(self):
        from playwright.sync_api import expect
        self.page.set_viewport_size({'width': 1366, 'height': 768})
        self.select(self.beta)
        self.page.evaluate('scrollTo(0,0)')
        expect(self.page.locator('#lead-notes')).to_be_hidden()
        expect(self.page.locator('#scan-socials')).to_be_hidden()
        build = self.page.locator('#build-button').bounding_box()
        preview = self.page.locator('#preview-canvas').bounding_box()
        self.assertGreaterEqual(build['y'], 0)
        self.assertLessEqual(build['y'] + build['height'], 768)
        self.assertLess(preview['y'], 768 - 100)
        expect(self.page.locator('#preview-title')).to_have_text('No website yet.')
        placeholder = self.page.locator('#preview-title').bounding_box()
        self.assertLess(placeholder['y'] + placeholder['height'], 768)
        self.page.get_by_role('button', name='Follow-up', exact=True).click()
        expect(self.page.locator('#lead-notes')).to_be_visible()
        self.page.locator('#lead-notes').fill('Keep this draft while the panel is collapsed.')
        self.page.locator('#workflow-section > summary').click()
        expect(self.page.locator('#lead-notes')).to_be_hidden()
        expect(self.page.locator('#workflow-save-state')).to_have_text('Unsaved changes')
        self.page.get_by_role('button', name='Mobile', exact=True).click()
        self.page.get_by_role('button', name='Follow-up', exact=True).click()
        expect(self.page.locator('#lead-notes')).to_have_value('Keep this draft while the panel is collapsed.')
        self.page.get_by_role('button', name='Socials', exact=True).click()
        expect(self.page.locator('#scan-socials')).to_be_visible()
        self.page.get_by_role('button', name='Why this lead', exact=True).click()
        expect(self.page.locator('#selected-reason')).to_be_visible()
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.locator('#detail-panel').evaluate('(el)=>el.scrollIntoView({block:"start"})')
        mobile_build = self.page.locator('#build-button').bounding_box()
        mobile_preview = self.page.locator('#preview-canvas').bounding_box()
        self.assertLess(mobile_build['y'] + mobile_build['height'], 600)
        self.assertLess(mobile_preview['y'], 650)
        self.assertEqual(self.errors, [])

    def test_advanced_filters_show_active_count_and_clear_together(self):
        from playwright.sync_api import expect
        self.select(self.beta)
        expect(self.page.locator('#website-filter')).to_be_hidden()
        expect(self.page.locator('#lead-sort')).to_be_hidden()
        self.open_section('list-filters')
        self.page.locator('#website-filter').select_option('missing')
        self.page.locator('[data-priority="HIGH"]').click()
        expect(self.page.locator('#filter-count')).to_have_text('2')
        expect(self.page.locator('.lead-row-name')).to_have_text([self.gamma.name])
        self.page.locator('#list-filters > summary').click()
        expect(self.page.locator('#filter-count')).to_be_visible()
        self.open_section('list-filters')
        self.page.locator('#clear-list-filters').click()
        expect(self.page.locator('#filter-count')).to_be_hidden()
        expect(self.page.locator('.lead-row')).to_have_count(4)
        expect(self.page.locator('#website-filter')).to_have_value('ALL')
        expect(self.page.locator('[data-priority="ALL"]')).to_have_attribute('aria-pressed', 'true')
        expect(self.page.locator('#selected-name')).to_have_text(self.beta.name)
        self.assertEqual(self.errors, [])

    def test_followup_summary_filters_badges_and_urgency_sorting(self):
        from datetime import date, timedelta
        from playwright.sync_api import expect

        today = date.today()
        workflows = {
            self.beta: {'status': 'FOLLOW_UP', 'follow_up_date': (today - timedelta(days=3)).isoformat(), 'notes': 'Overdue'},
            self.gamma: {'status': 'CONTACTED', 'follow_up_date': today.isoformat(), 'notes': 'Today'},
            self.low: {'status': 'INTERESTED', 'follow_up_date': (today + timedelta(days=2)).isoformat(), 'notes': 'Upcoming'},
            self.alpha: {'status': 'CLOSED', 'follow_up_date': (today - timedelta(days=10)).isoformat(), 'notes': 'Closed'},
        }
        for folder, workflow in workflows.items():
            (folder / 'lead_workflow.json').write_text(json.dumps(workflow), encoding='utf-8')

        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#followup-needs-count')).to_have_text('3')
        expect(self.page.locator('#followup-overdue-count')).to_have_text('1')
        expect(self.page.locator('#followup-today-count')).to_have_text('1')
        expect(self.page.locator('#followup-upcoming-count')).to_have_text('1')

        self.page.locator('[data-followup-filter="NEEDS"]').click()
        expect(self.page.locator('.lead-row')).to_have_count(3)
        expect(self.page.locator('.lead-row-name')).to_have_text([self.beta.name, self.gamma.name, self.low.name])
        expect(self.page.locator('.followup-overdue')).to_contain_text('3 days overdue')
        expect(self.page.locator('.followup-today')).to_have_text('Due today')
        expect(self.page.locator('.followup-upcoming')).to_contain_text('In 2 days')

        self.page.locator('[data-followup-filter="TODAY"]').click()
        expect(self.page.locator('.lead-row')).to_have_count(1)
        expect(self.page.locator('.lead-row-name')).to_have_text([self.gamma.name])
        self.assertEqual(self.errors, [])

    def test_two_builds_survive_switching_and_reload_without_replacing_selection(self):
        from playwright.sync_api import expect
        self.select(self.beta)
        self.page.locator('#build-button').click()
        expect(self.page.locator('#website-state')).to_have_text('Building website')
        self.select(self.gamma)
        self.page.locator('#build-button').click()
        expect(self.page.locator('.row-website-status.working')).to_have_count(2)
        self.select(self.alpha)
        self.website(self.beta)
        self.statuses['1'] = {'status': 'complete', 'message': 'Ready.'}
        expect(self.page.locator('.row-website-status.working')).to_have_count(1)
        expect(self.page.locator('#selected-name')).to_have_text(self.alpha.name)
        expect(self.page.frame_locator('#preview-frame').locator('h1')).to_have_text(self.alpha.name)
        self.select(self.gamma)
        self.page.reload()
        expect(self.page.locator('#selected-name')).to_have_text(self.gamma.name)
        expect(self.page.locator('#website-state')).to_have_text('Building website')
        self.statuses['2'] = {'status': 'error', 'message': 'Reference provider unavailable. Try again.'}
        expect(self.page.locator('#job-error')).to_contain_text('Reference provider unavailable')
        expect(self.page.locator('#build-button')).to_be_enabled()
        self.open_section('list-filters')
        self.page.locator('#website-filter').select_option('needs_attention')
        expect(self.page.locator('.lead-row')).to_have_count(1)
        expect(self.page.locator('.lead-row')).to_contain_text(self.gamma.name)
        self.open_section('list-filters')
        self.page.locator('#website-filter').select_option('ALL')
        self.select(self.beta)
        expect(self.page.frame_locator('#preview-frame').locator('h1')).to_have_text(self.beta.name)
        self.assertEqual(len(self.builds), 2)
        self.assertEqual(self.errors, [])

    def test_social_profiles_show_public_bios_contacts_sources_and_export(self):
        from playwright.sync_api import expect
        business_file = self.beta / 'business.json'
        business = json.loads(business_file.read_text())
        business.update(email='office@example.test', social_profiles=[{
            'platform': 'instagram', 'url': 'https://instagram.com/example', 'status': 'public',
            'source_url': 'https://business.example/contact', 'observed_at': '2026-11-12T00:00:00Z',
            'details': {'name': 'Example Plumbing', 'description': 'Public plumbing business bio.',
                        'emails': ['hello@example.test'], 'phones': ['+1 555 0100']}}])
        business_file.write_text(json.dumps(business))
        self.enable_list_management()
        self.select(self.beta)
        expect(self.page.locator('#contact-links a[href="mailto:office@example.test"]')).to_be_visible()
        self.open_section('social-section')
        self.page.locator('#social-results-label').click()
        expect(self.page.locator('.social-profile summary a')).to_have_attribute('href', 'https://instagram.com/example')
        self.page.locator('.social-profile summary').click()
        expect(self.page.locator('.social-profile-body')).to_contain_text('Public plumbing business bio.')
        expect(self.page.locator('.social-profile-body a[href="mailto:hello@example.test"]')).to_be_visible()
        expect(self.page.get_by_role('link', name='Discovery source')).to_have_attribute('href', 'https://business.example/contact')
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.assertLessEqual(self.page.locator('html').evaluate('(el)=>el.scrollWidth'), 390)
        self.page.set_viewport_size({'width': 1440, 'height': 1000})
        with self.page.expect_download() as download:
            self.page.locator('#export-button').click()
        import csv
        rows = list(csv.DictReader(Path(download.value.path()).read_text(encoding='utf-8-sig').splitlines()))
        row = next(item for item in rows if item['name'] == self.beta.name)
        self.assertEqual(row['instagram'], 'https://instagram.com/example')
        self.assertEqual(json.loads(row['social_profiles'])[0]['details']['emails'], ['hello@example.test'])
        self.assertEqual(self.errors, [])

    def test_social_scan_survives_selection_reload_and_preserves_unsaved_followup(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        status = {'status': 'running', 'message': 'Checking public Instagram information.'}
        posts = []
        def scan(route):
            posts.append(route.request.post_data_json)
            route.fulfill(json={'job_id': 'social-scan-test'})
        self.page.route('**/social-discovery', scan)
        self.page.route('**/job-status?job_id=social-scan-test', lambda route: route.fulfill(json=status))
        self.select(self.beta)
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('Keep this unsaved call note.')
        self.open_section('social-section')
        self.page.locator('#scan-socials').click()
        expect(self.page.locator('#social-scan-state')).to_have_text('Checking public Instagram information.')
        expect(self.page.locator('#scan-socials')).to_be_disabled()
        expect(self.page.locator('#find-button')).to_be_disabled()
        expect(self.page.locator('#build-button')).to_be_disabled()
        expect(self.page.locator('#delete-business-button')).to_be_disabled()
        self.select(self.gamma)
        expect(self.page.locator('#scan-socials')).to_be_enabled()
        expect(self.page.locator('#social-scan-state')).not_to_contain_text('Checking public Instagram')
        self.select(self.beta)
        self.page.reload()
        expect(self.page.locator('#selected-name')).to_have_text(self.beta.name)
        expect(self.page.locator('#social-scan-state')).to_have_text('Checking public Instagram information.')
        expect(self.page.locator('#lead-notes')).to_have_value('Keep this unsaved call note.')
        business_file = self.beta / 'business.json'
        business = json.loads(business_file.read_text())
        business.update(instagram='https://instagram.com/example', social_profiles=[{
            'platform': 'instagram', 'url': 'https://instagram.com/example', 'status': 'blocked',
            'note': 'Automated access is not allowed by this site.', 'details': {}}])
        business_file.write_text(json.dumps(business))
        status.update(status='complete', message='Found 1 linked profile; access limited.')
        expect(self.page.locator('#scan-socials')).to_be_enabled()
        expect(self.page.locator('#social-results-label')).to_have_text('View 1 social profile')
        expect(self.page.locator('#lead-notes')).to_have_value('Keep this unsaved call note.')
        expect(self.page.locator('#workflow-save-state')).to_have_text('Unsaved changes')
        expect(self.page.locator('#find-button')).to_be_enabled()
        expect(self.page.locator('#build-button')).to_be_enabled()
        self.assertEqual(posts, [{'priority': 'MEDIUM', 'name': self.beta.name}])
        self.assertEqual(self.errors, [])

    def test_failed_social_submission_can_retry_and_recover_an_accepted_scan(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        self.select(self.beta)
        self.page.route('**/social-discovery', lambda route: route.fulfill(status=503, json={'error': 'Social scanner unavailable.'}), times=1)
        self.open_section('social-section')
        self.page.locator('#scan-socials').click()
        expect(self.page.locator('#social-scan-state')).to_contain_text('Social scanner unavailable.')
        expect(self.page.locator('#scan-socials')).to_be_enabled()
        def accepted(route):
            with dashboard.jobs_lock:
                dashboard.jobs['recovered-social'] = {'kind': 'social', 'status': 'running', 'priority': 'MEDIUM',
                    'client_id': self.beta.name, 'client': str(self.beta), 'message': 'Recovered social scan.'}
            route.abort('failed')
        status = {'status': 'running', 'message': 'Recovered social scan.'}
        self.page.route('**/social-discovery', accepted)
        self.page.route('**/job-status?job_id=recovered-social', lambda route: route.fulfill(json=status))
        self.open_section('social-section')
        self.page.locator('#scan-socials').click()
        expect(self.page.locator('#social-scan-state')).to_have_text('Recovered social scan.')
        expect(self.page.locator('#scan-socials')).to_be_disabled()
        status.update(status='error', message='The public page could not be reached. Try again.')
        expect(self.page.locator('#social-scan-state')).to_contain_text('The public page could not be reached.')
        expect(self.page.locator('#scan-socials')).to_be_enabled()
        self.assertEqual(self.errors, [])

    def test_followup_drafts_survive_navigation_device_refresh_and_reload(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        self.select(self.beta)
        self.open_section('workflow-section')
        self.page.locator('#lead-workflow-status').select_option('FOLLOW_UP')
        self.open_section('workflow-section')
        self.page.locator('#lead-follow-up-date').fill('2026-11-18')
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('Ask the owner about the redesigned homepage.')
        expect(self.page.locator('#workflow-save-state')).to_have_text('Unsaved changes')
        self.page.get_by_role('button', name='Mobile', exact=True).click()
        expect(self.page.locator('#lead-notes')).to_have_value('Ask the owner about the redesigned homepage.')

        self.select(self.gamma)
        expect(self.page.locator('#lead-notes')).to_have_value('')
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('Roofing lead has a separate draft.')
        self.select(self.beta)
        expect(self.page.locator('#lead-workflow-status')).to_have_value('FOLLOW_UP')
        expect(self.page.locator('#lead-follow-up-date')).to_have_value('2026-11-18')
        expect(self.page.locator('#lead-notes')).to_have_value('Ask the owner about the redesigned homepage.')
        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#refresh-button')).to_be_enabled()
        expect(self.page.locator('#lead-notes')).to_have_value('Ask the owner about the redesigned homepage.')

        self.page.reload()
        expect(self.page.locator('#selected-name')).to_have_text(self.beta.name)
        expect(self.page.locator('#lead-workflow-status')).to_have_value('FOLLOW_UP')
        expect(self.page.locator('#lead-follow-up-date')).to_have_value('2026-11-18')
        expect(self.page.locator('#lead-notes')).to_have_value('Ask the owner about the redesigned homepage.')
        expect(self.page.locator('#workflow-save-state')).to_have_text('Unsaved changes')
        self.select(self.gamma)
        expect(self.page.locator('#lead-notes')).to_have_value('Roofing lead has a separate draft.')
        self.assertFalse((self.beta / 'lead_workflow.json').exists())
        self.assertFalse((self.gamma / 'lead_workflow.json').exists())
        self.assertEqual(self.errors, [])

    def test_followup_drafts_survive_build_and_search_progress_updates(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        self.select(self.beta)
        self.page.locator('#build-button').click()
        expect(self.page.locator('#website-state')).to_have_text('Building website')
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('Keep this draft while providers are working.')
        self.statuses['1'] = {'status': 'running', 'message': 'Checking the website layout.'}
        expect(self.page.locator('#build-message')).to_have_text('Checking the website layout.')
        expect(self.page.locator('#lead-notes')).to_have_value('Keep this draft while providers are working.')
        self.statuses['1'] = {'status': 'error', 'message': 'Build paused for this test.'}
        expect(self.page.locator('#job-error')).to_contain_text('Build paused for this test.')
        expect(self.page.locator('#lead-notes')).to_have_value('Keep this draft while providers are working.')

        self.page.route('**/generate', lambda route: route.fulfill(json={'job_id': 'draft-search'}))
        self.page.route('**/job-status?job_id=draft-search', lambda route: route.fulfill(json={
            'status': 'running', 'phase': 'Scoring businesses', 'message': 'Checking new prospects.', 'percent': 25}))
        self.page.locator('#find-button').click()
        self.page.locator('#niche').fill('Plumbing')
        self.page.locator('#area').fill('Test City')
        self.page.locator('#search-submit').click()
        expect(self.page.locator('#search-message')).to_have_text('Checking new prospects.')
        expect(self.page.locator('#lead-notes')).to_have_value('Keep this draft while providers are working.')
        expect(self.page.locator('#workflow-save-state')).to_have_text('Unsaved changes')
        self.assertEqual(self.errors, [])

    def test_followup_delayed_save_feedback_stays_with_its_business(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        held = []
        self.page.route('**/lead-workflow', lambda route: held.append(route))
        self.select(self.beta)
        self.open_section('workflow-section')
        self.page.locator('#lead-workflow-status').select_option('FOLLOW_UP')
        self.open_section('workflow-section')
        self.page.locator('#lead-follow-up-date').fill('2026-11-18')
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('Save only the plumbing follow-up.')
        with self.page.expect_request('**/lead-workflow'):
            self.open_section('workflow-section')
            self.page.locator('#save-lead-workflow').click()
        expect(self.page.locator('#workflow-save-state')).to_have_text('Saving…')
        self.select(self.gamma)
        expect(self.page.locator('#workflow-save-state')).to_have_text('')
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('Roofing notes are still unsaved.')

        response = self.client.post('/lead-workflow', json=held[0].request.post_data_json,
                                    headers={'X-Workspace-Token': dashboard.settings_token})
        self.assertEqual(response.status_code, 200)
        held[0].fulfill(json=response.get_json())
        expect(self.page.locator('.lead-row').filter(has_text=self.beta.name).locator('.workflow-chip')).to_have_text('Follow-up')
        expect(self.page.locator('#selected-name')).to_have_text(self.gamma.name)
        expect(self.page.locator('#lead-notes')).to_have_value('Roofing notes are still unsaved.')
        expect(self.page.locator('#workflow-save-state')).to_have_text('Unsaved changes')
        self.select(self.beta)
        expect(self.page.locator('#workflow-save-state')).to_have_text('Saved')
        expect(self.page.locator('#lead-notes')).to_have_value('Save only the plumbing follow-up.')
        expect(self.page.locator('#lead-workflow-status')).to_have_value('FOLLOW_UP')
        expect(self.page.locator('#lead-follow-up-date')).to_have_value('2026-11-18')
        self.assertFalse((self.gamma / 'lead_workflow.json').exists())
        self.assertEqual(len(held), 1)
        self.assertEqual(self.errors, [])

    def test_followup_save_preserves_newer_edits_and_blocks_duplicate_submissions(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        held = []
        self.page.route('**/lead-workflow', lambda route: held.append(route))
        self.select(self.beta)
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('First version sent to the workspace.')
        with self.page.expect_request('**/lead-workflow'):
            self.open_section('workflow-section')
            self.page.locator('#save-lead-workflow').click()
        self.page.get_by_role('button', name='Mobile', exact=True).click()
        expect(self.page.locator('#save-lead-workflow')).to_be_disabled()
        expect(self.page.locator('#save-lead-workflow')).to_have_text('Saving…')
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('Newer edits made while saving.')
        expect(self.page.locator('#save-lead-workflow')).to_be_disabled()
        self.assertEqual(len(held), 1)

        response = self.client.post('/lead-workflow', json=held[0].request.post_data_json,
                                    headers={'X-Workspace-Token': dashboard.settings_token})
        held[0].fulfill(json=response.get_json())
        expect(self.page.locator('#save-lead-workflow')).to_be_enabled()
        expect(self.page.locator('#lead-notes')).to_have_value('Newer edits made while saving.')
        expect(self.page.locator('#workflow-save-state')).to_have_text('Unsaved changes')
        with self.page.expect_request('**/lead-workflow'):
            self.open_section('workflow-section')
            self.page.locator('#save-lead-workflow').click()
        self.assertEqual(held[1].request.post_data_json['notes'], 'Newer edits made while saving.')
        stale_leads = self.client.get('/leads').get_json()
        held_leads = []
        self.page.route('**/leads', lambda route: held_leads.append(route), times=1)
        with self.page.expect_request('**/leads'):
            self.page.locator('#refresh-button').click()
        expect(self.page.locator('#save-lead-workflow')).to_be_disabled()
        response = self.client.post('/lead-workflow', json=held[1].request.post_data_json,
                                    headers={'X-Workspace-Token': dashboard.settings_token})
        held[1].fulfill(json=response.get_json())
        expect(self.page.locator('#workflow-save-state')).to_have_text('Saved')
        held_leads[0].fulfill(json=stale_leads)
        expect(self.page.locator('#refresh-button')).to_be_enabled()
        expect(self.page.locator('#lead-notes')).to_have_value('Newer edits made while saving.')
        expect(self.page.locator('#workflow-save-state')).to_have_text('Saved')
        self.page.reload()
        expect(self.page.locator('#lead-notes')).to_have_value('Newer edits made while saving.')
        self.assertEqual(json.loads((self.beta / 'lead_workflow.json').read_text())['notes'],
                         'Newer edits made while saving.')
        self.assertEqual(len(held), 2)
        self.assertEqual(self.errors, [])

    def test_followup_save_failure_preserves_owner_draft_and_can_be_retried(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        held = []
        self.page.route('**/lead-workflow', lambda route: held.append(route))
        self.select(self.beta)
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('Keep my call notes after a failed save.')
        with self.page.expect_request('**/lead-workflow'):
            self.open_section('workflow-section')
            self.page.locator('#save-lead-workflow').click()
        self.select(self.gamma)
        held[0].fulfill(status=503, json={'error': 'Workspace temporarily unavailable.'})
        expect(self.page.locator('#workflow-save-state')).to_have_text('')
        self.select(self.beta)
        expect(self.page.locator('#lead-notes')).to_have_value('Keep my call notes after a failed save.')
        expect(self.page.locator('#workflow-save-state')).to_contain_text('Workspace temporarily unavailable.')
        expect(self.page.locator('#save-lead-workflow')).to_be_enabled()
        self.page.get_by_role('button', name='Mobile', exact=True).click()
        expect(self.page.locator('#lead-notes')).to_have_value('Keep my call notes after a failed save.')
        expect(self.page.locator('#workflow-save-state')).to_contain_text('Workspace temporarily unavailable.')
        with self.page.expect_request('**/lead-workflow'):
            self.open_section('workflow-section')
            self.page.locator('#save-lead-workflow').click()
        response = self.client.post('/lead-workflow', json=held[1].request.post_data_json,
                                    headers={'X-Workspace-Token': dashboard.settings_token})
        held[1].fulfill(json=response.get_json())
        expect(self.page.locator('#workflow-save-state')).to_have_text('Saved')
        expect(self.page.locator('#lead-notes')).to_have_value('Keep my call notes after a failed save.')
        self.assertEqual(json.loads((self.beta / 'lead_workflow.json').read_text())['notes'],
                         'Keep my call notes after a failed save.')
        self.assertEqual(self.errors, [])

    def test_followup_cleared_draft_survives_reload_after_a_lost_save_reply(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        held = []
        self.page.route('**/lead-workflow', lambda route: held.append(route))
        self.select(self.beta)
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('The server accepts this earlier version.')
        with self.page.expect_request('**/lead-workflow'):
            self.open_section('workflow-section')
            self.page.locator('#save-lead-workflow').click()
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('')
        response = self.client.post('/lead-workflow', json=held[0].request.post_data_json,
                                    headers={'X-Workspace-Token': dashboard.settings_token})
        self.assertEqual(response.status_code, 200)
        self.page.reload()
        expect(self.page.locator('#selected-name')).to_have_text(self.beta.name)
        expect(self.page.locator('#lead-notes')).to_have_value('')
        expect(self.page.locator('#workflow-save-state')).to_have_text('Unsaved changes')
        expect(self.page.locator('#save-lead-workflow')).to_be_enabled()
        self.assertEqual(json.loads((self.beta / 'lead_workflow.json').read_text())['notes'],
                         'The server accepts this earlier version.')
        self.assertEqual(self.errors, [])

    def test_followup_draft_survives_reconnecting_after_initial_session_failure(self):
        from playwright.sync_api import expect
        self.page.unroute('**/session')
        requests = []
        def session(route):
            requests.append(route)
            if len(requests) == 1:
                route.fulfill(status=503, json={'error': 'Session temporarily unavailable.'})
            else:
                data = self.client.get('/session').get_json()
                data.update(workspace_id='test-workspace', capabilities={
                    'search_configured': True, 'website_configured': True})
                route.fulfill(json=data)
        self.page.route('**/session', session)
        self.page.reload()
        expect(self.page.locator('.lead-row')).to_have_count(4)
        self.select(self.beta)
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('Draft written before session recovery.')
        expect(self.page.locator('#save-lead-workflow')).to_be_disabled()
        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#save-lead-workflow')).to_be_enabled()
        expect(self.page.locator('#lead-notes')).to_have_value('Draft written before session recovery.')
        expect(self.page.locator('#workflow-save-state')).to_have_text('Unsaved changes')
        self.assertFalse((self.beta / 'lead_workflow.json').exists())
        self.assertEqual(self.errors, [])

    def test_followup_cleared_draft_survives_reload_before_an_uncertain_save_commits(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        held = []
        self.page.route('**/lead-workflow', lambda route: held.append(route))
        self.select(self.beta)
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('Earlier text whose save outcome is unknown.')
        with self.page.expect_request('**/lead-workflow'):
            self.open_section('workflow-section')
            self.page.locator('#save-lead-workflow').click()
        payload = held[0].request.post_data_json
        self.open_section('workflow-section')
        self.page.locator('#lead-notes').fill('')
        held[0].abort('failed')
        self.page.reload()
        expect(self.page.locator('#selected-name')).to_have_text(self.beta.name)
        expect(self.page.locator('#lead-notes')).to_have_value('')

        response = self.client.post('/lead-workflow', json=payload,
                                    headers={'X-Workspace-Token': dashboard.settings_token})
        self.assertEqual(response.status_code, 200)
        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#refresh-button')).to_be_enabled()
        expect(self.page.locator('#lead-notes')).to_have_value('')
        expect(self.page.locator('#workflow-save-state')).to_have_text('Unsaved changes')
        self.page.unroute('**/lead-workflow')
        self.open_section('workflow-section')
        self.page.locator('#save-lead-workflow').click()
        expect(self.page.locator('#workflow-save-state')).to_have_text('Saved')
        self.assertEqual(json.loads((self.beta / 'lead_workflow.json').read_text())['notes'], '')
        self.assertEqual(self.errors, [])

    def test_redesign_preserves_copy_rejection_recovers_and_rebuild_requires_choice(self):
        from playwright.sync_api import expect
        self.select(self.alpha)
        self.page.route('**/generate-landing-page', lambda route: route.fulfill(status=503, json={'error': 'Build service unavailable.'}), times=1)
        self.page.locator('#redesign-button').click()
        expect(self.page.locator('#job-error')).to_contain_text('Build service unavailable.')
        expect(self.page.locator('#redesign-button')).to_be_enabled()
        self.page.locator('#redesign-button').click()
        expect(self.page.locator('#website-state')).to_have_text('Building website')
        self.assertTrue(self.builds[0]['preserve_content'])
        self.statuses['1'] = {'status': 'complete', 'message': 'Ready.'}
        expect(self.page.locator('#redesign-button')).to_be_enabled()
        self.page.locator('#more-actions summary').click()
        self.page.locator('#rebuild-button').click()
        self.page.locator('#rebuild-dialog').get_by_role('button', name='Cancel', exact=True).click()
        self.assertEqual(len(self.builds), 1)
        self.page.locator('#more-actions summary').click()
        self.page.locator('#rebuild-button').click()
        self.page.locator('#confirm-rebuild').click()
        expect(self.page.locator('#website-state')).to_have_text('Building website')
        self.assertFalse(self.builds[1]['preserve_content'])

    def test_preview_failure_is_visible_and_retry_loads_the_actual_page(self):
        from playwright.sync_api import expect
        self.page.route('**/demo/**', lambda route: route.fulfill(status=500, body='Unavailable'), times=1)
        self.select(self.alpha)
        expect(self.page.locator('#preview-title')).to_have_text('Could not load the preview.')
        self.page.get_by_role('button', name='Try loading again').click()
        expect(self.page.frame_locator('#preview-frame').locator('h1')).to_have_text(self.alpha.name)
        (self.beta / 'website').mkdir()
        (self.beta / 'website' / 'index.html').write_text('<h1>Incomplete</h1>')
        self.select(self.beta)
        expect(self.page.locator('#preview-title')).to_have_text('This website needs a new build.')
        expect(self.page.locator('#preview-description')).to_contain_text('incomplete')
        expect(self.page.locator('#frame-stage')).to_be_hidden()

    def test_late_preview_response_cannot_replace_new_selection(self):
        from playwright.sync_api import expect
        pending = []
        self.page.route('**/preview-status?**', lambda route: pending.append(route), times=1)
        self.select(self.alpha)
        expect(self.page.locator('#preview-title')).to_have_text('Checking the preview…')
        self.select(self.beta)
        expect(self.page.locator('#preview-title')).to_have_text('No website yet.')
        pending[0].fulfill(json={'available': True, 'preview_url': '/demo/HIGH/Alpha%20%231%20%26%20Care/'})
        expect(self.page.locator('#selected-name')).to_have_text(self.beta.name)
        expect(self.page.locator('#frame-stage')).to_be_hidden()
        self.assertEqual(self.errors, [])

    def test_search_form_errors_progress_resume_and_completion(self):
        from playwright.sync_api import expect
        posts = []
        update = {'status': 'running', 'percent': 40, 'phase': 'Inspecting websites', 'total': 5,
                  'current_index': 2, 'high': 1, 'medium': 1, 'low': 0, 'message': 'Checking business details.'}
        def search(route):
            posts.append(route.request.post_data_json)
            route.fulfill(json={'job_id': 'search-1'})
        self.page.route('**/generate', search)
        self.page.route('**/job-status?**', lambda route: route.fulfill(json=update))
        self.page.route('**/generate', lambda route: route.fulfill(status=503, json={'error': 'Search unavailable.'}), times=1)
        self.page.locator('#find-button').click()
        self.page.get_by_label('Business type', exact=True).fill('Roofing')
        self.page.get_by_label('Location', exact=True).fill('Raleigh, NC')
        self.page.locator('#search-submit').click()
        expect(self.page.locator('#search-form-error')).to_have_text('Search unavailable.')
        self.page.locator('#search-submit').click()
        expect(self.page.locator('#search-count')).to_have_text('2 of 5 businesses checked')
        self.assertEqual(posts, [{'niche': 'Roofing', 'area': 'Raleigh, NC', 'max_results': 25}])
        self.page.reload()
        expect(self.page.locator('#search-progress-bar')).to_have_attribute('value', '40')
        expect(self.page.locator('#find-button')).to_be_disabled()
        update.update(status='complete', percent=100, phase='Search complete')
        expect(self.page.locator('#find-button')).to_be_enabled()
        expect(self.page.locator('#search-progress-bar')).to_have_attribute('value', '100')

    def test_lost_build_session_and_list_connection_can_be_retried(self):
        from playwright.sync_api import expect
        self.select(self.beta)
        self.page.locator('#build-button').click()
        expect(self.page.locator('#website-state')).to_have_text('Building website')
        self.statuses.clear()
        expect(self.page.locator('#job-error')).to_contain_text('no longer available')
        expect(self.page.locator('#build-button')).to_be_enabled()
        self.page.route('**/leads', lambda route: route.fulfill(status=503, json={'error': 'Offline.'}), times=1)
        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#workspace-error')).to_contain_text('Offline.')
        self.page.locator('#retry-workspace').click()
        expect(self.page.locator('#workspace-error')).to_be_hidden()
        expect(self.page.locator('#selected-name')).to_have_text(self.beta.name)

    def test_responsive_layout_long_names_and_keyboard_dialog(self):
        from playwright.sync_api import expect
        business = json.loads((self.alpha / 'business.json').read_text())
        business['business_name'] = '<img src=x onerror=alert(1)>' + 'LongName' * 30
        (self.alpha / 'business.json').write_text(json.dumps(business))
        self.page.locator('#refresh-button').click()
        self.page.locator('.lead-row').filter(has_text='<img').click()
        expect(self.page.locator('#selected-name')).to_contain_text('<img')
        self.assertEqual(self.page.locator('#selected-name img').count(), 0)
        for width in (1440, 1280, 1024, 800, 768, 390, 320):
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': 900})
                self.assertLessEqual(self.page.locator('html').evaluate('(el)=>el.scrollWidth'), width)
                self.page.locator('#find-button').click()
                expect(self.page.locator('#niche')).to_be_focused()
                self.assertLessEqual(self.page.locator('#find-dialog').evaluate('(el)=>el.scrollWidth'), width)
                self.page.keyboard.press('Escape')
                expect(self.page.locator('#find-dialog')).to_be_hidden()
        expect(self.page.locator('#business-panel')).to_be_hidden()
        self.page.locator('#back-to-businesses').click()
        expect(self.page.locator('#business-panel')).to_be_visible()
        expect(self.page.locator('#detail-panel')).to_be_hidden()
        self.assertEqual(self.errors, [])

    def enable_list_management(self):
        from playwright.sync_api import expect
        self.page.unroute('**/session')
        def session(route):
            data = self.client.get('/session').get_json()
            data.update(workspace_id='test-workspace', capabilities={
                'search_configured': True, 'website_configured': True})
            route.fulfill(json=data)
        self.page.route('**/session', session)
        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#clear-list-button')).to_be_enabled()

    def test_draft_qa_review_download_and_changed_files_stay_consistent(self):
        from playwright.sync_api import expect
        from test_website_status import passing_report
        self.enable_list_management()
        self.select(self.alpha)
        expect(self.page.locator('#website-state')).to_have_text('Draft — QA not verified')
        expect(self.page.locator('#saved-count')).to_have_text('4 saved · 0 QA passed · 0 reviewed')
        with self.page.expect_download() as draft:
            self.page.locator('#download-button').click()
        self.assertIn('DRAFT-website.zip', draft.value.suggested_filename)
        with patch.object(dashboard, 'validate', side_effect=passing_report):
            self.page.locator('#check-website').click()
            expect(self.page.locator('#website-state')).to_have_text('QA passed — review pending')
        expect(self.page.locator('#saved-count')).to_have_text('4 saved · 1 QA passed · 0 reviewed')
        self.page.locator('#review-website').click()
        expect(self.page.locator('#review-dialog')).to_be_visible()
        self.page.locator('#confirm-review').click()
        expect(self.page.locator('#website-state')).to_have_text('Reviewed for delivery')
        expect(self.page.locator('#saved-count')).to_have_text('4 saved · 1 QA passed · 1 reviewed')
        with self.page.expect_download() as reviewed:
            self.page.locator('#download-button').click()
        self.assertIn('reviewed-website.zip', reviewed.value.suggested_filename)
        self.page.reload()
        expect(self.page.locator('#website-state')).to_have_text('Reviewed for delivery')
        (self.alpha / 'website' / 'styles.css').write_text('body{color:black}')
        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#website-state')).to_have_text('Draft — QA not verified')
        expect(self.page.locator('#saved-count')).to_have_text('4 saved · 0 QA passed · 0 reviewed')
        expect(self.page.locator('#download-button')).to_have_text('Download draft ZIP')
        expect(self.page.locator('#review-website')).to_be_hidden()
        self.assertEqual(self.errors, [])

    def test_failed_recheck_is_retryable_and_keeps_selected_business(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        self.select(self.alpha)
        self.page.route('**/validate-website', lambda route: route.fulfill(status=500, json={'error': 'QA could not finish. Retry the check.'}), times=1)
        self.page.locator('#check-website').click()
        expect(self.page.locator('#website-action-error')).to_contain_text('QA could not finish')
        expect(self.page.locator('#selected-name')).to_have_text(self.alpha.name)
        expect(self.page.locator('#check-website')).to_be_enabled()
        expect(self.page.locator('#download-button')).to_be_enabled()
        self.page.locator('#check-website').click()
        expect(self.page.locator('#website-state')).to_have_text('Needs attention')
        expect(self.page.locator('#website-action-error')).to_be_hidden()
        self.open_section('qa-card')
        expect(self.page.locator('#qa-badge')).to_have_text('Review')
        self.assertEqual(self.errors, [])

    def test_list_sort_orders_filters_and_saved_preference(self):
        from playwright.sync_api import expect
        for folder, score in [(self.alpha, 80), (self.beta, 95), (self.gamma, 80), (self.low, 10)]:
            path = folder / 'business.json'
            data = json.loads(path.read_text())
            data['opportunity_score'] = score
            path.write_text(json.dumps(data))
        self.enable_list_management()
        orders = {
            'priority': [self.alpha, self.gamma, self.beta, self.low],
            'score-desc': [self.beta, self.alpha, self.gamma, self.low],
            'score-asc': [self.low, self.alpha, self.gamma, self.beta],
            'name-asc': [self.alpha, self.beta, self.low, self.gamma],
            'name-desc': [self.gamma, self.low, self.beta, self.alpha],
        }
        for sort, folders in orders.items():
            with self.subTest(sort=sort):
                self.open_section('list-filters')
                self.page.locator('#lead-sort').select_option(sort)
                expect(self.page.locator('.lead-row-name')).to_have_text([folder.name for folder in folders])
        self.page.locator('[data-priority="HIGH"]').click()
        self.open_section('list-filters')
        self.page.locator('#lead-sort').select_option('score-desc')
        expect(self.page.locator('.lead-row-name')).to_have_text([self.alpha.name, self.gamma.name])
        self.page.locator('#lead-search').fill('Roofing')
        expect(self.page.locator('.lead-row-name')).to_have_text([self.gamma.name])
        self.select(self.gamma)
        self.page.reload()
        expect(self.page.locator('#lead-sort')).to_have_value('score-desc')
        expect(self.page.locator('.lead-row-name')).to_have_text([folder.name for folder in orders['score-desc']])
        expect(self.page.locator('#selected-name')).to_have_text(self.gamma.name)
        self.assertEqual(self.errors, [])

    def test_delete_business_cancel_pending_lock_and_saved_result(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        self.select(self.alpha)
        expect(self.page.locator('#frame-stage')).to_be_visible()
        self.page.locator('#delete-business-button').click()
        expect(self.page.locator('#delete-description')).to_contain_text(self.alpha.name)
        self.page.locator('#delete-dialog').get_by_role('button', name='Cancel', exact=True).click()
        expect(self.page.locator('.lead-row')).to_have_count(4)
        self.assertTrue(self.alpha.exists())
        held = []
        self.page.route('**/delete-leads', lambda route: held.append(route), times=1)
        self.page.locator('#delete-business-button').click()
        self.page.locator('#confirm-delete').click()
        expect(self.page.locator('#confirm-delete')).to_be_disabled()
        expect(self.page.locator('#delete-dialog').get_by_role('button', name='Cancel', exact=True)).to_be_disabled()
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#delete-dialog')).to_be_visible()
        self.assertEqual(len(held), 1)
        held[0].continue_()
        expect(self.page.locator('#delete-dialog')).to_be_hidden()
        expect(self.page.locator('.lead-row')).to_have_count(3)
        expect(self.page.locator('#selected-workspace')).to_be_hidden()
        expect(self.page.locator('#preview-frame')).to_have_attribute('src', 'about:blank')
        expect(self.page.locator('#workspace-status')).to_contain_text('1 business removed')
        self.assertFalse(self.alpha.exists())
        archived = list((self.root / 'outputs/deleted_leads').rglob('website/index.html'))
        self.assertEqual(len(archived), 1)
        self.assertIn(self.alpha.name, archived[0].read_text())
        self.page.reload()
        expect(self.page.locator('.lead-row')).to_have_count(3)
        expect(self.page.locator('#selected-workspace')).to_be_hidden()
        self.assertEqual(self.errors, [])

    def test_clear_list_can_remove_priority_scope_or_all(self):
        from playwright.sync_api import expect
        self.enable_list_management()

        self.page.locator('#clear-list-button').click()
        expect(self.page.locator('#clear-menu-panel')).to_be_visible()
        self.page.locator('[data-clear-priority="LOW"]').click()
        expect(self.page.locator('#delete-description')).to_contain_text('1 low-priority business')
        expect(self.page.locator('#delete-description')).to_contain_text('outside this group will be kept')
        self.page.locator('#confirm-delete').click()
        expect(self.page.locator('.lead-row')).to_have_count(3)
        self.assertFalse(self.low.exists())
        self.assertTrue(self.alpha.exists())
        self.assertTrue(self.beta.exists())
        self.assertTrue(self.gamma.exists())

        self.page.locator('#clear-list-button').click()
        self.page.locator('[data-clear-priority="ALL"]').click()
        expect(self.page.locator('#delete-description')).to_contain_text('3 businesses')
        self.page.locator('#confirm-delete').click()
        expect(self.page.locator('.lead-row')).to_have_count(0)
        expect(self.page.locator('#business-list')).to_contain_text('Your next client starts here.')
        expect(self.page.locator('#saved-count')).to_have_text('0 saved · 0 QA passed · 0 reviewed')
        expect(self.page.locator('#clear-list-button')).to_be_disabled()
        self.page.reload()
        expect(self.page.locator('.lead-row')).to_have_count(0)
        self.assertEqual(len(list((self.root / 'outputs/deleted_leads').rglob('business.json'))), 4)
        self.assertEqual(self.errors, [])

    def test_active_jobs_disable_only_affected_delete_actions(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        self.select(self.beta)
        self.page.locator('#build-button').click()
        expect(self.page.locator('#website-state')).to_have_text('Building website')
        expect(self.page.locator('#delete-business-button')).to_be_disabled()
        expect(self.page.locator('#clear-list-button')).to_be_enabled()
        self.page.locator('#clear-list-button').click()
        expect(self.page.locator('[data-clear-priority="MEDIUM"]')).to_be_disabled()
        expect(self.page.locator('[data-clear-priority="LOW"]')).to_be_enabled()
        self.page.keyboard.press('Escape')
        self.select(self.alpha)
        expect(self.page.locator('#delete-business-button')).to_be_enabled()
        with dashboard.jobs_lock:
            dashboard.jobs['external-search'] = {'kind': 'leads', 'status': 'running', 'message': 'Searching elsewhere.'}
        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#search-message')).to_contain_text('Searching elsewhere.')
        expect(self.page.locator('#delete-business-button')).to_be_disabled()
        with dashboard.jobs_lock:
            dashboard.jobs['external-search']['status'] = 'complete'
        expect(self.page.locator('#delete-business-button')).to_be_enabled()
        expect(self.page.locator('#clear-list-button')).to_be_enabled()
        self.statuses['1'] = {'status': 'error', 'message': 'Test build ended.'}
        expect(self.page.locator('#clear-list-button')).to_be_enabled()
        self.assertEqual(self.errors, [])

    def test_delete_rejection_refreshes_jobs_without_removing_the_business(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        self.select(self.gamma)
        self.page.locator('#delete-business-button').click()
        with dashboard.jobs_lock:
            dashboard.jobs['external-build'] = {'kind': 'website', 'status': 'running',
                'priority': 'HIGH', 'client_id': self.gamma.name, 'client': str(self.gamma), 'message': 'Building elsewhere.'}
        self.statuses['external-build'] = {'status': 'running', 'message': 'Building elsewhere.'}
        self.page.locator('#confirm-delete').click()
        expect(self.page.locator('#delete-error')).to_contain_text('Wait for')
        expect(self.page.locator('#confirm-delete')).to_be_disabled()
        expect(self.page.locator('.lead-row')).to_have_count(4)
        self.assertTrue(self.gamma.exists())
        self.page.locator('#delete-dialog').get_by_role('button', name='Cancel', exact=True).click()
        expect(self.page.locator('#selected-name')).to_have_text(self.gamma.name)
        self.assertEqual(self.errors, [])

    def test_late_list_response_cannot_restore_a_deleted_business(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        stale = self.client.get('/leads').get_json()
        self.select(self.beta)
        self.page.locator('#build-button').click()
        expect(self.page.locator('#website-state')).to_have_text('Building website')
        held = []
        self.page.route('**/leads', lambda route: held.append(route), times=1)
        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#refresh-button')).to_be_disabled()
        self.website(self.beta)
        self.statuses['1'] = {'status': 'complete', 'message': 'Ready.'}
        expect(self.page.locator('#clear-list-button')).to_be_enabled()
        self.select(self.alpha)
        self.page.locator('#delete-business-button').click()
        self.page.locator('#confirm-delete').click()
        expect(self.page.locator('.lead-row')).to_have_count(3)
        expect(self.page.locator('#clear-list-button')).to_be_enabled()
        self.assertEqual(len(held), 1)
        with self.page.expect_response(lambda response: response.url.endswith('/leads')) as response:
            held[0].fulfill(json=stale)
        response.value.finished()
        self.page.evaluate('() => new Promise(resolve => requestAnimationFrame(resolve))')
        expect(self.page.locator('.lead-row')).to_have_count(3)
        expect(self.page.locator('.lead-row').filter(has_text=self.alpha.name)).to_have_count(0)
        self.assertEqual(self.errors, [])

    def test_generated_preview_isolated_from_app_and_still_runs_local_assets(self):
        from playwright.sync_api import expect
        import shutil
        # Security checks must cross the real HTTP/CORS boundary, not the
        # session response stub used by unrelated dashboard interaction tests.
        self.page.unroute('**/session')
        website = self.alpha / 'website'
        (website / 'fonts').mkdir()
        shutil.copyfile(dashboard.APP_ROOT / 'assets/fonts/Geist.ttf', website / 'fonts/Geist.ttf')
        (website / 'index.html').write_text('''<!doctype html><link rel="stylesheet" href="styles.css">
            <h1>Isolated preview</h1><button id="preview-action">Try interaction</button><script src="script.js"></script>''')
        (website / 'styles.css').write_text('''@font-face{font-family:AuditFont;src:url("fonts/Geist.ttf")}
            body{font-family:AuditFont,sans-serif;color:rgb(12,34,56)}''')
        (website / 'script.js').write_text('''document.body.dataset.scriptLoaded='yes';
            document.getElementById('preview-action').onclick=()=>document.body.dataset.clicked='yes';
            try { parent.document.documentElement.dataset.previewAttack='yes'; document.body.dataset.parentAccess='allowed'; }
            catch { document.body.dataset.parentAccess='blocked'; }
            try { localStorage.setItem('preview-audit','unsafe'); document.body.dataset.storageAccess='allowed'; }
            catch { document.body.dataset.storageAccess='blocked'; }
            for (const [name,path] of [['session','/session'],['settings','/api-settings']]) {
                fetch(path).then(response=>response.json()).then(()=>document.body.dataset[name]='allowed')
                    .catch(()=>document.body.dataset[name]='blocked');
            }''')
        self.select(self.alpha)
        expect(self.page.locator('#frame-stage')).to_be_visible()
        expect(self.page.locator('#preview-frame')).to_have_attribute('sandbox', 'allow-scripts')
        frame = self.page.frame_locator('#preview-frame')
        expect(frame.locator('body')).to_have_attribute('data-script-loaded', 'yes')
        expect(frame.locator('body')).to_have_attribute('data-parent-access', 'blocked')
        expect(frame.locator('body')).to_have_attribute('data-storage-access', 'blocked')
        expect(frame.locator('body')).to_have_attribute('data-session', 'blocked')
        expect(frame.locator('body')).to_have_attribute('data-settings', 'blocked')
        self.assertIsNone(self.page.locator('html').get_attribute('data-preview-attack'))
        self.assertEqual(frame.locator('body').evaluate('(body)=>getComputedStyle(body).color'), 'rgb(12, 34, 56)')
        self.assertTrue(frame.locator('body').evaluate('async ()=>{await document.fonts.load("16px AuditFont");return document.fonts.check("16px AuditFont");}'))
        frame.locator('#preview-action').click()
        expect(frame.locator('body')).to_have_attribute('data-clicked', 'yes')
        self.page.get_by_role('button', name='Mobile', exact=True).click()
        self.assertEqual(frame.locator('html').evaluate('()=>innerWidth'), 390)
        with self.page.expect_popup() as opened:
            self.page.locator('#open-preview').click()
        popup = opened.value
        try:
            expect(popup.locator('body')).to_have_attribute('data-session', 'blocked')
            expect(popup.locator('body')).to_have_attribute('data-settings', 'blocked')
            expect(popup.locator('body')).to_have_attribute('data-storage-access', 'blocked')
        finally:
            popup.close()
        self.assertEqual(self.errors, [])

    def test_key_save_locks_dialog_and_ignores_an_older_key_test(self):
        from playwright.sync_api import expect
        held_tests, held_saves = [], []
        def settings(route):
            if route.request.method != 'POST':
                route.continue_()
            elif route.request.post_data_json['action'] == 'test':
                held_tests.append(route)
            else:
                held_saves.append(route)
        self.page.route('**/api-settings', settings)
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-old-1234'}):
            self.page.locator('#settings-button').click()
            expect(self.page.locator('#save-settings')).to_be_enabled()
            self.page.locator('#test-deepseek').click()
            expect(self.page.locator('#test-deepseek')).to_have_text('Testing…')
            self.page.locator('#key-deepseek').fill('test-new-5678')
            self.page.locator('#save-settings').click()
            expect(self.page.locator('#settings-message')).to_have_text('Saving keys…')
            expect(self.page.locator('#settings-dialog').get_by_role('button', name='Close API settings')).to_be_disabled()
            expect(self.page.locator('#test-deepseek')).to_be_disabled()
            self.page.keyboard.press('Escape')
            expect(self.page.locator('#settings-dialog')).to_be_visible()
            self.assertEqual((len(held_tests), len(held_saves)), (1, 1))
            held_saves[0].continue_()
            expect(self.page.locator('#settings-message')).to_contain_text('API keys saved')
            expect(self.page.locator('#key-status-deepseek')).to_contain_text('5678')
            with self.page.expect_response(lambda response: response.url.endswith('/api-settings')) as response:
                held_tests[0].fulfill(json={'ok': True, 'message': 'Old key accepted.'})
            response.value.finished()
            self.page.evaluate('() => new Promise(resolve => requestAnimationFrame(resolve))')
            expect(self.page.locator('#key-result-deepseek')).to_have_text('')
            self.assertEqual(os.getenv('DEEPSEEK_API_KEY'), 'test-new-5678')
            self.page.locator('#settings-dialog').get_by_role('button', name='Close API settings').click()
        self.assertEqual(self.errors, [])

    def test_lost_search_reply_resumes_existing_job_and_blocks_website_builds(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        self.select(self.beta)
        posts = []
        def search(route):
            posts.append(route.request.post_data_json)
            with dashboard.jobs_lock:
                dashboard.jobs['recovered-search'] = {'kind': 'leads', 'status': 'running', 'message': 'Recovered active search.'}
            route.abort('failed')
        self.page.route('**/generate', search)
        self.page.locator('#find-button').click()
        self.page.locator('#niche').fill('Roofing')
        self.page.locator('#area').fill('Raleigh')
        self.page.locator('#search-submit').click()
        expect(self.page.locator('#find-dialog')).to_be_hidden()
        expect(self.page.locator('#search-message')).to_contain_text('Recovered active search.')
        expect(self.page.locator('#find-button')).to_be_disabled()
        expect(self.page.locator('#build-button')).to_be_disabled()
        expect(self.page.locator('#build-message')).to_contain_text('business search to finish')
        self.assertEqual(len(posts), 1)
        with dashboard.jobs_lock:
            dashboard.jobs['recovered-search']['status'] = 'complete'
        expect(self.page.locator('#find-button')).to_be_enabled()
        expect(self.page.locator('#build-button')).to_be_enabled()
        self.assertEqual(self.errors, [])

    def test_old_website_status_cannot_replace_a_new_build_from_another_tab(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        held = []
        self.page.route('**/landing-page-status?job_id=1', lambda route: held.append(route), times=1)
        self.select(self.beta)
        self.page.locator('#build-button').click()
        expect(self.page.locator('#website-state')).to_have_text('Building website')
        expect(self.page.locator('#find-button')).to_be_disabled()
        with dashboard.jobs_lock:
            dashboard.jobs['replacement-build'] = {'kind': 'website', 'status': 'running', 'priority': 'MEDIUM',
                'client_id': self.beta.name, 'client': str(self.beta), 'message': 'New build from another tab.'}
        self.statuses['replacement-build'] = {'status': 'running', 'message': 'New build from another tab.'}
        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#build-message')).to_contain_text('New build from another tab.')
        self.assertEqual(len(held), 1)
        with self.page.expect_response(lambda response: response.url.endswith('job_id=1')) as response:
            held[0].fulfill(json={'status': 'error', 'message': 'Obsolete failure.'})
        response.value.finished()
        self.page.evaluate('() => new Promise(resolve => requestAnimationFrame(resolve))')
        expect(self.page.locator('#website-state')).to_have_text('Building website')
        expect(self.page.locator('#job-error')).to_be_hidden()
        self.website(self.beta)
        self.statuses['replacement-build'] = {'status': 'complete', 'message': 'Ready.'}
        expect(self.page.locator('#download-button')).to_be_enabled()
        expect(self.page.locator('#find-button')).to_be_enabled()
        self.assertEqual(self.errors, [])

    def test_old_search_status_cannot_replace_a_new_search_from_another_tab(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        held = []
        self.page.route('**/generate', lambda route: route.fulfill(json={'job_id': 'old-search'}))
        self.page.route('**/job-status?job_id=old-search', lambda route: held.append(route), times=1)
        self.page.locator('#find-button').click()
        self.page.locator('#niche').fill('Roofing')
        self.page.locator('#area').fill('Raleigh')
        self.page.locator('#search-submit').click()
        expect(self.page.locator('#find-dialog')).to_be_hidden()
        with dashboard.jobs_lock:
            dashboard.jobs['new-search'] = {'kind': 'leads', 'status': 'running', 'message': 'New search from another tab.'}
        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#search-message')).to_contain_text('New search from another tab.')
        self.assertEqual(len(held), 1)
        with self.page.expect_response(lambda response: response.url.endswith('job_id=old-search')) as response:
            held[0].fulfill(status=404, json={'message': 'Old session ended.'})
        response.value.finished()
        self.page.evaluate('() => new Promise(resolve => requestAnimationFrame(resolve))')
        expect(self.page.locator('#search-message')).to_contain_text('New search from another tab.')
        expect(self.page.locator('#find-button')).to_be_disabled()
        with dashboard.jobs_lock:
            dashboard.jobs['new-search']['status'] = 'complete'
        expect(self.page.locator('#find-button')).to_be_enabled()
        self.assertEqual(self.errors, [])

    def test_refreshed_search_that_disappears_unlocks_the_workspace(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        held = []
        def search(route):
            with dashboard.jobs_lock:
                dashboard.jobs['ended-search'] = {'kind': 'leads', 'status': 'running', 'message': 'Checking businesses.'}
            route.fulfill(json={'job_id': 'ended-search'})
        self.page.route('**/generate', search)
        self.page.route('**/job-status?job_id=ended-search', lambda route: held.append(route), times=1)
        self.page.locator('#find-button').click()
        self.page.locator('#niche').fill('Roofing')
        self.page.locator('#area').fill('Raleigh')
        self.page.locator('#search-submit').click()
        expect(self.page.locator('#find-dialog')).to_be_hidden()
        self.page.locator('#refresh-button').click()
        expect(self.page.locator('#search-message')).to_contain_text('Checking businesses.')
        with dashboard.jobs_lock:
            dashboard.jobs.clear()
        self.assertEqual(len(held), 1)
        held[0].fulfill(status=404, json={'message': 'Session ended.'})
        expect(self.page.locator('#search-message')).to_contain_text('search session has ended')
        expect(self.page.locator('#find-button')).to_be_enabled()
        expect(self.page.locator('#clear-list-button')).to_be_enabled()
        self.assertEqual(self.errors, [])


    def test_build_stage_elapsed_and_failure_recovery_are_visible(self):
        from playwright.sync_api import expect
        self.select(self.beta)
        self.page.locator('#build-button').click()
        self.statuses['1'] = {'status': 'running', 'phase': 'copy', 'message': 'Writing business copy.'}
        expect(self.page.locator('#build-stage')).to_contain_text('Copy')
        expect(self.page.locator('#build-stage')).to_contain_text('elapsed')
        expect(self.page.locator('#step-qa')).not_to_have_class('build-step complete')
        self.statuses['1'] = {'status': 'error', 'phase': 'copy', 'message': 'API key rejected.', 'finished_at': 9999999999}
        expect(self.page.locator('#job-error')).to_contain_text('Change or test the API key')
        expect(self.page.locator('#job-settings-button')).to_be_visible()
        expect(self.page.locator('#build-button')).to_be_enabled()
        self.assertEqual(self.errors, [])


    def test_narrow_export_and_clear_menu_keyboard_navigation(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        for width in (1024, 768, 390, 320):
            self.page.set_viewport_size({'width': width, 'height': 900})
            expect(self.page.locator('#export-button')).to_be_visible()
            self.assertLessEqual(self.page.locator('html').evaluate('(el)=>el.scrollWidth'), width)
        with self.page.expect_download() as exported:
            self.page.locator('#export-button').click()
        self.assertTrue(exported.value.suggested_filename.endswith('.csv'))
        trigger = self.page.locator('#clear-list-button')
        trigger.focus()
        self.page.keyboard.press('ArrowDown')
        expect(self.page.locator('[data-clear-priority="HIGH"]')).to_be_focused()
        self.page.keyboard.press('End')
        expect(self.page.locator('[data-clear-priority="ALL"]')).to_be_focused()
        self.page.keyboard.press('Home')
        expect(self.page.locator('[data-clear-priority="HIGH"]')).to_be_focused()
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#clear-menu-panel')).to_be_hidden()
        expect(trigger).to_be_focused()
        self.page.keyboard.press('ArrowDown')
        self.page.keyboard.press('Enter')
        expect(self.page.locator('#delete-dialog')).to_be_visible()
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#delete-dialog')).to_be_hidden()
        expect(trigger).to_be_focused()
        self.assertEqual(self.errors, [])
