import os
import unittest
from unittest.mock import Mock, patch

import requests
from dotenv import dotenv_values

import api_settings
import preview_dashboard as dashboard
from test_dashboard import WorkspaceFixture


class APISettingsTests(WorkspaceFixture):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {name: '' for name, _ in api_settings.PROVIDERS.values()})
        environment.start()
        self.addCleanup(environment.stop)
        self.token = self.client.get('/api-settings').get_json()['token']

    def post(self, data):
        return self.client.post('/api-settings', json=data, headers={'X-Settings-Token': self.token})

    def test_status_never_returns_saved_secrets(self):
        os.environ['DEEPSEEK_API_KEY'] = 'test-old-secret-5736'
        response = self.client.get('/api-settings')
        data = response.get_json()
        self.assertEqual(data['providers']['deepseek'], {'configured': True, 'ending': '5736'})
        self.assertNotIn('test-old-secret', response.get_data(as_text=True))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_settings_reject_nonlocal_hostnames(self):
        self.assertEqual(self.client.get('/api-settings', headers={'Host': 'untrusted.example'}).status_code, 403)
        response = self.client.post('/api-settings', json={'action': 'save', 'keys': {'deepseek': 'test-replacement'}},
            headers={'Host': 'untrusted.example', 'X-Settings-Token': self.token})
        self.assertEqual(response.status_code, 403)
        self.assertFalse((self.root / '.env').exists())

    def test_save_updates_running_app_and_persists_without_losing_other_settings(self):
        config = self.root / '.env'
        config.write_text("# Keep this comment\nCUSTOM_SETTING=untouched\nGOOGLE_MAPS_API_KEY='test-maps-keep'\nDEEPSEEK_API_KEY='old-key'\n")
        os.environ['GOOGLE_MAPS_API_KEY'] = 'test-maps-keep'
        result = self.post({'action': 'save', 'keys': {'deepseek': '  test-replacement-1234  '}})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(os.getenv('DEEPSEEK_API_KEY'), 'test-replacement-1234')
        saved = dotenv_values(config)
        self.assertEqual(saved['DEEPSEEK_API_KEY'], 'test-replacement-1234')
        self.assertEqual(saved['GOOGLE_MAPS_API_KEY'], 'test-maps-keep')
        self.assertEqual(saved['CUSTOM_SETTING'], 'untouched')
        self.assertIn('# Keep this comment', config.read_text())
        self.assertTrue(self.client.get('/session').get_json()['capabilities']['website_configured'])
        self.assertNotIn('test-replacement', result.get_data(as_text=True))

    def test_blank_keeps_key_and_explicit_remove_clears_it(self):
        self.post({'action': 'save', 'keys': {'deepseek': 'test-original-9876'}})
        self.post({'action': 'save', 'keys': {'deepseek': '', 'google': 'test-maps-1234'}})
        self.assertEqual(os.getenv('DEEPSEEK_API_KEY'), 'test-original-9876')
        response = self.post({'action': 'save', 'keys': {'deepseek': None}})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.get('/session').get_json()['capabilities']['website_configured'])
        self.assertEqual(dotenv_values(self.root / '.env')['DEEPSEEK_API_KEY'], '')

    def test_invalid_input_and_missing_token_cannot_change_credentials(self):
        for keys in ({'deepseek': 'bad\nINJECTED=value'}, {'deepseek': '****5736'}, {'unknown': 'abc'}, {'deepseek': []}):
            self.assertEqual(self.post({'action': 'save', 'keys': keys}).status_code, 400)
        self.assertEqual(self.client.post('/api-settings', json={'action': 'save', 'keys': {'deepseek': 'test-valid-key'}}).status_code, 403)
        self.assertFalse((self.root / '.env').exists())
        self.assertEqual(self.post({'action': 'test', 'provider': []}).status_code, 400)

    def test_failed_file_write_keeps_previous_key_in_file_and_running_app(self):
        self.post({'action': 'save', 'keys': {'deepseek': 'test-original-9876'}})
        before = (self.root / '.env').read_bytes()
        with patch.object(api_settings.os, 'replace', side_effect=PermissionError):
            response = self.post({'action': 'save', 'keys': {'deepseek': 'test-replacement-1234'}})
        self.assertEqual(response.status_code, 500)
        self.assertEqual((self.root / '.env').read_bytes(), before)
        self.assertEqual(os.getenv('DEEPSEEK_API_KEY'), 'test-original-9876')
        self.assertEqual(list(self.root.glob('.api-settings-*')), [])

    def test_authentication_check_uses_candidate_without_saving_or_generating(self):
        candidate = 'test-unsaved-key-1234'
        with patch.object(api_settings.requests, 'request', return_value=Mock(status_code=200, json=lambda: {'data': []})) as provider:
            result = self.post({'action': 'test', 'provider': 'deepseek', 'key': candidate}).get_json()
        self.assertTrue(result['ok'])
        self.assertEqual(provider.call_args.args, ('GET', 'https://api.deepseek.com/models'))
        self.assertEqual(provider.call_args.kwargs['headers']['Authorization'], f'Bearer {candidate}')
        self.assertFalse(os.getenv('DEEPSEEK_API_KEY'))
        self.assertFalse((self.root / '.env').exists())

    def test_rejected_key_and_connection_failure_are_safe_and_actionable(self):
        key = 'test-private-rejected-5736'
        for failure in [Mock(status_code=401), requests.ConnectionError(key)]:
            with patch.object(api_settings.requests, 'request', **({'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure})):
                response = self.post({'action': 'test', 'provider': 'deepseek', 'key': key})
            self.assertFalse(response.get_json()['ok'])
            self.assertNotIn(key, response.get_data(as_text=True))

    def test_maps_and_image_checks_use_their_own_provider(self):
        with patch.object(api_settings.requests, 'request', return_value=Mock(status_code=200, json=lambda: {})) as provider:
            self.assertTrue(self.post({'action': 'test', 'provider': 'google', 'key': 'test-maps-key'}).get_json()['ok'])
        self.assertEqual(provider.call_args.args, ('POST', 'https://places.googleapis.com/v1/places:searchText'))
        self.assertEqual(provider.call_args.kwargs['headers']['X-Goog-FieldMask'], 'places.id')
        with patch.object(api_settings.requests, 'request', return_value=Mock(status_code=200, json=lambda: {'photos': []})) as provider:
            self.assertTrue(self.post({'action': 'test', 'provider': 'pexels', 'key': 'test-images-key'}).get_json()['ok'])
        self.assertEqual(provider.call_args.args, ('GET', 'https://api.pexels.com/v1/search'))

    def test_job_auth_error_points_to_settings_and_hides_secret(self):
        error = RuntimeError('test-private-key')
        error.status_code = 401
        with patch.object(dashboard, 'run_pipeline', side_effect=error):
            dashboard.run_landing_page('auth-error', self.alpha)
        job = self.client.get('/landing-page-status?job_id=auth-error').get_json()
        self.assertEqual(job['status'], 'error')
        self.assertIn('API keys', job['message'])
        self.assertNotIn('test-private-key', job['message'])
