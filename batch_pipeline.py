from pathlib import Path
import argparse

from pipeline_runner import run_pipeline


ROOT = Path("codex_handoffs")
PRIORITIES = [
    "HIGH",
    "MEDIUM",
]


def discover_clients():

    clients = []

    for priority in PRIORITIES:

        folder = ROOT / priority

        if not folder.exists():
            continue

        for client in folder.iterdir():

            if not client.is_dir():
                continue

            handoff = client / "AI_HANDOFF.json"

            if handoff.exists():
                clients.append(client)

    return clients



def run_dry_run(clients):

    print("\n============================")
    print("DRY RUN MODE")
    print("============================\n")


    for client in clients:

        print(
            f"✓ {client.name}"
        )


    print("\n============================")
    print(
        f"Total clients: {len(clients)}"
    )
    print(
        "No API calls made."
    )
    print("============================")



def run_batch(clients):

    processed = 0
    failed = 0


    print("\n============================")
    print("PRODUCTION MODE")
    print("============================")


    for client in clients:

        print("\n----------------------------")
        print(
            f"Processing: {client.name}"
        )
        print("----------------------------")


        try:

            run_pipeline(client)

            processed += 1


        except Exception as error:

            failed += 1

            print(
                f"FAILED {client.name}"
            )

            print(error)



    print("\n============================")
    print("FINAL RESULT")
    print("============================")

    print(
        f"Completed: {processed}"
    )

    print(
        f"Failed: {failed}"
    )

    print("============================")



def main():

    parser = argparse.ArgumentParser(
        description="LeadFinder Batch Pipeline"
    )


    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List clients without generating websites"
    )


    args = parser.parse_args()


    clients = discover_clients()


    if not clients:

        print(
            "No AI_HANDOFF.json files found."
        )

        return



    if args.dry_run:

        run_dry_run(
            clients
        )

    else:

        run_batch(
            clients
        )



if __name__ == "__main__":

    main()