# LeadFinder audit — 2026-10-29

Reviewed the active Flask dashboard, prospecting and handoff flow, DeepSeek page generator, validation, batch execution, delivery packaging, startup script, and CI configuration.

## Findings fixed

| Priority | Finding | Fix |
| --- | --- | --- |
| High | Client names and legacy preview paths could resolve outside the intended handoff directories. | Resolve exact client folders, reject path components, constrain resolved assets and ZIP entries, and replace arbitrary legacy paths with explicit compatibility routes. |
| High | Batch execution overwrote failed validation with PASS; landing-page jobs also announced success after failed validation. | Propagate failure, record FAILED, return a nonzero batch exit code, and report dashboard job errors. |
| High | An unsuccessful rerun could retain a previous successful status and DELIVERY.json. | Mark runs RUNNING, invalidate the previous delivery marker, and record FAILED on exceptions. Generate new sales materials only after validation passes. |
| High | Businesses sharing a name could overwrite each other's business.json. | Use a stable identity suffix when an existing folder belongs to another name/address pair. Existing overwritten data cannot be recovered by this change. |
| Medium | Sanitized folder names differed from display names, breaking generation; reserved URL characters broke previews. | Send the client folder ID separately and encode URLs. |
| Medium | Preview URLs without a trailing slash resolved relative stylesheets and scripts against the wrong directory. | Use canonical directory URLs and retain explicit legacy routes. |
| Medium | Missing Google credentials raised SystemExit inside a worker, leaving jobs running indefinitely. | Raise a normal application error so the dashboard records a terminal error. |
| Medium | Concurrent ZIP requests wrote to the same archive; concurrent generation could overwrite a client's assets. | Build each download in memory and reject duplicate active generation requests. |
| Medium | Website inspection discarded business-specific URL paths and fetched the homepage twice. | Inspect the exact supplied URL, reuse that response, and respect its redirect target for contact-page discovery. |
| Medium | A repeated pagination token could keep making API requests without collecting new leads. | Stop on repeated tokens. |
| Medium | CLI --output-dir was ignored; dashboard output depended on the working directory. | Forward the CLI option and supply absolute dashboard paths. Anchor batch discovery to the project directory. |
| Medium | Handoffs lost the priority, reason, and email source because field names differed between producer and consumer. | Map the producer's field names when building handoffs. |
| Medium | Nullable or incorrectly typed AI fields crashed HTML rendering. | Validate the response object and normalize optional fields before rendering. |
| Medium | Emoji console messages crashed the pipeline under Windows cp1252. | Use ASCII progress markers and enable UTF-8 in the Windows launcher. |
| Medium | Delivery packaging failed on nested asset directories. | Copy nested directories recursively. |
| Low | CI omitted Flask; startup and CI maintained separate dependency lists. | Add requirements.txt and use it in both paths. Ignore the local virtual environment. |
| Low | hboard.py contained captured ANSI-colored diff output and was invalid Python. | Preserve it as hboard_history.txt. |

The dashboard also rejects non-object JSON payloads, skips malformed lead records, excludes unsafe website link schemes, and associates a completed landing-page request with the lead that started it.

## Validation

- `python -m unittest discover -s tests -v`: **38 tests passed** (18 existing, 20 added).
- The integration test runs real handoff creation, HTML/CSS/JS generation, validation, status updates, delivery metadata, and sales-package generation, with external research and AI copy responses mocked.
- Flask request tests cover previews, relative assets, encoded names, compatibility URLs, ZIP contents, path traversal rejection, failed jobs, and duplicate requests.
- All root and test Python files parse successfully.
- Embedded dashboard JavaScript passes `node --check`.
- `git diff --check` passes.

## Limits

No live Google Places or DeepSeek requests were made, and browser interactions were not exercised. API credentials, billing, provider response quality, and browser timing remain unverified. External responses were mocked in tests. Existing lead folders, generated websites, and the pre-existing .vscode directory were left in place. Historical duplicates and already overwritten lead data were not migrated or repaired. AI-generated factual claims still require review; automated QA cannot establish that every claim is supported.

Changes are local and uncommitted.
