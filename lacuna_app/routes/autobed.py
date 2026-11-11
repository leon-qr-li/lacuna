"""自动铺底 (docs/decisions/2026-10-30-auto-bed.md): the songs the 配乐 page can bed with, and a random fill of the
free stretches, put straight onto the episode (lacuna_app/autobed.py)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .. import autobed
from ..i18n import tr
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
        out = autobed.fill(m, body.asset_ids, body.seed)
        return m.summary() | out

    @app.delete("/api/episodes/{episode_id}/music/autobed")
    def autobed_clear(episode_id: str):
        m = music(episode_id)
        n = autobed.clear(m)
        return m.summary() | {"removed": n, "message": tr("取消了 {n} 段铺底。", n=n)}
