"""Cover (phase 10, D49): Claude draws SVG covers from the publish pack, rendered locally."""
from __future__ import annotations

import re

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..episode import Episode
from ..poster import PosterBusy, PosterError, Posters
from .publish import publisher_of
from ..i18n import tr


class PosterReviseBody(BaseModel):
    instruction: str = Field(min_length=1, max_length=500, description="Leon's change, e.g. 换成暖色")  # i18n-ignore


def register(app, ctx) -> None:
    get = ctx.get
    posters = ctx.provide("posters", lambda: Posters(ctx.ws, publisher_of(ctx)))
    posters.on_usage = lambda eid, u: ctx.log_usage(eid, u | {"kind": "poster"})

    def poster_job(ep: Episode, fn) -> dict:
        try:
            fn()
        except PosterBusy as e:
            raise HTTPException(409, str(e))
        except PosterError as e:
            raise HTTPException(400, str(e))
        except KeyError:
            raise HTTPException(404, tr("没有这一版封面"))
        return posters.view(ep)

    @app.get("/api/episodes/{episode_id}/poster")
    def poster_get(episode_id: str):
        return posters.view(get(episode_id))

    @app.post("/api/episodes/{episode_id}/poster/generate")
    def poster_generate(episode_id: str):
        ep = get(episode_id)
        return poster_job(ep, lambda: posters.generate(ep))

    @app.post("/api/episodes/{episode_id}/poster/{variant}/revise")
    def poster_revise(episode_id: str, variant: str, body: PosterReviseBody):
        ep = get(episode_id)
        return poster_job(ep, lambda: posters.revise(ep, variant, body.instruction))

    @app.post("/api/episodes/{episode_id}/poster/{variant}/choose")
    def poster_choose(episode_id: str, variant: str):
        ep = get(episode_id)
        return poster_job(ep, lambda: posters.choose(ep, variant))

    @app.get("/api/episodes/{episode_id}/poster/{variant}.png")
    def poster_preview(episode_id: str, variant: str):
        ep = get(episode_id)
        if not re.fullmatch(r"v\d+", variant):
            raise HTTPException(404)
        try:
            path = posters.preview(ep, variant)
        except KeyError:
            raise HTTPException(404, tr("没有这一版封面"))
        except PosterError as e:
            raise HTTPException(500, str(e))
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
