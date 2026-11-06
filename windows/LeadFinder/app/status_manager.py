import json
from datetime import datetime
from pathlib import Path


def get_status_file(client):

    return client / "STATUS.json"



def save_status(client, status):

    data = {
        "client": client.name,
        "status": status,
        "updated_at": datetime.now().isoformat()
    }


    file = get_status_file(client)


    file.write_text(
        json.dumps(
            data,
            indent=2
        ),
        encoding="utf-8"
    )



def get_status(client):

    file = get_status_file(client)


    if not file.exists():

        return None


    return json.loads(
        file.read_text(
            encoding="utf-8"
        )
    )



def is_completed(client):

    status = get_status(client)


    if not status:

        return False


    return status.get("status") == "PASS"