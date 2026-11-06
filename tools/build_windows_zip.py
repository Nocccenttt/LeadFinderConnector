"""Package the application explicitly, excluding local credentials and business data."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
README = """LEADFINDER FOR WINDOWS

1. Extract the entire ZIP first (right-click > Extract All).
2. If you were provided a .env file, put it beside INSTALL_LEADFINDER.bat.
   Otherwise enter your supplied keys when setup asks for them.
3. Double-click INSTALL_LEADFINDER.bat and wait for setup to finish.
   Setup opens the app and creates a LeadFinder shortcut on your desktop.

NEXT TIME: Double-click the LeadFinder desktop shortcut.

Windows 10/11 (64-bit) and internet access are required for initial setup.
Setup downloads Python if needed, the app packages, and the browser used
for design research. No Git, commands, or administrator account are needed.

The app and your saved businesses are installed in:
%LOCALAPPDATA%\\LeadFinder\\app
After successful setup, you can move or delete this extracted ZIP folder.

Google Maps keys enable business searches. DeepSeek enables website builds.
Pexels is optional for images. Keys are supplied separately, not in this ZIP.
To change keys later, run STOP_LEADFINDER.bat in the installed app folder,
edit its .env file, then open LeadFinder again.

If setup fails, read the error and run the installer again to retry.
If opening fails, details are in the installed app's logs folder.
"""


def build_distribution(output, source=ROOT):
    source, output = Path(source), Path(output)
    files = [*source.glob('*.py')]
    files += [source / name for name in ('requirements.txt', '.env.example', 'START_LEADFINDER.bat',
                                        'STOP_LEADFINDER.bat', 'DOWNLOAD_LEADFINDER.bat')]
    extensions = {'.py', '.ps1', '.html', '.css', '.js', '.ttf', '.woff', '.woff2',
                  '.png', '.jpg', '.jpeg', '.webp', '.svg', '.ico'}
    for name in ('assets', 'static', 'templates', 'scripts'):
        files += [file for file in (source / name).rglob('*')
                  if file.is_file() and '__pycache__' not in file.parts and file.suffix.lower() in extensions]
    required = ['preview_dashboard.py', 'templates/dashboard.html', 'static/dashboard.js',
                'scripts/Install-LeadFinder.ps1', 'scripts/Start-LeadFinder.ps1',
                'scripts/Stop-LeadFinder.ps1', 'scripts/launch_dashboard.py', 'assets/fonts/Geist.ttf']
    for name in required:
        if source / name not in files:
            raise ValueError(f'Required application file missing: {name}')
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        archive.write(source / 'INSTALL_LEADFINDER.bat', 'LeadFinder/INSTALL_LEADFINDER.bat')
        archive.write(source / '.env.example', 'LeadFinder/.env.example')
        archive.writestr('LeadFinder/READ_ME_FIRST.txt', README)
        for file in sorted(set(files)):
            if file.is_symlink():
                raise ValueError(f'Application package cannot contain linked files: {file}')
            archive.write(file, 'LeadFinder/app/' + file.relative_to(source).as_posix())
    return output


if __name__ == '__main__':
    result = build_distribution(ROOT / 'outputs/distribution/LeadFinder-Windows.zip')
    print(f'Created {result} ({result.stat().st_size / 1024 / 1024:.1f} MB)')
