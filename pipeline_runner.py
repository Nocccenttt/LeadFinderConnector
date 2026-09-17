import argparse
from pathlib import Path

from deepseek_website_generator import generate_website
from website_validator import validate
from status_manager import save_status
from delivery_manager import create_delivery_json


def run_pipeline(client_folder):

    client_folder = Path(client_folder)

    print("\n============================")
    print(f"Client: {client_folder.name}")
    print("============================")


    # ----------------------------
    # Step 1: Find AI HANDOFF
    # ----------------------------

    ai_handoff = (
        client_folder /
        "AI_HANDOFF.json"
    )


    if not ai_handoff.exists():

        raise FileNotFoundError(
            "AI_HANDOFF.json not found"
        )


    print("\n🚀 Starting website generation...")


    # ----------------------------
    # Step 2: Generate Website
    # ----------------------------

    website_dir = generate_website(
        ai_handoff
    )


    print(
        f"Website created: {website_dir}"
    )


    # ----------------------------
    # Step 3: Validate Website
    # ----------------------------

    print("\n🔍 Running quality validation...")


    report = validate(
    client_folder
     )


    print(
        "Validation complete"
    )


    # ----------------------------
    # Step 4: Check Validation
    # ----------------------------

    status = "PASS"


    if isinstance(report, dict):

        if report.get("status") == "FAIL":

            status = "FAILED"



    # ----------------------------
    # Step 5: Save STATUS
    # ----------------------------

    save_status(
        client_folder,
        status
    )


    print(
        f"STATUS.json created: {status}"
    )



    # ----------------------------
    # Step 6: Create DELIVERY.json
    # ----------------------------

    if status == "PASS":

        delivery = create_delivery_json(
            client_folder
        )


        print(
            f"Delivery file created: {delivery}"
        )


    print("\n========== FINAL RESULT ==========")

    print(
        f"Client: {client_folder.name}"
    )

    print(
        f"Status: {status}"
    )

    print(
        "=================================\n"
    )


    return status



def main():

    parser = argparse.ArgumentParser(
        description="Run LeadFinder client pipeline"
    )


    parser.add_argument(
        "client_folder",
        help="Path to client folder"
    )


    args = parser.parse_args()


    run_pipeline(
        args.client_folder
    )



if __name__ == "__main__":

    main()