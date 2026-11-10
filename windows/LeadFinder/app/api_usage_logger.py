import json
from pathlib import Path
from datetime import datetime


def log_usage(client, usage):

    log_folder = Path("logs")

    log_folder.mkdir(
        exist_ok=True
    )


    file = log_folder / "api_usage.json"


    data = []

    if file.exists():

        data = json.loads(
            file.read_text(
                encoding="utf-8"
            )
        )


    data.append({

        "client": client,

        "prompt_tokens":
            usage.prompt_tokens,

        "completion_tokens":
            usage.completion_tokens,

        "total_tokens":
            usage.total_tokens,

        "date":
            datetime.now().isoformat()

    })


    file.write_text(

        json.dumps(
            data,
            indent=2
        ),

        encoding="utf-8"

    )