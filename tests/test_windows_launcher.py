"""Exercise Windows launchers against a real installed workspace, without paid APIs."""
import hashlib
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from zipfile import ZipFile

import requests

REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Requires Windows PowerShell')
class InstallerWrapperTests(unittest.TestCase):
    def test_installer_layouts_and_failure_codes_support_special_characters(self):
        for packaged in (False, True):
            for expected_code in (0, 7):
                with self.subTest(packaged=packaged, expected_code=expected_code), tempfile.TemporaryDirectory(prefix="LeadFinder's setup & (test) ") as folder:
                    root = Path(folder)
                    shutil.copy2(REPO / 'INSTALL_LEADFINDER.bat', root / 'INSTALL_LEADFINDER.bat')
                    app = root / 'app' if packaged else root
                    script = app / 'scripts' / 'Install-LeadFinder.ps1'
                    script.parent.mkdir(parents=True)
                    script.write_text('''param([string]$SourceRoot, [string]$ConfigSource)
@{source=$SourceRoot; config=$ConfigSource; root=(Split-Path -Parent $PSScriptRoot)} | ConvertTo-Json | Set-Content -LiteralPath $env:LEADFINDER_TEST_RESULT
exit ([int]$env:LEADFINDER_TEST_EXIT)
''', encoding='utf-8')
                    result_file = root / 'result.json'
                    env = {**os.environ, 'LEADFINDER_TEST_BAT': str(root / 'INSTALL_LEADFINDER.bat'),
                           'LEADFINDER_TEST_RESULT': str(result_file), 'LEADFINDER_TEST_EXIT': str(expected_code)}
                    result = subprocess.run(f'"{os.environ["COMSPEC"]}" /d /s /c ""%LEADFINDER_TEST_BAT%""',
                        env=env, capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
                    self.assertEqual(result.returncode, expected_code, result.stdout + result.stderr)
                    recorded = json.loads(result_file.read_text(encoding='utf-8-sig'))
                    self.assertEqual(Path(recorded['root']), app)
                    self.assertEqual(recorded['source'], str(app) if packaged else '')
                    self.assertEqual(recorded['config'], str(root / '.env') if packaged else '')


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

    def test_startup_timeout_stops_only_the_process_tree_it_started(self):
        with tempfile.TemporaryDirectory(prefix="LeadFinder's slow startup & (test) ") as folder:
            app = Path(folder)
            (app / 'scripts').mkdir()
            shutil.copy2(REPO / 'scripts' / 'launch_dashboard.py', app / 'scripts' / 'launch_dashboard.py')
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(app / '.venv')], check=True, capture_output=True)
            (app / 'preview_dashboard.py').write_text('''import os, time
from pathlib import Path
Path(__file__).with_name('started.pid').write_text(str(os.getpid()))
while True:
    time.sleep(1)
''', encoding='utf-8')
            other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
            try:
                result = subprocess.run(self.command(app=app) + ['-StartupTimeoutSeconds', '2'],
                    capture_output=True, text=True, timeout=20)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('did not become ready within 2 seconds', result.stdout + result.stderr)
                self.assertIsNone(other.poll(), 'Startup cleanup must not stop another Python process.')
                child_pid = int((app / 'started.pid').read_text())
                check = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                    '[bool](Get-Process -Id ([int]$env:LEADFINDER_TEST_PID) -ErrorAction SilentlyContinue)'],
                    env={**os.environ, 'LEADFINDER_TEST_PID': str(child_pid)}, capture_output=True, text=True, timeout=10)
                self.assertEqual(check.stdout.strip(), 'False', check.stdout + check.stderr)
                self.assertFalse((app / 'logs' / 'dashboard.pid').exists())
            finally:
                subprocess.run(self.command('Stop-LeadFinder.ps1', app=app), capture_output=True, timeout=20)
                other.terminate()
                other.wait(timeout=5)

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

    def test_download_repair_rejects_busy_workspace_before_replacing_files(self):
        with tempfile.TemporaryDirectory(prefix="LeadFinder's repair & (test) ") as folder:
            root = Path(folder)
            app = root / 'installed' / 'app'
            (app / 'scripts').mkdir(parents=True)
            shutil.copy2(REPO / 'scripts' / 'launch_dashboard.py', app / 'scripts' / 'launch_dashboard.py')
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(app / '.venv')], check=True, capture_output=True)
            # This real local server reports an active job without contacting a provider.
            main = app / 'preview_dashboard.py'
            main.write_text('''from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, os
from pathlib import Path
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = {'active_jobs': [{'kind': 'leads', 'status': 'running'}]} if self.path == '/session' else {'app': 'leadfinder', 'root': str(Path(__file__).resolve().parent)}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
ThreadingHTTPServer(('127.0.0.1', int(os.environ['LEADFINDER_PORT'])), Handler).serve_forever()
''', encoding='utf-8')
            originals = {main: main.read_bytes()}
            for name in ('.env', 'codex_handoffs/saved-business.txt', 'outputs/saved-export.txt'):
                target = app / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('Saved local work.', encoding='utf-8')
                originals[target] = target.read_bytes()
            archive_path = root / 'download.zip'
            with ZipFile(archive_path, 'w') as archive:
                archive.writestr('source/preview_dashboard.py', '# Updated application; must not overwrite active work.\n')
                for name in ('Install-LeadFinder.ps1', 'Stop-LeadFinder.ps1'):
                    archive.write(REPO / 'scripts' / name, 'source/scripts/' + name)
                for name in ('assets/probe.txt', 'static/probe.txt', 'templates/probe.txt'):
                    archive.writestr('source/' + name, 'Update payload')
            downloaded_installer = root / 'DOWNLOAD_LEADFINDER.bat'
            shutil.copy2(REPO / 'DOWNLOAD_LEADFINDER.bat', downloaded_installer)
            command = '''
function Invoke-WebRequest {
    param($Uri, $OutFile, $TimeoutSec, [switch]$UseBasicParsing)
    Copy-Item -LiteralPath $env:LEADFINDER_TEST_ARCHIVE -Destination $OutFile
}
$text=[IO.File]::ReadAllText($env:LEADFINDER_SETUP_FILE)
$marker='#'+' LEADFINDER_SETUP'
& ([scriptblock]::Create($text.Substring($text.IndexOf($marker)+$marker.Length)))
'''
            env = {**os.environ, 'LEADFINDER_INSTALL_ROOT': str(app.parent),
                   'LEADFINDER_SETUP_FILE': str(downloaded_installer),
                   'LEADFINDER_TEST_ARCHIVE': str(archive_path),
                   'LEADFINDER_NO_LAUNCH': '1', 'LEADFINDER_SKIP_KEY_PROMPT': '1'}
            try:
                started = subprocess.run(self.command(app=app), capture_output=True, text=True, timeout=30)
                self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
                result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                    env=env, capture_output=True, text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('A search or build is running', result.stdout + result.stderr)
                for path, content in originals.items():
                    self.assertEqual(path.read_bytes(), content, str(path))
                self.assertFalse((app / 'assets' / 'probe.txt').exists())
                self.assertTrue(requests.get(self.address + '/session', timeout=3).json()['active_jobs'])
            finally:
                subprocess.run(self.command('Stop-LeadFinder.ps1', app=app), capture_output=True, timeout=20)

    @unittest.skipUnless(os.getenv('LEADFINDER_TEST_APP'), 'Requires a real installer-prepared workspace')
    def test_repository_setup_repairs_missing_pythonw_in_place(self):
        installer = self.app / 'INSTALL_LEADFINDER.bat'
        original_installer = installer.read_bytes() if installer.exists() else None
        config = (self.app / '.env').read_bytes()
        business = self.app / 'codex_handoffs' / 'repository-setup-test.txt'
        output = self.app / 'outputs' / 'repository-setup-test.txt'
        for sentinel in (business, output):
            self.assertFalse(sentinel.exists())
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text('Saved work must survive repository setup.', encoding='utf-8')
            self.addCleanup(lambda path=sentinel: path.unlink(missing_ok=True))
        pythonw = self.app / '.venv' / 'Scripts' / 'pythonw.exe'
        self.assertTrue(pythonw.is_file())
        self.assertTrue((self.app / 'scripts' / 'Install-LeadFinder.ps1').is_file())
        with tempfile.TemporaryDirectory(prefix='LeadFinder repository setup ') as folder:
            temporary = Path(folder)
            backup = temporary / 'pythonw.exe'
            wrong_install = temporary / 'must not install here'
            shortcuts = temporary / 'shortcuts'
            shutil.copy2(REPO / 'INSTALL_LEADFINDER.bat', installer)
            shutil.copy2(pythonw, backup)
            pythonw.unlink()
            try:
                base_python = Path(getattr(sys, '_base_executable', sys.executable))
                env = {**os.environ, 'LEADFINDER_TEST_BAT': str(installer),
                       'LEADFINDER_INSTALL_ROOT': str(wrong_install),
                       'LEADFINDER_SHORTCUT_FOLDER': str(shortcuts),
                       'LEADFINDER_NO_LAUNCH': '1', 'LEADFINDER_SKIP_KEY_PROMPT': '1',
                       'PATH': str(base_python.parent) + os.pathsep + os.environ.get('PATH', '')}
                result = subprocess.run(f'"{os.environ["COMSPEC"]}" /d /s /c ""%LEADFINDER_TEST_BAT%""',
                    env=env, capture_output=True, text=True, timeout=240, stdin=subprocess.DEVNULL)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(pythonw.is_file(), 'Repository setup must restore the missing windowless Python launcher.')
                self.assertFalse(wrong_install.exists(), 'Repository setup must prepare this folder in place.')
                self.assertTrue((shortcuts / 'LeadFinder.lnk').is_file())
                self.assertEqual((self.app / '.env').read_bytes(), config)
                for sentinel in (business, output):
                    self.assertEqual(sentinel.read_text(encoding='utf-8'), 'Saved work must survive repository setup.')
                self.launch()
                self.assertEqual(requests.get(self.address + '/health', timeout=3).json(),
                                 {'app': 'leadfinder', 'root': str(self.app)})
            finally:
                if not pythonw.exists():
                    shutil.copy2(backup, pythonw)
                if original_installer is None:
                    installer.unlink(missing_ok=True)
                else:
                    installer.write_bytes(original_installer)

    @unittest.skipUnless(os.getenv('LEADFINDER_TEST_APP'), 'Requires a real installer-prepared workspace')
    def test_zip_update_restarts_idle_app_and_preserves_keys(self):
        self.launch()
        before = (self.app / '.env').read_bytes()
        env = {**os.environ, 'LEADFINDER_INSTALL_ROOT': str(self.app.parent)}
        result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(REPO / 'scripts' / 'Install-LeadFinder.ps1'), '-SourceRoot', str(REPO),
            '-ShortcutFolder', str(Path(self.temp.name) / 'shortcuts'), '-NoLaunch', '-SkipKeyPrompt'],
            env=env, capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.app / '.env').read_bytes(), before)
        self.launch()
        settings = requests.get(self.address + '/api-settings', timeout=3)
        self.assertEqual(settings.status_code, 200)
        self.assertIn('providers', settings.json())

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
