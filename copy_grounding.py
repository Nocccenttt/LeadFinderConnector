"""Keep contextual writing while rejecting unsupported company promises."""
import re


PATTERNS = (
    r"\b(?:guarantee[ds]?|certified|licensed|insured|award[- ]winning|top[- ]rated)\b",
    r"\b(?:\d+\+?\s+years?|since\s+(?:19|20)\d{2}|24\s*/\s*7)\b",
    r"(?:[$£€]\s*\d|\b\d(?:\.\d)?[- ]star\b|\b\d+\s*%\b)",
)


def check_marketing_copy(copy, business, verified_services):
    """Pattern checks, not a claim of exhaustive factual verification.

Reference metadata and image queries are excluded: they are research inputs,
not assertions made to customers. General questions about services are allowed.
"""
    fields = ("headline", "subheadline", "intro", "about_title", "about", "services_intro", "benefits", "process",
              "local_intro", "faq", "cta_title", "cta_text", "feature_title", "feature_text", "guide_title", "guide_intro", "guide_topics")
    findings = []
    source = str(business).lower()
    company = re.escape(str(business.get("business_name") or business.get("name") or ""))
    for field in fields:
        value = copy.get(field, "")
        text = str(value)
        for pattern in PATTERNS:
            for match in re.finditer(pattern, text, re.I):
                if match.group().lower() not in source:
                    findings.append(f"{field}: unsupported factual claim {match.group()!r}")
        if not verified_services:
            offer = r"\b(?:we|our\s+(?:team|business|company))\s+(?:offer|provide|perform|speciali[sz]e|deliver)\b"
            if company:
                offer += rf"|{company}\s+(?:offers|provides|performs|speciali[sz]es|delivers)\b"
            if re.search(offer, text, re.I):
                findings.append(f"{field}: company service assertion without a verified service list")
    if findings:
        raise ValueError("Content grounding failed: " + "; ".join(findings))
    return {"status": "PASS", "scope": "Unsupported-claim pattern checks; business facts still require source verification.",
            "verified_service_count": len(verified_services)}
