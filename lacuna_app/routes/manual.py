"""Manual editing (decision `manual-editing`): waveform tiles, the transcript of a stretch, cut a selection."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .. import manual
from .episodes import PlayheadBody


class CutBody(PlayheadBody):
    start: float = Field(ge=0, description="timeline seconds")
    end: float = Field(ge=0)
    track: str | None = Field(None, max_length=200, description="one host's track only (silence it there); "
                                                                "None removes the stretch from every track")


def register(app, ctx) -> None:
    get, mutate = ctx.get, ctx.mutate

    @app.get("/api/episodes/{episode_id}/manual/wave")
    def wave(episode_id: str, tile: int, v: str | None = None):
        if not 0 <= tile < 100_000:
            raise HTTPException(422, "bad tile")
        try:
            return manual.wave(get(episode_id), v, tile)
        except KeyError:
            raise HTTPException(404, "no such version")

    @app.get("/api/episodes/{episode_id}/manual/words")
    def words(episode_id: str, t0: float, t1: float, v: str | None = None):
        if t1 < t0 or t1 - t0 > 600:
            raise HTTPException(422, "bad range")
        try:
            return {"utterances": manual.words(get(episode_id), v, t0, t1)}
        except KeyError:
            raise HTTPException(404, "no such version")

    @app.post("/api/episodes/{episode_id}/manual/cut")
    def cut(episode_id: str, body: CutBody):
        if body.end <= body.start:
            raise HTTPException(422, "end must be after start")
        ep = get(episode_id)
        return mutate(ep, body.playhead, lambda: {"edit_id": manual.cut(ep, body.start, body.end, body.track)})
