# LeadFinder

LeadFinder is the internal Wolf Forge prospecting and website-demo workspace.

It finds local businesses, ranks opportunities, saves business records, builds website demos, validates generated sites, previews them in the dashboard, and packages approved output for delivery.

## Windows setup

For a normal Windows installation, see [docs/WINDOWS_INSTALL.md](docs/WINDOWS_INSTALL.md).

From a Git checkout:

```powershell
.\INSTALL_LEADFINDER.bat
```

Then launch with:

```powershell
.\START_LEADFINDER.bat
```

Stop the local app with:

```powershell
.\STOP_LEADFINDER.bat
```

## Development

Install runtime dependencies:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Run the regression suite:

```powershell
python -m unittest discover -s tests -v
```

The GitHub workflow also runs browser checks and the Windows installer/launcher suite.

## Source of truth

The repository root is the application source of truth. Generated client workspaces, logs, build output, distribution archives, and local credentials are intentionally excluded from Git.

Windows distributions are generated from the root source:

```powershell
python tools/build_windows_zip.py
```

The generated archive is written to `outputs/distribution/LeadFinder-Windows.zip`.

## Repository layout

- `preview_dashboard.py` — local dashboard server and API
- `templates/`, `static/` — dashboard UI
- `pipeline_runner.py` — website build pipeline
- `website_validator.py` — generated-site validation
- `scripts/` — Windows install/start/stop helpers
- `tools/` — distribution tooling
- `tests/` — regression, browser, and Windows tests
- `docs/` — setup, audits, design notes, and archived internal notes

## Credentials and generated data

Do not commit `.env`, API keys, saved lead workspaces, generated websites, logs, or exported distributions.

See [SECURITY.md](SECURITY.md) for security notes.
