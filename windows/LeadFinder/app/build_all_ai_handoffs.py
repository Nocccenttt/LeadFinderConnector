# build_all_ai_handoffs.py

from pathlib import Path
from ai_handoff import build_ai_handoff


def main():
    root = Path("codex_handoffs")
    created = 0

    for priority in ("HIGH", "MEDIUM"):
        for business_json in (root / priority).glob("*/business.json"):
            build_ai_handoff(business_json)
            created += 1
            print(f"Created: {business_json.parent / 'AI_HANDOFF.json'}")

    print(f"\nCreated {created} AI handoff(s).")


if __name__ == "__main__":
    main()