import json
from datetime import datetime
from pathlib import Path


def create_offer_json(client_folder):

    client_folder = Path(client_folder)


    business_file = (
        client_folder /
        "business.json"
    )


    business = {}


    if business_file.exists():

        business = json.loads(
            business_file.read_text(
                encoding="utf-8"
            )
        )


    offer = {

        "client":
            business.get(
                "business_name",
                client_folder.name
            ),

        "offer_type":
            "Website Upgrade Demo",

        "purpose":
            "Sales presentation landing page concept",

        "status":
            "PRESENTATION_READY",

        "cta":
            "Schedule Strategy Call",

        "created_at":
            datetime.now().isoformat()

    }


    sales_folder = (
        client_folder /
        "DEMO_PACKAGE" /
        "Sales"
    )


    sales_folder.mkdir(
        parents=True,
        exist_ok=True
    )


    output = (
        sales_folder /
        "OFFER.json"
    )


    output.write_text(
        json.dumps(
            offer,
            indent=2
        ),
        encoding="utf-8"
    )


    return output



if __name__ == "__main__":

    import argparse


    parser = argparse.ArgumentParser()

    parser.add_argument(
        "client_folder"
    )

    args = parser.parse_args()


    result = create_offer_json(
        args.client_folder
    )


    print(
        f"Offer created: {result}"
    )