"""The sample tour's before / after (new-user batch, bubble tour): the first 30 seconds of the recording as it
was, and the same stretch of the current cut. Any episode works; only the tour asks for it."""
from __future__ import annotations

from fastapi import HTTPException, Query

from .. import sample

RAW_S = 30.0


def register(app, ctx) -> None:
    get = ctx.get

    @app.get("/api/episodes/{episode_id}/tour/raw")
    def raw_and_cut(episode_id: str, s: float = Query(RAW_S, gt=0, le=60)):
        ep = get(episode_id)
        with ep.lock:
            return ep.ab(frozenset(), ep.enabled, (0, 0), ctx_s=s, max_s=s)

    @app.get("/api/episodes/{episode_id}/tour/marks")
    def marks(episode_id: str):
        out = sample.tour_marks(get(episode_id))
        if out is None:
            raise HTTPException(404, "not the sample episode")
        return out
