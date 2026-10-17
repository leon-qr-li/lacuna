"""Core: health, episodes, streamed audio, edits, review, manual ops, undo/redo, chat proposals."""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..audio import parse_range
from ..dictation import Dictation
from ..editor import editor_status
from ..chat_learning import remember_text
from ..episode import ConflictError
from ..episode_index import EpisodeIndex


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


class OpBody(PlayheadBody):
    op: dict
    title: str = Field("手动修改", max_length=200)
    reason: str = Field("", max_length=2000)


def register(app, ctx) -> None:
    ws, adapter, get, mutate = ctx.ws, ctx.adapter, ctx.get, ctx.mutate
    dictation = ctx.provide("dictation", lambda: Dictation(ws.root / "models"))
    index = ctx.provide("episode_index", lambda: EpisodeIndex(ws, ctx.loaded, ctx.peek))

    @app.get("/api/health")
    def health():
        return {"ok": True, "workspace": str(ws.root)} | editor_status(adapter) | dictation.status()

    @app.get("/api/episodes")
    def list_episodes():
        return {"episodes": index.rows()} | editor_status(adapter)

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
        if (ask := remember_text(body.text)) is not None:      # "记住：……" -> a candidate rule, no AI call
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
    ctx.provide("chat_learner").asks.remember(ep.id, ask, playhead)   # built by routes/learning.py
    reply = f"记下了：「{ask}」。它在「学到的规则」里等你确认，采用后从下一期的 AI 初剪开始照做。"
    ep.log_turn(f"记住：{ask}", playhead, reply, remember=True)
    return {"reply": reply, "notes": [], "adapter": "remember", "proposal": None, "usage": None}
