"""Shared localhost server for VS Code and the Windows launcher."""
from waitress import create_server


def serve_dashboard(app, port):
    server = create_server(app, host='127.0.0.1', port=port, threads=8,
                           expose_tracebacks=False)
    print(f'Running on http://127.0.0.1:{server.effective_port}', flush=True)
    try:
        server.run()
    finally:
        server.close()
