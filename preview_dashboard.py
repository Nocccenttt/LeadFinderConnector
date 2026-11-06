import csv
import json
import hashlib
import os
from io import BytesIO
from pathlib import Path
from threading import Lock, Thread
from time import time
from uuid import uuid4
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file, send_from_directory, url_for

from pipeline_runner import run_pipeline
from seo_lead_finder_prospecting_batch import run as run_lead_finder

load_dotenv()

app = Flask(__name__)
APP_ROOT = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parent
HANDOFFS = ROOT / "codex_handoffs"

jobs = {}
jobs_lock = Lock()


def preview_info(folder):
    website = folder / "website"
    missing = []
    for name in ("index.html", "styles.css", "script.js"):
        asset = website / name
        try:
            valid = (website.resolve().parent == folder.resolve() and asset.is_file()
                     and asset.resolve().parent == website.resolve() and asset.stat().st_size > 0)
        except OSError:
            # A build can replace files while this read-only status request runs.
            valid = False
        if not valid:
            missing.append(name)
    available = not missing
    state = "ready" if available else "incomplete" if website.exists() else "missing"
    message = {
        "ready": "Website ready to preview.",
        "incomplete": "The website files are incomplete. Build it again to create a complete preview.",
        "missing": "No website has been built for this business yet.",
    }[state]
    for filename in ("STATUS.json", "quality_report.json"):
        try:
            status = json.loads((folder / filename).read_text(encoding="utf-8")).get("status")
            if status in ("FAILED", "NEEDS REVIEW"):
                state = "failed"
                message = "The last build needs attention. You can retry the build."
        except (OSError, ValueError, AttributeError):
            continue
    return {
        "available": available, "state": state, "message": message, "missing_assets": missing,
        "preview_url": url_for("demo_named", priority=folder.parent.name, name=folder.name) if available else "",
        "download_url": url_for("download_demo_named", priority=folder.parent.name, name=folder.name) if available else "",
    }

def discover_leads():
    leads = []
    for priority in ("HIGH", "MEDIUM", "LOW"):
        folder = HANDOFFS / priority
        if not folder.exists():
            continue
        for client_folder in folder.iterdir():
            if resolve_lead_folder(priority, client_folder.name) is None:
                continue
            business_file = client_folder / "business.json"
            if not business_file.exists():
                continue
            try:
                business = json.loads(business_file.read_text(encoding="utf-8"))
                if not isinstance(business, dict):
                    continue
                score = int(business.get("opportunity_score") or 0)
                website = str(business.get("website") or "")
                parsed = urlparse(website)
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    website = ""
            except Exception:
                continue
            preview = preview_info(client_folder)
            ready = preview["available"]
            leads.append({
                "client_id": client_folder.name,
                "name": business.get("business_name", client_folder.name),
                "address": business.get("address", ""),
                "phone": business.get("phone", ""),
                "website": website,
                "priority": priority,
                "score": score,
                "reason": business.get("opportunity_reasons", ""),
                "category": business.get("business_type") or business.get("niche") or "",
                "can_generate": resolve_client(priority, client_folder.name) is not None,
                "preview_state":preview["state"],
                "preview_message":preview["message"],
                "folder": str(client_folder.relative_to(ROOT)),
                "demo_ready": ready,
                "demo_url": url_for("demo_named", priority=priority, name=client_folder.name) if ready else "",
                "download_url": url_for("download_demo_named", priority=priority, name=client_folder.name) if ready else "",
            })
    leads.sort(key=lambda lead: (0 if lead["priority"] == "HIGH" else 1 if lead["priority"] == "MEDIUM" else 2, -int(lead["score"] or 0)))
    return leads


def update_job(job_id, event=None, **changes):
    with jobs_lock:
        job = jobs.setdefault(job_id, {})
        job.update(changes)
        if event:
            job.setdefault("log", []).append(event)
            job["log"] = job["log"][-40:]


def make_progress_callback(job_id):
    started = time()

    def progress(event):
        event = dict(event or {})
        update_job(
            job_id,
            {"type": event.get("log_type", "work"), "text": event.get("log", event.get("message", ""))},
            phase=event.get("phase", "Working"),
            subphase=event.get("subphase", ""),
            current_business=event.get("current_business", ""),
            current_index=event.get("current_index", 0),
            total=event.get("total", 0),
            percent=event.get("percent", 0),
            high=event.get("high", 0),
            medium=event.get("medium", 0),
            low=event.get("low", 0),
            message=event.get("message", "Working..."),
            elapsed_seconds=int(time() - started),
        )

    return progress


def run_generation(job_id, niche, area, max_results):
    started = time()
    try:
        callback = make_progress_callback(job_id)
        update_job(
            job_id,
            {"type": "work", "text": "Starting LeadFinder..."},
            status="running", phase="Starting", subphase=f"{niche} • {area}",
            current_business="", current_index=0, total=0, percent=0,
            high=0, medium=0, low=0, message="Starting crawler...",
            elapsed_seconds=0,
        )
        run_lead_finder(
            niche=niche,
            area=area,
            output="leads.csv",
            max_results=max_results,
            output_dir=ROOT / "outputs",
            codex_dir=HANDOFFS,
            progress_callback=callback,
        )
        with jobs_lock:
            current = dict(jobs.get(job_id, {}))
        callback({
            "phase": "Complete",
            "subphase": f"{niche} • {area}",
            "current_business": "",
            "current_index": current.get("total", 0),
            "total": current.get("total", 0),
            "percent": 100,
            "high": current.get("high", 0),
            "medium": current.get("medium", 0),
            "low": current.get("low", 0),
            "message": "Lead generation complete.",
            "log_type": "ok",
            "log": "✓ Lead generation complete.",
        })
        update_job(job_id, status="complete", message="Lead generation complete.", elapsed_seconds=int(time() - started))
    except Exception as error:
        update_job(
            job_id,
            {"type": "error", "text": f"✕ {error}"},
            status="error", phase="Error", message=str(error),
            percent=0, elapsed_seconds=int(time() - started),
        )


@app.get("/")
def home():
    return render_template("dashboard.html")


@app.get("/dashboard-font")
def dashboard_font():
    return send_file(APP_ROOT/"assets/fonts/Geist.ttf", mimetype="font/ttf")


@app.get("/session")
def session_state():
    with jobs_lock:
        active = [{"job_id":job_id, **{key:job.get(key) for key in ("kind","status","message","priority","client_id","started_at")}}
                  for job_id,job in jobs.items() if job.get("status") in ("queued","running")]
    return jsonify({"workspace_id":hashlib.sha256(str(HANDOFFS.resolve()).encode()).hexdigest()[:12],
                    "capabilities":{"search_configured":bool(os.getenv("GOOGLE_MAPS_API_KEY")),"website_configured":bool(os.getenv("DEEPSEEK_API_KEY"))},
                    "active_jobs":active})


@app.get("/preview-status")
def preview_status():
    folder = resolve_lead_folder(request.args.get("priority"), request.args.get("name"))
    if folder is None:
        return jsonify({"error":"Business not found. Refresh the list and select it again."}),404
    return jsonify(preview_info(folder))


@app.post("/generate")
def generate():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object."}), 400
    niche = str(data.get("niche", "")).strip()
    area = str(data.get("area", "")).strip()
    if not niche or not area:
        return jsonify({"error": "Business type and location are required."}), 400
    try:
        max_results = int(data.get("max_results", 25))
    except (TypeError, ValueError):
        max_results = 25
    max_results = max(1, min(max_results, 100))
    job_id = uuid4().hex
    with jobs_lock:
        if any(job.get("kind") == "leads" and job.get("status") in ("queued", "running") for job in jobs.values()):
            return jsonify({"error": "Lead generation is already running."}), 409
        jobs[job_id] = {"status": "queued", "message": "Queued...", "log": [], "percent": 0, "high": 0, "medium": 0, "low": 0}
        jobs[job_id]["kind"] = "leads"
        jobs[job_id]["started_at"] = time()
    Thread(target=run_generation, args=(job_id, niche, area, max_results), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.get("/job-status")
def job_status():
    job_id = request.args.get("job_id")
    with jobs_lock:
        job = dict(jobs.get(job_id, {}))
    if not job:
        return jsonify({"status": "error", "message": "Job not found."}), 404
    return jsonify(job)


@app.get("/leads")
def leads():
    items = discover_leads()
    return jsonify({
        "high": sum(1 for lead in items if lead["priority"] == "HIGH"),
        "medium": sum(1 for lead in items if lead["priority"] == "MEDIUM"),
        "low": sum(1 for lead in items if lead["priority"] == "LOW"),
        "ready":sum(1 for lead in items if lead["demo_ready"]),
        "total": len(items),
        "leads": items,
    })


def resolve_client(priority, name):
    folder = resolve_lead_folder(priority, name)
    if folder and str(priority).upper() in ("HIGH", "MEDIUM") and (folder / "AI_HANDOFF.json").is_file():
        return folder
    return None


def resolve_lead_folder(priority, name):
    priority = str(priority or "").upper()
    name = str(name or "")
    if priority not in ("HIGH", "MEDIUM", "LOW") or not name or name in (".", "..") or any(c in name for c in ("/", "\\", ":")):
        return None
    base = (HANDOFFS / priority).resolve()
    folder = (base / name).resolve()
    if base.parent == HANDOFFS.resolve() and folder.parent == base and folder.is_dir():
        return folder
    return None


def run_landing_page(job_id, client_folder, preserve_content=False):
    try:
        update_job(job_id, status="running", started_at=time(),message="Researching, writing and building your website. This can take a few minutes.")
        status = run_pipeline(client_folder, preserve_content=True) if preserve_content else run_pipeline(client_folder)
        if status != "PASS":
            raise RuntimeError("Website validation failed; review quality_report.json.")
        with app.test_request_context():
            preview = preview_info(client_folder)
        if not preview["available"]:
            raise RuntimeError(preview["message"])
        update_job(job_id, status="complete", message="Landing page ready.",
                   preview_url=preview["preview_url"], download_url=preview["download_url"])
    except Exception as error:
        update_job(job_id, status="error", message=str(error))


@app.post("/generate-landing-page")
def generate_landing_page():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object."}), 400
    client_folder = resolve_client(data.get("priority"), data.get("name"))
    if not client_folder:
        return jsonify({"error": "Lead handoff not found. Generate the lead handoff first."}), 404
    job_id = uuid4().hex
    with jobs_lock:
        if any(job.get("client") == str(client_folder) and job.get("status") in ("queued", "running") for job in jobs.values()):
            return jsonify({"error": "A landing page is already being generated for this lead."}), 409
        jobs[job_id] = {"status": "queued", "message": "Queued website build...", "kind":"website",
                        "priority":client_folder.parent.name,"client_id":client_folder.name,"started_at":time()}
        jobs[job_id]["client"] = str(client_folder)
    Thread(target=run_landing_page, args=(job_id, client_folder, data.get("preserve_content") is True), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.get("/landing-page-status")
def landing_page_status():
    job_id = request.args.get("job_id")
    with jobs_lock:
        job = dict(jobs.get(job_id, {}))
    if not job:
        return jsonify({"status": "error", "message": "Job not found."}), 404
    return jsonify(job)


def get_demo_folder(priority, name):
    folder = resolve_lead_folder(priority, name)
    if folder is None:
        return None
    website = folder / "website"
    if website.resolve().parent != folder or not (website / "index.html").is_file():
        return None
    if (website / "index.html").resolve().parent != website.resolve():
        return None
    return folder


@app.get("/demo/codex_handoffs/<priority>/<name>/<path:asset>")
@app.get("/demo/<priority>/<name>/<path:asset>")
def demo_asset_named(priority, name, asset):
    folder = get_demo_folder(priority, name)
    if not folder:
        return "Landing page not found.", 404
    website = folder / "website"
    file_path = (website / asset).resolve()
    if not file_path.is_file() or website.resolve() not in file_path.parents:
        return "Asset not found.", 404
    return send_from_directory(website, file_path.relative_to(website.resolve()).as_posix())


@app.get("/demo/codex_handoffs/<priority>/<name>/")
@app.get("/demo/<priority>/<name>/")
def demo_named(priority, name):
    folder = get_demo_folder(priority, name)
    if not folder:
        return "Landing page not found.", 404
    return send_from_directory(folder / "website", "index.html")


@app.get("/download-demo/codex_handoffs/<priority>/<name>")
@app.get("/download-demo/<priority>/<name>")
def download_demo_named(priority, name):
    import zipfile

    folder = get_demo_folder(priority, name)
    if not folder:
        return "Landing page not found.", 404
    website = folder / "website"
    required = ["index.html", "styles.css", "script.js"]
    missing = [item for item in required if not (website / item).is_file()]
    if missing:
        return "Landing page package is incomplete. Missing: " + ", ".join(missing), 500

    # Each request owns its archive; simultaneous downloads cannot overwrite it.
    package = BytesIO()
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in website.rglob("*"):
            if file.is_file() and website.resolve() in file.resolve().parents:
                archive.write(file, file.relative_to(website))
    package.seek(0)
    return send_file(package, as_attachment=True,
                     download_name=f"{folder.name}-landing-page.zip", mimetype="application/zip")


@app.get("/export")
def export():
    leads = discover_leads()
    export_file = ROOT / "outputs" / "leadfinder_export.csv"
    export_file.parent.mkdir(exist_ok=True)
    fields = ["name", "address", "phone", "website", "priority", "score", "reason"]
    with export_file.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: lead.get(field, "") for field in fields} for lead in leads)
    return send_file(export_file, as_attachment=True, download_name="leadfinder_leads.csv")


if __name__ == "__main__":
    print()
    print("==============================")
    print("       LEADFINDER")
    print("==============================")
    print()
    print("Open: http://127.0.0.1:3000")
    print()
    print("Dashboard file:", Path(__file__).resolve())
    print("Workspace UI: modern minimal")
    app.run(host="127.0.0.1", port=3000, debug=False)
