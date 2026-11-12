"""Give the windowless Windows process persistent startup and application logs."""
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
logs = root / "logs"
logs.mkdir(exist_ok=True)
sys.stdout = (logs / "dashboard.out.log").open("a", encoding="utf-8", buffering=1)
sys.stderr = (logs / "dashboard.err.log").open("a", encoding="utf-8", buffering=1)
sys.path.insert(0, str(root))
runpy.run_path(str(root / "preview_dashboard.py"), run_name="__main__")
