[1mdiff --git a/preview_dashboard.py b/preview_dashboard.py[m
[1mindex a6557d0..2a485c6 100644[m
[1m--- a/preview_dashboard.py[m
[1m+++ b/preview_dashboard.py[m
[36m@@ -1,205 +1,480 @@[m
[31m-from flask import Flask, render_template_string, send_from_directory[m
[31m-from pathlib import Path[m
 import json[m
[32m+[m[32mfrom pathlib import Path[m
[32m+[m
[32m+[m[32mfrom flask import Flask, abort, render_template_string, send_file[m
 [m
 [m
 app = Flask(__name__)[m
 [m
[32m+[m[32mBASE_DIR = Path(__file__).resolve().parent[m
[32m+[m[32mHANDOFFS_DIR = BASE_DIR / "codex_handoffs"[m
 [m
[31m-ROOT = Path("codex_handoffs")[m
[32m+[m[32mALLOWED_ASSETS = {[m
[32m+[m[32m    "offer": "DEMO_PACKAGE/Sales/OFFER.json",[m
[32m+[m[32m    "sales_notes": "DEMO_PACKAGE/Sales/SALES_NOTES.json",[m
[32m+[m[32m    "delivery": "DELIVERY.json",[m
[32m+[m[32m    "quality": "quality_report.json",[m
[32m+[m[32m}[m
 [m
 [m
 HTML = """[m
 <!DOCTYPE html>[m
[31m-<html>[m
[31m-[m
[32m+[m[32m<html lang="en">[m
 <head>[m
[31m-[m
[31m-<title>LeadFinder Preview Dashboard</title>[m
[31m-[m
[31m-<style>[m
[31m-[m
[31m-body {[m
[31m-    font-family: Arial, sans-serif;[m
[31m-    padding: 40px;[m
[31m-    background: #f5f5f5;[m
[31m-}[m
[31m-[m
[31m-[m
[31m-.card {[m
[31m-[m
[31m-    background:white;[m
[31m-    padding:20px;[m
[31m-    margin-bottom:20px;[m
[31m-    border-radius:10px;[m
[31m-[m
[31m-}[m
[31m-[m
[31m-[m
[31m-a {[m
[31m-[m
[31m-    display:inline-block;[m
[31m-    margin-top:10px;[m
[31m-    padding:10px 20px;[m
[31m-    background:#111;[m
[31m-    color:white;[m
[31m-    text-decoration:none;[m
[31m-    border-radius:5px;[m
[31m-[m
[31m-}[m
[31m-[m
[31m-[m
[31m-.pass {[m
[31m-[m
[31m-    color:green;[m
[31m-[m
[31m-}[m
[31m-[m
[31m-[m
[31m-.pending {[m
[31m-[m
[31m-    color:orange;[m
[31m-[m
[31m-}[m
[31m-[m
[31m-</style>[m
[31m-[m
[32m+[m[32m    <meta charset="UTF-8">[m
[32m+[m[32m    <meta name="viewport" content="width=device-width, initial-scale=1.0">[m
[32m+[m[32m    <title>LeadFinder Sales Dashboard</title>[m
[32m+[m
[32m+[m[32m    <style>[m
[32m+[m[32m        * {[m
[32m+[m[32m            box-sizing: border-box;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        body {[m
[32m+[m[32m            margin: 0;[m
[32m+[m[32m            font-family: Arial, sans-serif;[m
[32m+[m[32m            background: #f5f7fa;[m
[32m+[m[32m            color: #17202a;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        header {[m
[32m+[m[32m            background: #111827;[m
[32m+[m[32m            color: white;[m
[32m+[m[32m            padding: 28px 40px;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        header h1 {[m
[32m+[m[32m            margin: 0 0 6px;[m
[32m+[m[32m            font-size: 28px;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        header p {[m
[32m+[m[32m            margin: 0;[m
[32m+[m[32m            color: #cbd5e1;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        main {[m
[32m+[m[32m            max-width: 1400px;[m
[32m+[m[32m            margin: 0 auto;[m
[32m+[m[32m            padding: 35px 25px;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .section-title {[m
[32m+[m[32m            margin: 35px 0 18px;[m
[32m+[m[32m            font-size: 22px;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .client-grid {[m
[32m+[m[32m            display: grid;[m
[32m+[m[32m            grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));[m
[32m+[m[32m            gap: 20px;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .client-card {[m
[32m+[m[32m            background: white;[m
[32m+[m[32m            border: 1px solid #e5e7eb;[m
[32m+[m[32m            border-radius: 12px;[m
[32m+[m[32m            padding: 22px;[m
[32m+[m[32m            box-shadow: 0 3px 10px rgba(0, 0, 0, 0.05);[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .client-name {[m
[32m+[m[32m            font-size: 21px;[m
[32m+[m[32m            font-weight: 700;[m
[32m+[m[32m            margin-bottom: 18px;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .meta {[m
[32m+[m[32m            display: grid;[m
[32m+[m[32m            grid-template-columns: 1fr 1fr;[m
[32m+[m[32m            gap: 12px;[m
[32m+[m[32m            margin-bottom: 20px;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .meta-box {[m
[32m+[m[32m            background: #f8fafc;[m
[32m+[m[32m            border-radius: 8px;[m
[32m+[m[32m            padding: 12px;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .meta-label {[m
[32m+[m[32m            display: block;[m
[32m+[m[32m            font-size: 11px;[m
[32m+[m[32m            text-transform: uppercase;[m
[32m+[m[32m            color: #64748b;[m
[32m+[m[32m            margin-bottom: 5px;[m
[32m+[m[32m            font-weight: 700;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .meta-value {[m
[32m+[m[32m            font-size: 16px;[m
[32m+[m[32m            font-weight: 700;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .priority-high {[m
[32m+[m[32m            color: #b91c1c;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .priority-medium {[m
[32m+[m[32m            color: #b45309;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .priority-low {[m
[32m+[m[32m            color: #475569;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .status-pass {[m
[32m+[m[32m            color: #15803d;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .status-fail {[m
[32m+[m[32m            color: #b91c1c;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .buttons {[m
[32m+[m[32m            display: grid;[m
[32m+[m[32m            gap: 9px;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .button {[m
[32m+[m[32m            display: block;[m
[32m+[m[32m            text-align: center;[m
[32m+[m[32m            text-decoration: none;[m
[32m+[m[32m            padding: 11px 14px;[m
[32m+[m[32m            border-radius: 7px;[m
[32m+[m[32m            font-weight: 700;[m
[32m+[m[32m            font-size: 14px;[m
[32m+[m[32m            border: 1px solid #d1d5db;[m
[32m+[m[32m            color: #111827;[m
[32m+[m[32m            background: white;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .button:hover {[m
[32m+[m[32m            background: #f3f4f6;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .button-primary {[m
[32m+[m[32m            background: #111827;[m
[32m+[m[32m            color: white;[m
[32m+[m[32m            border-color: #111827;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .button-primary:hover {[m
[32m+[m[32m            background: #1f2937;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        .empty {[m
[32m+[m[32m            background: white;[m
[32m+[m[32m            padding: 30px;[m
[32m+[m[32m            border-radius: 10px;[m
[32m+[m[32m            border: 1px solid #e5e7eb;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        footer {[m
[32m+[m[32m            text-align: center;[m
[32m+[m[32m            padding: 30px;[m
[32m+[m[32m            color: #64748b;[m
[32m+[m[32m            font-size: 13px;[m
[32m+[m[32m        }[m
[32m+[m
[32m+[m[32m        @media (max-width: 600px) {[m
[32m+[m[32m            header {[m
[32m+[m[32m                padding: 22px;[m
[32m+[m[32m            }[m
[32m+[m
[32m+[m[32m            main {[m
[32m+[m[32m                padding: 25px 15px;[m
[32m+[m[32m            }[m
[32m+[m
[32m+[m[32m            .client-grid {[m
[32m+[m[32m                grid-template-columns: 1fr;[m
[32m+[m[32m            }[m
[32m+[m[32m        }[m
[32m+[m[32m    </style>[m
 </head>[m
 [m
[31m-[m
 <body>[m
 [m
[31m-[m
[31m-<h1>🚀 LeadFinder Website Dashboard</h1>[m
[31m-[m
[31m-[m
[31m-{% for client in clients %}[m
[31m-[m
[31m-<div class="card">[m
[31m-[m
[31m-<h2>{{client.name}}</h2>[m
[31m-[m
[31m-[m
[31m-<p>[m
[31m-Status:[m
[31m-<span class="{{client.status_class}}">[m
[31m-{{client.status}}[m
[31m-</span>[m
[31m-</p>[m
[31m-[m
[31m-[m
[31m-<a href="/website/{{client.path}}" target="_blank">[m
[31m-View Website[m
[31m-</a>[m
[31m-[m
[31m-[m
[31m-</div>[m
[31m-[m
[31m-[m
[31m-{% endfor %}[m
[31m-[m
[32m+[m[32m<header>[m
[32m+[m[32m    <h1>LeadFinder Sales Dashboard</h1>[m
[32m+[m[32m    <p>Landing page demos, sales assets, and delivery packages</p>[m
[32m+[m[32m</header>[m
[32m+[m
[32m+[m[32m<main>[m
[32m+[m
[32m+[m[32m    {% if high %}[m
[32m+[m[32m        <h2 class="section-title">HIGH Priority Leads</h2>[m
[32m+[m
[32m+[m[32m        <div class="client-grid">[m
[32m+[m[32m            {% for client in high %}[m
[32m+[m[32m                {{ client_card(client) | safe }}[m
[32m+[m[32m            {% endfor %}[m
[32m+[m[32m        </div>[m
[32m+[m[32m    {% endif %}[m
[32m+[m
[32m+[m[32m    {% if medium %}[m
[32m+[m[32m        <h2 class="section-title">MEDIUM Priority Leads</h2>[m
[32m+[m
[32m+[m[32m        <div class="client-grid">[m
[32m+[m[32m            {% for client in medium %}[m
[32m+[m[32m                {{ client_card(client) | safe }}[m
[32m+[m[32m            {% endfor %}[m
[32m+[m[32m        </div>[m
[32m+[m[32m    {% endif %}[m
[32m+[m
[32m+[m[32m    {% if not high and not medium %}[m
[32m+[m[32m        <div class="empty">[m
[32m+[m[32m            <h2>No sales-ready leads found.</h2>[m
[32m+[m[32m            <p>[m
[32m+[m[32m                LeadFinder has not generated any HIGH or MEDIUM landing-page[m
[32m+[m[32m                demos yet.[m
[32m+[m[32m            </p>[m
[32m+[m[32m        </div>[m
[32m+[m[32m    {% endif %}[m
[32m+[m
[32m+[m[32m</main>[m
[32m+[m
[32m+[m[32m<footer>[m
[32m+[m[32m    LeadFinder[m
[32m+[m[32m</footer>[m
 [m
 </body>[m
[31m-[m
 </html>[m
 """[m
 [m
 [m
[31m-def get_clients():[m
[32m+[m[32mdef load_json(path):[m
[32m+[m[32m    if not path.exists():[m
[32m+[m[32m        return {}[m
 [m
[31m-    clients = [][m
[32m+[m[32m    try:[m
[32m+[m[32m        return json.loads(path.read_text(encoding="utf-8"))[m
[32m+[m[32m    except (json.JSONDecodeError, OSError):[m
[32m+[m[32m        return {}[m
 [m
 [m
[31m-    for client in ROOT.rglob("website"):[m
[32m+[m[32mdef find_clients():[m
[32m+[m[32m    clients = [][m
 [m
[31m-        index = client / "index.html"[m
[32m+[m[32m    if not HANDOFFS_DIR.exists():[m
[32m+[m[32m        return clients[m
 [m
[32m+[m[32m    for priority in ("HIGH", "MEDIUM"):[m
[32m+[m[32m        priority_dir = HANDOFFS_DIR / priority[m
 [m
[31m-        if not index.exists():[m
[32m+[m[32m        if not priority_dir.exists():[m
             continue[m
 [m
[32m+[m[32m        for client_folder in priority_dir.iterdir():[m
[32m+[m[32m            if not client_folder.is_dir():[m
[32m+[m[32m                continue[m
 [m
[31m-        client_folder = client.parent[m
[31m-[m
[31m-[m
[31m-        status = "UNKNOWN"[m
[31m-[m
[31m-[m
[31m-        status_file = ([m
[31m-            client_folder /[m
[31m-            "STATUS.json"[m
[31m-        )[m
[32m+[m[32m            business_file = client_folder / "business.json"[m
[32m+[m[32m            status_file = client_folder / "STATUS.json"[m
[32m+[m[32m            quality_file = client_folder / "quality_report.json"[m
[32m+[m[32m            website_file = client_folder / "website" / "index.html"[m
 [m
[32m+[m[32m            if not website_file.exists():[m
[32m+[m[32m                continue[m
 [m
[31m-        if status_file.exists():[m
[32m+[m[32m            business = load_json(business_file)[m
[32m+[m[32m            status = load_json(status_file)[m
[32m+[m[32m            quality = load_json(quality_file)[m
 [m
[31m-            data = json.loads([m
[31m-                status_file.read_text()[m
[32m+[m[32m            business_name = ([m
[32m+[m[32m                business.get("business_name")[m
[32m+[m[32m                or business.get("name")[m
[32m+[m[32m                or business.get("company_name")[m
[32m+[m[32m                or client_folder.name[m
             )[m
 [m
[31m-            status = data.get([m
[31m-                "status",[m
[31m-                "UNKNOWN"[m
[32m+[m[32m            score = ([m
[32m+[m[32m                business.get("score")[m
[32m+[m[32m                or business.get("lead_score")[m
[32m+[m[32m                or business.get("total_score")[m
[32m+[m[32m                or 0[m
             )[m
 [m
[32m+[m[32m            status_value = ([m
[32m+[m[32m                status.get("status")[m
[32m+[m[32m                or quality.get("status")[m
[32m+[m[32m                or "UNKNOWN"[m
[32m+[m[32m            )[m
 [m
[31m-        clients.append({[m
[31m-[m
[31m-            "name":[m
[31m-                client_folder.name,[m
[31m-[m
[31m-            "path":[m
[31m-                str([m
[31m-                    index.relative_to(ROOT)[m
[31m-                ).replace("\\","/"),[m
[32m+[m[32m            clients.append([m
[32m+[m[32m                {[m
[32m+[m[32m                    "name": business_name,[m
[32m+[m[32m                    "folder": client_folder,[m
[32m+[m[32m                    "priority": priority,[m
[32m+[m[32m                    "score": score,[m
[32m+[m[32m                    "status": status_value,[m
[32m+[m[32m                }[m
[32m+[m[32m            )[m
 [m
[31m-            "status":[m
[31m-                status,[m
[32m+[m[32m    return sorted([m
[32m+[m[32m        clients,[m
[32m+[m[32m        key=lambda client: ([m
[32m+[m[32m            0 if client["priority"] == "HIGH" else 1,[m
[32m+[m[32m            -int(client["score"]) if str(client["score"]).isdigit() else 0,[m
[32m+[m[32m            client["name"].lower(),[m
[32m+[m[32m        ),[m
[32m+[m[32m    )[m
 [m
[31m-            "status_class":[m
[31m-                status.lower()[m
 [m
[31m-        })[m
[32m+[m[32mdef client_card(client):[m
[32m+[m[32m    folder = client["folder"][m
 [m
[32m+[m[32m    priority_class = ([m
[32m+[m[32m        "priority-high"[m
[32m+[m[32m        if client["priority"] == "HIGH"[m
[32m+[m[32m        else "priority-medium"[m
[32m+[m[32m    )[m
 [m
[31m-    return clients[m
[32m+[m[32m    status_class = ([m
[32m+[m[32m        "status-pass"[m
[32m+[m[32m        if str(client["status"]).upper() in {"PASS", "PASSED", "SUCCESS"}[m
[32m+[m[32m        else "status-fail"[m
[32m+[m[32m    )[m
 [m
[32m+[m[32m    relative_folder = folder.relative_to(BASE_DIR)[m
[32m+[m
[32m+[m[32m    return f"""[m
[32m+[m[32m    <div class="client-card">[m
[32m+[m
[32m+[m[32m        <div class="client-name">[m
[32m+[m[32m            {client["name"]}[m
[32m+[m[32m        </div>[m
[32m+[m
[32m+[m[32m        <div class="meta">[m
[32m+[m
[32m+[m[32m            <div class="meta-box">[m
[32m+[m[32m                <span class="meta-label">Priority</span>[m
[32m+[m[32m                <span class="meta-value {priority_class}">[m
[32m+[m[32m                    {client["priority"]}[m
[32m+[m[32m                </span>[m
[32m+[m[32m            </div>[m
[32m+[m
[32m+[m[32m            <div class="meta-box">[m
[32m+[m[32m                <span class="meta-label">Score</span>[m
[32m+[m[32m                <span class="meta-value">[m
[32m+[m[32m                    {client["score"]}[m
[32m+[m[32m                </span>[m
[32m+[m[32m            </div>[m
[32m+[m
[32m+[m[32m            <div class="meta-box">[m
[32m+[m[32m                <span class="meta-label">Status</span>[m
[32m+[m[32m                <span class="meta-value {status_class}">[m
[32m+[m[32m                    {client["status"]}[m
[32m+[m[32m                </span>[m
[32m+[m[32m            </div>[m
[32m+[m
[32m+[m[32m        </div>[m
[32m+[m
[32m+[m[32m        <div class="buttons">[m
[32m+[m
[32m+[m[32m            <a[m
[32m+[m[32m                class="button button-primary"[m
[32m+[m[32m                href="/demo/{relative_folder}"[m
[32m+[m[32m                target="_blank"[m
[32m+[m[32m            >[m
[32m+[m[32m                VIEW DEMO[m
[32m+[m[32m            </a>[m
[32m+[m
[32m+[m[32m            <a[m
[32m+[m[32m                class="button"[m
[32m+[m[32m                href="/asset/offer/{relative_folder}"[m
[32m+[m[32m                target="_blank"[m
[32m+[m[32m            >[m
[32m+[m[32m                SALES OFFER[m
[32m+[m[32m            </a>[m
[32m+[m
[32m+[m[32m            <a[m
[32m+[m[32m                class="button"[m
[32m+[m[32m                href="/asset/sales_notes/{relative_folder}"[m
[32m+[m[32m                target="_blank"[m
[32m+[m[32m            >[m
[32m+[m[32m                SALES NOTES[m
[32m+[m[32m            </a>[m
[32m+[m
[32m+[m[32m            <a[m
[32m+[m[32m                class="button"[m
[32m+[m[32m                href="/asset/delivery/{relative_folder}"[m
[32m+[m[32m                target="_blank"[m
[32m+[m[32m            >[m
[32m+[m[32m                DELIVERY PACKAGE[m
[32m+[m[32m            </a>[m
[32m+[m
[32m+[m[32m        </div>[m
[32m+[m
[32m+[m[32m    </div>[m
[32m+[m[32m    """[m
 [m
 [m
 @app.route("/")[m
 def dashboard():[m
[32m+[m[32m    clients = find_clients()[m
[32m+[m
[32m+[m[32m    high = [[m
[32m+[m[32m        client for client in clients[m
[32m+[m[32m        if client["priority"] == "HIGH"[m
[32m+[m[32m    ][m
[32m+[m
[32m+[m[32m    medium = [[m
[32m+[m[32m        client for client in clients[m
[32m+[m[32m        if client["priority"] == "MEDIUM"[m
[32m+[m[32m    ][m
 [m
     return render_template_string([m
         HTML,[m
[31m-        clients=get_clients()[m
[32m+[m[32m        high=high,[m
[32m+[m[32m        medium=medium,[m
[32m+[m[32m        client_card=client_card,[m
     )[m
 [m
 [m
[32m+[m[32m@app.route("/demo/<path:client_path>")[m
[32m+[m[32mdef demo(client_path):[m
[32m+[m[32m    client_folder = (BASE_DIR / client_path).resolve()[m
 [m
[31m-@app.route("/website/<path:file>")[m
[31m-def website(file):[m
[32m+[m[32m    try:[m
[32m+[m[32m        client_folder.relative_to(HANDOFFS_DIR.resolve())[m
[32m+[m[32m    except ValueError:[m
[32m+[m[32m        abort(404)[m
 [m
[31m-    folder = ([m
[31m-        ROOT /[m
[31m-        Path(file).parent[m
[31m-    )[m
[32m+[m[32m    website_file = client_folder / "website" / "index.html"[m
 [m
[31m-    filename = ([m
[31m-        Path(file).name[m
[31m-    )[m
[32m+[m[32m    if not website_file.exists():[m
[32m+[m[32m        abort(404)[m
 [m
[32m+[m[32m    return send_file(website_file)[m
 [m
[31m-    return send_from_directory([m
[31m-        folder,[m
[31m-        filename[m
[31m-    )[m
 [m
[32m+[m[32m@app.route("/asset/<asset>/<path:client_path>")[m
[32m+[m[32mdef asset(asset, client_path):[m
[32m+[m[32m    if asset not in ALLOWED_ASSETS:[m
[32m+[m[32m        abort(404)[m
[32m+[m
[32m+[m[32m    client_folder = (BASE_DIR / client_path).resolve()[m
[32m+[m
[32m+[m[32m    try:[m
[32m+[m[32m        client_folder.relative_to(HANDOFFS_DIR.resolve())[m
[32m+[m[32m    except ValueError:[m
[32m+[m[32m        abort(404)[m
[32m+[m
[32m+[m[32m    asset_file = client_folder / ALLOWED_ASSETS[asset][m
[32m+[m
[32m+[m[32m    if not asset_file.exists():[m
[32m+[m[32m        abort(404)[m
[32m+[m
[32m+[m[32m    return send_file(asset_file)[m
 [m
 [m
 if __name__ == "__main__":[m
[32m+[m[32m    print("LeadFinder Sales Dashboard")[m
[32m+[m[32m    print("Open: http://localhost:3000")[m
 [m
     app.run([m
         host="0.0.0.0",[m
         port=3000,[m
[31m-        debug=True[m
[32m+[m[32m        debug=False,[m
     )[m
\ No newline at end of file[m
