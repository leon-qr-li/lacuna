"""FastAPI app: JSON API + streamed audio + the built web UI. Bind to 127.0.0.1 only.

Routes live in `lacuna_app/routes/`, one module per feature, each with `register(app, ctx)`;
they are discovered automatically, so a new feature adds a file and never edits this one.
"""
from __future__ import annotations

import json
import threading
import weakref
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .cold import Restoring
from .editor import EditorAdapter, make_adapter
from .i18n import tr
from .episode import ConflictError, Episode
from .store import PathError, Workspace, now_iso

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
USAGE_LOG = "ai_usage.jsonl"     # one line per Claude call: tokens, seconds, estimated cost


_USAGE_LOCK = threading.Lock()     # parallel calls (4 covers at once): appends are not atomic on Windows


def log_usage(path: Path, episode_id: str, usage: dict) -> None:
    line = {"at": now_iso(), "episode": episode_id, **usage}
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
        # the KEEP_OPEN most recently used episodes stay in memory; the others load on demand
        # (~0.1 s each). `_alive` also finds an evicted episode a background job still holds, so
        # there is never more than one Episode object (and one writer) per episode.
        self.episodes: OrderedDict[str, Episode] = OrderedDict()
        self._alive: weakref.WeakValueDictionary[str, Episode] = weakref.WeakValueDictionary()
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

    @property
    def models_dir(self) -> Path:
        """Speech models: one copy for every workspace of the installation (routes/spaces.py)."""
        return Path(self.option("models_dir") or self.ws.root / "models")

    def log_usage(self, episode_id: str, usage: dict) -> None:
        log_usage(self.ws.root / USAGE_LOG, episode_id, usage)

    KEEP_OPEN = 3

    def get(self, episode_id: str) -> Episode:
        """The episode, loaded if needed, marked as most recently used. An episode whose audio is in cloud
        storage (cold.py) starts coming back and answers 423 until it is here."""
        cold = self.provide("cold")
        if cold is not None and cold.on:
            self.peek(episode_id)               # 400 / 404 first
            try:
                cold.opening(self.ws, episode_id)
            except Restoring:
                with self.lock:                 # a copy loaded while the audio was away is not kept
                    self.episodes.pop(episode_id, None)
                    self._alive.pop(episode_id, None)
                raise
        ep = self.peek(episode_id)
        with self.lock:
            self.episodes[episode_id] = ep
            self.episodes.move_to_end(episode_id)
            while len(self.episodes) > self.KEEP_OPEN:
                self.episodes.popitem(last=False)    # freed once no job holds it any more
        return ep

    def peek(self, episode_id: str) -> Episode:
        """The episode, loaded if needed, without keeping it in memory (listing, learning)."""
        try:
            self.ws.episode_dir(episode_id)
        except PathError:
            raise HTTPException(400, "invalid episode id")
        with self.lock:
            ep = self.episodes.get(episode_id) or self._alive.get(episode_id)
            if ep is None:
                if episode_id not in self.ws.episode_ids():
                    raise HTTPException(404, "no such episode")
                ep = self._alive[episode_id] = Episode(self.ws, episode_id)
            return ep

    def loaded(self, episode_id: str) -> Episode | None:
        """The episode if it is in memory right now, else None (never loads)."""
        with self.lock:
            return self.episodes.get(episode_id) or self._alive.get(episode_id)

    def open_episodes(self):
        """Every episode, one at a time: only the recently used ones stay in memory."""
        for eid in self.ws.episode_ids():
            try:
                yield self.peek(eid)
            except Exception:     # a broken episode must not hide the others
                continue

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
    ctx.web_dist = web_dist

    @app.exception_handler(ConflictError)
    async def _conflict(_req, exc: ConflictError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(Restoring)
    async def _restoring(_req, exc: Restoring):
        detail = tr("取回音频没有成功，请稍后再打开这一集。") if exc.error else tr("正在取回这一集的音频…")
        return JSONResponse({"detail": detail, "restoring": {"progress": round(exc.progress, 3), "failed": bool(exc.error)}},
                            status_code=423)

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
