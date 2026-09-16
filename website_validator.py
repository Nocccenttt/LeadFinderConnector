import argparse
import json
from pathlib import Path

from bs4 import BeautifulSoup


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

    with business_file.open(
        "r",
        encoding="utf-8"
    ) as f:
        business = json.load(f)


    # LeadFinder uses business_name
    client_name = (
        business.get("business_name")
        or business.get("name")
        or business.get("company_name")
        or "UNKNOWN"
    )


    report = {
        "client": client_name,
        "checks": {},
        "warnings": [],
    }


    # File checks

    for filename in [
        "index.html",
        "styles.css",
        "script.js",
    ]:

        file_path = website_folder / filename

        report["checks"][filename] = (
            "PASS"
            if file_path.exists()
            and file_path.stat().st_size > 0
            else "FAIL"
        )


    # HTML checks

    html_file = website_folder / "index.html"

    issues = []

    if html_file.exists():

        html = html_file.read_text(
            encoding="utf-8"
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )


        if not soup.title:
            issues.append(
                "Missing title tag"
            )


        if not soup.find("h1"):
            issues.append(
                "Missing H1"
            )


        if client_name.lower() not in html.lower():

            issues.append(
                "Business name missing"
            )


    else:

        issues.append(
            "index.html missing"
        )


    report["checks"]["html"] = {
        "status":
            "PASS"
            if not issues
            else "NEEDS REVIEW",

        "issues": issues
    }


    # Claim checks

    if html_file.exists():

        content = html_file.read_text(
            encoding="utf-8"
        ).lower()


        for claim in FORBIDDEN_CLAIMS:

            if claim in content:
                report["warnings"].append(
                    claim
                )


    report["status"] = (
        "PASS"
        if report["checks"]["html"]["status"] == "PASS"
        and not report["warnings"]
        else "NEEDS REVIEW"
    )


    output = (
        client_folder /
        "quality_report.json"
    )


    with output.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )


    return output



if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "client_folder"
    )

    args = parser.parse_args()


    result = validate(
        args.client_folder
    )


    print(
        f"Report created: {result}"
    )