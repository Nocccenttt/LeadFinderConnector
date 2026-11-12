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

Search and priority controls stay above the saved list. Open **Filters** for lead status, website status, and **Sort by**. The filter count shows how many filters are active; **Clear filters** returns to the full list while keeping your selected business and sort choice. Use the compact follow-up strip for overdue, due-today, and upcoming leads. The app remembers your sort choice for this workspace.

Select a business to see its website action and preview first. Use **Follow-up**, **Socials**, or **Why this lead** near the business header to open the matching section below the preview. **Quality checks** expands below the preview to show the validation details.

Website files start as **Draft — QA not verified**. Click **Recheck QA** to check the current files locally without another generation run. **QA passed — review pending** means automated checks passed; review business facts, copy, links, and desktop/mobile layouts, then click **Review for delivery** and confirm. Only that explicit action marks the current files **Reviewed for delivery**. Changing the website files or QA report invalidates the previous review. **Revoke review** returns a reviewed website to review pending.

Complete files remain downloadable as a clearly labeled **draft ZIP**, including when QA needs attention. A **reviewed ZIP** requires passing QA and a current delivery review. Downloads pause during a website build. Older QA reports need a local recheck before delivery review because they do not identify the exact files checked.

Follow-up notes, status, and date edits stay with each business while you switch businesses or preview devices and while searches, builds, or list refreshes update the screen. Unsaved drafts also survive a page reload in the same browser tab when browser storage is available. Click **Save follow-up** to write changes to the workspace; the form shows **Unsaved changes**, **Saving…**, **Saved**, or an error with **Retry save**. Edits made during a save stay unsaved until you save them too.

Select a business, open **Socials**, and click **Scan socials** to find social profiles linked from its website and check publicly exposed business bios, emails, phone numbers, and addresses. Open **View profiles** for the details, discovery sources, and observation dates. New business searches also discover profile links and make a short public-detail check. Supported profiles include Facebook, Instagram, LinkedIn company pages, YouTube, TikTok, X/Twitter, Pinterest, Threads, and Bluesky. Social links and collected details are included in CSV exports and saved generator handoffs.

Social discovery follows business website links and organization `sameAs` data; it does not guess accounts from a business name. A business without a website needs an already saved profile as a starting point. Scans respect crawl restrictions and report inaccessible or login-only pages as **Access limited**. Previously collected details retain their original observation dates when a later attempt is blocked. Each scan checks up to three business website pages and twelve profiles within a time limit; another scan can retry profiles that were not checked. No extra API keys are needed for these public-page checks.

Select a business and click **Delete business** to remove that entry, or use **Clear list** to remove all saved businesses, including entries hidden by filters. Both actions ask for confirmation. Wait for an active business search, website build, social scan, or follow-up save for the selected businesses to finish before deleting.

Removed businesses and their saved websites are kept in `outputs/deleted_leads` inside the app folder. They no longer appear in the saved list or future CSV exports; previously exported files remain available.

## Distribution and setup

Follow-up saves are written one at a time so simultaneous tabs cannot share a temporary file. At most two website builds can run together. LeadFinder journals unfinished jobs locally and shows them as **Interrupted** after a restart; it never repeats paid work automatically. For builds started with recovery checkpoints, it restores the previous website and generated copy and keeps interrupted output in the business folder's build backup. Review the preview before retrying. Backups from older app versions may need manual recovery because they lack a checkpoint.

The ZIP contains all application source and assets and installs them into the local app folder. You can delete the extracted ZIP folder after successful setup. To build a fresh clean ZIP, run `python tools/build_windows_zip.py`; the result is `outputs/distribution/LeadFinder-Windows.zip`. The package builder excludes credentials, customer data, virtual environments, generated demos and logs.

The optional standalone `DOWNLOAD_LEADFINDER.bat` uses the `ui/final-polish` branch for downloads. If LeadFinder is already installed and working, it opens the installed copy without downloading updates. Neither installer requires Git, a terminal command, or administrator access. Python is obtained from [python.org](https://www.python.org/ftp/python/3.13.17/) and its Windows signature is verified before installation.

## Build progress and recovery actions

During a website build, the workspace shows the actual stage and elapsed time: preparation, reference research, copy, design, rendering, validation, and packaging. These are work stages, not estimated percentages. The Check step activates when validation begins; delivery review remains separate.

For a rejected key, use **Change API key** and test the replacement before retrying. For failed QA, expand **Quality checks** and use **Recheck QA** or rebuild after correcting the reported issues. Connection interruptions reconnect to the existing job. Failed previews offer **Try loading again**. Failed downloads show an error and keep the download button available for retry; refresh first if the files changed.

## Narrow windows and keyboard controls

**Export CSV** is available at the bottom of the saved-business panel at every supported window width. **Clear list** opens a keyboard-accessible menu: use Up/Down, Home/End, and Enter to choose; Escape closes it and returns focus to its button. Escape also closes the website actions menu and returns focus to its summary. Cancelling a list-clear confirmation returns focus to Clear list.

## Production server and dependency versions

Both the Windows launcher and VS Code run the dashboard through Waitress, bound to `127.0.0.1`. The startup message appears after the server has opened its port. Searches and builds remain background jobs so their duration does not hold an HTTP request open.

`requirements.txt` pins direct and transitive application dependencies to the tested versions. Setup installs that file and verifies Waitress is available. Existing installations need setup rerun after updating these dependencies. The installer uses Python 3.13; Windows Python 3.13 wheels were checked for every pinned dependency. Playwright's matching browser must still be installed during setup. Future dependency updates require refreshing the pins and rerunning the checks.
