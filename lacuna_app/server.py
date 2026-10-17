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
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .audio import parse_range
from .dictation import Dictation, DictationError
from .editor import EditorAdapter, editor_status, make_adapter
from .episode import ConflictError, Episode
from .exporter import ExportBusy, Exporter
from .importer import ImportBusy, ImportError_, Importer, list_dir
from .learning import Learning
from .library import KINDS, Library, LibraryError, lookup_credit
from .music import ROLES, EpisodeMusic
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


def next_episode_id(ids: list[str]) -> str:
    """EP00N after the highest EPnnn already used (EP001_AI counts as 1)."""
    import re
    nums = [int(m.group(1)) for i in ids if (m := re.match(r"EP(\d+)", i))]
    return f"EP{(max(nums) + 1) if nums else 1:03d}"


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


class ImportBody(BaseModel):
    id: str = Field(min_length=1, max_length=120, description="episode id = folder name, e.g. EP002")
    title: str = Field("", max_length=200)
    leon: str = Field(min_length=1, max_length=2000, description="path of Leon's raw track")
    pei: str = Field(min_length=1, max_length=2000, description="path of Pei's raw track")
class RuleBody(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    action: str = Field(pattern="^(approve|reject|reset)$")


class LibraryFileBody(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    kind: str = Field("music", pattern="^(music|jingle|clip)$")
    note: str = Field("", max_length=500)


class AssetBody(BaseModel):
    note: str | None = Field(None, max_length=500)
    kind: str | None = Field(None, pattern="^(music|jingle|clip)$")
    credit: dict | None = None
    confirm: bool = False


class PlacementBody(BaseModel):
    asset_id: str | None = Field(None, max_length=40)
    role: str | None = Field(None, pattern="^(intro|interlude|outro|bed|clip)$")
    at_s: float | None = Field(None, ge=0, description="position on the final mix (seconds)")
    until_s: float | None = Field(None, ge=0, description="bed: end on the final mix (seconds)")
    src_in_s: float | None = Field(None, ge=0)
    src_out_s: float | None = Field(None, ge=0)
    overlap_s: float | None = Field(None, ge=0, le=30)
    gain_db: float | None = Field(None, ge=-30, le=12)
    lead_s: float | None = Field(None, ge=0, le=5)
    status: str | None = Field(None, pattern="^(applied|proposed)$")


class SeriesBody(BaseModel):
    name: str = Field("洛城二三事", min_length=1, max_length=80)


class OpBody(PlayheadBody):
    op: dict
    title: str = Field("手动修改", max_length=200)
    reason: str = Field("", max_length=2000)


def create_app(workspace: str | Path, adapter: EditorAdapter | None = None, web_dist: Path = WEB_DIST,
               importer: Importer | None = None, dictation: Dictation | None = None,
               credit_client=None) -> FastAPI:
    """`credit_client`: an Anthropic-like client for the library's credit lookup (tests inject a fake)."""
    ws = Workspace(workspace).ensure()
    adapter = adapter or make_adapter("auto")
    app = FastAPI(title="LACUNA Studio", docs_url="/api/docs", openapi_url="/api/openapi.json")
    episodes: dict[str, Episode] = {}
    lock = threading.Lock()
    exporter = Exporter(ws)
    importer = importer or Importer(ws)
    learning = Learning(ws)
    dictation = dictation or Dictation(ws.root / "models")
    library = Library(ws)
    musics: dict[str, EpisodeMusic] = {}

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
        return {"ok": True, "workspace": str(ws.root)} | editor_status(adapter) | dictation.status()

    @app.post("/api/dictation/warm")
    def dictation_warm():
        dictation.warm()
        return {"ok": True}

    @app.post("/api/dictation")
    async def dictate(request: Request):
        """Raw recorded audio in the body (any format ffmpeg reads) → text. Stays on this machine."""
        data = await request.body()
        try:
            return await run_in_threadpool(dictation.transcribe, data)
        except DictationError as e:
            raise HTTPException(422, str(e))

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

    # ------------------------------------------------------------------ import
    @app.get("/api/fs")
    def browse(path: str | None = None):
        try:
            return list_dir(path, ws.root)
        except ImportError_ as e:
            raise HTTPException(404, str(e))

    @app.get("/api/imports")
    def imports():
        return {"jobs": importer.status(), "next_id": next_episode_id(ws.episode_ids() + [j["id"] for j in importer.status()])}

    @app.post("/api/imports")
    def start_import(body: ImportBody):
        try:
            return {"job": importer.start(body.id.strip(), body.title, body.leon, body.pei)}
        except ImportBusy as e:
            raise HTTPException(409, str(e))
        except ImportError_ as e:
            raise HTTPException(422, str(e))

    @app.get("/api/imports/{episode_id}")
    def import_status(episode_id: str):
        j = importer.status(episode_id)
        if j is None:
            raise HTTPException(404, "no such import")
        return {"job": j}

    @app.post("/api/imports/{episode_id}/resume")
    def resume_import(episode_id: str):
        try:
            return {"job": importer.resume(episode_id)}
        except KeyError:
            raise HTTPException(404, "no such import")
        except ImportBusy as e:
            raise HTTPException(409, str(e))

    @app.post("/api/imports/{episode_id}/cancel")
    def cancel_import(episode_id: str):
        try:
            importer.cancel(episode_id)
        except KeyError:
            raise HTTPException(409, "这一集没有在导入")
        return {"job": importer.status(episode_id)}

    @app.delete("/api/imports/{episode_id}")
    def forget_import(episode_id: str):
        try:
            importer.forget(episode_id)
        except KeyError:
            raise HTTPException(404, "no such import")
        except ImportBusy as e:
            raise HTTPException(409, str(e))
        return {"ok": True}
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

    # ------------------------------------------------------------------ media library + music (D43)
    def music(episode_id: str) -> EpisodeMusic:
        ep = get(episode_id)
        with lock:
            m = musics.get(episode_id)
            if m is None or m.ep is not ep:
                m = musics[episode_id] = EpisodeMusic(ws, ep, library)
            return m

    def asset_or_404(asset_id: str) -> dict:
        try:
            return library.asset(asset_id)
        except KeyError:
            raise HTTPException(404, "no such asset")

    @app.get("/api/library")
    def library_view():
        from .editor import find_api_key, sdk_installed
        lookup = credit_client is not None or (bool(find_api_key()[0]) and sdk_installed())
        return library.view() | {"lookup": lookup}

    @app.post("/api/library/files")
    def library_add(body: LibraryFileBody):
        try:
            return {"asset": library.asset_view(library.add_file(body.path, body.kind, body.note.strip()))}
        except LibraryError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/library/scan")
    def library_scan():
        library.ensure_dirs()
        try:
            return {"added": library.scan()} | library.view() | {"lookup": credit_client is not None}
        except LibraryError as e:
            raise HTTPException(422, str(e))

    @app.patch("/api/library/assets/{asset_id}")
    def library_update(asset_id: str, body: AssetBody):
        try:
            return {"asset": library.asset_view(library.update(asset_id, note=body.note, kind=body.kind,
                                                               credit=body.credit, confirm=body.confirm))}
        except KeyError:
            raise HTTPException(404, "no such asset")
        except LibraryError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/library/assets/{asset_id}/lookup")
    def library_lookup(asset_id: str):
        asset_or_404(asset_id)
        out = lookup_credit(library, asset_id, client=credit_client)
        if out.get("usage"):
            log_usage(ws.root / USAGE_LOG, f"library:{asset_id}", out["usage"])
        return out

    @app.delete("/api/library/assets/{asset_id}")
    def library_remove(asset_id: str):
        asset_or_404(asset_id)
        library.remove(asset_id)
        return {"ok": True}

    @app.get("/api/library/assets/{asset_id}/audio")
    def library_audio(asset_id: str):
        a = asset_or_404(asset_id)
        try:
            p = library.path_of(a)
        except PathError:
            raise HTTPException(404, "file missing")
        if not p.is_file():
            raise HTTPException(404, "file missing")
        return FileResponse(p, headers={"Cache-Control": "private, max-age=3600"})

    @app.post("/api/library/open")
    def library_open():
        library.ensure_dirs()
        import os, subprocess, sys
        d = str(library.dir)
        if sys.platform == "win32":
            os.startfile(d)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"folder": d}

    @app.get("/api/episodes/{episode_id}/music")
    def music_view(episode_id: str):
        return music(episode_id).summary()

    def placement_fields(m: EpisodeMusic, body: PlacementBody) -> dict:
        f = body.model_dump(exclude_unset=True)
        for k in ("at_s", "until_s"):     # the UI speaks final-mix time; anchors live on the voice timeline
            if f.get(k) is not None:
                f[k] = m.final_to_voice_s(f[k])
        return f

    @app.post("/api/episodes/{episode_id}/music")
    def music_add(episode_id: str, body: PlacementBody):
        m = music(episode_id)
        if not body.asset_id or not body.role:
            raise HTTPException(422, "asset_id and role are required")
        asset_or_404(body.asset_id)
        f = placement_fields(m, body)
        f.pop("asset_id"), f.pop("role")
        m.add(body.asset_id, body.role, **{k: v for k, v in f.items() if v is not None})
        return m.summary()

    @app.patch("/api/episodes/{episode_id}/music/{pid}")
    def music_update(episode_id: str, pid: str, body: PlacementBody):
        m = music(episode_id)
        if body.asset_id:
            asset_or_404(body.asset_id)
        try:
            m.update(pid, **placement_fields(m, body))
        except KeyError:
            raise HTTPException(404, "no such placement")
        return m.summary()

    @app.delete("/api/episodes/{episode_id}/music/{pid}")
    def music_remove(episode_id: str, pid: str):
        m = music(episode_id)
        try:
            m.remove(pid)
        except KeyError:
            raise HTTPException(404, "no such placement")
        return m.summary()

    @app.get("/api/episodes/{episode_id}/music/{pid}/preview")
    def music_preview(episode_id: str, pid: str):
        try:
            wav, start = music(episode_id).preview(pid)
        except KeyError:
            raise HTTPException(404, "no such placement")
        return Response(wav, media_type="audio/wav", headers={"Cache-Control": "no-store", "X-Start": str(start)})

    @app.post("/api/episodes/{episode_id}/music/series/apply")
    def music_series_apply(episode_id: str, body: SeriesBody):
        m = music(episode_id)
        m.apply_series(body.name)
        return m.summary()

    @app.post("/api/episodes/{episode_id}/music/series/save")
    def music_series_save(episode_id: str, body: SeriesBody):
        m = music(episode_id)
        m.save_as_series(body.name)
        return m.summary()

    @app.post("/api/episodes/{episode_id}/music/series/dismiss")
    def music_series_dismiss(episode_id: str):
        m = music(episode_id)
        m.dismiss_series()
        return m.summary()

    @app.get("/api/episodes/{episode_id}/mix/{version}.wav")
    def mix_audio(episode_id: str, version: str, request: Request):
        m = music(episode_id)
        enabled = m.ep.enabled
        if version != m.mix_key(enabled):
            raise HTTPException(404, "unknown or expired version")
        total = m.wav_size(enabled)
        rng = parse_range(request.headers.get("range"), total)
        headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
        if request.headers.get("range") and rng is None:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        first, last = rng or (0, total - 1)
        headers["Content-Length"] = str(last - first + 1)
        if rng:
            headers["Content-Range"] = f"bytes {first}-{last}/{total}"
        return StreamingResponse(m.iter_wav(enabled, first, last), status_code=206 if rng else 200,
                                 media_type="audio/wav", headers=headers)

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
    app.state.importer = importer
    app.state.dictation = dictation
    app.state.library = library
    return app
