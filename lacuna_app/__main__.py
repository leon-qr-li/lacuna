"""`python -m lacuna_app --workspace <path>`: start LACUNA Studio on http://127.0.0.1:<port>."""
from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"   # loopback only, never exposed on the network (a development checkout)
# On shutdown, connections still open (a paused <audio> keeps its WAV stream open) get this long to
# finish before they are dropped.
GRACEFUL_SHUTDOWN = 3
# An idle keep-alive connection stays open this long. Longer than the proxy in front keeps its idle
# connections (cloudflared: 90 s), so the proxy never sends a request on a connection we are closing
# at that moment: with uvicorn's 5 s, the page's 5-second presence beat (and any POST after a 5 s
# pause) now and then met a reset, which the proxy answers with 502 (batch 10 load test).
KEEP_ALIVE = 120


def make_server(app, port: int, host: str = HOST):
    import uvicorn

    return uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning",
                                         timeout_keep_alive=KEEP_ALIVE, timeout_graceful_shutdown=GRACEFUL_SHUTDOWN))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="lacuna_app", description="LACUNA Studio (local web app)")
    ap.add_argument("--workspace", default=os.environ.get("LACUNA_WORKSPACE"),
                    help="LACUNA_Workspace folder (or env LACUNA_WORKSPACE)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--editor", choices=["auto", "mock", "claude"], default="auto",
                    help="AI producer backend: auto = Claude if ANTHROPIC_API_KEY is set, else rules")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--host", default=HOST,
                    help="address to listen on; anything but loopback needs LACUNA_CLOUD=1 (the cloud container)")
    args = ap.parse_args(argv)
    from .cloud import enabled as cloud_enabled
    if args.host not in ("127.0.0.1", "localhost", "::1") and not cloud_enabled():
        ap.error("--host other than loopback is only for cloud mode (LACUNA_CLOUD=1)")
    if not args.workspace:
        ap.error("--workspace is required")
    ws = Path(args.workspace).expanduser()
    if not ws.is_dir():
        ap.error(f"workspace folder not found: {ws}")

    from .editor import make_adapter
    from .server import create_app

    from .appinfo import current_version
    from .quiet import install as quiet_disconnect_noise

    quiet_disconnect_noise()
    app = create_app(ws, make_adapter(args.editor))
    url = f"http://{args.host}:{args.port}/"
    print(f"LACUNA Studio {current_version()} → {url}  (workspace: {ws.resolve()}, editor: {args.editor})")
    if not args.no_browser and not cloud_enabled():
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    make_server(app, args.port, args.host).run()


if __name__ == "__main__":
    main()
