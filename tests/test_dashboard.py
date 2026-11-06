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
        self.assertEqual((info['state'], info['available']), ('ready', True))
        with self.client.get(info['preview_url']) as response:
            self.assertEqual(response.status_code, 200)
        (self.beta / 'STATUS.json').write_text('{"status":"FAILED"}')
        self.assertEqual(self.info(self.beta).get_json()['state'], 'failed')
        (self.beta / 'website' / 'script.js').write_text('')
        self.assertFalse(self.info(self.beta).get_json()['available'])
        self.assertEqual(self.client.get('/preview-status?priority=HIGH&name=../outside').status_code, 404)

    def test_list_reports_build_eligibility_and_complete_packages(self):
        leads = self.client.get('/leads').get_json()
        self.assertEqual((leads['total'], leads['ready'], leads['low']), (4, 1, 1))
        by_name = {lead['name']: lead for lead in leads['leads']}
        self.assertTrue(by_name[self.beta.name]['can_generate'])
        self.assertFalse(by_name[self.low.name]['can_generate'])
        self.assertFalse(by_name[self.beta.name]['demo_ready'])
        with self.client.get(by_name[self.alpha.name]['download_url']) as response:
            with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                self.assertEqual(set(archive.namelist()), {'index.html', 'styles.css', 'script.js'})

    def test_incomplete_build_does_not_report_success(self):
        with patch.object(dashboard, 'run_pipeline', return_value='PASS'):
            dashboard.run_landing_page('incomplete', self.beta)
        response = self.client.get('/landing-page-status?job_id=incomplete').get_json()
        self.assertEqual(response['status'], 'error')
        self.assertNotIn('preview_url', response)

    def test_session_exposes_resumable_jobs_without_credentials(self):
        with patch.object(dashboard, 'Thread'), patch.dict(os.environ, {'GOOGLE_MAPS_API_KEY': 'secret-maps', 'DEEPSEEK_API_KEY': 'secret-model'}):
            website = self.client.post('/generate-landing-page', json={'priority': 'HIGH', 'name': self.alpha.name}).get_json()
            search = self.client.post('/generate', json={'niche': 'Roofing', 'area': 'Raleigh'}).get_json()
            response = self.client.get('/session')
            session = response.get_json()
        self.assertEqual(session['capabilities'], {'search_configured': True, 'website_configured': True})
        jobs = {job['job_id']: job for job in session['active_jobs']}
        self.assertEqual(jobs[website['job_id']]['client_id'], self.alpha.name)
        self.assertEqual(jobs[website['job_id']]['kind'], 'website')
        self.assertEqual(jobs[search['job_id']]['kind'], 'leads')
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
            route.fulfill(status=200 if result else 404, json=result or {'message': 'Job not found.'})
        self.page.route('**/generate-landing-page', build)
        self.page.route('**/landing-page-status?**', status)
        self.page.goto(f'http://127.0.0.1:{self.server.server_port}')
        self.page.locator('.lead-row').first.wait_for()

    def select(self, folder):
        self.page.locator('.lead-row').filter(has_text=folder.name).click()

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
        self.page.locator('#website-filter').select_option('failed')
        expect(self.page.locator('.lead-row')).to_have_count(1)
        expect(self.page.locator('.lead-row')).to_contain_text(self.gamma.name)
        self.page.locator('#website-filter').select_option('ALL')
        self.select(self.beta)
        expect(self.page.frame_locator('#preview-frame').locator('h1')).to_have_text(self.beta.name)
        self.assertEqual(len(self.builds), 2)
        self.assertEqual(self.errors, [])

    def test_redesign_preserves_copy_rejection_recovers_and_rebuild_requires_choice(self):
        from playwright.sync_api import expect
        self.select(self.alpha)
        self.page.route('**/generate-landing-page', lambda route: route.fulfill(status=503, json={'error': 'Build service unavailable.'}), times=1)
        self.page.locator('#redesign-button').click()
        expect(self.page.locator('#job-error')).to_have_text('Build service unavailable.')
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
