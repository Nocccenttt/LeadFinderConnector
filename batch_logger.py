import json
from datetime import datetime
from pathlib import Path


class BatchLogger:

    def __init__(self):

        timestamp = datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        self.run_dir = (
            Path("batch_runs")
            / timestamp
        )

        self.run_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.completed = []
        self.failed = []


    def add_completed(self, client):

        self.completed.append(
            {
                "client": client.name,
                "status": "PASS"
            }
        )


    def add_failed(self, client, error):

        self.failed.append(
            {
                "client": client.name,
                "status": "FAILED",
                "error": str(error)
            }
        )


    def save(self):

        summary = {
            "run_time": datetime.now().isoformat(),
            "completed": len(self.completed),
            "failed": len(self.failed),
            "total": (
                len(self.completed)
                +
                len(self.failed)
            )
        }


        (self.run_dir / "summary.json").write_text(
            json.dumps(
                summary,
                indent=2
            ),
            encoding="utf-8"
        )


        (self.run_dir / "completed.json").write_text(
            json.dumps(
                self.completed,
                indent=2
            ),
            encoding="utf-8"
        )


        (self.run_dir / "failed.json").write_text(
            json.dumps(
                self.failed,
                indent=2
            ),
            encoding="utf-8"
        )


        return self.run_dir