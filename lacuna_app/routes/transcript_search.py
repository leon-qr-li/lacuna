"""逐字稿搜索 (lacuna_app/transcript_search.py): the places a text is said in an episode's current version."""
from __future__ import annotations

from fastapi import HTTPException

from .. import transcript_search


def register(app, ctx) -> None:
    get = ctx.get

    @app.get("/api/episodes/{episode_id}/transcript/search")
    def search(episode_id: str, q: str, v: str | None = None):
        try:
            return transcript_search.search(get(episode_id), v, q)
        except KeyError:
            raise HTTPException(404, "no such version")
