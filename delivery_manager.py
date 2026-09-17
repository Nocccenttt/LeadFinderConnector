import json
from datetime import datetime
from pathlib import Path


def create_delivery_json(client_folder):

    delivery = {
        "client": client_folder.name,
        "pipeline_stage": "DELIVERY_READY",
        "website_status": "PASS",
        "qa_status": "PASS",
        "approval_status": "PENDING",
        "created_at": datetime.now().isoformat()
    }


    output = (
        client_folder /
        "DELIVERY.json"
    )


    output.write_text(
        json.dumps(
            delivery,
            indent=2
        ),
        encoding="utf-8"
    )


    return output