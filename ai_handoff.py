import json
from pathlib import Path


DO_NOT_INVENT = [
    "services",
    "reviews",
    "certifications",
    "awards",
    "years in business",
    "guarantees",
    "locations",
    "pricing",
    "business claims",
]


def build_ai_handoff(business_json_path):
    """Build an AI-ready website specification from LeadFinder data."""

    business_json_path = Path(business_json_path)

    with business_json_path.open("r", encoding="utf-8") as f:
        business = json.load(f)

    handoff = {
        "handoff_version": "1.0",
        "source": "LeadFinder",
        "source_of_truth": "business.json",
        "lead": {
            "priority": business.get("priority", ""),
            "opportunity_score": business.get("opportunity_score", 0),
            "opportunity": business.get("opportunity", ""),
            "reason": business.get("reason", ""),
            "opportunity_reasons": business.get(
                "opportunity_reasons", []
            ),
        },
        "business": {
            "name": business.get("name", ""),
            "address": business.get("address", ""),
            "phone": business.get("phone", ""),
            "website": business.get("website", ""),
            "website_status": business.get("website_status", ""),
        },
        "verified_online_presence": {
            "facebook": business.get("facebook", ""),
            "instagram": business.get("instagram", ""),
            "linkedin": business.get("linkedin", ""),
            "other_socials": business.get("other_socials", ""),
            "email": business.get("email", ""),
            "email_source_url": business.get("email_source_url", ""),
        },
        "website_build": {
            "objective": (
                "Create a modern, mobile-first local business website "
                "using only verified information contained in this handoff."
            ),
            "requirements": [
                "Use the business name exactly as provided.",
                "Preserve verified contact information.",
                "Preserve verified website information.",
                "Use the LeadFinder opportunity to guide website strategy.",
                "Make the website clear, professional, and conversion-focused.",
                "Make the website mobile-first and responsive.",
                "Use only information supported by the source data.",
            ],
            "do_not_invent": DO_NOT_INVENT,
            "unsupported_information": (
                "If information is not present in the source data, "
                "omit it rather than guessing."
            ),
        },
    }

    output_path = business_json_path.parent / "AI_HANDOFF.json"

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(
            handoff,
            f,
            indent=2,
            ensure_ascii=False,
        )

    build_website_prompt(handoff, business_json_path.parent)

    return output_path


def build_website_prompt(handoff, output_dir):
    """Create the prompt that will eventually be sent to a website generator."""

    business = handoff["business"]
    lead = handoff["lead"]
    rules = handoff["website_build"]

    prompt = f"""# Website Generator Brief

## Lead
Priority: {lead["priority"]}
Opportunity Score: {lead["opportunity_score"]}
Opportunity: {lead["opportunity"]}
Reason: {lead["reason"]}

## Business
Name: {business["name"]}
Address: {business["address"]}
Phone: {business["phone"]}
Website: {business["website"]}
Website Status: {business["website_status"]}

## Verified Online Presence
Facebook: {handoff["verified_online_presence"]["facebook"]}
Instagram: {handoff["verified_online_presence"]["instagram"]}
LinkedIn: {handoff["verified_online_presence"]["linkedin"]}
Email: {handoff["verified_online_presence"]["email"]}

## Objective

{rules["objective"]}

## Build Requirements

"""

    for requirement in rules["requirements"]:
        prompt += f"- {requirement}\n"

    prompt += """
## Information Rules

Do NOT invent:
"""

    for item in rules["do_not_invent"]:
        prompt += f"- {item}\n"

    prompt += f"""
## Missing Information

{rules["unsupported_information"]}

## Final Instruction

Build the website around the verified business information above.
Prioritize clarity, trust, local relevance, mobile usability, and
conversion-focused calls to action.

Do not fabricate facts to make the website appear more complete.
"""

    output_path = Path(output_dir) / "WEBSITE_GENERATOR_PROMPT.md"

    with output_path.open("w", encoding="utf-8") as f:
        f.write(prompt)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Create an AI-ready website handoff from LeadFinder data."
    )

    parser.add_argument(
        "business_json",
        help="Path to a LeadFinder business.json file",
    )

    args = parser.parse_args()

    output = build_ai_handoff(args.business_json)

    print(f"AI handoff created: {output}")