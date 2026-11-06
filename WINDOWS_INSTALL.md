# Install LeadFinder on Windows

1. Extract **LeadFinder-Windows.zip**, then double-click **INSTALL_LEADFINDER.bat** inside it. Windows 10/11 (64-bit) and internet access are required for setup.
2. If you were given a `.env` file, put it next to the installer before running it. Otherwise enter your supplied API keys in the setup window. Keys stay on your computer and are never included in the public download.
3. Setup downloads LeadFinder, installs Python if needed, creates a private Python environment, installs the packages and Chromium used for design research, and opens the dashboard when it is ready.
4. Next time, double-click the **LeadFinder** desktop shortcut. It starts the app in the background and opens your browser. Repeated launches reuse the running workspace; they do not reinstall packages.

Files and saved businesses live in `%LOCALAPPDATA%\LeadFinder\app`. The download contains application code, without the developer's saved businesses or generated demos. Closing the browser tab leaves the local server running so you can reopen it quickly.

To change supplied keys later, run `STOP_LEADFINDER.bat` in that installed folder, edit `.env`, then open LeadFinder again. Google Maps is needed to find businesses, DeepSeek to build websites, and Pexels is optional for images. Setup can open the dashboard without keys, but those features require the corresponding keys.

Setup can be retried after a failed download. Existing `.env` files and saved businesses are preserved. If opening fails, a message identifies the problem; startup logs are in the installed app's `logs` folder. The launcher chooses an available local port and remembers it for later launches.

The ZIP contains all application source and assets and installs them into the local app folder. You can delete the extracted ZIP folder after successful setup. To build a fresh clean ZIP, run `python tools/build_windows_zip.py`; the result is `outputs/distribution/LeadFinder-Windows.zip`. The package builder excludes credentials, customer data, virtual environments, generated demos and logs.

The optional standalone `DOWNLOAD_LEADFINDER.bat` downloads the current `codex/leadfinder-fixes` version instead. Neither installer requires Git, a terminal command, or administrator access. Python is obtained from [python.org](https://www.python.org/ftp/python/3.13.17/) and its Windows signature is verified before installation.
