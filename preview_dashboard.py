from flask import Flask, render_template_string, send_from_directory
from pathlib import Path
import json


app = Flask(__name__)


ROOT = Path("codex_handoffs")


HTML = """
<!DOCTYPE html>
<html>

<head>

<title>LeadFinder Preview Dashboard</title>

<style>

body {
    font-family: Arial, sans-serif;
    padding: 40px;
    background: #f5f5f5;
}


.card {

    background:white;
    padding:20px;
    margin-bottom:20px;
    border-radius:10px;

}


a {

    display:inline-block;
    margin-top:10px;
    padding:10px 20px;
    background:#111;
    color:white;
    text-decoration:none;
    border-radius:5px;

}


.pass {

    color:green;

}


.pending {

    color:orange;

}

</style>

</head>


<body>


<h1>🚀 LeadFinder Website Dashboard</h1>


{% for client in clients %}

<div class="card">

<h2>{{client.name}}</h2>


<p>
Status:
<span class="{{client.status_class}}">
{{client.status}}
</span>
</p>


<a href="/website/{{client.path}}" target="_blank">
View Website
</a>


</div>


{% endfor %}


</body>

</html>
"""


def get_clients():

    clients = []


    for client in ROOT.rglob("website"):

        index = client / "index.html"


        if not index.exists():
            continue


        client_folder = client.parent


        status = "UNKNOWN"


        status_file = (
            client_folder /
            "STATUS.json"
        )


        if status_file.exists():

            data = json.loads(
                status_file.read_text()
            )

            status = data.get(
                "status",
                "UNKNOWN"
            )


        clients.append({

            "name":
                client_folder.name,

            "path":
                str(
                    index.relative_to(ROOT)
                ).replace("\\","/"),

            "status":
                status,

            "status_class":
                status.lower()

        })


    return clients



@app.route("/")
def dashboard():

    return render_template_string(
        HTML,
        clients=get_clients()
    )



@app.route("/website/<path:file>")
def website(file):

    folder = (
        ROOT /
        Path(file).parent
    )

    filename = (
        Path(file).name
    )


    return send_from_directory(
        folder,
        filename
    )



if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=3000,
        debug=True
    )