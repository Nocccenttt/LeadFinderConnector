"""Exercise the production HTTP server without services or customer data."""
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
import requests


class ProductionServerTests(unittest.TestCase):
    def test_local_http_health_parallel_requests_and_errors(self):
        program = '''
from flask import Flask
from dashboard_server import serve_dashboard
app = Flask(__name__)
@app.get('/health')
def health(): return {'app': 'test'}
@app.get('/failure')
def failure(): raise RuntimeError('private-error-detail')
serve_dashboard(app, 0)
'''
        process = subprocess.Popen([sys.executable, '-u', '-c', program], stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True)
        try:
            line = process.stdout.readline().strip()
            self.assertTrue(line.startswith('Running on http://127.0.0.1:'), line)
            url = line.removeprefix('Running on ')
            def fetch(_):
                response = requests.get(url + '/health', timeout=5)
                self.assertEqual(response.json(), {'app': 'test'})
                self.assertIn('waitress', response.headers['Server'].lower())
            with ThreadPoolExecutor(max_workers=8) as workers:
                list(workers.map(fetch, range(16)))
            response = requests.get(url + '/failure', timeout=5)
            self.assertEqual(response.status_code, 500)
            self.assertNotIn('private-error-detail', response.text)
        finally:
            process.terminate()
            process.wait(timeout=10)
            process.stdout.close()
