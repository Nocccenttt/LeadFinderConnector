import argparse
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from api_usage_logger import log_usage


load_dotenv()

MODEL = "deepseek-chat"

SYSTEM_PROMPT = """
You are Wolf Forge's senior website designer and conversion copywriter.

Create ONE complete premium local-business landing page as a SINGLE HTML DOCUMENT.

SOURCE OF TRUTH:
Use ONLY verified information supplied in the business data and AI handoff.

NEVER invent:
- services
- reviews
- ratings
- testimonials
- awards
- certifications
- licenses
- years in business
- customer counts
- guarantees
- pricing
- discounts
- statistics
- staff
- locations
- service areas
- business hours
- unsupported claims

If information is missing, omit it.

DESIGN:
Create a premium, custom, expensive-looking local business website.

Use:
- dramatic hero
- large typography
- strong CTA
- premium cards
- layered sections
- gradients
- shadows
- borders
- visual depth
- responsive layouts
- subtle animations
- strong mobile design
- category-appropriate styling

Do NOT make it look like:
- a generic AI template
- a SaaS dashboard
- a plain white website

The first viewport must be impressive.

CONTENT:
Use the verified business name prominently.

Use verified phone number with a tel: link.

Use verified email when available.

Use verified website when available.

Use verified address/location when available.

Services may ONLY be displayed if verified in the supplied data.

Build useful sections appropriate to the available information.

Possible sections:
- Header
- Hero
- Contact/highlight strip
- About
- Verified services
- Benefits
- Process
- Location/service area
- FAQ
- CTA
- Footer

Do not create empty sections.

Do not repeat information unnecessarily.

ELEMENTOR:
The design must be realistic to rebuild in Elementor Pro using:
- Containers
- Headings
- Text Editor
- Buttons
- Icons
- Icon Boxes
- Images
- Accordion
- Forms
- Maps

Avoid React, Vue, frameworks, external libraries and complex JavaScript.

TECHNICAL:
Return a complete HTML document.

Put all CSS inside ONE <style> tag.

Put all JavaScript inside ONE <script> tag.

Do not use external fonts.

Do not use external CSS frameworks.

Do not use external JavaScript libraries.

Use semantic HTML.

Use responsive CSS.

Use accessible contrast.

Include visible focus states.

Include reduced-motion support.

Buttons must be real links or buttons.

Phone numbers must use tel:.

Do not use placeholder text.

Do not mention:
- AI
- LeadFinder
- Wolf Forge
- internal production processes

Do not claim the page is a demo.

The HTML must end with </html>.

Keep the implementation compact enough to finish completely.

OUTPUT:
Return ONLY the complete HTML document.
No markdown.
No explanation.
"""


REBUILD_NOTES = """# Elementor Rebuild Notes

## Page Structure

Recreate the generated page in Elementor Pro using Flexbox Containers.

Recommended structure:

1. Header / Navigation
2. Hero
3. Verified highlights
4. About / value section
5. Verified services, when present
6. Benefits / process, when present
7. Location / service area, when present
8. FAQ, when supported
9. Primary CTA
10. Footer

## Elementor Widgets

Use:
- Container
- Heading
- Text Editor
- Button
- Icon
- Icon Box
- Image
- Accordion
- Form
- Google Maps when appropriate

Recreate gradients, shadows, borders, spacing and animations with Elementor styling and Custom CSS.

## Source-of-Truth Rule

Do not add business claims that are not present in business.json or AI_HANDOFF.json.
"""


def load_json(path):
    return Path(path).read_text(encoding="utf-8")


def get_business_name(business, handoff):
    return (
        business.get("business_name")
        or business.get("name")
        or handoff.get("business_name")
        or handoff.get("business", {}).get("business_name")
        or handoff.get("business", {}).get("name")
    )


def extract_html(content):
    content = content.strip()

    content = re.sub(
        r"^```(?:html)?\s*",
        "",
        content,
        flags=re.IGNORECASE,
    )

    content = re.sub(
        r"\s*```$",
        "",
        content,
    )

    match = re.search(
        r"<!doctype html>.*?</html>",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match:
        return match.group(0).strip()

    match = re.search(
        r"<html\b.*?</html>",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match:
        return match.group(0).strip()

    raise RuntimeError(
        "DeepSeek did not return a complete HTML document."
    )


def extract_tag_content(html, tag):
    pattern = rf"<{tag}\b[^>]*>(.*?)</{tag}>"

    match = re.search(
        pattern,
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return ""

    return match.group(1).strip()


def remove_tag(html, tag):
    pattern = rf"<{tag}\b[^>]*>.*?</{tag}>"

    return re.sub(
        pattern,
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def generate_website(handoff_path):
    handoff_path = Path(handoff_path)

    handoff = __import__("json").loads(
        load_json(handoff_path)
    )

    business_path = handoff_path.parent / "business.json"

    if not business_path.exists():
        raise RuntimeError("business.json not found.")

    business = __import__("json").loads(
        load_json(business_path)
    )

    business_name = get_business_name(
        business,
        handoff,
    )

    if not business_name:
        raise RuntimeError("Business name is missing.")

    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set."
        )

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    source = __import__("json").dumps(
        {
            "business": business,
            "ai_handoff": handoff,
        },
        indent=2,
        ensure_ascii=False,
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": source,
            },
        ],
        temperature=0.6,
        max_tokens=4500,
    )

    print("\nDeepSeek Usage:")
    print(response.usage)

    try:
        log_usage(
            business_name,
            response.usage,
        )
    except Exception as error:
        print(
            f"Usage logging skipped: {error}"
        )

    content = response.choices[0].message.content or ""

    html = extract_html(content)

    if not html.lower().endswith("</html>"):
        raise RuntimeError(
            "Generated HTML is incomplete."
        )

    css = extract_tag_content(
        html,
        "style",
    )

    javascript = extract_tag_content(
        html,
        "script",
    )

    clean_html = remove_tag(
        html,
        "style",
    )

    clean_html = remove_tag(
        clean_html,
        "script",
    )

    clean_html = clean_html.replace(
        "<head>",
        "<head>\n    <link rel=\"stylesheet\" href=\"styles.css\">",
        1,
    )

    clean_html = clean_html.replace(
        "</body>",
        "    <script src=\"script.js\"></script>\n</body>",
        1,
    )

    output_dir = (
        handoff_path.parent / "website"
    )

    output_dir.mkdir(
        exist_ok=True
    )

    (output_dir / "index.html").write_text(
        clean_html,
        encoding="utf-8",
    )

    (output_dir / "styles.css").write_text(
        css,
        encoding="utf-8",
    )

    (output_dir / "script.js").write_text(
        javascript,
        encoding="utf-8",
    )

    (
        output_dir /
        "ELEMENTOR_REBUILD_NOTES.md"
    ).write_text(
        REBUILD_NOTES,
        encoding="utf-8",
    )

    return output_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Generate premium websites "
            "using DeepSeek"
        )
    )

    parser.add_argument(
        "ai_handoff",
        help="Path to AI_HANDOFF.json",
    )

    args = parser.parse_args()

    result = generate_website(
        args.ai_handoff
    )

    print(
        f"\nWebsite created: {result}"
    )