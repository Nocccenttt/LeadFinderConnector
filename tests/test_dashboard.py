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
            route.fulfill(status=200 if result else 404, json=result or {'message': 'Job not found.'})
        self.page.route('**/generate-landing-page', build)
        self.page.route('**/landing-page-status?**', status)
        self.page.goto(f'http://127.0.0.1:{self.server.server_port}')
        self.page.locator('.lead-row').first.wait_for()

    def select(self, folder):
        self.page.locator('.lead-row').filter(has_text=folder.name).click()

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
                self.page.locator('#lead-sort').select_option(sort)
                expect(self.page.locator('.lead-row-name')).to_have_text([folder.name for folder in folders])
        self.page.locator('[data-priority="HIGH"]').click()
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

    def test_clear_list_includes_filtered_businesses_and_stays_empty_after_reload(self):
        from playwright.sync_api import expect
        self.enable_list_management()
        self.page.locator('[data-priority="HIGH"]').click()
        expect(self.page.locator('.lead-row')).to_have_count(2)
        self.page.locator('#clear-list-button').click()
        expect(self.page.locator('#delete-description')).to_contain_text('all 4 saved businesses')
        expect(self.page.locator('#delete-description')).to_contain_text('hidden by your current search or filters')
        self.page.locator('#confirm-delete').click()
        expect(self.page.locator('.lead-row')).to_have_count(0)
        expect(self.page.locator('#business-list')).to_contain_text('Your next client starts here.')
        expect(self.page.locator('#saved-count')).to_have_text('0 saved · 0 websites ready')
        expect(self.page.locator('#clear-list-button')).to_be_disabled()
        self.page.reload()
        expect(self.page.locator('#business-list')).to_contain_text('Your next client starts here.')
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
        expect(self.page.locator('#clear-list-button')).to_be_disabled()
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
        expect(self.page.locator('#clear-list-button')).to_be_disabled()
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
