import csv
import json
from pathlib import Path
from threading import Lock, Thread
from time import time
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request, send_file, send_from_directory

from pipeline_runner import run_pipeline
from seo_lead_finder_prospecting_batch import run as run_lead_finder

load_dotenv()

app = Flask(__name__)
ROOT = Path(__file__).resolve().parent
HANDOFFS = ROOT / "codex_handoffs"

jobs = {}
jobs_lock = Lock()


HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LeadFinder</title>
<style>
*{box-sizing:border-box}
:root{--bg:#080d18;--panel:#101827;--panel2:#0c1422;--border:#243149;--text:#f4f7fb;--muted:#8e9ab0;--gold:#d7ad52;--green:#75c99b;--red:#e57d7d;--high:#efb27b;--medium:#9db8d8}
body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Arial,Helvetica,sans-serif}
button,input,select{font:inherit}button{cursor:pointer}
.app{width:min(1400px,94%);margin:auto;padding:28px 0 50px}
.header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:24px}
.brand{font-size:27px;font-weight:900;letter-spacing:2px}.subtitle{color:var(--muted);margin-top:5px}
.live{display:flex;align-items:center;gap:8px;color:var(--green);font-size:13px;font-weight:800}.live-dot{width:8px;height:8px;border-radius:50%;background:var(--green)}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:22px;margin-bottom:18px}
.panel-title{font-size:17px;font-weight:800;margin-bottom:18px}
.form{display:grid;grid-template-columns:minmax(220px,1fr) minmax(220px,1fr) 150px 190px;gap:12px}
input,select{width:100%;min-height:48px;padding:0 14px;color:var(--text);background:var(--panel2);border:1px solid var(--border);border-radius:10px;outline:none}
input:focus,select:focus{border-color:var(--gold)}
.primary{min-height:48px;border:0;border-radius:10px;background:var(--gold);color:#111;font-weight:900}.primary:hover{background:#e4bd68}.primary:disabled{opacity:.5;cursor:wait}
.secondary{min-height:44px;padding:0 16px;border-radius:9px;border:1px solid var(--border);background:var(--panel2);color:var(--text);font-weight:700}.secondary:hover{border-color:#3b4a67}.secondary:disabled{opacity:.5;cursor:not-allowed}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.stat{background:var(--panel2);border:1px solid var(--border);border-radius:12px;padding:20px}.stat-number{font-size:31px;font-weight:900}.stat-label{color:var(--muted);margin-top:4px;font-size:13px;text-transform:uppercase;letter-spacing:.7px}
.toolbar{display:grid;grid-template-columns:1fr 150px auto auto;gap:10px;margin-bottom:16px}
.leads{display:grid;gap:12px}.lead{background:var(--panel2);border:1px solid var(--border);border-radius:13px;padding:18px}.lead-top{display:flex;justify-content:space-between;gap:20px}.lead-name{font-size:18px;font-weight:850}.lead-address{color:var(--muted);margin-top:5px;line-height:1.45}.lead-reason{color:#b7c1d1;margin-top:8px;font-size:14px}
.badge{min-width:90px;height:fit-content;padding:7px 11px;border-radius:999px;text-align:center;font-size:12px;font-weight:900}.badge.high{background:rgba(239,178,123,.12);color:var(--high)}.badge.medium{background:rgba(157,184,216,.12);color:var(--medium)}.badge.low{background:rgba(117,201,155,.10);color:var(--green)}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:15px}.actions a,.actions button{display:inline-flex;align-items:center;text-decoration:none;color:var(--text);background:#172237;border:1px solid #273650;padding:8px 12px;border-radius:8px;font-size:12px;font-weight:800}.actions a:hover,.actions button:hover{border-color:var(--gold)}
.empty{color:var(--muted);padding:30px 10px;text-align:center}

.progress-panel{display:none}.progress-head{display:flex;justify-content:space-between;gap:15px;align-items:flex-start}.progress-phase{font-size:22px;font-weight:900}.progress-sub{color:var(--muted);margin-top:5px}.progress-percent{font-size:28px;font-weight:900;color:var(--gold)}
.progress-track{height:10px;background:#1b2638;border-radius:999px;overflow:hidden;margin:20px 0 12px}.progress-bar{width:0;height:100%;background:var(--gold);transition:width .25s ease}
.progress-meta{display:flex;justify-content:space-between;color:var(--muted);font-size:13px}.current-box{margin-top:18px;padding:17px;background:var(--panel2);border:1px solid var(--border);border-radius:12px}.current-label{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--muted)}.current-name{font-size:20px;font-weight:900;margin-top:5px}.current-action{margin-top:6px;color:#d9e0eb}
.mini-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}.mini-stat{padding:13px;background:#0a111e;border:1px solid var(--border);border-radius:10px}.mini-stat strong{font-size:21px}.mini-stat span{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;margin-top:3px}
.activity{margin-top:16px}.activity-title{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:8px}.activity-log{max-height:190px;overflow:auto;background:#090f1b;border:1px solid var(--border);border-radius:10px;padding:8px}.activity-line{padding:7px 8px;border-bottom:1px solid #182236;font-size:13px}.activity-line:last-child{border-bottom:0}.activity-line.ok{color:#cfe9da}.activity-line.work{color:#f0d7a0}.activity-line.error{color:#f0aaaa}
.progress-complete{display:none;margin-top:16px;padding:14px;border:1px solid rgba(117,201,155,.3);border-radius:10px;color:var(--green);font-weight:800}
.progress-error{display:none;margin-top:16px;padding:14px;border:1px solid rgba(229,125,125,.3);border-radius:10px;color:var(--red);font-weight:800}

.demo-grid{display:grid;grid-template-columns:300px 1fr;gap:16px}.demo-info{background:var(--panel2);border:1px solid var(--border);border-radius:12px;padding:17px}.demo-name{font-size:20px;font-weight:900}.demo-meta{color:var(--muted);font-size:13px;line-height:1.6;margin-top:8px}.preview{height:620px;background:#fff;border:1px solid var(--border);border-radius:12px;overflow:hidden}.preview iframe{width:100%;height:100%;border:0;background:#fff}
.status{color:var(--muted);min-height:20px;margin-top:12px}
@media(max-width:900px){.form{grid-template-columns:1fr 1fr}.toolbar{grid-template-columns:1fr 150px}.toolbar button{grid-column:auto}.demo-grid{grid-template-columns:1fr}.preview{height:520px}}
@media(max-width:620px){.app{width:92%;padding-top:20px}.header{align-items:flex-start;flex-direction:column}.form,.stats,.toolbar,.mini-stats{grid-template-columns:1fr}.lead-top,.progress-head{flex-direction:column}.progress-percent{font-size:24px}}
</style>
</head>
<body>
<div class="app">
<header class="header">
<div><div class="brand">LEADFINDER</div><div class="subtitle">Lead Generation & Sales Control Center</div></div>
<div class="live"><span class="live-dot"></span> LIVE</div>
</header>

<section class="panel">
<div class="panel-title">Generate Leads</div>
<div id="frontend-version" class="status">Frontend V3 • Connected.</div>
<form id="generate-form">
<div class="form">
<input id="niche" type="text" placeholder="Business Type" value="Tree Service" required>
<input id="area" type="text" placeholder="Location" value="Raleigh, NC" required>
<select id="max-results"><option value="10">10 Leads</option><option value="25" selected>25 Leads</option><option value="50">50 Leads</option><option value="100">100 Leads</option></select>
<button id="generate-button" class="primary" type="submit">GENERATE LEADS</button>
</div>
</form>
</section>

<section id="progress-panel" class="panel progress-panel">
<div class="progress-head">
<div><div id="progress-phase" class="progress-phase">Starting...</div><div id="progress-sub" class="progress-sub"></div></div>
<div id="progress-percent" class="progress-percent">0%</div>
</div>
<div class="progress-track"><div id="progress-bar" class="progress-bar"></div></div>
<div class="progress-meta"><span id="progress-count">Preparing...</span><span id="progress-elapsed">0s</span></div>
<div class="current-box">
<div class="current-label">Current Business</div>
<div id="current-business" class="current-name">Starting LeadFinder...</div>
<div id="current-action" class="current-action">Preparing crawler...</div>
</div>
<div class="mini-stats">
<div class="mini-stat"><strong id="progress-high">0</strong><span>High</span></div>
<div class="mini-stat"><strong id="progress-medium">0</strong><span>Medium</span></div>
<div class="mini-stat"><strong id="progress-low">0</strong><span>Low</span></div>
</div>
<div class="activity"><div class="activity-title">Live Activity</div><div id="activity-log" class="activity-log"></div></div>
<div id="progress-complete" class="progress-complete">✓ Lead generation complete. Leads are ready below.</div>
<div id="progress-error" class="progress-error"></div>
</section>

<section class="panel">
<div class="stats">
<div class="stat"><div id="high-count" class="stat-number">0</div><div class="stat-label">High</div></div>
<div class="stat"><div id="medium-count" class="stat-number">0</div><div class="stat-label">Medium</div></div>
<div class="stat"><div id="total-count" class="stat-number">0</div><div class="stat-label">Total</div></div>
</div>
</section>

<section class="panel">
<div class="panel-title">Leads</div>
<div class="toolbar">
<input id="search" type="search" placeholder="Search leads...">
<select id="priority-filter"><option value="ALL">All</option><option value="HIGH">High</option><option value="MEDIUM">Medium</option><option value="LOW">Low</option></select>
<button id="refresh" class="secondary" type="button">REFRESH</button>
<button id="export" class="secondary" type="button">EXPORT CSV</button>
</div>
<div id="leads" class="leads"><div class="empty">No leads generated yet.</div></div>
</section>

<section id="demo-panel" class="panel" style="display:none">
<div class="panel-title">Landing Page Demo</div>
<div class="demo-grid">
<div class="demo-info">
<div id="demo-name" class="demo-name">Select a lead</div>
<div id="demo-meta" class="demo-meta"></div>
<div id="demo-status" class="status">Ready.</div>
<div class="actions">
<button id="generate-demo" class="primary" type="button">GENERATE LANDING PAGE</button>
<button id="regenerate-demo" class="secondary" type="button">REGENERATE</button>
<button id="open-preview" class="secondary" type="button">OPEN PREVIEW</button>
<button id="download-demo" class="secondary" type="button">DOWNLOAD WEBSITE ZIP</button>
</div>
</div>
<div class="preview"><iframe id="preview-frame" title="Landing page preview"></iframe></div>
</div>
</section>
</div>

<script>
console.log("LEADFINDER FRONTEND V3 LOADED", window.location.href);
let allLeads=[];
let selectedLead=null;
let activeJob=null;
let statusTimer=null;
let demoTimer=null;

const $=id=>document.getElementById(id);
const form=$("generate-form"), button=$("generate-button"), progressPanel=$("progress-panel");

function escapeHtml(value){
    return String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
}
function resetProgress(){
    $("progress-phase").textContent="Starting LeadFinder...";
    $("progress-sub").textContent="";
    $("progress-percent").textContent="0%";
    $("progress-bar").style.width="0%";
    $("progress-count").textContent="Preparing...";
    $("progress-elapsed").textContent="0s";
    $("current-business").textContent="Starting LeadFinder...";
    $("current-action").textContent="Preparing crawler...";
    $("progress-high").textContent="0";
    $("progress-medium").textContent="0";
    $("progress-low").textContent="0";
    $("activity-log").innerHTML="";
    $("progress-complete").style.display="none";
    $("progress-error").style.display="none";
}
function renderProgress(job){
    const percent=Math.max(0,Math.min(100,Number(job.percent||0)));
    $("progress-phase").textContent=job.phase||"Working...";
    $("progress-sub").textContent=job.subphase||"";
    $("progress-percent").textContent=percent+"%";
    $("progress-bar").style.width=percent+"%";
    $("progress-count").textContent=job.total ? `Lead ${job.current_index||0} of ${job.total}` : "Preparing...";
    $("progress-elapsed").textContent=(job.elapsed_seconds||0)+"s";
    $("current-business").textContent=job.current_business||"Preparing...";
    $("current-action").textContent=job.message||"Working...";
    $("progress-high").textContent=job.high||0;
    $("progress-medium").textContent=job.medium||0;
    $("progress-low").textContent=job.low||0;
    const log=job.log||[];
    $("activity-log").innerHTML=log.map(item=>{
        const cls=item.type==="error"?"error":item.type==="work"?"work":"ok";
        return `<div class="activity-line ${cls}">${escapeHtml(item.text)}</div>`;
    }).join("");
    const box=$("activity-log"); box.scrollTop=box.scrollHeight;
}
form.addEventListener("submit",async event=>{
    event.preventDefault();
    const niche=$("niche").value.trim(), area=$("area").value.trim(), maxResults=Number($("max-results").value);
    if(!niche||!area)return;
    button.disabled=true;
    resetProgress();
    progressPanel.style.display="block";
    try{
        const response=await fetch("/generate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({niche,area,max_results:maxResults})});
        const data=await response.json();
        if(!response.ok)throw new Error(data.error||"Generation failed.");
        activeJob=data.job_id;
        watchJob(activeJob);
    }catch(error){
        button.disabled=false;
        $("progress-error").style.display="block";
        $("progress-error").textContent=error.message;
    }
});
function watchJob(jobId){
    if(statusTimer)clearInterval(statusTimer);
    const poll=async()=>{
        try{
            const response=await fetch("/job-status?job_id="+encodeURIComponent(jobId));
            const job=await response.json();
            renderProgress(job);
            if(job.status==="complete"){
                clearInterval(statusTimer);
                button.disabled=false;
                $("progress-bar").style.width="100%";
                $("progress-percent").textContent="100%";
                $("progress-complete").style.display="block";
                await loadLeads();
            }else if(job.status==="error"){
                clearInterval(statusTimer);
                button.disabled=false;
                $("progress-error").style.display="block";
                $("progress-error").textContent=job.message||"Generation failed.";
            }
        }catch(error){
            clearInterval(statusTimer);
            button.disabled=false;
            $("progress-error").style.display="block";
            $("progress-error").textContent="Could not read job status.";
        }
    };
    poll();
    statusTimer=setInterval(poll,700);
}
async function loadLeads(){
    try{
        const response=await fetch("/leads");
        const data=await response.json();
        allLeads=data.leads||[];
        $("high-count").textContent=data.high||0;
        $("medium-count").textContent=data.medium||0;
        $("total-count").textContent=data.total||0;
        renderLeads();
    }catch(error){$("leads").innerHTML='<div class="empty">Unable to load leads.</div>';}
}
function renderLeads(){
    const search=$("search").value.trim().toLowerCase(), priority=$("priority-filter").value;
    const filtered=allLeads.filter(lead=>{
        const haystack=[lead.name,lead.address,lead.reason].join(" ").toLowerCase();
        return (!search||haystack.includes(search))&&(priority==="ALL"||lead.priority===priority);
    });
    $("leads").innerHTML=filtered.length?filtered.map((lead)=>renderLead(lead)).join(""):'<div class="empty">No matching leads.</div>';
}
function renderLead(lead){
    const priority=String(lead.priority||"").toUpperCase();
    const cls=priority==="HIGH"?"high":priority==="MEDIUM"?"medium":"low";
    const index=allLeads.indexOf(lead);
    const website=lead.website?`<a href="${escapeHtml(lead.website)}" target="_blank" rel="noopener">WEBSITE</a>`:"";
    return `<article class="lead"><div class="lead-top"><div><div class="lead-name">${escapeHtml(lead.name)}</div><div class="lead-address">${escapeHtml(lead.address)}</div><div class="lead-reason">${escapeHtml(lead.reason)}</div></div><div class="badge ${cls}">${escapeHtml(priority)} · ${escapeHtml(String(lead.score))}</div></div><div class="actions">${website}<button type="button" data-lead-index="${index}">SELECT LEAD</button></div></article>`;
}
$("leads").addEventListener("click",event=>{
    const btn=event.target.closest("[data-lead-index]");
    if(!btn)return;
    selectLead(allLeads[Number(btn.dataset.leadIndex)]);
});
function selectLead(lead){
    if(!lead)return;
    selectedLead=lead;
    $("demo-panel").style.display="block";
    $("demo-name").textContent=lead.name||"Selected Lead";
    $("demo-meta").innerHTML=escapeHtml(lead.address||"")+"<br>"+escapeHtml(lead.phone||"")+"<br>"+escapeHtml(lead.website||"No website");
    $("demo-status").textContent=lead.demo_ready?"Landing page already exists.":"Ready to generate with DeepSeek.";
    $("preview-frame").src=lead.demo_url||"about:blank";
    $("generate-demo").disabled=false;
    $("regenerate-demo").disabled=!lead.demo_ready;
    $("open-preview").disabled=!lead.demo_url;
    $("download-demo").disabled=!lead.download_url;
    $("demo-panel").scrollIntoView({behavior:"smooth",block:"start"});
}
async function generateDemo(){
    if(!selectedLead)return;
    const status=$("demo-status");
    $("generate-demo").disabled=true;$("regenerate-demo").disabled=true;
    status.textContent="Starting landing-page pipeline...";
    try{
        const response=await fetch("/generate-landing-page",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({priority:selectedLead.priority,name:selectedLead.name})});
        const data=await response.json();
        if(!response.ok)throw new Error(data.error||"Landing page generation failed.");
        watchLandingPage(data.job_id);
    }catch(error){$("generate-demo").disabled=false;status.textContent=error.message;}
}
function watchLandingPage(jobId){
    if(demoTimer)clearInterval(demoTimer);
    demoTimer=setInterval(async()=>{
        try{
            const response=await fetch("/landing-page-status?job_id="+encodeURIComponent(jobId));
            const job=await response.json();
            $("demo-status").textContent=job.message||"Generating...";
            if(job.status==="complete"){
                clearInterval(demoTimer);
                selectedLead.demo_ready=true;selectedLead.demo_url=job.preview_url;selectedLead.download_url=job.download_url;
                $("generate-demo").disabled=false;$("regenerate-demo").disabled=false;$("open-preview").disabled=false;$("download-demo").disabled=false;
                $("preview-frame").src=job.preview_url+"?t="+Date.now();
                $("demo-status").textContent="Landing page ready.";
                await loadLeads();
            }else if(job.status==="error"){
                clearInterval(demoTimer);$("generate-demo").disabled=false;$("demo-status").textContent=job.message||"Landing page generation failed.";
            }
        }catch(error){clearInterval(demoTimer);$("generate-demo").disabled=false;$("demo-status").textContent="Could not read landing-page status.";}
    },700);
}
$("generate-demo").addEventListener("click",generateDemo);
$("regenerate-demo").addEventListener("click",generateDemo);
$("open-preview").addEventListener("click",()=>{if(selectedLead?.demo_url)window.open(selectedLead.demo_url,"_blank","noopener");});
$("download-demo").addEventListener("click",()=>{if(selectedLead?.download_url)window.location.href=selectedLead.download_url;});
$("search").addEventListener("input",renderLeads);
$("priority-filter").addEventListener("change",renderLeads);
$("refresh").addEventListener("click",loadLeads);
$("export").addEventListener("click",()=>{window.location.href="/export";});
loadLeads();
</script>
</body>
</html>
"""


def discover_leads():
    leads = []
    for priority in ("HIGH", "MEDIUM", "LOW"):
        folder = HANDOFFS / priority
        if not folder.exists():
            continue
        for client_folder in folder.iterdir():
            if not client_folder.is_dir():
                continue
            business_file = client_folder / "business.json"
            if not business_file.exists():
                continue
            try:
                business = json.loads(business_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            website_dir = client_folder / "website"
            relative = client_folder.relative_to(ROOT).as_posix()
            ready = (website_dir / "index.html").exists()
            leads.append({
                "name": business.get("business_name", client_folder.name),
                "address": business.get("address", ""),
                "phone": business.get("phone", ""),
                "website": business.get("website", ""),
                "priority": business.get("opportunity", priority),
                "score": business.get("opportunity_score", 0),
                "reason": business.get("opportunity_reasons", ""),
                "folder": str(client_folder.relative_to(ROOT)),
                "demo_ready": ready,
                "demo_url": "/demo/" + relative if ready else "",
                "download_url": "/download-demo/" + relative if ready else "",
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
    return render_template_string(HTML)


@app.post("/generate")
def generate():
    data = request.get_json(silent=True) or {}
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
        jobs[job_id] = {"status": "queued", "message": "Queued...", "log": [], "percent": 0, "high": 0, "medium": 0, "low": 0}
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
        "total": len(items),
        "leads": items,
    })


def resolve_client(priority, name):
    priority = str(priority or "").upper()
    if priority not in ("HIGH", "MEDIUM"):
        return None
    folder = HANDOFFS / priority / str(name)
    if folder.is_dir() and (folder / "AI_HANDOFF.json").exists():
        return folder
    return None


def run_landing_page(job_id, client_folder):
    try:
        update_job(job_id, status="running", message="DeepSeek is generating the landing page...")
        run_pipeline(client_folder)
        website = client_folder / "website" / "index.html"
        if not website.exists():
            raise RuntimeError("Pipeline finished without creating website/index.html.")
        relative = client_folder.relative_to(ROOT).as_posix()
        update_job(job_id, status="complete", message="Landing page ready.", preview_url="/demo/" + relative, download_url="/download-demo/" + relative)
    except Exception as error:
        update_job(job_id, status="error", message=str(error))


@app.post("/generate-landing-page")
def generate_landing_page():
    data = request.get_json(silent=True) or {}
    client_folder = resolve_client(data.get("priority"), data.get("name"))
    if not client_folder:
        return jsonify({"error": "Lead handoff not found. Generate the lead handoff first."}), 404
    job_id = uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"status": "queued", "message": "Queued landing-page generation..."}
    Thread(target=run_landing_page, args=(job_id, client_folder), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.get("/landing-page-status")
def landing_page_status():
    job_id = request.args.get("job_id")
    with jobs_lock:
        job = dict(jobs.get(job_id, {}))
    if not job:
        return jsonify({"status": "error", "message": "Job not found."}), 404
    return jsonify(job)


@app.get("/demo/<path:client_path>/<path:asset>")
def demo_asset(client_path, asset):
    """Serve CSS/JS/images before the generic demo route can catch them."""
    folder = ROOT / client_path
    website = folder / "website"

    if not website.is_dir():
        return "Landing page not found.", 404

    file_path = (website / asset).resolve()
    website_root = website.resolve()

    if not file_path.is_file() or website_root not in file_path.parents:
        return "Asset not found.", 404

    return send_from_directory(website, asset)


@app.get("/demo/<path:client_path>")
def demo(client_path):
    folder = ROOT / client_path
    website = folder / "website"

    if not (website / "index.html").exists():
        return "Landing page not found.", 404

    return send_from_directory(website, "index.html")


@app.get("/download-demo/<path:client_path>")
def download_demo(client_path):
    """Download the complete landing page package, not just index.html."""
    import tempfile
    import zipfile

    folder = ROOT / client_path
    website = folder / "website"

    if not (website / "index.html").exists():
        return "Landing page not found.", 404

    required = ["index.html", "styles.css", "script.js"]
    missing = [name for name in required if not (website / name).is_file()]

    if missing:
        return (
            "Landing page package is incomplete. Missing: "
            + ", ".join(missing)
        ), 500

    package_dir = ROOT / "outputs" / "landing_pages"
    package_dir.mkdir(parents=True, exist_ok=True)

    zip_path = package_dir / f"{folder.name}-landing-page.zip"

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for file in website.rglob("*"):
            if file.is_file():
                archive.write(file, file.relative_to(website))

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f"{folder.name}-landing-page.zip",
        mimetype="application/zip",
    )


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
    print("Frontend version: V3")
    app.run(host="127.0.0.1", port=3000, debug=False)
