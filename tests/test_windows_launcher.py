"""Exercise Windows launchers against a real installed workspace, without paid APIs."""
import hashlib
import http.server
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Requires Windows PowerShell')
class WindowsLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='LeadFinder test ')
        if os.getenv('LEADFINDER_TEST_APP'):
            cls.app = Path(os.environ['LEADFINDER_TEST_APP']).resolve()
        else:
            cls.app = Path(cls.temp.name) / 'app'
            cls.app.mkdir()
            for source in REPO.glob('*.py'):
                shutil.copy2(source, cls.app / source.name)
            for name in ['assets', 'static', 'templates', 'scripts']:
                shutil.copytree(REPO / name, cls.app / name)
            shutil.copy2(REPO / '.env.example', cls.app / '.env')
            subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(cls.app / '.venv')], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.address = f'http://127.0.0.1:{self.port}'
        self.addCleanup(self.stop)

    def command(self, script='Start-LeadFinder.ps1', app=None):
        command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                   str(REPO / 'scripts' / script), '-AppRoot', str(app or self.app)]
        if script.startswith('Start'):
            command += ['-Port', str(self.port), '-NoBrowser', '-NoDialogs']
        return command

    def stop(self):
        subprocess.run(self.command('Stop-LeadFinder.ps1'), capture_output=True, timeout=20)

    def launch(self):
        result = subprocess.run(self.command(), capture_output=True, text=True, timeout=75)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ready_launch_repeated_click_and_stop_preserve_settings(self):
        before = hashlib.sha256((self.app / '.env').read_bytes()).hexdigest()
        self.launch()
        self.assertEqual(requests.get(self.address + '/health', timeout=3).json(), {'app': 'leadfinder', 'root': str(self.app)})
        self.assertIn('Find businesses', requests.get(self.address, timeout=3).text)
        server_id = (self.app / 'logs' / 'dashboard.pid').read_text().strip()
        self.launch()
        self.assertEqual((self.app / 'logs' / 'dashboard.pid').read_text().strip(), server_id)
        self.assertEqual(hashlib.sha256((self.app / '.env').read_bytes()).hexdigest(), before)
        self.stop()
        with self.assertRaises(requests.ConnectionError):
            requests.get(self.address + '/health', timeout=2)

    def test_simultaneous_clicks_open_one_server(self):
        processes = [subprocess.Popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        for process in processes:
            output, error = process.communicate(timeout=75)
            self.assertEqual(process.returncode, 0, output + error)
        self.assertEqual(requests.get(self.address + '/health', timeout=3).json()['root'], str(self.app))

    def test_occupied_port_leaves_other_app_running(self):
        class OtherApp(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"app":"another-application"}')

            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', self.port), OtherApp)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        result = subprocess.run(self.command(), capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.port), result.stdout + result.stderr)
        self.assertEqual(requests.get(self.address, timeout=2).json()['app'], 'another-application')

    def test_startup_failure_returns_error_and_log(self):
        with tempfile.TemporaryDirectory(prefix='LeadFinder broken ') as folder:
            app = Path(folder)
            (app / 'scripts').mkdir()
            shutil.copy2(REPO / 'scripts' / 'launch_dashboard.py', app / 'scripts' / 'launch_dashboard.py')
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(app / '.venv')], check=True, capture_output=True)
            (app / 'preview_dashboard.py').write_text('raise RuntimeError("Deliberate startup failure")')
            result = subprocess.run(self.command(app=app), capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('dashboard.err.log', result.stdout + result.stderr)
            self.assertIn('Deliberate startup failure', (app / 'logs' / 'dashboard.err.log').read_text())

    def test_default_launch_finds_another_port_without_stopping_other_app(self):
        class OtherApp(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"app":"another-application"}')

            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', self.port), OtherApp)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port_file = self.app / 'logs' / 'dashboard.port'
        port_file.parent.mkdir(exist_ok=True)
        port_file.write_text(str(self.port))
        command = self.command()
        position = command.index('-Port')
        del command[position:position+2]
        for _ in range(2):
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        selected = int(port_file.read_text().strip())
        self.assertNotEqual(selected, self.port)
        self.assertEqual(requests.get(f'http://127.0.0.1:{selected}/health', timeout=3).json()['root'], str(self.app))
        self.assertEqual(requests.get(self.address, timeout=2).json()['app'], 'another-application')

    def test_scripts_parse_on_windows_powershell(self):
        source = '''
        $ErrorActionPreference='Stop'
        Get-ChildItem -LiteralPath (Join-Path $env:LEADFINDER_TEST_REPO 'scripts') -Filter *.ps1 | ForEach-Object {
            $errors=$null; $tokens=$null
            [Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$tokens,[ref]$errors) | Out-Null
            if ($errors) { throw ($errors | Out-String) }
        }
        $text=[IO.File]::ReadAllText((Join-Path $env:LEADFINDER_TEST_REPO 'DOWNLOAD_LEADFINDER.bat'))
        $marker='#'+' LEADFINDER_SETUP'; $errors=$null; $tokens=$null
        [Management.Automation.Language.Parser]::ParseInput($text.Substring($text.IndexOf($marker)+$marker.Length),[ref]$tokens,[ref]$errors) | Out-Null
        if ($errors) { throw ($errors | Out-String) }
        '''
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', source],
            env={**os.environ, 'LEADFINDER_TEST_REPO': str(REPO)}, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(os.getenv('LEADFINDER_TEST_APP'), 'Requires a real installer-prepared workspace')
    def test_installer_second_run_is_offline_and_preserves_data(self):
        with tempfile.TemporaryDirectory(prefix="LeadFinder's download & setup ") as folder:
            installer = Path(folder) / 'DOWNLOAD_LEADFINDER.bat'
            shutil.copy2(REPO / installer.name, installer)
            sentinel = self.app / 'codex_handoffs' / 'installer-test.txt'
            sentinel.parent.mkdir(exist_ok=True)
            sentinel.write_text('Saved business data must survive setup.')
            self.addCleanup(lambda: sentinel.unlink(missing_ok=True))
            before = (self.app / '.env').read_bytes()
            config = self.app / 'requirements.txt'
            modified = config.stat().st_mtime_ns
            env = {**os.environ, 'LEADFINDER_INSTALL_ROOT': str(self.app.parent), 'LEADFINDER_TEST_BAT': str(installer),
                   'LEADFINDER_NO_LAUNCH': '1', 'HTTPS_PROXY': 'http://127.0.0.1:1'}
            result = subprocess.run(f'"{os.environ["COMSPEC"]}" /d /s /c ""%LEADFINDER_TEST_BAT%""',
                env=env, capture_output=True, text=True, timeout=25, stdin=subprocess.DEVNULL)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('already installed', result.stdout)
            self.assertEqual((self.app / '.env').read_bytes(), before)
            self.assertEqual(config.stat().st_mtime_ns, modified)
            self.assertEqual(sentinel.read_text(), 'Saved business data must survive setup.')
            self.assertFalse((self.app / "Brown's Tree Service - Website Demo.zip").exists())
