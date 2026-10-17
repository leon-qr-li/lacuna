"""FastAPI app: JSON API + streamed audio + the built web UI. Bind to 127.0.0.1 only."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from urllib.parse import quote
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .audio import parse_range
from .editor import EditorAdapter, editor_status, make_adapter
from .episode import ConflictError, Episode
from .exporter import ExportBusy, Exporter
from .learning import Learning
from .store import PathError, Workspace

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
USAGE_LOG = "ai_usage.jsonl"     # one line per Claude call: tokens, seconds, estimated cost


def log_usage(path: Path, episode_id: str, usage: dict) -> None:
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "episode": episode_id, **usage}
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass      # bookkeeping must never break the chat


class PlayheadBody(BaseModel):
    playhead: float | None = Field(None, ge=0, description="seconds on the timeline the client is playing")


class ReviewBody(PlayheadBody):
    action: str = Field(pattern="^(keep|restore|apply)$")


class BatchReviewBody(PlayheadBody):
    action: str = Field(pattern="^(approve|keep|restore)$")
    ids: list[str] | None = Field(None, max_length=5000, description="defaults to every edit still pending review")


class ChatBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    playhead: float = Field(ge=0)


class ExportBody(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["mp3", "wav"], min_length=1)
    mp3_kbps: int = Field(128, ge=64, le=320)
    channels: int = Field(2, ge=1, le=2)


class RuleBody(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    action: str = Field(pattern="^(approve|reject|reset)$")


class OpBody(PlayheadBody):
    op: dict
    title: str = Field("手动修改", max_length=200)
    reason: str = Field("", max_length=2000)


def create_app(workspace: str | Path, adapter: EditorAdapter | None = None, web_dist: Path = WEB_DIST) -> FastAPI:
    ws = Workspace(workspace).ensure()
    adapter = adapter or make_adapter("auto")
    app = FastAPI(title="LACUNA Studio", docs_url="/api/docs", openapi_url="/api/openapi.json")
    episodes: dict[str, Episode] = {}
    lock = threading.Lock()
    exporter = Exporter(ws)
    learning = Learning(ws)

    def get(episode_id: str) -> Episode:
        try:
            ws.episode_dir(episode_id)
        except PathError:
            raise HTTPException(400, "invalid episode id")
        with lock:
            ep = episodes.get(episode_id)
            if ep is None:
                if episode_id not in ws.episode_ids():
                    raise HTTPException(404, "no such episode")
                ep = episodes[episode_id] = Episode(ws, episode_id)
            return ep

    @app.exception_handler(ConflictError)
    async def _conflict(_req, exc: ConflictError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    def mutate(ep: Episode, playhead: float | None, fn) -> dict:
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

    # ------------------------------------------------------------------ API
    @app.get("/api/health")
    def health():
        return {"ok": True, "workspace": str(ws.root)} | editor_status(adapter)

    @app.get("/api/episodes")
    def list_episodes():
        out = []
        for eid in ws.episode_ids():
            try:
                s = get(eid).summary()
                out.append({k: s[k] for k in ("id", "title", "demo", "duration", "raw_duration", "pending_review")})
            except Exception as e:   # a broken episode must not hide the others
                out.append({"id": eid, "title": eid, "error": str(e)})
        return {"episodes": out} | editor_status(adapter)

    @app.get("/api/episodes/{episode_id}")
    def load_episode(episode_id: str):
        return get(episode_id).summary()

    @app.get("/api/episodes/{episode_id}/audio/{version}.wav")
    def audio(episode_id: str, version: str, request: Request):
        ep = get(episode_id)
        enabled = ep.enabled_for_key(version)
        if enabled is None:
            if version != ep.version_key():
                raise HTTPException(404, "unknown or expired version")
            enabled = ep.enabled
        total = ep.wav_size(enabled)
        rng = parse_range(request.headers.get("range"), total)
        headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
        if request.headers.get("range") and rng is None:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        first, last = rng or (0, total - 1)
        headers["Content-Length"] = str(last - first + 1)
        if rng:
            headers["Content-Range"] = f"bytes {first}-{last}/{total}"
        return StreamingResponse(ep.iter_wav(enabled, first, last), status_code=206 if rng else 200,
                                 media_type="audio/wav", headers=headers)

    @app.get("/api/episodes/{episode_id}/clips/{cid}.wav")
    def clip(episode_id: str, cid: str):
        c = get(episode_id).clip(cid)
        if c is None:
            raise HTTPException(404, "clip expired")
        return Response(c.wav, media_type="audio/wav", headers={"Cache-Control": "private, max-age=600"})

    @app.get("/api/episodes/{episode_id}/edits/{eid}/ab")
    def edit_ab(episode_id: str, eid: str):
        try:
            return get(episode_id).edit_ab(eid)
        except KeyError:
            raise HTTPException(404, "no such edit")

    @app.get("/api/episodes/{episode_id}/edits/{eid}/text")
    def edit_text(episode_id: str, eid: str):
        try:
            return {"lines": get(episode_id).edit_text(eid)}
        except KeyError:
            raise HTTPException(404, "no such edit")

    @app.post("/api/episodes/{episode_id}/edits/{eid}/review")
    def review(episode_id: str, eid: str, body: ReviewBody):
        ep = get(episode_id)
        return mutate(ep, body.playhead, lambda: ep.review(eid, body.action))

    @app.post("/api/episodes/{episode_id}/review")
    def review_batch(episode_id: str, body: BatchReviewBody):
        ep = get(episode_id)
        return mutate(ep, body.playhead, lambda: {"changed": ep.review_all(body.action, body.ids)})

    @app.post("/api/episodes/{episode_id}/ops")
    def apply_op(episode_id: str, body: OpBody):
        ep = get(episode_id)
        try:
            return mutate(ep, body.playhead, lambda: {"edit_id": ep.apply_op(body.op, body.title, body.reason).id})
        except (TypeError, ValueError) as e:
            if isinstance(e, ConflictError):
                raise
            raise HTTPException(422, f"bad op: {e}")

    @app.post("/api/episodes/{episode_id}/undo")
    def undo(episode_id: str, body: PlayheadBody):
        ep = get(episode_id)
        return mutate(ep, body.playhead, lambda: {"done": ep.undo()})

    @app.post("/api/episodes/{episode_id}/redo")
    def redo(episode_id: str, body: PlayheadBody):
        ep = get(episode_id)
        return mutate(ep, body.playhead, lambda: {"done": ep.redo()})

    @app.post("/api/episodes/{episode_id}/chat")
    def chat(episode_id: str, body: ChatBody):
        out = get(episode_id).chat(body.text, body.playhead, adapter)
        if out.get("usage"):
            log_usage(ws.root / USAGE_LOG, episode_id, out["usage"])
        return out

    @app.get("/api/episodes/{episode_id}/proposals/{pid}/ab")
    def proposal_ab(episode_id: str, pid: str):
        try:
            return get(episode_id).proposal_ab(pid)
        except KeyError:
            raise HTTPException(404, "no such proposal")

    @app.post("/api/episodes/{episode_id}/proposals/{pid}/approve")
    def approve(episode_id: str, pid: str, body: PlayheadBody):
        ep = get(episode_id)
        return mutate(ep, body.playhead, lambda: ep.approve_proposal(pid))

    @app.post("/api/episodes/{episode_id}/proposals/{pid}/discard")
    def discard(episode_id: str, pid: str, body: PlayheadBody):
        ep = get(episode_id)
        return mutate(ep, body.playhead, lambda: ep.discard_proposal(pid))

    # ------------------------------------------------------------------ export
    @app.post("/api/episodes/{episode_id}/export")
    def start_export(episode_id: str, body: ExportBody):
        ep = get(episode_id)
        try:
            return {"job": exporter.start(ep, body.formats, body.mp3_kbps, body.channels)}
        except ExportBusy as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            if isinstance(e, ConflictError):
                raise
            raise HTTPException(422, str(e))

    @app.get("/api/episodes/{episode_id}/export")
    def export_status(episode_id: str):
        get(episode_id)
        return {"job": exporter.status(episode_id)}

    @app.get("/api/episodes/{episode_id}/exports/{name}")
    def export_file(episode_id: str, name: str):
        get(episode_id)
        try:
            path = exporter.file_path(episode_id, name)
        except (PathError, FileNotFoundError):
            raise HTTPException(404, "no such export file")
        # ASCII fallback first, then the UTF-8 name (episode ids are often Chinese)
        ascii_name = path.name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
        disp = f"attachment; filename=\"{ascii_name}\"; filename*=utf-8''{quote(path.name)}"
        return FileResponse(path, headers={"Content-Disposition": disp})

    @app.post("/api/episodes/{episode_id}/exports/open")
    def open_exports(episode_id: str):
        get(episode_id)
        return {"folder": exporter.open_folder(episode_id)}

    # ------------------------------------------------------------------ learning (D27)
    def open_episodes() -> list[Episode]:
        out = []
        for eid in ws.episode_ids():
            try:
                out.append(get(eid))
            except Exception:     # a broken episode must not hide what the others teach
                continue
        return out

    @app.get("/api/learning")
    def learning_overview():
        return learning.overview(open_episodes())

    @app.post("/api/learning/rules")
    def learning_decide(body: RuleBody):
        try:
            return learning.decide(body.id, body.action, open_episodes())
        except KeyError:
            raise HTTPException(404, "no such rule")

    # ------------------------------------------------------------------ web UI
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
    app.state.episodes = episodes
    app.state.exporter = exporter
    return app
