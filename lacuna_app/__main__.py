"""`python -m lacuna_app --workspace <path>`: start LACUNA Studio on http://127.0.0.1:<port>."""
from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"   # loopback only, never exposed on the network


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

    app = create_app(ws, make_adapter(args.editor))
    url = f"http://{HOST}:{args.port}/"
    print(f"LACUNA Studio → {url}  (workspace: {ws.resolve()}, editor: {args.editor})")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
