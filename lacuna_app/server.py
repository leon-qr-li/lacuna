"""FastAPI app: JSON API + streamed audio + the built web UI. Bind to 127.0.0.1 only.

Routes live in `lacuna_app/routes/`, one module per feature, each with `register(app, ctx)`;
they are discovered automatically, so a new feature adds a file and never edits this one.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .editor import EditorAdapter, make_adapter
from .episode import ConflictError, Episode
from .store import PathError, Workspace

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
USAGE_LOG = "ai_usage.jsonl"     # one line per Claude call: tokens, seconds, estimated cost


_USAGE_LOCK = threading.Lock()     # parallel calls (4 covers at once): appends are not atomic on Windows


def log_usage(path: Path, episode_id: str, usage: dict) -> None:
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "episode": episode_id, **usage}
    try:
        with _USAGE_LOCK, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass      # bookkeeping must never break the chat


def next_episode_id(ids: list[str]) -> str:
    """EP00N after the highest EPnnn already used (EP001_AI counts as 1)."""
    import re
    nums = [int(m.group(1)) for i in ids if (m := re.match(r"EP(\d+)", i))]
    return f"EP{(max(nums) + 1) if nums else 1:03d}"


class AppContext:
    """What route modules share: the workspace, the chat adapter, open episodes and services.

    `provide(name, factory)` returns the service passed to `create_app(**services)` under that
    name (tests inject fakes this way), else builds it once with `factory()`. Either way it is
    cached and also set as `app.state.<name>`.
    """

    def __init__(self, app: FastAPI, ws: Workspace, adapter: EditorAdapter, services: dict[str, Any]):
        self.app, self.ws, self.adapter = app, ws, adapter
        self.lock = threading.Lock()
        self.episodes: dict[str, Episode] = {}
        self._given = dict(services)
        self._built: dict[str, Any] = {}

    def provide(self, name: str, factory: Callable[[], Any] | None = None) -> Any:
        if name not in self._built:
            svc = self._given.get(name)
            if svc is None:
                if factory is None:
                    return None
                svc = factory()
            self._built[name] = svc
            setattr(self.app.state, name, svc)
        return self._built[name]

    def option(self, name: str, default: Any = None) -> Any:
        """A plain create_app keyword (not a service), e.g. a fake client for tests."""
        return self._given.get(name, default)

    def log_usage(self, episode_id: str, usage: dict) -> None:
        log_usage(self.ws.root / USAGE_LOG, episode_id, usage)

    def get(self, episode_id: str) -> Episode:
        try:
            self.ws.episode_dir(episode_id)
        except PathError:
            raise HTTPException(400, "invalid episode id")
        with self.lock:
            ep = self.episodes.get(episode_id)
            if ep is None:
                if episode_id not in self.ws.episode_ids():
                    raise HTTPException(404, "no such episode")
                ep = self.episodes[episode_id] = Episode(self.ws, episode_id)
            return ep

    def open_episodes(self) -> list[Episode]:
        out = []
        for eid in self.ws.episode_ids():
            try:
                out.append(self.get(eid))
            except Exception:     # a broken episode must not hide the others
                continue
        return out

    def mutate(self, ep: Episode, playhead: float | None, fn) -> dict:
        """Run a mutation; return the new summary plus the playhead mapped onto the new timeline."""
        try:
            before = ep.enabled
            extra = fn() or {}
        except KeyError:
            raise HTTPException(404, "no such edit or proposal")
        out = ep.summary() | extra
        if playhead is not None:
            out["playhead"] = ep.map_playhead(playhead, before, ep.enabled)
        return out


def create_app(workspace: str | Path, adapter: EditorAdapter | None = None, web_dist: Path = WEB_DIST,
               **services: Any) -> FastAPI:
    """`services`: prebuilt services or options by name (importer=, publisher=, posters=, dictation=,
    credit_client=, ...); anything left out is built by the route module that needs it."""
    from . import routes

    ws = Workspace(workspace).ensure()
    adapter = adapter or make_adapter("auto")
    app = FastAPI(title="LACUNA Studio", docs_url="/api/docs", openapi_url="/api/openapi.json")
    ctx = AppContext(app, ws, adapter, services)

    @app.exception_handler(ConflictError)
    async def _conflict(_req, exc: ConflictError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    routes.register_all(app, ctx)

    # ------------------------------------------------------------------ web UI (last: catch-all)
    if (web_dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            return FileResponse(web_dist / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def no_ui():
            return Response("<p>LACUNA API is running. Build the UI: <code>cd web && npm ci && npm run build</code></p>",
                            media_type="text/html")

    app.state.workspace = ws
    app.state.episodes = ctx.episodes
    app.state.ctx = ctx
    return app
