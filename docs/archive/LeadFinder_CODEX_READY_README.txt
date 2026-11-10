LEADFINDER - CODEX READY VERSION

When you run run_leadfinder_batch_logged.bat, it automatically creates:

outputs\
  - Full CSV
  - HIGH-only CSV
  - MEDIUM-only CSV
  - SUMMARY.json

codex_handoffs\
  HIGH\
    Business Name\
      business.json
      WEBSITE_BUILD_PROMPT.md
      README.md
  MEDIUM\
    Business Name\
      business.json
      WEBSITE_BUILD_PROMPT.md
      README.md

Only HIGH and MEDIUM leads are sent into codex_handoffs.
Each business folder contains the verified data and a ready-to-use website build prompt.

No API key is stored in the BAT file. GOOGLE_MAPS_API_KEY must remain an environment variable.
