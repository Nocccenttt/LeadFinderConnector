#!/bin/bash
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is required. Install it from https://www.python.org/downloads/macos/"
    read -r -p "Press Return to close..."
    exit 1
fi

if [[ ! -f .env ]]; then
    echo "Missing .env in $(pwd). Add your existing DEEPSEEK_API_KEY there."
    read -r -p "Press Return to close..."
    exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python deepseek_website_generator.py \
    "codex_handoffs/HIGH/Brown's Tree Service/AI_HANDOFF.json" \
    --reference-analysis-only

echo "Open codex_handoffs/HIGH/Brown's Tree Service/reference_analysis.json to inspect the result."
read -r -p "Press Return to close..."
