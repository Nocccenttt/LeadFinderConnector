"""Social enrichment uses public-page fixtures, never live provider requests."""
import csv
import io
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import preview_dashboard as dashboard
import seo_lead_finder_prospecting_batch as finder
import social_discovery as social
from ai_handoff import build_ai_handoff
from test_dashboard import WorkspaceFixture


def page(html='', status=200, **headers):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = status
    response.headers = {'Content-Type': 'text/html', **headers}
    response.encoding = 'utf-8'
    response.iter_content.return_value = [html.encode('utf-8')]
    return response


class SocialDiscoveryTests(unittest.TestCase):
    def test_profile_urls_are_canonical_and_share_post_login_and_lookalikes_are_rejected(self):
        cases = {
            '//www.facebook.com/ExampleBusiness/?utm_source=site': ('facebook', 'https://facebook.com/examplebusiness'),
            'https://m.facebook.com/profile.php?id=123&utm_source=site': ('facebook', 'https://facebook.com/profile.php?id=123'),
            'https://instagram.com/ExampleBusiness/': ('instagram', 'https://instagram.com/examplebusiness'),
            'https://www.linkedin.com/company/example/about/': ('linkedin', 'https://linkedin.com/company/example'),
            'https://twitter.com/ExampleBusiness/status/123': ('x', 'https://x.com/examplebusiness'),
            'https://youtube.com/@ExampleBusiness/videos': ('youtube', 'https://youtube.com/@ExampleBusiness'),
            'https://tiktok.com/@ExampleBusiness/video/123': ('tiktok', 'https://tiktok.com/@examplebusiness'),
            'https://threads.net/@ExampleBusiness': ('threads', 'https://threads.com/@examplebusiness'),
            'https://bsky.app/profile/example.test': ('bluesky', 'https://bsky.app/profile/example.test'),
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(social.social_url(value, 'https://business.example/'), expected)
        for value in ('https://facebook.com.evil.test/brand', 'https://facebook.com@evil.test/brand',
                      'https://facebook.com/sharer.php?u=https://business.example', 'https://instagram.com/p/123',
                      'https://linkedin.com/in/someone', 'https://x.com/intent/tweet', 'https://youtube.com/watch?v=123',
                      'https://pinterest.com/pin/123', 'https://instagram.com/accounts/login',
                      'javascript:alert(1)', 'https://facebook.com:9000/brand', 'https://facebook.com'):
            with self.subTest(value=value):
                self.assertIsNone(social.social_url(value))

    def test_business_same_as_and_anchors_are_deduplicated_with_source_evidence(self):
        html = '''<a href="//www.instagram.com/Example">Instagram</a>
        <a href="https://instagram.com/example/?utm_source=footer">Instagram again</a>
        <a href="https://facebook.com/sharer.php?u=https://business.example">Share</a>
        <script type="application/ld+json">{"@graph":[
        {"@type":"LocalBusiness","sameAs":["https://linkedin.com/company/example","https://facebook.com/example"]},
        {"@type":"Person","sameAs":"https://facebook.com/someemployee"}]}</script>
        <script type="application/ld+json">invalid</script>'''
        result = social.extract_profiles(html, 'https://business.example/about')
        self.assertEqual({item['url'] for item in result}, {'https://instagram.com/example',
            'https://linkedin.com/company/example', 'https://facebook.com/example'})
        self.assertTrue(all(item['source_url'] == 'https://business.example/about' for item in result))

    def test_profile_details_collect_only_exposed_bio_and_business_contacts(self):
        details = social.profile_details('''<title>Example Care</title>
        <meta property="og:description" content="Local care. Email hello@example.test for bookings.">
        <a href="mailto:bookings@example.test?subject=Hello">Email</a><a href="tel:+1-555-0100">Call</a>
        <script type="application/ld+json">{"@type":"LocalBusiness","name":"Example Care",
        "telephone":"+1-555-0200","address":{"streetAddress":"1 Main St","addressLocality":"Raleigh"}}</script>''')
        self.assertEqual(details['name'], 'Example Care')
        self.assertEqual(details['emails'], ['hello@example.test', 'bookings@example.test'])
        self.assertEqual(details['phones'], ['+1-555-0100', '+1-555-0200'])
        self.assertEqual(details['address'], '1 Main St, Raleigh')
        self.assertIsNone(social.profile_details('<title>Log in to Facebook</title><input type="password">'))

    def test_public_address_validation_rejects_private_mixed_and_malformed_targets(self):
        def addresses(value):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (value, 443))]
        for address in ('127.0.0.1', '10.1.2.3', '169.254.169.254', '192.168.1.1', '::1'):
            with self.subTest(address=address), patch.object(social.socket, 'getaddrinfo', return_value=addresses(address)):
                self.assertEqual(social.public_url('https://business.example/'), '')
        with patch.object(social.socket, 'getaddrinfo', return_value=addresses('93.184.216.34')):
            self.assertEqual(social.public_url('https://business.example/'), 'https://business.example/')
            for value in ('file:///secret', 'http://localhost/', 'https://a:b@business.example/', 'https://business.example:444/'):
                self.assertEqual(social.public_url(value), '')

    def test_crawl_visits_business_contact_page_and_records_public_and_blocked_profiles(self):
        pages = {
            'https://business.example/robots.txt': page('User-agent: *\nAllow: /'),
            'https://business.example/': page('<a href="/contact">Contact</a><a href="https://instagram.com/example">IG</a>'),
            'https://business.example/contact': page('<a href="https://linkedin.com/company/example">LinkedIn</a>'),
            'https://instagram.com/robots.txt': page('User-agent: *\nAllow: /'),
            'https://instagram.com/example': page('<title>Example</title><meta name="description" content="Public business bio">'),
            'https://linkedin.com/robots.txt': page('User-agent: *\nDisallow: /'),
        }
        with patch.object(social, 'public_url', side_effect=lambda url, base='': url), patch.object(
            social.requests, 'get', side_effect=lambda url, **kwargs: pages[url]) as get, patch.object(social.time, 'sleep'):
            result = social.crawl_socials({'website': 'https://business.example/'})
        profiles = {profile['platform']: profile for profile in result['profiles']}
        self.assertEqual(profiles['instagram']['details']['description'], 'Public business bio')
        self.assertEqual(profiles['instagram']['source_url'], 'https://business.example/')
        self.assertTrue(profiles['instagram']['observed_at'])
        self.assertEqual(profiles['linkedin']['status'], 'blocked')
        self.assertNotIn('https://linkedin.com/company/example', [call.args[0] for call in get.call_args_list])
        self.assertIn('public details available for 1', result['note'])

    def test_redirect_rechecks_public_address_and_target_crawl_permissions(self):
        pages = {
            'https://business.example/robots.txt': page('', 404),
            'https://business.example/': page('', 302, Location='http://127.0.0.1/private'),
        }
        with patch.object(social, 'public_url', side_effect=lambda url, base='': '' if '127.0.0.1' in url else url), patch.object(
            social.requests, 'get', side_effect=lambda url, **kwargs: pages[url]) as get:
            result = social.PublicCrawler().get('https://business.example/')
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('http://127.0.0.1/private', [call.args[0] for call in get.call_args_list])
        pages['https://business.example/'] = page('', 302, Location='https://other.example/profile')
        pages['https://other.example/robots.txt'] = page('User-agent: *\nDisallow: /')
        with patch.object(social, 'public_url', side_effect=lambda url, base='': url), patch.object(
            social.requests, 'get', side_effect=lambda url, **kwargs: pages[url]) as get:
            self.assertEqual(social.PublicCrawler().get('https://business.example/')['status'], 'blocked')
            self.assertNotIn('https://other.example/profile', [call.args[0] for call in get.call_args_list])

    def test_time_size_content_and_login_limits_are_reported_without_inventing_details(self):
        self.assertEqual(social.PublicCrawler(budget_seconds=0).get('https://facebook.com/example')['status'], 'not_checked')
        with patch.object(social, 'public_url', side_effect=lambda url, base='': url), patch.object(
            social.requests, 'get', return_value=page('x' * 512001)):
            self.assertEqual(social.PublicCrawler().read('https://business.example/')['status'], 'unavailable')
        with patch.object(social.PublicCrawler, 'get', return_value={'status': 'public', 'url': 'https://facebook.com/example',
                            'html': '<title>Log in to Facebook</title>'}):
            result = social.crawl_socials({'facebook': 'https://facebook.com/example'}, crawl_website=False)
        self.assertEqual(result['profiles'][0]['status'], 'blocked')
        self.assertEqual(result['profiles'][0]['details'], {})

    def test_social_only_businesses_remain_website_opportunities_and_do_not_probe_contact_paths(self):
        with patch.object(finder, 'fetch') as fetch:
            site = finder.inspect_website('https://www.facebook.com/example')
        fetch.assert_not_called()
        self.assertEqual(site['facebook'], 'https://facebook.com/example')
        lead = finder.Lead(1, 'Example', website='https://www.facebook.com/example')
        self.assertEqual(finder.score_lead(lead, site)[:2], (100, 'HIGH'))

    def test_new_search_enrichment_flows_into_business_handoff_and_batch_csv(self):
        profile = {'platform': 'facebook', 'url': 'https://facebook.com/example', 'status': 'public',
                   'source_url': 'https://business.example/contact', 'details': {'description': 'Public business bio'}}
        site = {'status': 'working', 'email': '', 'email_source_url': '', 'facebook': profile['url'],
                'instagram': '', 'linkedin': '', 'other_socials': [], 'social_profiles': [profile],
                'mobile_meta': False, 'cta': False, 'contact_info': False}
        lead = finder.Lead(1, 'Example', website='https://business.example/')
        with patch.object(finder, 'inspect_website', return_value=site), patch.object(finder, 'crawl_socials', return_value={
            'profiles': [profile], 'checked_at': '2026-11-12T00:00:00Z', 'note': 'Found 1 profile.'}):
            finder.enrich_lead(lead)
        with tempfile.TemporaryDirectory() as directory:
            folder = finder.write_codex_handoff(lead, directory)
            business = json.loads((folder / 'business.json').read_text())
            self.assertEqual(business['social_profiles'][0]['details']['description'], 'Public business bio')
            csv_path = Path(directory) / 'leads.csv'
            finder.write_opportunity_csv([lead], csv_path, lead.opportunity)
            with csv_path.open(encoding='utf-8-sig', newline='') as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(json.loads(row['social_profiles'])[0]['url'], profile['url'])

    def test_retry_prioritizes_profiles_that_exceeded_an_earlier_scan_time_limit(self):
        profiles = [
            {'platform': 'facebook', 'url': 'https://facebook.com/example', 'status': 'public', 'details': {'name': 'Example'}},
            {'platform': 'instagram', 'url': 'https://instagram.com/example', 'status': 'not_checked', 'details': {}},
        ]
        order = []
        def limited(url):
            order.append(url)
            return {'url': url, 'status': 'not_checked', 'note': 'Scan time limit reached.'}
        with patch.object(social.PublicCrawler, 'get', side_effect=limited):
            result = social.crawl_socials({'social_profiles': profiles}, crawl_website=False)
        self.assertEqual(order[0], 'https://instagram.com/example')
        self.assertNotIn('checked_at', result['profiles'][1])
        rediscovered = social.merge_profiles(profiles, social.extract_profiles(
            '<a href="https://facebook.com/example">Facebook</a>', 'https://business.example/'))
        self.assertEqual(rediscovered[0]['status'], 'public')

    def test_transient_failure_preserves_previous_contacts_and_generator_handoff(self):
        old = {'platform': 'facebook', 'url': 'https://facebook.com/example', 'status': 'public',
               'observed_at': '2026-11-01T00:00:00Z', 'details': {'description': 'Saved bio', 'emails': ['hello@example.test']}}
        with patch.object(social.PublicCrawler, 'get', return_value={'status': 'blocked', 'note': 'Access limited', 'url': old['url']}):
            result = social.crawl_socials({'social_profiles': [old]}, crawl_website=False)
        self.assertEqual(result['profiles'][0]['details']['description'], 'Saved bio')
        self.assertEqual(result['profiles'][0]['observed_at'], old['observed_at'])
        self.assertEqual(result['profiles'][0]['status'], 'blocked')
        with tempfile.TemporaryDirectory() as directory:
            lead = finder.Lead(1, 'Example', opportunity='HIGH', social_profiles=result['profiles'], social_scan={'note': result['note']})
            folder = finder.write_codex_handoff(lead, directory)
            finder.write_codex_handoff(finder.Lead(1, 'Example', opportunity='HIGH'), directory)
            business = json.loads((folder / 'business.json').read_text())
            self.assertEqual(business['facebook'], old['url'])
            self.assertEqual(business['social_profiles'][0]['details']['emails'], ['hello@example.test'])
            handoff = json.loads(build_ai_handoff(folder / 'business.json').read_text())
            self.assertEqual(handoff['verified_online_presence']['social_profiles'][0]['url'], old['url'])


class SocialDashboardTests(WorkspaceFixture):
    def test_scan_requires_local_workspace_token_and_blocks_conflicting_work(self):
        payload = {'priority': 'MEDIUM', 'name': self.beta.name}
        headers = {'X-Workspace-Token': dashboard.settings_token}
        with patch.object(dashboard, 'Thread') as thread:
            self.assertEqual(self.client.post('/social-discovery', json=payload).status_code, 403)
            self.assertEqual(self.client.post('/social-discovery', json=[], headers=headers).status_code, 400)
            self.assertEqual(self.client.post('/social-discovery', json=payload, headers={**headers, 'Origin': 'https://untrusted.example'}).status_code, 403)
            response = self.client.post('/social-discovery', json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)
            job_id = response.get_json()['job_id']
            self.assertEqual(self.client.get('/session').get_json()['active_jobs'][0]['kind'], 'social')
            self.assertEqual(self.client.post('/social-discovery', json=payload, headers=headers).status_code, 409)
            self.assertEqual(self.client.post('/generate-landing-page', json=payload).status_code, 409)
            self.assertEqual(self.client.post('/generate', json={'niche': 'care', 'area': 'Test'}).status_code, 409)
            self.assertEqual(self.client.post('/delete-leads', json={'leads': [payload]}, headers=headers).status_code, 409)
            self.assertEqual(dashboard.jobs[job_id]['status'], 'queued')
            self.assertEqual(thread.call_count, 1)

    def test_scan_updates_list_csv_and_handoff_without_altering_followup_or_generated_website(self):
        business_file = self.alpha / 'business.json'
        original = json.loads(business_file.read_text())
        original['services'] = ['Verified service']
        business_file.write_text(json.dumps(original))
        (self.alpha / 'lead_workflow.json').write_text('{"notes":"Saved call notes"}')
        (self.alpha / 'AI_HANDOFF.json').write_text(json.dumps({'custom_instructions': 'Preserve this instruction',
            'verified_online_presence': {'email': 'saved@example.test'}}))
        website_before = (self.alpha / 'website/index.html').read_bytes()
        profile = {'platform': 'instagram', 'url': 'https://instagram.com/example', 'source_url': 'https://business.example/contact',
                   'status': 'public', 'details': {'name': 'Example', 'description': 'Local business bio', 'emails': ['hello@example.test']}}
        report = {'profiles': [profile], 'checked_at': '2026-11-12T00:00:00Z', 'status': 'complete', 'note': 'Found 1 linked profile.'}
        with patch.object(dashboard, 'crawl_socials', return_value=report):
            dashboard.run_social_discovery('social-test', self.alpha)
        self.assertEqual(dashboard.jobs['social-test']['status'], 'complete')
        lead = next(item for item in self.client.get('/leads').get_json()['leads'] if item['client_id'] == self.alpha.name)
        self.assertEqual(lead['instagram'], profile['url'])
        self.assertEqual(lead['social_profiles'][0]['details']['description'], 'Local business bio')
        self.assertEqual(lead['workflow']['notes'], 'Saved call notes')
        self.assertEqual(json.loads(business_file.read_text())['services'], ['Verified service'])
        self.assertEqual((self.alpha / 'website/index.html').read_bytes(), website_before)
        handoff = json.loads((self.alpha / 'AI_HANDOFF.json').read_text())
        self.assertEqual(handoff['verified_online_presence']['instagram'], profile['url'])
        self.assertEqual(handoff['verified_online_presence']['email'], 'saved@example.test')
        self.assertEqual(handoff['custom_instructions'], 'Preserve this instruction')
        with self.client.get('/export') as response:
            rows = list(csv.DictReader(io.StringIO(response.data.decode('utf-8-sig'))))
        row = next(row for row in rows if row['name'] == self.alpha.name)
        self.assertEqual(row['instagram'], profile['url'])
        self.assertEqual(json.loads(row['social_profiles'])[0]['details']['emails'], ['hello@example.test'])

    def test_failed_scan_keeps_saved_business_and_reports_recoverable_failure(self):
        before = (self.beta / 'business.json').read_bytes()
        with patch.object(dashboard, 'crawl_socials', side_effect=RuntimeError('internal failure')):
            dashboard.run_social_discovery('failed-social', self.beta)
        self.assertEqual(dashboard.jobs['failed-social']['status'], 'error')
        self.assertEqual((self.beta / 'business.json').read_bytes(), before)
