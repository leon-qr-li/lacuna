"""The episode's name (episode_name.py): read it, and rename from the episode page, the home card or the
publish page. A rename also becomes the publish pack's title, so the episode has one name everywhere."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .. import episode_name
from .publish import publisher_of


class NameBody(BaseModel):
    name: str = Field("", max_length=200, description="the name part; \"\" = back to only the number")


def register(app, ctx) -> None:
    publisher = publisher_of(ctx)

    @app.get("/api/episodes/{episode_id}/name")
    def get_name(episode_id: str):
        return episode_name.view(ctx.ws, ctx.peek(episode_id))

    @app.put("/api/episodes/{episode_id}/name")
    def set_name(episode_id: str, body: NameBody):
        ep = ctx.peek(episode_id)
        out = episode_name.rename(ctx.ws, ep, body.name)
        if out["short"]:
            try:
                publisher.edit(ep, title=out["short"])
            except KeyError:          # no publish pack yet: it starts from this name when written
                pass
        return out
