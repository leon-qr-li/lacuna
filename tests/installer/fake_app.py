"""Stand-in for `python -m lacuna_app` in launcher tests: answers /api/app with the VERSION of its
working directory, exits with the code written to <root>/control, and fails at once when its
version folder holds a BROKEN file (a release that cannot start)."""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

port, root = int(sys.argv[1]), Path(sys.argv[2])
here = Path.cwd()
if (here / "BROKEN").exists():
    sys.exit(3)
version = (here / "VERSION").read_text().strip()


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"version": version}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", port), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
control = root / "control"
while True:
    if control.exists():
        code = int(control.read_text() or 0)
        control.unlink()
        srv.shutdown()
        srv.server_close()
        sys.exit(code)
    time.sleep(0.05)
