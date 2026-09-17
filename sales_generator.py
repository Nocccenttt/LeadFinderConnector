import json
from datetime import datetime
from pathlib import Path


def load_json(file):

    if not file.exists():
        return {}

    return json.loads(
        file.read_text(
            encoding="utf-8"
        )
    )


def generate_sales_package(client_folder):

    client_folder = Path(client_folder)


    business = load_json(
        client_folder / "business.json"
    )


    handoff = load_json(
        client_folder / "AI_HANDOFF.json"
    )


    sales_folder = (
        client_folder
        /
        "DEMO_PACKAGE"
        /
        "Sales"
    )


    sales_folder.mkdir(
        parents=True,
        exist_ok=True
    )


    business_name = (
        business.get("business_name")
        or client_folder.name
    )


    # -------------------------
    # OFFER.JSON
    # -------------------------

    offer = {

        "client":
            business_name,

        "offer_type":
            "Website Upgrade Demo",

        "purpose":
            "Custom landing page concept created for sales presentation",

        "status":
            "PRESENTATION_READY",

        "next_step":
            "Schedule Strategy Call",

        "created_at":
            datetime.now().isoformat()

    }


    (sales_folder / "OFFER.json").write_text(

        json.dumps(
            offer,
            indent=2
        ),

        encoding="utf-8"

    )


    # -------------------------
    # SALES NOTES
    # -------------------------

    notes = {

        "client":
            business_name,

        "sales_angle":
            "Improve online conversion opportunities",

        "talking_points": [

            "Show the custom landing page concept",

            "Explain how a stronger online presence can support customer acquisition",

            "Discuss opportunities for improving website experience"

        ],

        "opening_script":
            f"We created a custom website concept for {business_name} to show what a stronger online experience could look like.",


        "created_at":
            datetime.now().isoformat()

    }


    (sales_folder / "SALES_NOTES.json").write_text(

        json.dumps(
            notes,
            indent=2
        ),

        encoding="utf-8"

    )


    # -------------------------
    # DEMO SUMMARY
    # -------------------------

    summary = {

        "client":
            business_name,

        "assets_created": [

            "Landing Page Demo",

            "Offer",

            "Sales Notes"

        ],

        "status":
            "READY_FOR_SALES_REVIEW",

        "created_at":
            datetime.now().isoformat()

    }


    demo_folder = (
        client_folder
        /
        "DEMO_PACKAGE"
    )


    (demo_folder / "demo_summary.json").write_text(

        json.dumps(
            summary,
            indent=2
        ),

        encoding="utf-8"

    )


    return sales_folder



if __name__ == "__main__":

    import argparse


    parser = argparse.ArgumentParser(
        description="Generate sales package"
    )


    parser.add_argument(
        "client_folder"
    )


    args = parser.parse_args()


    result = generate_sales_package(
        args.client_folder
    )


    print(
        f"Sales package created: {result}"
    )