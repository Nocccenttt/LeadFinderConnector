import csv
import json
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from flask import Flask, jsonify, render_template_string, request, send_file, send_from_directory

from pipeline_runner import run_pipeline

from seo_lead_finder_prospecting_batch import run as run_lead_finder


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

* {
    box-sizing: border-box;
}

:root {
    --bg: #080d18;
    --panel: #101827;
    --panel-2: #0c1422;
    --border: #243149;
    --text: #f4f7fb;
    --muted: #8e9ab0;
    --gold: #d7ad52;
    --gold-dark: #a98536;
    --high: #efb27b;
    --medium: #9db8d8;
    --green: #75c99b;
}

body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family:
        Inter,
        Arial,
        Helvetica,
        sans-serif;
}

button,
input,
select {
    font: inherit;
}

button {
    cursor: pointer;
}

.app {
    width: min(1400px, 94%);
    margin: auto;
    padding: 28px 0 50px;
}

.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 20px;
    margin-bottom: 28px;
}

.brand {
    font-size: 27px;
    font-weight: 900;
    letter-spacing: 2px;
}

.subtitle {
    color: var(--muted);
    margin-top: 5px;
}

.live {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--green);
    font-size: 13px;
    font-weight: 700;
}

.live-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--green);
}

.panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 22px;
    margin-bottom: 18px;
}

.panel-title {
    font-size: 17px;
    font-weight: 800;
    margin-bottom: 18px;
}

.form {
    display: grid;
    grid-template-columns: minmax(220px, 1fr)
                         minmax(220px, 1fr)
                         150px
                         190px;
    gap: 12px;
}

input,
select {
    width: 100%;
    min-height: 48px;
    padding: 0 14px;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 10px;
    outline: none;
}

input:focus,
select:focus {
    border-color: var(--gold);
}

.primary {
    min-height: 48px;
    border: 0;
    border-radius: 10px;
    background: var(--gold);
    color: #111;
    font-weight: 900;
}

.primary:hover {
    background: #e4bd68;
}

.primary:disabled {
    opacity: .5;
    cursor: wait;
}

.status {
    margin-top: 15px;
    color: var(--muted);
    min-height: 20px;
}

.progress-wrap {
    display: none;
    margin-top: 15px;
}

.progress {
    height: 6px;
    background: #1c2739;
    border-radius: 10px;
    overflow: hidden;
}

.progress-bar {
    width: 20%;
    height: 100%;
    background: var(--gold);
    transition: width .3s ease;
}

.stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
}

.stat {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
}

.stat-number {
    font-size: 31px;
    font-weight: 900;
}

.stat-label {
    color: var(--muted);
    margin-top: 4px;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: .7px;
}

.toolbar {
    display: grid;
    grid-template-columns: 1fr 150px auto;
    gap: 10px;
    margin-bottom: 16px;
}

.secondary {
    min-height: 44px;
    padding: 0 16px;
    border-radius: 9px;
    border: 1px solid var(--border);
    background: var(--panel-2);
    color: var(--text);
    font-weight: 700;
}

.secondary:hover {
    border-color: #3b4a67;
}

.leads {
    display: grid;
    gap: 12px;
}

.lead {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 13px;
    padding: 18px;
}

.lead-top {
    display: flex;
    justify-content: space-between;
    gap: 20px;
}

.lead-name {
    font-size: 18px;
    font-weight: 850;
}

.lead-address {
    color: var(--muted);
    margin-top: 5px;
    line-height: 1.45;
}

.lead-reason {
    color: #b7c1d1;
    margin-top: 8px;
    font-size: 14px;
}

.badge {
    min-width: 90px;
    height: fit-content;
    padding: 7px 11px;
    border-radius: 999px;
    text-align: center;
    font-size: 12px;
    font-weight: 900;
}

.badge.high {
    background: rgba(239, 178, 123, .12);
    color: var(--high);
}

.badge.medium {
    background: rgba(157, 184, 216, .12);
    color: var(--medium);
}

.actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 15px;
}

.actions a {
    text-decoration: none;
    color: var(--text);
    background: #172237;
    border: 1px solid #273650;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 800;
}

.actions a:hover {
    border-color: var(--gold);
}

.empty {
    color: var(--muted);
    padding: 30px 10px;
    text-align: center;
}

@media (max-width: 900px) {

    .form {
        grid-template-columns: 1fr 1fr;
    }

    .toolbar {
        grid-template-columns: 1fr 150px;
    }

    .toolbar button {
        grid-column: span 2;
    }

}

@media (max-width: 620px) {

    .app {
        width: 92%;
        padding-top: 20px;
    }

    .header {
        align-items: flex-start;
        flex-direction: column;
    }

    .form,
    .stats,
    .toolbar {
        grid-template-columns: 1fr;
    }

    .toolbar button {
        grid-column: auto;
    }

    .lead-top {
        flex-direction: column;
    }

}


.demo-grid{display:grid;grid-template-columns:300px 1fr;gap:16px}
.demo-info{background:var(--panel-2);border:1px solid var(--border);border-radius:12px;padding:17px}
.demo-name{font-size:20px;font-weight:900}
.demo-meta{color:var(--muted);font-size:13px;line-height:1.6;margin-top:8px}
.preview{height:620px;background:#fff;border:1px solid var(--border);border-radius:12px;overflow:hidden}
.preview iframe{width:100%;height:100%;border:0;background:#fff}
@media(max-width:900px){.demo-grid{grid-template-columns:1fr}.preview{height:520px}}

</style>

</head>


<body>

<div class="app">

    <header class="header">

        <div>
            <div class="brand">LEADFINDER</div>

            <div class="subtitle">
                Lead Generation & Sales Control Center
            </div>
        </div>

        <div class="live">
            <span class="live-dot"></span>
            LIVE
        </div>

    </header>


    <section class="panel">

        <div class="panel-title">
            Generate Leads
        </div>

        <form id="generate-form">

            <div class="form">

                <input
                    id="niche"
                    type="text"
                    placeholder="Business Type"
                    value="Tree Service"
                    required
                >

                <input
                    id="area"
                    type="text"
                    placeholder="Location"
                    value="Raleigh, NC"
                    required
                >

                <select id="max-results">

                    <option value="10">
                        10 Leads
                    </option>

                    <option value="25" selected>
                        25 Leads
                    </option>

                    <option value="50">
                        50 Leads
                    </option>

                    <option value="100">
                        100 Leads
                    </option>

                </select>

                <button
                    id="generate-button"
                    class="primary"
                    type="submit"
                >
                    GENERATE LEADS
                </button>

            </div>

        </form>

        <div id="status" class="status">
            Ready.
        </div>

        <div id="progress-wrap" class="progress-wrap">

            <div class="progress">
                <div
                    id="progress-bar"
                    class="progress-bar"
                ></div>
            </div>

        </div>

    </section>


    <section class="panel">

        <div class="stats">

            <div class="stat">

                <div
                    id="high-count"
                    class="stat-number"
                >
                    0
                </div>

                <div class="stat-label">
                    High
                </div>

            </div>


            <div class="stat">

                <div
                    id="medium-count"
                    class="stat-number"
                >
                    0
                </div>

                <div class="stat-label">
                    Medium
                </div>

            </div>


            <div class="stat">

                <div
                    id="total-count"
                    class="stat-number"
                >
                    0
                </div>

                <div class="stat-label">
                    Total
                </div>

            </div>

        </div>

    </section>


    <section class="panel">

        <div class="panel-title">
            Leads
        </div>

        <div class="toolbar">

            <input
                id="search"
                type="search"
                placeholder="Search leads..."
            >

            <select id="priority-filter">

                <option value="ALL">
                    All
                </option>

                <option value="HIGH">
                    High
                </option>

                <option value="MEDIUM">
                    Medium
                </option>

            </select>

            <button
                id="refresh"
                class="secondary"
                type="button"
            >
                REFRESH
            </button>

            <button
                id="export"
                class="secondary"
                type="button"
            >
                EXPORT CSV
            </button>

        </div>

        <div
            id="leads"
            class="leads"
        >
            <div class="empty">
                No leads generated yet.
            </div>
        </div>

    </section>

    <section id="demo-panel" class="panel demo-panel" style="display:none">

        <div class="panel-title">Landing Page Demo</div>

        <div class="demo-grid">

            <div class="demo-info">
                <div id="demo-name" class="demo-name">Select a lead</div>
                <div id="demo-meta" class="demo-meta"></div>
                <div id="demo-status" class="status">Ready.</div>

                <div class="actions">
                    <button id="generate-demo" class="primary" type="button">
                        GENERATE LANDING PAGE
                    </button>

                    <button id="regenerate-demo" class="secondary" type="button">
                        REGENERATE
                    </button>

                    <button id="open-preview" class="secondary" type="button">
                        OPEN PREVIEW
                    </button>

                    <button id="download-demo" class="secondary" type="button">
                        DOWNLOAD LANDING PAGE
                    </button>
                </div>
            </div>

            <div class="preview">
                <iframe
                    id="preview-frame"
                    title="Landing page preview"
                ></iframe>
            </div>

        </div>

    </section>

</div>


<script>

let allLeads = [];
let activeJob = null;
let statusTimer = null;


const form =
    document.getElementById("generate-form");

const button =
    document.getElementById("generate-button");

const statusBox =
    document.getElementById("status");

const progressWrap =
    document.getElementById("progress-wrap");

const progressBar =
    document.getElementById("progress-bar");

const leadsBox =
    document.getElementById("leads");

const searchBox =
    document.getElementById("search");

const priorityFilter =
    document.getElementById("priority-filter");


form.addEventListener("submit", async (event) => {

    event.preventDefault();

    const niche =
        document.getElementById("niche").value.trim();

    const area =
        document.getElementById("area").value.trim();

    const maxResults =
        Number(
            document.getElementById("max-results").value
        );

    if (!niche || !area) {

        statusBox.textContent =
            "Business type and location are required.";

        return;
    }

    button.disabled = true;

    progressWrap.style.display = "block";

    progressBar.style.width = "10%";

    statusBox.textContent =
        "Starting LeadFinder...";

    try {

        const response = await fetch(
            "/generate",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    niche: niche,
                    area: area,
                    max_results: maxResults
                })
            }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Generation failed."
            );
        }

        activeJob = data.job_id;

        watchJob(activeJob);

    } catch (error) {

        button.disabled = false;

        progressWrap.style.display = "none";

        statusBox.textContent =
            error.message;

    }

});


function watchJob(jobId) {

    if (statusTimer) {
        clearInterval(statusTimer);
    }

    statusTimer = setInterval(
        async () => {

            try {

                const response = await fetch(
                    "/job-status?job_id=" +
                    encodeURIComponent(jobId)
                );

                const job =
                    await response.json();

                statusBox.textContent =
                    job.message || "Working...";

                if (job.status === "running") {

                    progressBar.style.width = "60%";

                }

                if (job.status === "complete") {

                    clearInterval(statusTimer);

                    progressBar.style.width = "100%";

                    button.disabled = false;

                    await 
let selectedLead = null;
let demoTimer = null;

function selectLead(lead) {
    selectedLead = lead;

    const panel = document.getElementById("demo-panel");
    panel.style.display = "block";

    document.getElementById("demo-name").textContent =
        lead.name || "Selected Lead";

    document.getElementById("demo-meta").innerHTML =
        escapeHtml(lead.address || "") + "<br>" +
        escapeHtml(lead.phone || "") + "<br>" +
        escapeHtml(lead.website || "No website");

    document.getElementById("demo-status").textContent =
        lead.demo_ready
            ? "Landing page already exists."
            : "Ready to generate with DeepSeek.";

    document.getElementById("preview-frame").src =
        lead.demo_url || "about:blank";

    document.getElementById("generate-demo").disabled = false;
    document.getElementById("regenerate-demo").disabled = !lead.demo_ready;

    panel.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}

async function generateDemo() {
    if (!selectedLead) return;

    const generateButton =
        document.getElementById("generate-demo");

    const regenerateButton =
        document.getElementById("regenerate-demo");

    const status =
        document.getElementById("demo-status");

    generateButton.disabled = true;
    regenerateButton.disabled = true;
    status.textContent =
        "DeepSeek is generating the landing page...";

    try {
        const response = await fetch(
            "/generate-landing-page",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    priority: selectedLead.priority,
                    name: selectedLead.name
                })
            }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Landing page generation failed."
            );
        }

        watchLandingPage(data.job_id);

    } catch (error) {
        generateButton.disabled = false;
        status.textContent = error.message;
    }
}

function watchLandingPage(jobId) {
    if (demoTimer) {
        clearInterval(demoTimer);
    }

    demoTimer = setInterval(async () => {
        try {
            const response = await fetch(
                "/landing-page-status?job_id=" +
                encodeURIComponent(jobId)
            );

            const job = await response.json();

            document.getElementById("demo-status").textContent =
                job.message || "Generating...";

            if (job.status === "complete") {
                clearInterval(demoTimer);

                selectedLead.demo_ready = true;
                selectedLead.demo_url = job.preview_url;
                selectedLead.download_url = job.download_url;

                document.getElementById("generate-demo").disabled = false;
                document.getElementById("regenerate-demo").disabled = false;

                document.getElementById("preview-frame").src =
                    job.preview_url + "?t=" + Date.now();

                document.getElementById("demo-status").textContent =
                    "Landing page ready.";

                await loadLeads();
            }

            if (job.status === "error") {
                clearInterval(demoTimer);

                document.getElementById("generate-demo").disabled = false;

                document.getElementById("demo-status").textContent =
                    job.message || "Landing page generation failed.";
            }

        } catch (error) {
            clearInterval(demoTimer);

            document.getElementById("generate-demo").disabled = false;

            document.getElementById("demo-status").textContent =
                "Could not read landing-page status.";
        }

    }, 1000);
}

document.getElementById("generate-demo")
    .addEventListener("click", generateDemo);

document.getElementById("regenerate-demo")
    .addEventListener("click", generateDemo);

document.getElementById("open-preview")
    .addEventListener("click", () => {
        if (selectedLead && selectedLead.demo_url) {
            window.open(
                selectedLead.demo_url,
                "_blank",
                "noopener"
            );
        }
    });

document.getElementById("download-demo")
    .addEventListener("click", () => {
        if (selectedLead && selectedLead.download_url) {
            window.location.href =
                selectedLead.download_url;
        }
    });


loadLeads();

                    statusBox.textContent =
                        "Lead generation complete.";

                    setTimeout(() => {
                        progressWrap.style.display = "none";
                    }, 700);

                }

                if (job.status === "error") {

                    clearInterval(statusTimer);

                    button.disabled = false;

                    progressBar.style.width = "0%";

                    statusBox.textContent =
                        job.message || "Generation failed.";

                }

            } catch (error) {

                clearInterval(statusTimer);

                button.disabled = false;

                statusBox.textContent =
                    "Could not read job status.";

            }

        },
        1000
    );
}


async function loadLeads() {

    try {

        const response =
            await fetch("/leads");

        const data =
            await response.json();

        allLeads = data.leads || [];

        document.getElementById("high-count")
            .textContent = data.high;

        document.getElementById("medium-count")
            .textContent = data.medium;

        document.getElementById("total-count")
            .textContent = data.total;

        renderLeads();

    } catch (error) {

        leadsBox.innerHTML =
            '<div class="empty">Unable to load leads.</div>';

    }

}


function renderLeads() {

    const search =
        searchBox.value.trim().toLowerCase();

    const priority =
        priorityFilter.value;

    const filtered =
        allLeads.filter((lead) => {

            const matchesSearch =
                !search ||
                String(lead.name || "")
                    .toLowerCase()
                    .includes(search) ||
                String(lead.address || "")
                    .toLowerCase()
                    .includes(search) ||
                String(lead.reason || "")
                    .toLowerCase()
                    .includes(search);

            const matchesPriority =
                priority === "ALL" ||
                lead.priority === priority;

            return matchesSearch && matchesPriority;
        });

    if (!filtered.length) {

        leadsBox.innerHTML =
            '<div class="empty">No matching leads.</div>';

        return;
    }

    leadsBox.innerHTML =
        filtered.map(renderLead).join("");

}


function renderLead(lead) {

    const priority =
        String(lead.priority || "")
            .toUpperCase();

    const badgeClass =
        priority === "HIGH"
            ? "high"
            : "medium";

    const website =
        lead.website
            ? `
                <a
                    href="${escapeAttribute(lead.website)}"
                    target="_blank"
                    rel="noopener"
                >
                    WEBSITE
                </a>
              `
            : "";

    return `
        <article class="lead">

            <div class="lead-top">

                <div>

                    <div class="lead-name">
                        ${escapeHtml(lead.name)}
                    </div>

                    <div class="lead-address">
                        ${escapeHtml(lead.address)}
                    </div>

                    <div class="lead-reason">
                        ${escapeHtml(lead.reason)}
                    </div>

                </div>

                <div class="badge ${badgeClass}">
                    ${escapeHtml(priority)}
                    ·
                    ${escapeHtml(String(lead.score))}
                </div>

            </div>

            <div class="actions">
                ${website}
                <button
                    type="button"
                    onclick='selectLead(${JSON.stringify(lead)})'
                >
                    SELECT LEAD
                </button>
            </div>

        </article>
    `;
}


function escapeHtml(value) {

    return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

}


function escapeAttribute(value) {

    return escapeHtml(value);

}


searchBox.addEventListener(
    "input",
    renderLeads
);


priorityFilter.addEventListener(
    "change",
    renderLeads
);


document.getElementById("refresh")
    .addEventListener(
        "click",
        loadLeads
    );


document.getElementById("export")
    .addEventListener(
        "click",
        () => {

            window.location.href =
                "/export";

        }
    );


loadLeads();

</script>

</body>
</html>
"""


def discover_leads():
    leads = []

    for priority in ("HIGH", "MEDIUM"):

        folder = HANDOFFS / priority

        if not folder.exists():
            continue

        for client_folder in folder.iterdir():

            if not client_folder.is_dir():
                continue

            business_file = (
                client_folder / "business.json"
            )

            if not business_file.exists():
                continue

            try:

                business = json.loads(
                    business_file.read_text(
                        encoding="utf-8"
                    )
                )

            except Exception:

                continue

            website_dir = client_folder / "website"

            leads.append({
                "name": business.get(
                    "business_name",
                    client_folder.name
                ),
                "address": business.get(
                    "address",
                    ""
                ),
                "phone": business.get(
                    "phone",
                    ""
                ),
                "website": business.get(
                    "website",
                    ""
                ),
                "priority": business.get(
                    "opportunity",
                    priority
                ),
                "score": business.get(
                    "opportunity_score",
                    0
                ),
                "reason": business.get(
                    "opportunity_reasons",
                    ""
                ),
                "folder": str(client_folder.relative_to(ROOT)),
                "demo_ready": (website_dir / "index.html").exists(),
                "demo_url": (
                    "/demo/" + client_folder.relative_to(ROOT).as_posix()
                    if (website_dir / "index.html").exists()
                    else ""
                ),
                "download_url": (
                    "/download-demo/" + client_folder.relative_to(ROOT).as_posix()
                    if (website_dir / "index.html").exists()
                    else ""
                )
            })

    leads.sort(
        key=lambda lead: (
            0 if lead["priority"] == "HIGH" else 1,
            -int(lead["score"] or 0)
        )
    )

    return leads


def run_generation(
    job_id,
    niche,
    area,
    max_results
):

    try:

        with jobs_lock:
            jobs[job_id] = {
                "status": "running",
                "message":
                    "Searching Google Maps..."
            }

        run_lead_finder(
            niche=niche,
            area=area,
            output="leads.csv",
            max_results=max_results
        )

        with jobs_lock:
            jobs[job_id] = {
                "status": "complete",
                "message":
                    "Lead generation complete."
            }

    except Exception as error:

        with jobs_lock:
            jobs[job_id] = {
                "status": "error",
                "message": str(error)
            }


@app.get("/")
def home():

    return render_template_string(HTML)


@app.post("/generate")
def generate():

    data = request.get_json(
        silent=True
    ) or {}

    niche = str(
        data.get("niche", "")
    ).strip()

    area = str(
        data.get("area", "")
    ).strip()

    if not niche or not area:

        return jsonify({
            "error":
                "Business type and location are required."
        }), 400

    try:

        max_results = int(
            data.get("max_results", 25)
        )

    except (TypeError, ValueError):

        max_results = 25

    max_results = max(
        1,
        min(max_results, 100)
    )

    job_id = uuid4().hex

    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "message": "Queued..."
        }

    Thread(
        target=run_generation,
        args=(
            job_id,
            niche,
            area,
            max_results
        ),
        daemon=True
    ).start()

    return jsonify({
        "job_id": job_id
    })


@app.get("/job-status")
def job_status():

    job_id = request.args.get("job_id")

    with jobs_lock:

        job = jobs.get(job_id)

    if not job:

        return jsonify({
            "status": "error",
            "message": "Job not found."
        }), 404

    return jsonify(job)


@app.get("/leads")
def leads():

    items = discover_leads()

    high = sum(
        1 for lead in items
        if lead["priority"] == "HIGH"
    )

    medium = sum(
        1 for lead in items
        if lead["priority"] == "MEDIUM"
    )

    return jsonify({
        "high": high,
        "medium": medium,
        "total": len(items),
        "leads": items
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
        with jobs_lock:
            jobs[job_id] = {
                "status": "running",
                "message": "DeepSeek is generating the landing page..."
            }

        run_pipeline(client_folder)

        website = client_folder / "website" / "index.html"
        if not website.exists():
            raise RuntimeError(
                "Pipeline finished without creating website/index.html."
            )

        relative = client_folder.relative_to(ROOT).as_posix()

        with jobs_lock:
            jobs[job_id] = {
                "status": "complete",
                "message": "Landing page ready.",
                "preview_url": "/demo/" + relative,
                "download_url": "/download-demo/" + relative
            }

    except Exception as error:
        with jobs_lock:
            jobs[job_id] = {
                "status": "error",
                "message": str(error)
            }


@app.post("/generate-landing-page")
def generate_landing_page():
    data = request.get_json(silent=True) or {}

    client_folder = resolve_client(
        data.get("priority"),
        data.get("name")
    )

    if not client_folder:
        return jsonify({
            "error": "Lead handoff not found. Generate the lead handoff first."
        }), 404

    job_id = uuid4().hex

    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "message": "Queued landing-page generation..."
        }

    Thread(
        target=run_landing_page,
        args=(job_id, client_folder),
        daemon=True
    ).start()

    return jsonify({"job_id": job_id})


@app.get("/landing-page-status")
def landing_page_status():
    job_id = request.args.get("job_id")

    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({
            "status": "error",
            "message": "Job not found."
        }), 404

    return jsonify(job)


@app.get("/demo/<path:client_path>")
def demo(client_path):
    folder = ROOT / client_path
    website = folder / "website"

    if not (website / "index.html").exists():
        return "Landing page not found.", 404

    return send_from_directory(website, "index.html")


@app.get("/download-demo/<path:client_path>")
def download_demo(client_path):
    folder = ROOT / client_path
    website = folder / "website" / "index.html"

    if not website.exists():
        return "Landing page not found.", 404

    return send_file(
        website,
        as_attachment=True,
        download_name=f"{folder.name}-landing-page.html"
    )


@app.get("/export")
def export():

    leads = discover_leads()

    export_file = ROOT / "outputs" / "leadfinder_export.csv"

    export_file.parent.mkdir(
        exist_ok=True
    )

    fields = [
        "name",
        "address",
        "phone",
        "website",
        "priority",
        "score",
        "reason"
    ]

    with export_file.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields
        )

        writer.writeheader()
        writer.writerows(leads)

    return send_file(
        export_file,
        as_attachment=True,
        download_name="leadfinder_leads.csv"
    )


if __name__ == "__main__":

    print()
    print("==============================")
    print("       LEADFINDER")
    print("==============================")
    print()
    print("Open: http://localhost:3000")
    print()

    app.run(
        host="127.0.0.1",
        port=3000,
        debug=False
    )