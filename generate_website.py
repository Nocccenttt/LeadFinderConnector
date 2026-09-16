import argparse
import json
from pathlib import Path

from openai import OpenAI


MODEL = "gpt-5.6"


def load_handoff(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def generate_website(handoff_path):
    handoff_path = Path(handoff_path)
    handoff = load_handoff(handoff_path)

    client = OpenAI()

    instructions = """
You are a professional local-business website generator.

Generate a complete, production-ready static website from the supplied
LeadFinder AI handoff.

Rules:

1. Use ONLY verified information contained in the handoff.
2. Never invent services, reviews, certifications, awards, pricing,
   guarantees, years in business, locations, or other business claims.
3. If information is missing, omit it.
4. Preserve the business name, phone, address, website, email, and verified
   social information exactly when provided.
5. Create a modern, professional, mobile-first responsive website.
6. Make the website conversion-focused without making unsupported claims.
7. Use accessible semantic HTML.
8. Use clean CSS.
9. Use JavaScript only when necessary.
10. Return ONLY valid JSON.

The JSON must have exactly this structure:

{
  "index.html": "...complete HTML...",
  "styles.css": "...complete CSS...",
  "script.js": "...complete JavaScript..."
}
"""

    response = client.responses.create(
        model=MODEL,
        instructions=instructions,
        input=json.dumps(handoff, indent=2, ensure_ascii=False),
    )

    raw = response.output_text.strip()

    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()

    website = json.loads(raw)

    output_dir = handoff_path.parent / "website"
    output_dir.mkdir(exist_ok=True)

    for filename in ("index.html", "styles.css", "script.js"):
        content = website.get(filename, "")
        (output_dir / filename).write_text(
            content,
            encoding="utf-8",
        )

    return output_dir


def main():
    parser = argparse.ArgumentParser(
        description="Generate a website from a LeadFinder AI handoff."
    )

    parser.add_argument(
        "ai_handoff",
        help="Path to AI_HANDOFF.json",
    )

    args = parser.parse_args()

    output_dir = generate_website(args.ai_handoff)

    print(f"Website created: {output_dir}")


if __name__ == "__main__":
    main()