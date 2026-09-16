import argparse
import json
from pathlib import Path

from website_validator import validate
from deepseek_website_generator import generate_website


def run_pipeline(client_folder):

    client_folder = Path(client_folder)

    handoff = client_folder / "AI_HANDOFF.json"

    if not handoff.exists():
        raise FileNotFoundError(
            f"Missing AI_HANDOFF.json: {handoff}"
        )

    print("\n🚀 Starting website generation...")

    website = generate_website(
        handoff
    )

    print(
        f"✅ Website created: {website}"
    )

    print("\n🔍 Running quality validation...")

    report_path = validate(
        client_folder
    )

    print(
        f"✅ QA Report created: {report_path}"
    )


    # Reload fresh report after validation
    with report_path.open(
        "r",
        encoding="utf-8"
    ) as file:
        report = json.load(file)


    print("\n========== FINAL RESULT ==========")

    print(
        f"Client: {report.get('client', 'UNKNOWN')}"
    )

    print(
        f"Status: {report.get('status', 'UNKNOWN')}"
    )


    if report.get("warnings"):

        print("\nWarnings:")

        for warning in report["warnings"]:
            print(
                f"- {warning}"
            )


    if report.get("checks"):

        print("\nChecks:")

        for check, result in report["checks"].items():
            print(
                f"{check}: {result}"
            )


    print("\n=================================")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=
        "Run LeadFinder website pipeline"
    )

    parser.add_argument(
        "client_folder",
        help=
        "Path to client folder"
    )

    args = parser.parse_args()

    run_pipeline(
        args.client_folder
    )