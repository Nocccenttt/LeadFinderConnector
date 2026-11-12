import csv
import json
import hashlib
import os
import secrets
from io import BytesIO, StringIO
from pathlib import Path
from threading import Lock, Thread
from time import time
from datetime import date, datetime, timezone
from uuid import uuid4
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file, send_from_directory, url_for

from pipeline_runner import run_pipeline
from seo_lead_finder_prospecting_batch import run as run_lead_finder
from api_settings import key_status, save_keys, test_key, safe_job_error
from social_discovery import crawl_socials, legacy_social_fields, saved_profiles
from website_status import website_status
from website_validator import validate
from status_manager import save_status
from delivery_manager import create_delivery_json
from job_store import save_jobs, load_jobs
from build_progress import observe_build
from release_info import VERSION

load_dotenv(Path(__file__).resolve().parent / '.env', override=True)

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
APP_ROOT = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parent
HANDOFFS = ROOT / "codex_handoffs"

jobs = load_jobs(ROOT)
jobs_lock = Lock()
workflow_write_lock = Lock()
settings_token = secrets.token_urlsafe(32)


@app.before_request
def require_local_workspace():
    # The dashboard is a local app, including searches/builds that use saved keys.
    if urlparse(request.host_url).hostname not in ('localhost', '127.0.0.1', '::1'):
        return jsonify({'error': 'Open LeadFinder using its local app address.'}), 403
    origin = request.headers.get('Origin')
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and origin and origin.rstrip('/') != request.host_url.rstrip('/'):
        return jsonify({'error': 'Make changes from the local LeadFinder workspace.'}), 403


@app.after_request
def isolate_generated_previews(response):
    # Generated HTML must not share the dashboard's origin, even in a new tab.
    if request.endpoint in ('demo_named', 'demo_asset_named'):
        response.headers['Content-Security-Policy'] = 'sandbox allow-scripts'
        asset = (request.view_args or {}).get('asset', '')
        if Path(asset).suffix.lower() in ('.ttf', '.otf', '.woff', '.woff2'):
            response.headers['Access-Control-Allow-Origin'] = '*'
    return response


def preview_info(folder, building=None):
    if building is None:
        with jobs_lock:
            building = any(job.get('kind') == 'website' and job.get('status') in ('queued', 'running') and
                           job.get('client') == str(folder) for job in jobs.values())
    info = website_status(folder, building=building)
    return {**info,
            'preview_url': url_for('demo_named', priority=folder.parent.name, name=folder.name) if info['available'] else '',
            'download_url': url_for('download_demo_named', priority=folder.parent.name, name=folder.name, kind='draft') if info['can_download_draft'] else '',
            'approved_download_url': url_for('download_demo_named', priority=folder.parent.name, name=folder.name, kind='reviewed') if info['approved'] else ''}

WORKFLOW_STATUSES = ("NEW", "CONTACTED", "FOLLOW_UP", "INTERESTED", "CLOSED")


def read_lead_workflow(folder):
    workflow = {"status": "NEW", "notes": "", "follow_up_date": ""}
    try:
        saved = json.loads((folder / "lead_workflow.json").read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            status = str(saved.get("status") or "NEW").upper()
            workflow["status"] = status if status in WORKFLOW_STATUSES else "NEW"
            workflow["notes"] = str(saved.get("notes") or "")[:5000]
            follow_up = str(saved.get("follow_up_date") or "")
            if follow_up:
                date.fromisoformat(follow_up)
                workflow["follow_up_date"] = follow_up
    except (OSError, ValueError, TypeError):
        pass
    return workflow


def write_lead_workflow(folder, workflow):
    with workflow_write_lock:
        output = folder / "lead_workflow.json"
        temporary = folder / f".lead-workflow-{uuid4().hex}.tmp"
        try:
            temporary.write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding="utf-8")
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)


def discover_leads():
    leads = []
    for priority in ("HIGH", "MEDIUM", "LOW"):
        folder = HANDOFFS / priority
        if not folder.is_dir():
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
            workflow = read_lead_workflow(client_folder)
            ready = preview["available"]
            leads.append({
                "client_id": client_folder.name,
                "name": business.get("business_name", client_folder.name),
                "address": business.get("address", ""),
                "phone": business.get("phone", ""),
                "website": website,
                "email": business.get('email', ''),
                "email_found_on": business.get('email_found_on') or business.get('email_source_url', ''),
                **legacy_social_fields(saved_profiles(business)),
                "social_profiles": saved_profiles(business),
                "social_scan": business.get('social_scan', {}) if isinstance(business.get('social_scan'), dict) else {},
                "priority": priority,
                "score": score,
                "reason": business.get("opportunity_reasons", ""),
                "category": business.get("business_type") or business.get("niche") or "",
                "can_generate": resolve_client(priority, client_folder.name) is not None,
                "preview_state":preview["state"],
                "website_status": preview,
                "website_state": preview['state'],
                "files_available": preview['available'],
                "qa_status": preview['qa']['status'],
                "delivery_review": 'APPROVED' if preview['approved'] else 'PENDING' if preview['qa_passed'] else 'NOT_READY',
                "preview_message":preview["message"],
                "qa": preview["qa"],
                "workflow": workflow,
                "folder": str(client_folder.relative_to(ROOT)),
                "demo_ready": ready,  # Legacy preview-availability alias; delivery readiness is in website_status.
                "demo_url": url_for("demo_named", priority=priority, name=client_folder.name) if ready else "",
                "download_url": preview["download_url"],
                "approved_download_url": preview["approved_download_url"],
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
        save_jobs(ROOT, jobs)


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
        message = safe_job_error(error, 'google')
        update_job(
            job_id,
            {"type": "error", "text": f"✕ {message}"},
            status="error", phase="Error", message=message,
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
        interrupted = [{"job_id": key, **value} for key, value in jobs.items() if value.get('interrupted') and not any(
            other.get('kind') == value.get('kind') and other.get('priority') == value.get('priority') and
            other.get('client_id') == value.get('client_id') and other.get('started_at', 0) > value.get('started_at', 0)
            for other in jobs.values())]
    response = jsonify({"workspace_id":hashlib.sha256(str(HANDOFFS.resolve()).encode()).hexdigest()[:12],
                    "workspace_token": settings_token,
                    "capabilities":{"search_configured":bool(os.getenv("GOOGLE_MAPS_API_KEY")),"website_configured":bool(os.getenv("DEEPSEEK_API_KEY"))},
                    "active_jobs":active, "interrupted_jobs":interrupted,
                    "version":VERSION, "data_folder":str(ROOT.resolve())})
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get("/health")
def health():
    return jsonify({"app": "leadfinder", "root": str(ROOT.resolve())})


@app.route('/api-settings', methods=['GET', 'POST'])
def api_settings():
    if urlparse(request.host_url).hostname not in ('localhost', '127.0.0.1', '::1'):
        return jsonify({'error': 'Open API settings from the local LeadFinder app.'}), 403
    if request.method == 'GET':
        response = jsonify({'providers': key_status(), 'token': settings_token})
        response.headers['Cache-Control'] = 'no-store'
        return response
    if not secrets.compare_digest(request.headers.get('X-Settings-Token', '').encode('utf-8'), settings_token.encode('utf-8')):
        return jsonify({'error': 'Reopen API settings and try again.'}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Expected API settings as a JSON object.'}), 400
    try:
        if data.get('action') == 'test':
            result = test_key(data.get('provider'), data.get('key'))
        elif data.get('action') == 'save':
            result = {'providers': save_keys(ROOT / '.env', data.get('keys')),
                      'message': 'API keys saved. New searches and builds use them immediately. Retry the failed task.'}
        else:
            return jsonify({'error': 'Choose Save or Test.'}), 400
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except OSError:
        return jsonify({'error': 'Could not save the keys. Check that the app folder is writable and try again.'}), 500
    response = jsonify(result)
    response.headers['Cache-Control'] = 'no-store'
    return response


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
    niche, area = data.get("niche", ""), data.get("area", "")
    if not isinstance(niche, str) or not isinstance(area, str):
        return jsonify({"error": "Enter the business type and location as text."}), 400
    niche, area = niche.strip(), area.strip()
    if not niche or not area:
        return jsonify({"error": "Business type and location are required."}), 400
    if len(niche) > 180 or len(area) > 180:
        return jsonify({"error": "Keep the business type and location within 180 characters each."}), 400
    try:
        limit = data.get("max_results", 25)
        if isinstance(limit, bool) or not isinstance(limit, (int, str)):
            raise ValueError
        max_results = int(limit)
    except (TypeError, ValueError, OverflowError):
        return jsonify({"error": "Choose a whole number of businesses to find."}), 400
    max_results = max(1, min(max_results, 100))
    job_id = uuid4().hex
    with jobs_lock:
        if any(job.get("kind") == "leads" and job.get("status") in ("queued", "running") for job in jobs.values()):
            return jsonify({"error": "Lead generation is already running."}), 409
        if any(job.get("kind") in ("website", "social") and job.get("status") in ("queued", "running") for job in jobs.values()):
            return jsonify({"error": "Wait for the current website builds or social scans to finish before starting a business search."}), 409
        jobs[job_id] = {"status": "queued", "message": "Queued...", "log": [], "percent": 0, "high": 0, "medium": 0, "low": 0}
        jobs[job_id]["kind"] = "leads"
        jobs[job_id]["started_at"] = time()
        save_jobs(ROOT, jobs)
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
        "ready":sum(1 for lead in items if lead["website_status"]["qa_passed"]),
        "approved":sum(1 for lead in items if lead["website_status"]["approved"]),
        "total": len(items),
        "leads": items,
    })


@app.post("/lead-workflow")
def save_lead_workflow():
    if urlparse(request.host_url).hostname not in ('localhost', '127.0.0.1', '::1'):
        return jsonify({'error': 'Open the local LeadFinder app to update a lead.'}), 403
    if not secrets.compare_digest(request.headers.get('X-Workspace-Token', '').encode('utf-8'), settings_token.encode('utf-8')):
        return jsonify({'error': 'Refresh the workspace before updating this lead.'}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Expected lead workflow details.'}), 400
    folder = resolve_lead_folder(data.get('priority'), data.get('name'))
    if folder is None or not (folder / 'business.json').is_file():
        return jsonify({'error': 'This business is no longer available. Refresh the list.'}), 404
    status = str(data.get('status') or 'NEW').upper()
    if status not in WORKFLOW_STATUSES:
        return jsonify({'error': 'Choose a valid lead status.'}), 400
    notes = data.get('notes', '')
    if not isinstance(notes, str) or len(notes) > 5000:
        return jsonify({'error': 'Keep notes within 5,000 characters.'}), 400
    follow_up = data.get('follow_up_date', '')
    if follow_up is None:
        follow_up = ''
    if not isinstance(follow_up, str):
        return jsonify({'error': 'Choose a valid follow-up date.'}), 400
    follow_up = follow_up.strip()
    if follow_up:
        try:
            date.fromisoformat(follow_up)
        except ValueError:
            return jsonify({'error': 'Choose a valid follow-up date.'}), 400
    workflow = {'status': status, 'notes': notes.strip(), 'follow_up_date': follow_up}
    try:
        write_lead_workflow(folder, workflow)
    except OSError:
        return jsonify({'error': 'Could not save this lead workflow. Check folder permissions and try again.'}), 500
    return jsonify({'workflow': workflow, 'message': 'Lead workflow saved.'})


@app.post("/delete-leads")
def delete_leads():
    if urlparse(request.host_url).hostname not in ('localhost', '127.0.0.1', '::1'):
        return jsonify({'error': 'Open the local LeadFinder app to delete businesses.'}), 403
    origin = request.headers.get('Origin')
    if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
        return jsonify({'error': 'Delete businesses from the local LeadFinder app.'}), 403
    if not secrets.compare_digest(request.headers.get('X-Workspace-Token', '').encode('utf-8'), settings_token.encode('utf-8')):
        return jsonify({'error': 'Refresh the workspace before deleting businesses.'}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('leads'), list) or not data['leads']:
        return jsonify({'error': 'Select at least one business to delete.'}), 400

    targets = []
    seen = set()
    for item in data['leads']:
        if not isinstance(item, dict) or not isinstance(item.get('priority'), str) or not isinstance(item.get('name'), str):
            return jsonify({'error': 'Each business needs its priority and saved name.'}), 400
        priority, name = item['priority'].upper(), item['name']
        if priority not in ('HIGH', 'MEDIUM', 'LOW') or not name or name in ('.', '..') or any(c in name for c in ('/', '\\', ':', '\0')):
            return jsonify({'error': 'Invalid business selection. Refresh the list and try again.'}), 400
        if (priority, name) in seen:
            return jsonify({'error': 'Select each business only once.'}), 400
        seen.add((priority, name))
        targets.append({'priority': priority, 'name': name})

    # Searches, builds and removals share this lock so no job starts using a folder
    # between validation and moving it out of the saved list.
    with jobs_lock:
        if any(job.get('kind') == 'leads' and job.get('status') in ('queued', 'running') for job in jobs.values()):
            return jsonify({'error': 'Wait for the current business search to finish before deleting.'}), 409
        folders = []
        root = ROOT.resolve()
        try:
            handoffs = HANDOFFS.resolve()
        except (OSError, RuntimeError):
            handoffs = None
        if handoffs != root / 'codex_handoffs':
            return jsonify({'error': 'The saved business folder is linked elsewhere. No businesses were deleted.'}), 409
        for item in targets:
            try:
                folder = resolve_lead_folder(item['priority'], item['name'])
            except (OSError, RuntimeError):
                folder = None
            expected = handoffs / item['priority'] / item['name']
            if folder is None or folder != expected or not (folder / 'business.json').is_file():
                return jsonify({'error': 'A selected business is no longer available. Refresh the list and try again.'}), 404
            if any(job.get('status') in ('queued', 'running') and (
                job.get('client') == str(folder) or
                (job.get('priority'), job.get('client_id')) == (item['priority'], item['name'])
            ) for job in jobs.values()):
                return jsonify({'error': 'Wait for the selected businesses to finish building before deleting.'}), 409
            folders.append(folder)

        archive = root / 'outputs' / 'deleted_leads'
        try:
            safe_archive = (root / 'outputs').resolve() == root / 'outputs' and archive.resolve() == archive
        except (OSError, RuntimeError):
            safe_archive = False
        if not safe_archive:
            return jsonify({'error': 'The deleted business folder is linked elsewhere. No businesses were deleted.'}), 409
        batch = archive / uuid4().hex
        moved = []
        try:
            batch.mkdir(parents=True, exist_ok=False)
            for folder in folders:
                destination = batch / folder.parent.name / folder.name
                destination.parent.mkdir(exist_ok=True)
                folder.rename(destination)
                moved.append((folder, destination))
        except OSError:
            # Directory renames retain generated websites and avoid partially
            # deleting file contents if Windows has a file open or a disk fails.
            rollback_failed = False
            for folder, destination in reversed(moved):
                try:
                    destination.rename(folder)
                except OSError:
                    rollback_failed = True
            if rollback_failed:
                return jsonify({'error': 'Could not finish clearing the list. Some businesses remain in outputs/deleted_leads with their saved files. Refresh the list before trying again.'}), 500
            return jsonify({'error': 'Could not delete the selected businesses. No businesses were removed. Close files using these folders and try again.'}), 500

    return jsonify({'deleted_count': len(targets), 'deleted': targets,
                    'message': 'Businesses removed from the saved list. Their files are kept in outputs/deleted_leads.'})


def resolve_client(priority, name):
    folder = resolve_lead_folder(priority, name)
    if folder and str(priority).upper() in ("HIGH", "MEDIUM") and (folder / "AI_HANDOFF.json").is_file():
        return folder
    return None


def resolve_lead_folder(priority, name):
    priority = str(priority or "").upper()
    name = str(name or "")
    if priority not in ("HIGH", "MEDIUM", "LOW") or not name or name in (".", "..") or any(c in name for c in ("/", "\\", ":", "\0")):
        return None
    try:
        handoffs = HANDOFFS.resolve()
        base = (handoffs / priority).resolve()
        folder = (base / name).resolve()
        if base == handoffs / priority and folder == base / name and folder.is_dir():
            return folder
    except (OSError, RuntimeError, ValueError):
        pass
    return None


def website_request_folder(data):
    if not isinstance(data, dict):
        return None, (jsonify({'error': 'Choose a saved business.'}), 400)
    if not secrets.compare_digest(request.headers.get('X-Workspace-Token', '').encode('utf-8'), settings_token.encode('utf-8')):
        return None, (jsonify({'error': 'Refresh the workspace before changing website review.'}), 403)
    folder = resolve_lead_folder(data.get('priority'), data.get('name'))
    if folder is None or not (folder / 'business.json').is_file():
        return None, (jsonify({'error': 'This saved business is no longer available.'}), 404)
    try:
        if any((folder / name).resolve().parent != folder for name in ('business.json', 'quality_report.json', 'STATUS.json', 'DELIVERY.json')):
            return None, (jsonify({'error': 'Saved website metadata is linked elsewhere.'}), 409)
    except (OSError, RuntimeError):
        return None, (jsonify({'error': 'Saved website metadata is unavailable.'}), 409)
    if any(job.get('status') in ('queued', 'running') and (job.get('kind') == 'leads' or job.get('client') == str(folder)) for job in jobs.values()):
        return None, (jsonify({'error': 'Wait for active work on this business to finish.'}), 409)
    return folder, None


@app.post('/validate-website')
def validate_website():
    with jobs_lock:
        folder, error = website_request_folder(request.get_json(silent=True))
        if error:
            return error
        before = preview_info(folder, building=False)
        if not before['can_download_draft']:
            return jsonify({'error': 'Complete website files are required before QA can run.'}), 409
        try:
            (folder / 'DELIVERY.json').unlink(missing_ok=True)
            report = json.loads(Path(validate(folder)).read_text(encoding='utf-8'))
            save_status(folder, 'PASS' if report.get('status') == 'PASS' else 'NEEDS REVIEW')
            if report.get('status') == 'PASS':
                create_delivery_json(folder)
            return jsonify(preview_info(folder, building=False))
        except (OSError, ValueError, RuntimeError):
            app.logger.exception('Website QA recheck failed.')
            return jsonify({'error': 'QA could not finish. Your website files were kept; retry the check.'}), 500


@app.post('/delivery-review')
def delivery_review():
    data = request.get_json(silent=True)
    with jobs_lock:
        folder, error = website_request_folder(data)
        if error:
            return error
        if data.get('action') not in ('approve', 'revoke'):
            return jsonify({'error': 'Choose approve or revoke.'}), 400
        output = folder / 'DELIVERY.json'
        if data['action'] == 'revoke':
            try:
                output.unlink(missing_ok=True)
            except OSError:
                return jsonify({'error': 'Delivery review could not be removed. Check folder permissions and retry.'}), 500
            return jsonify(preview_info(folder, building=False))
        info = preview_info(folder, building=False)
        if not info['can_review'] or data.get('fingerprint') != info['fingerprint'] or data.get('qa_report_hash') != info['qa_report_hash']:
            return jsonify({'error': 'The website or QA result changed. Refresh, recheck QA, and review the current draft.'}), 409
        reviewed = {'client': folder.name, 'pipeline_stage': 'REVIEWED_FOR_DELIVERY', 'website_status': 'PASS',
                    'qa_status': 'PASS', 'approval_status': 'APPROVED', 'website_fingerprint': info['fingerprint'],
                    'qa_report_hash': info['qa_report_hash'], 'reviewed_at': datetime.now(timezone.utc).isoformat()}
        temporary = folder / f'.delivery-review-{uuid4().hex}.tmp'
        try:
            temporary.write_text(json.dumps(reviewed, indent=2), encoding='utf-8')
            temporary.replace(output)
        except OSError:
            return jsonify({'error': 'Delivery review could not be saved. Check folder permissions and try again.'}), 500
        finally:
            temporary.unlink(missing_ok=True)
        return jsonify(preview_info(folder, building=False))


def run_social_discovery(job_id, folder):
    try:
        update_job(job_id, status='running', message='Finding linked social profiles and public business details…')
        business_file = folder / 'business.json'
        if business_file.resolve().parent != folder:
            raise ValueError('The saved business file is linked elsewhere.')
        business = json.loads(business_file.read_text(encoding='utf-8'))
        report = crawl_socials(business, progress=lambda message: update_job(job_id, message=message))
        # Re-read before writing so unrelated enrichment made during the scan is retained.
        if resolve_lead_folder(folder.parent.name, folder.name) != folder or business_file.resolve().parent != folder:
            raise ValueError('The saved business location changed during the scan.')
        current = json.loads(business_file.read_text(encoding='utf-8'))
        current.update(social_profiles=report['profiles'], social_scan={key: value for key, value in report.items() if key != 'profiles'})
        current.update(legacy_social_fields(report['profiles']))
        for name in ('AI_HANDOFF.json', 'WEBSITE_GENERATOR_PROMPT.md'):
            if (folder / name).resolve().parent != folder:
                raise ValueError('The saved handoff is linked elsewhere.')
        updates = [(business_file, current)]
        handoff_file = folder / 'AI_HANDOFF.json'
        if handoff_file.is_file():
            handoff = json.loads(handoff_file.read_text(encoding='utf-8'))
            presence = handoff.get('verified_online_presence', {})
            handoff['verified_online_presence'] = {
                **(presence if isinstance(presence, dict) else {}), **legacy_social_fields(report['profiles']),
                'social_profiles': report['profiles'], 'social_scan': current['social_scan'],
                'social_profile_note': 'Profiles are linked-source observations. Review business identity and public bios before using them as verified business claims.',
            }
            updates.append((handoff_file, handoff))
        for target, value in updates:
            temporary = target.with_name(f'.{target.name}-social-{job_id}.tmp')
            try:
                temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        update_job(job_id, status='complete', message=report['note'])
    except Exception:
        app.logger.exception('Social profile discovery failed.')
        update_job(job_id, status='error', message='Could not complete the social scan. Saved business data is still available; refresh and try again.')


@app.post('/social-discovery')
def social_discovery():
    if not secrets.compare_digest(request.headers.get('X-Workspace-Token', '').encode('utf-8'), settings_token.encode('utf-8')):
        return jsonify({'error': 'Refresh the workspace before scanning social profiles.'}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Choose a saved business to scan.'}), 400
    job_id = uuid4().hex
    with jobs_lock:
        folder = resolve_lead_folder(data.get('priority'), data.get('name'))
        if folder is None or not (folder / 'business.json').is_file():
            return jsonify({'error': 'This saved business is no longer available.'}), 404
        if any(job.get('status') in ('queued', 'running') and
               (job.get('kind') == 'leads' or job.get('client') == str(folder)) for job in jobs.values()):
            return jsonify({'error': 'Wait for the active search or work on this business to finish.'}), 409
        if sum(job.get('kind') == 'social' and job.get('status') in ('queued', 'running') for job in jobs.values()) >= 2:
            return jsonify({'error': 'Two social scans are already running. Wait for one to finish.'}), 409
        jobs[job_id] = {'kind': 'social', 'status': 'queued', 'message': 'Queued social scan…',
                        'client': str(folder), 'priority': folder.parent.name, 'client_id': folder.name, 'started_at': time()}
        save_jobs(ROOT, jobs)
    Thread(target=run_social_discovery, args=(job_id, folder), daemon=True).start()
    return jsonify({'job_id': job_id})


def run_landing_page(job_id, client_folder, preserve_content=False):
    try:
        update_job(job_id, status="running", started_at=time(),message="Researching, writing and building your website. This can take a few minutes.")
        with observe_build(lambda phase, message: update_job(job_id, phase=phase, message=message, phase_started_at=time())):
            status = run_pipeline(client_folder, preserve_content=True) if preserve_content else run_pipeline(client_folder)
        if status != "PASS":
            raise RuntimeError("Website validation failed; review quality_report.json.")
        with app.test_request_context():
            preview = preview_info(client_folder, building=False)
        if not preview["available"]:
            raise RuntimeError(preview["message"])
        update_job(job_id, status="complete", finished_at=time(), phase="complete", message="Website draft built. Check QA and review before delivery.",
                   preview_url=preview["preview_url"], download_url=preview["download_url"])
    except Exception as error:
        update_job(job_id, status="error", finished_at=time(), message=safe_job_error(error, 'deepseek'))


@app.post("/generate-landing-page")
def generate_landing_page():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object."}), 400
    job_id = uuid4().hex
    with jobs_lock:
        client_folder = resolve_client(data.get("priority"), data.get("name"))
        if not client_folder:
            return jsonify({"error": "Lead handoff not found. Generate the lead handoff first."}), 404
        if any(job.get("kind") == "leads" and job.get("status") in ("queued", "running") for job in jobs.values()):
            return jsonify({"error": "Wait for the current business search to finish before building a website."}), 409
        if any(job.get("client") == str(client_folder) and job.get("status") in ("queued", "running") for job in jobs.values()):
            return jsonify({"error": "A landing page is already being generated for this lead."}), 409
        if sum(job.get('kind') == 'website' and job.get('status') in ('queued', 'running') for job in jobs.values()) >= 2:
            return jsonify({'error': 'Two website builds are already running. Wait for one to finish before starting another.'}), 409
        jobs[job_id] = {"status": "queued", "message": "Queued website build...", "kind":"website",
                        "priority":client_folder.parent.name,"client_id":client_folder.name,"started_at":time()}
        jobs[job_id]["client"] = str(client_folder)
        save_jobs(ROOT, jobs)
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
    try:
        if website.resolve().parent != folder or not (website / "index.html").is_file():
            return None
        if (website / "index.html").resolve().parent != website.resolve():
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return folder


@app.get("/demo/codex_handoffs/<priority>/<name>/<path:asset>")
@app.get("/demo/<priority>/<name>/<path:asset>")
def demo_asset_named(priority, name, asset):
    folder = get_demo_folder(priority, name)
    if not folder:
        return "Landing page not found.", 404
    website = folder / "website"
    try:
        file_path = (website / asset).resolve()
        valid = file_path.is_file() and website.resolve() in file_path.parents
    except (OSError, RuntimeError, ValueError):
        valid = False
    if not valid:
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

    folder = resolve_lead_folder(priority, name)
    if folder is None:
        return jsonify({'error': 'Website not found.'}), 404
    kind = request.args.get('kind', 'draft')
    if kind not in ('draft', 'reviewed'):
        return jsonify({'error': 'Choose a draft or reviewed download.'}), 400
    with jobs_lock:
        busy = any(job.get('status') in ('queued', 'running') and
                   (job.get('kind') == 'leads' or job.get('kind') == 'website' and job.get('client') == str(folder)) for job in jobs.values())
        info = preview_info(folder, building=busy)
        if not info['can_download_draft']:
            return jsonify({'error': 'Complete, stable website files are required. Wait for the build or retry it.'}), 409
        if kind == 'reviewed' and not info['approved']:
            return jsonify({'error': 'These files have not passed QA and delivery review. Download a draft or review the current website.'}), 409
        package = BytesIO()
        with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for file in (folder / 'website').rglob('*'):
                if file.is_file():
                    archive.write(file, file.relative_to(folder / 'website'))
        after = preview_info(folder, building=False)
        if after['fingerprint'] != info['fingerprint'] or kind == 'reviewed' and not after['approved']:
            return jsonify({'error': 'Website files changed while preparing the ZIP. Refresh and retry.'}), 409
    package.seek(0)
    label = 'reviewed' if kind == 'reviewed' else 'DRAFT'
    return send_file(package, as_attachment=True, download_name=f'{folder.name}-{label}-website.zip', mimetype='application/zip')


@app.get("/export")
def export():
    leads = discover_leads()
    fields = ["name", "address", "phone", "email", "email_found_on", "website", "priority", "score", "reason",
              "website_state", "qa_status", "delivery_review",
              "facebook", "instagram", "linkedin", "other_socials", "social_profiles", "social_scan"]
    def text_cell(value):
        if isinstance(value, dict) or isinstance(value, list) and any(isinstance(item, dict) for item in value):
            value = json.dumps(value, ensure_ascii=False)
        if isinstance(value, list):
            value = '; '.join(str(item) for item in value)
        text = str(value) if value is not None else ''
        # Web-sourced names and phone numbers must remain text in spreadsheets.
        if text.lstrip('\ufeff \t\r\n').startswith(('=', '+', '-', '@')):
            text = "'" + text
        return text

    file = StringIO(newline='')
    writer = csv.DictWriter(file, fieldnames=fields)
    writer.writeheader()
    writer.writerows({field: text_cell(lead.get(field, '')) for field in fields} for lead in leads)
    # Each download owns its snapshot; a second export cannot replace its bytes.
    package = BytesIO(file.getvalue().encode('utf-8-sig'))
    return send_file(package, as_attachment=True, download_name="leadfinder_leads.csv", mimetype='text/csv')


if __name__ == "__main__":
    port = int(os.getenv("LEADFINDER_PORT", "3000"))
    print()
    print("==============================")
    print("       LEADFINDER")
    print("==============================")
    print()
    print(f"Open: http://127.0.0.1:{port}")
    print()
    print("Dashboard file:", Path(__file__).resolve())
    print("Workspace UI: modern minimal")
    from dashboard_server import serve_dashboard
    serve_dashboard(app, port)
