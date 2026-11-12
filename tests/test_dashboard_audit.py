"""Dashboard audit regressions use isolated data and never call paid providers."""
import csv
import io
from unittest.mock import patch

import preview_dashboard as dashboard
from test_dashboard import WorkspaceFixture


class DashboardAuditTests(WorkspaceFixture):
    def test_nonlocal_hostnames_cannot_read_the_workspace_or_start_work(self):
        for url in ('/', '/session', '/leads'):
            self.assertEqual(self.client.get(url, base_url='http://untrusted.example').status_code, 403)
        with patch.object(dashboard, 'Thread') as thread:
            for url, payload in [('/generate', {'niche': 'Roofing', 'area': 'Test City'}),
                                 ('/generate-landing-page', {'priority': 'HIGH', 'name': self.alpha.name})]:
                response = self.client.post(url, json=payload, base_url='http://untrusted.example')
                self.assertEqual(response.status_code, 403)
                for origin in ('https://untrusted.example', 'null'):
                    self.assertEqual(self.client.post(url, json=payload, headers={'Origin': origin}).status_code, 403)
            thread.assert_not_called()
        self.assertEqual(self.client.get('/session', base_url='http://127.0.0.1').status_code, 200)
        self.assertEqual(self.client.get('/session', base_url='http://[::1]').status_code, 200)

    def test_exports_keep_their_own_snapshot_when_downloads_overlap(self):
        def rows(prefix):
            return [{'name': f'{prefix} business {number:04d}', 'address': '123 Test Street ' * 8,
                     'phone': '555-0100', 'priority': 'HIGH', 'score': 90} for number in range(250)]

        with patch.object(dashboard, 'discover_leads', side_effect=[rows('First'), rows('Second')]):
            first = self.client.get('/export', buffered=False)
            self.addCleanup(first.close)
            second = self.client.get('/export', buffered=False)
            self.addCleanup(second.close)
            second_rows = list(csv.DictReader(io.StringIO(second.get_data().decode('utf-8-sig'))))
            first_rows = list(csv.DictReader(io.StringIO(first.get_data().decode('utf-8-sig'))))
        self.assertEqual(len(first_rows), 250)
        self.assertEqual(len(second_rows), 250)
        self.assertTrue(all(row['name'].startswith('First business') for row in first_rows))
        self.assertTrue(all(row['name'].startswith('Second business') for row in second_rows))

    def test_export_keeps_unicode_and_text_cells_without_overwriting_previous_files(self):
        output = self.root / 'outputs' / 'leadfinder_export.csv'
        output.parent.mkdir()
        output.write_text('Previous saved export', encoding='utf-8')
        records = [{'name': '=1+1', 'address': '\t@SUM(1,2)', 'phone': '+1 (555) 0100',
                    'website': 'https://example.com', 'priority': 'HIGH', 'score': 90,
                    'reason': ['Needs a website', 'Café in Montréal']},
                   {'name': 'Café in Montréal', 'address': '-2+3', 'phone': '555-0101'}]
        with patch.object(dashboard, 'discover_leads', return_value=records):
            with self.client.get('/export') as response:
                self.assertEqual(response.status_code, 200)
                exported = list(csv.DictReader(io.StringIO(response.data.decode('utf-8-sig'))))
        self.assertEqual(exported[0]['name'], "'=1+1")
        self.assertEqual(exported[0]['address'], "'\t@SUM(1,2)")
        self.assertEqual(exported[0]['phone'], "'+1 (555) 0100")
        self.assertEqual(exported[0]['reason'], 'Needs a website; Café in Montréal')
        self.assertEqual(exported[1]['name'], 'Café in Montréal')
        self.assertEqual(exported[1]['address'], "'-2+3")
        self.assertEqual(output.read_text(encoding='utf-8'), 'Previous saved export')

    def test_generated_pages_are_sandboxed_even_when_opened_directly(self):
        website = self.alpha / 'website'
        (website / 'nested.html').write_text('<script>window.test = true</script>', encoding='utf-8')
        (website / 'font.woff2').write_bytes(b'test font')
        lead = next(item for item in self.client.get('/leads').get_json()['leads'] if item['client_id'] == self.alpha.name)
        for suffix in ('', 'index.html', 'nested.html', 'script.js', 'styles.css'):
            with self.subTest(suffix=suffix), self.client.get(lead['demo_url'] + suffix) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get('Content-Security-Policy'), 'sandbox allow-scripts')
                self.assertNotIn('Access-Control-Allow-Origin', response.headers)
        with self.client.get(lead['demo_url'] + 'font.woff2') as response:
            self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), '*')
        for url in ('/session', '/api-settings'):
            self.assertNotIn('Access-Control-Allow-Origin', self.client.get(url).headers)

    def test_active_search_blocks_builds_until_the_search_finishes(self):
        for status in ('queued', 'running'):
            with self.subTest(status=status), patch.object(dashboard, 'Thread') as thread:
                dashboard.jobs['search'] = {'kind': 'leads', 'status': status}
                response = self.client.post('/generate-landing-page', json={
                    'priority': 'HIGH', 'name': self.alpha.name})
                self.assertEqual(response.status_code, 409)
                thread.assert_not_called()
        dashboard.jobs['search']['status'] = 'complete'
        with patch.object(dashboard, 'Thread') as thread:
            self.assertEqual(self.client.post('/generate-landing-page', json={
                'priority': 'HIGH', 'name': self.alpha.name}).status_code, 200)
            thread.assert_called_once()

    def test_active_build_blocks_search_but_not_a_different_business_build(self):
        with patch.object(dashboard, 'Thread') as thread:
            for folder in (self.alpha, self.beta):
                self.assertEqual(self.client.post('/generate-landing-page', json={
                    'priority': folder.parent.name, 'name': folder.name}).status_code, 200)
            response = self.client.post('/generate', json={'niche': 'Roofing', 'area': 'Test City'})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(thread.call_count, 2)

    def test_invalid_search_fields_do_not_start_paid_work(self):
        invalid = [{'niche': None, 'area': 'Test City'}, {'niche': [], 'area': 'Test City'},
                   {'niche': 'Roofing', 'area': {}}, {'niche': 'x' * 181, 'area': 'Test City'},
                   {'niche': 'Roofing', 'area': 'Test City', 'max_results': float('inf')},
                   {'niche': 'Roofing', 'area': 'Test City', 'max_results': True},
                   {'niche': 'Roofing', 'area': 'Test City', 'max_results': 'invalid'}]
        with patch.object(dashboard, 'Thread') as thread:
            for payload in invalid:
                with self.subTest(payload=payload):
                    dashboard.jobs.clear()
                    self.assertEqual(self.client.post('/generate', json=payload).status_code, 400)
            thread.assert_not_called()

    def test_null_byte_lead_ids_return_not_found_without_crashing(self):
        for url in ('/preview-status', '/generate-landing-page'):
            with self.subTest(url=url):
                response = (self.client.get(url, query_string={'priority': 'HIGH', 'name': '\0'})
                            if url == '/preview-status' else
                            self.client.post(url, json={'priority': 'HIGH', 'name': '\0'}))
                self.assertEqual(response.status_code, 404)

    def test_linked_or_looping_business_folders_do_not_break_the_saved_list(self):
        alias = self.alpha.parent / 'Alias'
        loop = self.alpha.parent / 'Loop'
        try:
            alias.symlink_to(self.alpha, target_is_directory=True)
            loop.symlink_to(loop, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'Directory links unavailable: {error}')
        response = self.client.get('/leads')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['total'], 4)
        self.assertIsNone(dashboard.resolve_client('HIGH', alias.name))

    def test_looping_preview_directory_does_not_break_other_businesses(self):
        website = self.beta / 'website'
        try:
            website.symlink_to(website, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'Directory links unavailable: {error}')
        response = self.client.get('/leads')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['total'], 4)
        with self.client.get(f'/demo/{self.beta.parent.name}/{self.beta.name}/') as response:
            self.assertEqual(response.status_code, 404)
