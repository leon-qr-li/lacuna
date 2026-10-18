"""Voice levels (backlog 7): measured loudness, per-track gain, 「统一两人音量」 (lacuna_app/levels.py)."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .. import levels
from ..i18n import tr


class GainBody(BaseModel):
    gain_db: float | None = Field(None, ge=levels.GAIN_MIN, le=levels.GAIN_MAX, description="absolute track gain")
    delta_db: float | None = Field(None, ge=-24, le=24, description="change from the current gain")
    playhead: float | None = Field(None, ge=0)


class AutoBody(BaseModel):
    playhead: float | None = Field(None, ge=0)


def register(app, ctx) -> None:
    get, mutate = ctx.get, ctx.mutate

    @app.get("/api/episodes/{episode_id}/levels")
    def levels_view(episode_id: str):
        return levels.view(get(episode_id))

    @app.post("/api/episodes/{episode_id}/levels/auto")
    def levels_auto(episode_id: str, body: AutoBody):
        ep = get(episode_id)
        return mutate(ep, body.playhead, lambda: {"changed": levels.auto_level(ep)}) | {
            "levels": levels.view(ep)}

    @app.post("/api/episodes/{episode_id}/levels/{track}")
    def levels_set(episode_id: str, track: str, body: GainBody):
        ep = get(episode_id)
        if track not in levels.voice_tracks(ep):
            raise HTTPException(404, tr("没有这条音轨：{track}", track=track))
        if (body.gain_db is None) == (body.delta_db is None):
            raise HTTPException(422, "give gain_db or delta_db")
        g = body.gain_db if body.gain_db is not None else levels.current_gains(ep).get(track, 0.0) + body.delta_db
        return mutate(ep, body.playhead, lambda: {"changed": levels.set_gains(ep, {track: g})}) | {
            "levels": levels.view(ep)}
