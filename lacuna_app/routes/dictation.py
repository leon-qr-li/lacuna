"""Chat voice input (D43): recorded audio → text, decoded on this machine."""
from __future__ import annotations

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..dictation import Dictation, DictationError


def register(app, ctx) -> None:
    dictation = ctx.provide("dictation", lambda: Dictation(ctx.ws.root / "models"))

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
