import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from tools.build_windows_zip import build_distribution


class WindowsDistributionTests(unittest.TestCase):
    def test_zip_contains_runnable_app_and_excludes_credentials_and_business_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = {
                'INSTALL_LEADFINDER.bat': '@echo off', 'START_LEADFINDER.bat': '@echo off',
                'STOP_LEADFINDER.bat': '@echo off', 'DOWNLOAD_LEADFINDER.bat': '@echo off',
                '.env.example': 'DEEPSEEK_API_KEY=', 'requirements.txt': 'Flask',
                'preview_dashboard.py': 'print("app")', 'reference_website_generator.py': 'print("generator")',
                'templates/dashboard.html': '<h1>Workspace</h1>', 'static/dashboard.js': 'console.log("ready")',
                'scripts/Install-LeadFinder.ps1': 'Write-Host setup', 'scripts/Start-LeadFinder.ps1': 'Write-Host start',
                'scripts/Stop-LeadFinder.ps1': 'Write-Host stop', 'scripts/launch_dashboard.py': 'print("launch")',
                'assets/fonts/Geist.ttf': 'test-font',
                '.env': 'PRIVATE-TEST-KEY', '.venv/secret.txt': 'PRIVATE-TEST-KEY',
                'codex_handoffs/HIGH/Customer/business.json': 'PRIVATE-CUSTOMER-DATA',
                'outputs/leads.csv': 'PRIVATE-CUSTOMER-DATA', 'logs/debug.log': 'PRIVATE-TEST-KEY',
            }
            for name, value in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(value)
            result = build_distribution(root / 'out.zip', source=root)
            with ZipFile(result) as archive:
                names = set(archive.namelist())
                self.assertTrue({'LeadFinder/INSTALL_LEADFINDER.bat', 'LeadFinder/READ_ME_FIRST.txt',
                    'LeadFinder/.env.example', 'LeadFinder/app/preview_dashboard.py',
                    'LeadFinder/app/reference_website_generator.py', 'LeadFinder/app/scripts/launch_dashboard.py',
                    'LeadFinder/app/assets/fonts/Geist.ttf'} <= names)
                payload = b''.join(archive.read(name) for name in names)
                self.assertNotIn(b'PRIVATE-TEST-KEY', payload)
                self.assertNotIn(b'PRIVATE-CUSTOMER-DATA', payload)
                self.assertFalse(any('/.venv/' in name or '/codex_handoffs/' in name or '/outputs/' in name or name.endswith('/.env') for name in names))

    def test_missing_required_app_file_prevents_incomplete_distribution(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'app.zip'
            with self.assertRaises(ValueError):
                build_distribution(target, source=Path(folder))
            self.assertFalse(target.exists())
