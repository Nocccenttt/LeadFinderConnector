import json
from pathlib import Path


client_folder = Path(
    r"codex_handoffs\HIGH\Brown's Tree Service"
)


data = {
    "client": "Brown's Tree Service",
    "status": "READY_FOR_REVIEW",
    "website": True,
    "qa": "PASS"
}


output = client_folder / "REVIEW.json"


with output.open(
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        data,
        f,
        indent=2
    )


print(
    f"Created: {output}"
)