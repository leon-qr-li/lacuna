"""Core: health, episodes, streamed audio, edits, review, manual ops, undo/redo, chat proposals."""
from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..audio import parse_range
from ..dictation import Dictation
from ..editor import editor_status
from ..chat_learning import remember_text
from ..episode import ConflictError
from ..episode_index import EpisodeIndex
from ..levels import chat_volume
from .. import sample
from ..store import POSTER_FILE, read_json
from .archive import archive_of


class PlayheadBody(BaseModel):
    playhead: float | None = Field(None, ge=0, description="seconds on the timeline the client is playing")


class ReviewBody(PlayheadBody):
    action: str = Field(pattern="^(keep|restore|apply)$")
    rev: int | None = Field(None, description="the episode version the page showed (coedit.py); stale -> 409")


class BatchReviewBody(PlayheadBody):
    action: str = Field(pattern="^(approve|keep|restore)$")
    rev: int | None = Field(None, description="the episode version the page showed (coedit.py); stale -> 409")
    ids: list[str] | None = Field(None, max_length=5000, description="defaults to every edit still pending review")


class ChatBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    playhead: float = Field(ge=0)


class OpBody(PlayheadBody):
    op: dict
    title: str = Field("手动修改", max_length=200)  # i18n-ignore
    reason: str = Field("", max_length=2000)


def register(app, ctx) -> None:
    ws, adapter, get, mutate = ctx.ws, ctx.adapter, ctx.get, ctx.mutate
    dictation = ctx.provide("dictation", lambda: Dictation(ctx.models_dir))
    index = ctx.provide("episode_index", lambda: EpisodeIndex(ws, ctx.loaded, ctx.peek))

    @app.get("/api/health")
    def health():
        return {"ok": True, "workspace": str(ws.root)} | editor_status(adapter) | dictation.status()

    def poster_url(eid: str) -> str | None:
        """The chosen cover's preview (routes/poster.py) for the episode's tile, or None (no cover chosen)."""
        try:
            f = ws.episode_dir(eid) / POSTER_FILE
            chosen = read_json(f).get("chosen") if f.is_file() else None
            if not (isinstance(chosen, str) and re.fullmatch(r"v\d+", chosen)):
                return None
            return f"/api/episodes/{quote(eid)}/poster/{chosen}.png?v={f.stat().st_mtime_ns}"
        except Exception:        # noqa: BLE001 - a bad poster file only costs the tile its picture
            return None

    def exported(eid: str) -> bool:
        """Whether the episode was ever exported: the tile's status stripe (batch 7, T3)."""
        try:
            return any((ws.root / "exports" / eid).glob("*.json"))
        except OSError:
            return False

    @app.get("/api/episodes")
    def list_episodes():
        hidden = archive_of(ctx).archived()     # archived episodes live on the 已归档 page
        rows = [r | {"poster": poster_url(r["id"]), "exported": exported(r["id"])}
                for r in index.rows() if r["id"] not in hidden]
        return {"episodes": rows, "archived": len(hidden)} | editor_status(adapter)

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
        ep.previewer      # recordings missing: a clear 409 now, not a stream cut off after its headers
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

        def run():
            with ep.lock:
                ep.check_fresh([eid], body.rev)
                ep.review(eid, body.action)
        return mutate(ep, body.playhead, run)

    @app.post("/api/episodes/{episode_id}/review")
    def review_batch(episode_id: str, body: BatchReviewBody):
        ep = get(episode_id)

        def run():
            with ep.lock:
                ep.check_fresh(body.ids if body.ids is not None else ep.pending_ids(), body.rev)
                return {"changed": ep.review_all(body.action, body.ids)}
        return mutate(ep, body.playhead, run)

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
        if (out := chat_volume(get(episode_id), body.text, body.playhead)) is not None:   # "我的声音太低", no AI call
            return out
        if (out := sample.tour_chat(get(episode_id), body.text, body.playhead)) is not None:   # the tour's line, scripted
            return out
        if (ask := remember_text(body.text)) is not None:      # "记住：……" -> a draft rule to confirm
            return remember(ctx, get(episode_id), ask, body.playhead)
        out = get(episode_id).chat(body.text, body.playhead, adapter)
        if out.get("usage"):
            ctx.log_usage(episode_id, out["usage"])
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


def remember(ctx, ep, ask: str, playhead: float) -> dict:
    """LACUNA's reading of what Leon asked to remember, as a draft he confirms; nothing is stored as a rule yet."""
    draft = ctx.provide("lessons").remember(ep, ask, playhead)    # built by routes/lessons.py
    return {"reply": "", "notes": [], "adapter": "remember", "proposal": None, "usage": None, "remember": draft}
