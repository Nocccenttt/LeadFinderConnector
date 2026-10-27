"""Validate generated website assets, factual-claim risks, and on-page SEO."""
import argparse
import json
from pathlib import Path

from bs4 import BeautifulSoup
from website_planning import build_seo_strategy, validate_seo_html


FORBIDDEN_CLAIMS = [
    "award winning",
    "award-winning",
    "best in",
    "number one",
    "#1",
    "certified",
    "guaranteed",
    "years of experience",
    "years in business",
    "thousands of customers",
    "satisfied customers",
    "happy customers",
]


def validate(client_folder):
    client_folder = Path(client_folder)
    business_file = client_folder / "business.json"
    website_folder = client_folder / "website"

    with business_file.open("r", encoding="utf-8") as file:
        business = json.load(file)

    client_name = (
        business.get("business_name")
        or business.get("name")
        or business.get("company_name")
        or "UNKNOWN"
    )
    seo_strategy_path = client_folder / "SEO_STRATEGY.json"
    if seo_strategy_path.exists():
        with seo_strategy_path.open("r", encoding="utf-8") as file:
            seo_strategy = json.load(file)
    else:
        seo_strategy = build_seo_strategy(business, {})

    report = {"client": client_name, "checks": {}, "warnings": []}

    for filename in ("index.html", "styles.css", "script.js"):
        file_path = website_folder / filename
        report["checks"][filename] = (
            "PASS" if file_path.exists() and file_path.stat().st_size > 0 else "FAIL"
        )

    html_file = website_folder / "index.html"
    issues = []
    html = ""
    if html_file.exists():
        html = html_file.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        if not soup.title:
            issues.append("Missing title tag")
        if not soup.find("h1"):
            issues.append("Missing H1")
        if client_name.lower() not in html.lower():
            issues.append("Business name missing")
    else:
        issues.append("index.html missing")

    report["checks"]["html"] = {
        "status": "PASS" if not issues else "NEEDS REVIEW",
        "issues": issues,
    }

    seo_report = validate_seo_html(html, business, seo_strategy) if html else {
        "status": "NEEDS REVIEW",
        "issues": ["Cannot run SEO checks because index.html is missing"],
        "warnings": [],
        "metrics": {},
    }
    report["checks"]["seo"] = seo_report
    report["warnings"].extend(seo_report.get("warnings", []))

    content = html.lower()
    for claim in FORBIDDEN_CLAIMS:
        if claim in content:
            report["warnings"].append(
                f"Potential unsupported claim detected: {claim}"
            )

    asset_failures = any(value != "PASS" for key, value in report["checks"].items()
                         if key in ("index.html", "styles.css", "script.js"))
    report["status"] = (
        "PASS"
        if not asset_failures
        and report["checks"]["html"]["status"] == "PASS"
        and seo_report.get("status") == "PASS"
        and not any("Potential unsupported claim" in warning for warning in report["warnings"])
        else "NEEDS REVIEW"
    )

    output = client_folder / "quality_report.json"
    with output.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("client_folder")
    args = parser.parse_args()
    result = validate(args.client_folder)
    print(f"Report created: {result}")
