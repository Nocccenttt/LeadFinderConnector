import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


MODEL = "deepseek-chat"


def load_handoff(path):
    path = Path(path)

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def generate_website(handoff_path):
    handoff_path = Path(handoff_path)
    handoff = load_handoff(handoff_path)

    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set."
        )

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    system_prompt = """
You are a professional local-business website generator.

Create a complete static website from the supplied LeadFinder AI handoff.

IMPORTANT RULES:

1. Use ONLY verified information in the handoff.
2. Never invent services.
3. Never invent reviews or testimonials.
4. Never invent certifications or awards.
5. Never invent years in business.
6. Never invent guarantees.
7. Never invent locations.
8. Never invent pricing.
9. Never invent business claims.
10. If information is missing, omit it.
11. Preserve the business name exactly.
12. Preserve verified phone and address information.
13. Create a modern, professional, mobile-first website.
14. Make the design responsive.
15. Use semantic HTML.
16. Use clean CSS.
17. Use JavaScript only when useful.
18. Make calls to action clear without making unsupported claims.

Return ONLY valid JSON.

The JSON must have exactly these keys:

{
  "index.html": "...",
  "styles.css": "...",
  "script.js": "..."
}

Do not use Markdown code fences.
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": json.dumps(
                    handoff,
                    indent=2,
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0.7,
    )

    content = response.choices[0].message.content.strip()

    if content.startswith("```"):
        content = content.strip("`")

        if content.startswith("json"):
            content = content[4:].strip()

    website = json.loads(content)

    required_files = (
        "index.html",
        "styles.css",
        "script.js",
    )

    for filename in required_files:
        if filename not in website:
            raise ValueError(
                f"DeepSeek response is missing {filename}"
            )

    output_dir = handoff_path.parent / "website"
    output_dir.mkdir(exist_ok=True)

    for filename in required_files:
        (output_dir / filename).write_text(
            website[filename],
            encoding="utf-8",
        )

    return output_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a website using DeepSeek."
    )

    parser.add_argument(
        "ai_handoff",
        help="Path to AI_HANDOFF.json",
    )

    args = parser.parse_args()

    output = generate_website(args.ai_handoff)

    print(f"Website created: {output}")