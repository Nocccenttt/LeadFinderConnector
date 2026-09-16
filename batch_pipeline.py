from pathlib import Path

from pipeline_runner import run_pipeline


def main():

    root = Path("codex_handoffs")

    processed = 0
    failed = 0


    for priority in [
        "HIGH",
        "MEDIUM"
    ]:

        folder = root / priority

        if not folder.exists():
            continue


        for client in folder.iterdir():

            if not client.is_dir():
                continue


            handoff = (
                client /
                "AI_HANDOFF.json"
            )


            if not handoff.exists():
                print(
                    f"Skipping {client.name}: No AI_HANDOFF.json"
                )
                continue


            print(
                "\n============================"
            )

            print(
                f"Processing: {client.name}"
            )

            print(
                "============================"
            )


            try:

                run_pipeline(
                    client
                )

                processed += 1


            except Exception as e:

                failed += 1

                print(
                    f"FAILED {client.name}: {e}"
                )


    print(
        "\n============================"
    )

    print(
        f"Completed: {processed}"
    )

    print(
        f"Failed: {failed}"
    )

    print(
        "============================"
    )


if __name__ == "__main__":
    main()