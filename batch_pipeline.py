from pathlib import Path
import argparse

from pipeline_runner import run_pipeline
from batch_logger import BatchLogger
from status_manager import (
    save_status,
    is_completed,
)


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



def run_batch(clients, resume=False):

    logger = BatchLogger()

    processed = 0
    skipped = 0
    failed = 0


    print("\n============================")
    print("PRODUCTION MODE")
    print("============================")


    for client in clients:


        if resume and is_completed(client):

            print(
                f"⏭ Skipping {client.name}: Already completed"
            )

            skipped += 1

            continue



        print("\n----------------------------")
        print(
            f"Processing: {client.name}"
        )
        print("----------------------------")


        try:

            run_pipeline(client)


            save_status(
                client,
                "PASS"
            )


            logger.add_completed(
                client
            )


            processed += 1



        except Exception as error:


            save_status(
                client,
                "FAILED"
            )


            logger.add_failed(
                client,
                error
            )


            failed += 1


            print(
                f"FAILED {client.name}: {error}"
            )



    run_folder = logger.save()



    print("\n============================")
    print("FINAL RESULT")
    print("============================")


    print(
        f"Completed: {processed}"
    )

    print(
        f"Skipped: {skipped}"
    )

    print(
        f"Failed: {failed}"
    )

    print(
        f"Log saved: {run_folder}"
    )


    print("============================")



def main():

    parser = argparse.ArgumentParser(
        description="LeadFinder Batch Pipeline"
    )


    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show clients without generating websites"
    )


    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip completed clients"
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
            clients,
            resume=args.resume
        )



if __name__ == "__main__":

    main()