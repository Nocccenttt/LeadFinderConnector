import argparse
import json
import shutil
import tempfile
from pathlib import Path

from reference_website_generator import generate_website
from website_validator import validate
from status_manager import save_status
from delivery_manager import create_delivery_json
from sales_generator import generate_sales_package


def run_pipeline(client_folder, preserve_content=False):
    client_folder = Path(client_folder).resolve()
    if not client_folder.is_dir():
        raise FileNotFoundError(f"Client folder not found: {client_folder}")
    save_status(client_folder, "RUNNING")
    (client_folder / "DELIVERY.json").unlink(missing_ok=True)
    backup = None
    keep_backup = False
    website = client_folder / 'website'
    approved_copy = client_folder / 'GENERATED_COPY.json'
    try:
        # Keep the previous working assets until the new build has passed QA.
        # Nested symlinks are copied as links; junctions are never traversed.
        def reject_junctions(folder, names):
            for name in names:
                path = Path(folder) / name
                if path.is_dir() and not path.is_symlink() and path.resolve() != path.absolute():
                    raise RuntimeError('A website folder is linked elsewhere; the build was not started.')
            return []

        if website.resolve() != website or approved_copy.resolve() != approved_copy:
            raise RuntimeError('Saved website files are linked elsewhere; the build was not started.')
        backup = Path(tempfile.mkdtemp(prefix='.build-backup-', dir=client_folder))
        if website.exists():
            shutil.copytree(website, backup / 'website', symlinks=True, ignore=reject_junctions)
        if approved_copy.exists():
            shutil.copy2(approved_copy, backup / 'GENERATED_COPY.json', follow_symlinks=False)
        result = None
        try:
            result = _run_pipeline(client_folder, preserve_content=preserve_content)
        finally:
            if result != 'PASS':
                try:
                    if (backup / 'website').exists():
                        if website.is_symlink():
                            website.unlink()
                        elif website.exists():
                            shutil.rmtree(website)
                        (backup / 'website').rename(website)
                    if (backup / 'GENERATED_COPY.json').exists():
                        (backup / 'GENERATED_COPY.json').replace(approved_copy)
                    else:
                        approved_copy.unlink(missing_ok=True)
                except OSError as error:
                    keep_backup = True
                    raise RuntimeError(f'The build failed and its previous files could not be fully restored. The backup is kept at {backup}.') from error
        return result
    except Exception:
        save_status(client_folder, "FAILED")
        (client_folder / "DELIVERY.json").unlink(missing_ok=True)
        raise
    finally:
        if backup is not None and not keep_backup:
            shutil.rmtree(backup, ignore_errors=True)


def _run_pipeline(client_folder, preserve_content=False):

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


    print("\n[start] Starting website generation...")


    # ----------------------------
    # Step 2: Generate Website
    # ----------------------------

    website_dir = generate_website(ai_handoff, preserve_content=True) if preserve_content else generate_website(ai_handoff)


    print(
        f"Website created: {website_dir}"
    )


    # ----------------------------
    # Step 3: Validate Website
    # ----------------------------

    print("\n[check] Running quality validation...")


    report_path = validate(client_folder)
    report_path = Path(report_path)

    if not report_path.exists():
        raise RuntimeError(f"Validator did not create a report: {report_path}")

    with report_path.open("r", encoding="utf-8") as report_file:
        report = json.load(report_file)

    print(f"Validation report: {report_path}")


    # ----------------------------
    # Step 4: Check Validation
    # ----------------------------

    status = "PASS" if report.get("status") == "PASS" else "FAILED"



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

        sales_package = generate_sales_package(client_folder)
        print(f"Sales package created: {sales_package}")


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


    status = run_pipeline(args.client_folder)
    if status != "PASS":
        raise SystemExit(1)



if __name__ == "__main__":

    main()
