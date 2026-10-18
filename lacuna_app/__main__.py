"""`python -m lacuna_app --workspace <path>`: start LACUNA Studio on http://127.0.0.1:<port>."""
from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"   # loopback only, never exposed on the network
# On restart/update, connections still open (a paused <audio> keeps its WAV stream open) get this
# long to finish before they are dropped; the process is killed if it still hasn't exited after FORCE_EXIT.
GRACEFUL_SHUTDOWN = 3
FORCE_EXIT = 20


def make_server(app, port: int):
    import uvicorn

    return uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="warning",
                                         timeout_graceful_shutdown=GRACEFUL_SHUTDOWN))


def force_exit_later(code: int, after: float = FORCE_EXIT) -> threading.Timer:
    """Last resort: the launcher waits for this process to exit before it can update or restart."""
    t = threading.Timer(after, lambda: os._exit(code))
    t.daemon = True
    t.start()
    return t


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="lacuna_app", description="LACUNA Studio (local web app)")
    ap.add_argument("--workspace", default=os.environ.get("LACUNA_WORKSPACE"),
                    help="LACUNA_Workspace folder (or env LACUNA_WORKSPACE)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--editor", choices=["auto", "mock", "claude"], default="auto",
                    help="AI producer backend: auto = Claude if ANTHROPIC_API_KEY is set, else rules")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    if not args.workspace:
        ap.error("--workspace is required")
    ws = Path(args.workspace).expanduser()
    if not ws.is_dir():
        ap.error(f"workspace folder not found: {ws}")

    import uvicorn

    from .editor import make_adapter
    from .server import create_app

    from .appinfo import current_version
    from .quiet import install as quiet_disconnect_noise

    exit_code = 0
    server: uvicorn.Server | None = None

    def restart(code: int) -> None:
        """Stop serving and exit with `code`: the launcher swaps in an update (75) or restarts (76)."""
        nonlocal exit_code
        exit_code = code
        if server is not None:
            server.should_exit = True
            force_exit_later(code)

    quiet_disconnect_noise()
    app = create_app(ws, make_adapter(args.editor), restart=restart)
    url = f"http://{HOST}:{args.port}/"
    print(f"LACUNA Studio {current_version()} → {url}  (workspace: {ws.resolve()}, editor: {args.editor})")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    server = make_server(app, args.port)
    server.run()
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
