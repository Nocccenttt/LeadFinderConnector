# Install LeadFinder on Windows

1. Extract **LeadFinder-Windows.zip**, then double-click **INSTALL_LEADFINDER.bat** inside it. Windows 10/11 (64-bit) and internet access are required for setup.
2. If you were given a `.env` file, put it next to the installer before running it. Otherwise enter your supplied API keys in the setup window. Keys stay on your computer and are never included in the public download.
3. Setup downloads LeadFinder, installs Python if needed, creates a private Python environment, installs the packages and Chromium used for design research, and opens the dashboard when it is ready.
4. Next time, double-click the **LeadFinder** desktop shortcut. It starts the app in the background and opens your browser. Repeated launches reuse the running workspace; they do not reinstall packages.

Files and saved businesses live in `%LOCALAPPDATA%\LeadFinder\app`. The download contains application code, without the developer's saved businesses or generated demos. Closing the browser tab leaves the local server running so you can reopen it quickly.

To change supplied keys later, click **API keys** in the app. Enter a replacement, optionally click **Test**, then click **Save keys**. Blank fields keep their saved values; **Remove saved key** explicitly clears a key. Saved changes apply to new requests immediately without restarting. Google Maps is needed to find businesses, DeepSeek to build websites, and Pexels is optional for images. Setup can open the dashboard without keys, but those features require the corresponding keys.

Setup can be retried after a failed download. Existing `.env` files and saved businesses are preserved. If opening fails, a message identifies the problem; startup logs are in the installed app's `logs` folder. The launcher chooses an available local port and remembers it for later launches.

## Setting up a Git checkout

If you open LeadFinder from a Git checkout in VS Code, run the installer from that repository folder:

```powershell
.\INSTALL_LEADFINDER.bat
```

The installer recognizes the repository layout and prepares `.venv`, packages, and the browser for that checkout. Existing `.env`, saved businesses in `codex_handoffs`, and files in `outputs` stay in place. The desktop shortcut points to this checkout; setup does not create a separate app workspace in `%LOCALAPPDATA%`.

After setup succeeds, open the app again with:

```powershell
.\START_LEADFINDER.bat
```

If the launcher reports that setup is incomplete, rerun `INSTALL_LEADFINDER.bat` in the same folder. A Git pull updates application code; local setup creates the Python environment needed to run it.

## Managing the saved business list

Use **Sort by** to order businesses by priority, opportunity score in either direction, or name A–Z or Z–A. The app remembers your sort choice for this workspace, and sorting works with the search and status filters.

Select a business and click **Delete business** to remove that entry, or use **Clear list** to remove all saved businesses, including entries hidden by filters. Both actions ask for confirmation. Wait for an active business search or a website build for the selected businesses to finish before deleting.

Removed businesses and their saved websites are kept in `outputs/deleted_leads` inside the app folder. They no longer appear in the saved list or future CSV exports; previously exported files remain available.

## Distribution and setup

The ZIP contains all application source and assets and installs them into the local app folder. You can delete the extracted ZIP folder after successful setup. To build a fresh clean ZIP, run `python tools/build_windows_zip.py`; the result is `outputs/distribution/LeadFinder-Windows.zip`. The package builder excludes credentials, customer data, virtual environments, generated demos and logs.

The optional standalone `DOWNLOAD_LEADFINDER.bat` uses the current `FinalFinal` version for downloads. If LeadFinder is already installed and working, it opens the installed copy without downloading updates. Neither installer requires Git, a terminal command, or administrator access. Python is obtained from [python.org](https://www.python.org/ftp/python/3.13.17/) and its Windows signature is verified before installation.
