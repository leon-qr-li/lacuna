"""English um / uh (decision `english-fillers`): list them, take them all out in one undoable step."""
from __future__ import annotations

from pydantic import Field

from .. import fillers
from ..events import note
from .episodes import PlayheadBody


class CutBody(PlayheadBody):
    tracks: list[str] | None = Field(None, max_length=20, description="only these hosts' fillers; None = every host")


def register(app, ctx) -> None:
    get, mutate = ctx.get, ctx.mutate

    @app.get("/api/episodes/{episode_id}/fillers")
    def listing(episode_id: str):
        ep = get(episode_id)
        fillers.backfill(ep)
        return fillers.listing(ep)

    @app.post("/api/episodes/{episode_id}/fillers/cut")
    def cut(episode_id: str, body: CutBody):
        ep = get(episode_id)
        def go():
            n = len(fillers.cut(ep, body.tracks))
            note(n=n)
            return {"cut": n}
        return mutate(ep, body.playhead, go)
