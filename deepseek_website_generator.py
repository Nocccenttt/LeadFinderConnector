import json
import os
import argparse
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from api_usage_logger import log_usage


load_dotenv()


MODEL = "deepseek-chat"



def load_handoff(path):

    path = Path(path)

    with path.open(
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)



def generate_website(handoff_path):

    handoff_path = Path(handoff_path)

    handoff = load_handoff(
        handoff_path
    )


    api_key = os.getenv(
        "DEEPSEEK_API_KEY"
    )


    if not api_key:

        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set."
        )



    client = OpenAI(

        api_key=api_key,

        base_url="https://api.deepseek.com"

    )



    system_prompt = """
You are a professional local-business landing page generator.

Create a complete static website from the supplied LeadFinder AI handoff.

IMPORTANT RULES:

1. Use ONLY verified information in the handoff.
2. Never invent services.
3. Never invent reviews.
4. Never invent certifications.
5. Never invent years in business.
6. Never invent guarantees.
7. Never invent pricing.
8. Never invent locations.
9. If information is missing, omit it.
10. Preserve business name exactly.
11. Preserve verified contact details.
12. Create a modern mobile-first landing page.
13. Use semantic HTML.
14. Use clean CSS.
15. Use JavaScript only if necessary.

STRICT JSON RULES:

Return ONLY valid JSON.

The JSON must have exactly these keys:

{
"index.html": "",
"styles.css": "",
"script.js": ""
}

Rules:

- Escape all quotes correctly.
- Do not use markdown.
- Do not use code fences.
- Do not include explanations.
- Ensure JSON closes properly.
"""



    response = client.chat.completions.create(

        model=MODEL,

        response_format={
            "type": "json_object"
        },

        messages=[

            {
                "role": "system",
                "content": system_prompt
            },

            {
                "role": "user",
                "content": json.dumps(
                    handoff,
                    indent=2,
                    ensure_ascii=False
                )
            }

        ],

        temperature=0.7

    )



    print("\nDeepSeek Usage:")

    print(
        response.usage
    )


    # Save token usage

    try:

        log_usage(

            handoff.get(
                "business_name",
                handoff_path.parent.name
            ),

            response.usage

        )

    except Exception as e:

        print(
            f"Usage logging skipped: {e}"
        )



    content = (

        response
        .choices[0]
        .message
        .content
        .strip()

    )



    try:

        website = json.loads(
            content
        )


    except json.JSONDecodeError:


        debug_file = (

            handoff_path.parent /

            "deepseek_raw_response.txt"

        )


        debug_file.write_text(

            content,

            encoding="utf-8"

        )


        raise RuntimeError(

            "DeepSeek returned invalid JSON. "
            "Check deepseek_raw_response.txt"

        )



    required_files = (

        "index.html",

        "styles.css",

        "script.js"

    )



    for filename in required_files:

        if filename not in website:

            raise ValueError(

                f"Missing generated file: {filename}"

            )



    output_dir = (

        handoff_path.parent /

        "website"

    )


    output_dir.mkdir(

        exist_ok=True

    )



    for filename in required_files:


        file_path = (

            output_dir /

            filename

        )


        file_path.write_text(

            website[filename],

            encoding="utf-8"

        )



    return output_dir





if __name__ == "__main__":


    parser = argparse.ArgumentParser(

        description="Generate website using DeepSeek"

    )


    parser.add_argument(

        "ai_handoff",

        help="Path to AI_HANDOFF.json"

    )


    args = parser.parse_args()



    result = generate_website(

        args.ai_handoff

    )


    print(

        f"\nWebsite created: {result}"

    )