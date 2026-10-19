"""Chat voice input (D43): recorded audio → text, decoded on this machine, then a context pass that
fixes homophones and names (dictation_fix.py; only text leaves the machine)."""
from __future__ import annotations

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..dictation import Dictation, DictationError
from .. import show
from ..dictation_fix import DictationFixer, FixContext
from ..episode import to_base
from ..publish import load_names
from ..store import PUBLISH_FILE, read_json

TRANSCRIPT_RADIUS_S = 40.0
CHAT_TURNS = 6
MAX_TERMS = 40


def fix_context(ws, ep, at: float | None, where: str) -> FixContext:
    corrections = load_names(ws)
    profile = show.load(ws.root)
    ctx = FixContext(where=where, corrections=[{"wrong": c["wrong"], "right": c["right"]} for c in corrections],
                     show=profile["show_name"])
    names = show.host_names(profile) + [c["right"] for c in corrections]
    if ep is None:
        ctx.names = list(dict.fromkeys(names))
        return ctx
    if ep.transcript:
        names += list(ep.transcript.get("tracks", {}))      # this episode's hosts (maybe since renamed)
    ctx.names = list(dict.fromkeys(names))
    ctx.episode_title = str(ep.meta.get("title") or "")
    try:
        pack = read_json(ep.dir / PUBLISH_FILE) if (ep.dir / PUBLISH_FILE).is_file() else {}
        draft = pack.get("draft") or pack
        ctx.terms = list(dict.fromkeys(
            [f["name"] for f in draft.get("films") or [] if f.get("name")]
            + [g["term"] for g in draft.get("glossary") or [] if g.get("term")]
            + [str(s) for s in draft.get("shows") or [] if s]))[:MAX_TERMS]
    except (OSError, ValueError, AttributeError, TypeError, KeyError):
        pass
    with ep.lock:
        if at is not None and ep.transcript:
            cuts = ep.cuts_for(ep.enabled)
            ctx.transcript = ep.transcript_text(to_base(int(max(at, 0.0) * ep.sr), cuts) / ep.sr,
                                                TRANSCRIPT_RADIUS_S)
        ctx.chat = [t["said"] for t in ep.chat_history()[-CHAT_TURNS:]]
    return ctx


def register(app, ctx) -> None:
    dictation = ctx.provide("dictation", lambda: Dictation(ctx.models_dir))
    fixer = ctx.provide("dictation_fixer", DictationFixer)

    @app.post("/api/dictation/warm")
    def dictation_warm():
        dictation.warm()
        return {"ok": True}

    def heard(data: bytes, episode: str | None, at: float | None, where: str) -> dict:
        out = dictation.transcribe(data)
        raw = out["text"]
        if not raw or not fixer.available:
            return out | {"raw": raw, "corrected": False}
        try:
            fctx = fix_context(ctx.ws, ctx.peek(episode) if episode else None, at, where)
        except Exception:       # noqa: BLE001 - no episode context is still better than no dictation
            fctx = fix_context(ctx.ws, None, None, where)
        fixed = fixer.fix(raw, fctx)
        return out | {"text": fixed["text"], "raw": raw, "corrected": fixed["corrected"],
                      "fix_seconds": fixed["seconds"]}

    @app.post("/api/dictation")
    async def dictate(request: Request, episode: str | None = None, at: float | None = None, where: str = "chat"):
        """Raw recorded audio in the body (any format ffmpeg reads) → text. The audio stays on this
        machine; `episode` / `at` (playhead seconds) / `where` give the correction pass its context."""
        data = await request.body()
        where = where if where in ("chat", "poster") else "chat"
        try:
            return await run_in_threadpool(heard, data, episode, at, where)
        except DictationError as e:
            raise HTTPException(422, str(e))
