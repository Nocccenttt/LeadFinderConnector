# Security guidance

## API keys and local configuration

- Never commit `.env` or any file containing live credentials.
- Copy `.env.example` to `.env` locally and add your own API keys.
- If a key was ever committed, revoke or rotate it in the provider dashboard. Deleting the file in a later commit does not remove it from Git history.
- Keep API keys out of logs, generated landing pages, CSV exports, issues, and pull requests.

## Generated landing pages

Use only verified business information. Do not publish fabricated reviews, credentials, pricing, guarantees, or claims. Review generated copy before sending it to a prospect or deploying it publicly.
