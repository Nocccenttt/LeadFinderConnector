import json
import shutil
from pathlib import Path
from datetime import datetime


def build_package(client_folder):

    client_folder = Path(client_folder)

    package = (
        client_folder /
        "DELIVERY_PACKAGE"
    )

    website = package / "Website"
    data = package / "Data"
    reports = package / "Reports"


    # Create folders

    website.mkdir(
        parents=True,
        exist_ok=True
    )

    data.mkdir(
        exist_ok=True
    )

    reports.mkdir(
        exist_ok=True
    )


    # Copy website

    source_website = (
        client_folder /
        "website"
    )

    if source_website.exists():

        for file in source_website.iterdir():

            shutil.copy(
                file,
                website / file.name
            )


    # Copy data files

    for filename in [
        "business.json",
        "AI_HANDOFF.json"
    ]:

        source = (
            client_folder /
            filename
        )

        if source.exists():

            shutil.copy(
                source,
                data / filename
            )


    # Copy reports

    for filename in [
        "quality_report.json",
        "STATUS.json",
        "DELIVERY.json"
    ]:

        source = (
            client_folder /
            filename
        )

        if source.exists():

            shutil.copy(
                source,
                reports / filename
            )


    # Create summary

    summary = {

        "client":
            client_folder.name,

        "package_status":
            "READY_FOR_REVIEW",

        "created_at":
            datetime.now().isoformat(),

        "contents": [
            "Website",
            "Business Data",
            "AI Data",
            "QA Reports"
        ]

    }


    (package / "delivery_summary.json").write_text(
        json.dumps(
            summary,
            indent=2
        ),
        encoding="utf-8"
    )


    return package



if __name__ == "__main__":

    import argparse


    parser = argparse.ArgumentParser()

    parser.add_argument(
        "client_folder"
    )

    args = parser.parse_args()


    output = build_package(
        args.client_folder
    )


    print(
        f"Package created: {output}"
    )