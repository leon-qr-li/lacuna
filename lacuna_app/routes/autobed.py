"""自动铺底 (docs/decisions/2026-10-30-auto-bed.md): the songs the 配乐 page can bed with, and a random fill of the
free stretches as a suggestion (lacuna_app/autobed.py)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .. import autobed
from ..music import EpisodeMusic
from .library import library_of


class FillBody(BaseModel):
    asset_ids: list[str] = Field(max_length=200)
    seed: int | None = None


def register(app, ctx) -> None:
    library = library_of(ctx)

    def music(episode_id: str) -> EpisodeMusic:
        return EpisodeMusic(ctx.ws, ctx.get(episode_id), library)

    @app.get("/api/episodes/{episode_id}/music/autobed")
    def autobed_view(episode_id: str):
        return autobed.view(music(episode_id))

    @app.post("/api/episodes/{episode_id}/music/autobed")
    def autobed_fill(episode_id: str, body: FillBody):
        m = music(episode_id)
        out = autobed.suggest(m, body.asset_ids, body.seed)
        return m.summary() | {"message": out["message"]}
