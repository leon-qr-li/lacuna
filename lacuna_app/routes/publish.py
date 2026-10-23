"""Publish pack (phase 9, D46): title, blurb, show notes, chapters, name check."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..editor import editor_status
from ..episode import Episode
from ..publish import PublishBusy, Publisher
from ..i18n import tr


class PublishEditBody(BaseModel):
    markdown: str | None = Field(None, max_length=200_000, description="Leon's Markdown; null = back to generated")
    title: str | None = Field(None, max_length=200)
    rev: int | None = Field(None, description="the pack version the page showed; stale -> 409 (coedit.py)")


class LevelBody(BaseModel):
    level: str = Field(pattern="^(lean|std|full)$", description="how detailed the timeline is")
    rev: int | None = Field(None, description="the pack version the page showed; stale -> 409 (coedit.py)")


class NameBody(BaseModel):
    heard: str = Field(min_length=1, max_length=200)
    action: str = Field(pattern="^(apply|ignore)$")


def publisher_of(ctx) -> Publisher:
    """Shared with the cover module, which builds on the publish pack."""
    pub = ctx.provide("publisher", lambda: Publisher(ctx.ws))
    pub.on_usage = lambda eid, u: ctx.log_usage(eid, u | {"kind": "publish"})
    return pub


def register(app, ctx) -> None:
    get = ctx.get
    publisher = publisher_of(ctx)

    def publish_view(ep: Episode) -> dict:
        return publisher.view(ep) | editor_status(ctx.adapter)

    @app.get("/api/episodes/{episode_id}/publish")
    def publish_get(episode_id: str):
        return publish_view(get(episode_id))

    @app.post("/api/episodes/{episode_id}/publish/generate")
    def publish_generate(episode_id: str):
        ep = get(episode_id)
        try:
            publisher.start(ep)
        except PublishBusy as e:
            raise HTTPException(409, str(e))
        return publish_view(ep)

    def publish_change(ep: Episode, fn) -> dict:
        try:
            fn()
        except KeyError:
            raise HTTPException(404, tr("还没有生成发布资料"))
        return publish_view(ep)

    @app.post("/api/episodes/{episode_id}/publish/retime")
    def publish_retime(episode_id: str):
        ep = get(episode_id)
        return publish_change(ep, lambda: publisher.retime(ep))

    @app.put("/api/episodes/{episode_id}/publish")
    def publish_edit(episode_id: str, body: PublishEditBody):
        ep = get(episode_id)
        return publish_change(ep, lambda: publisher.edit(ep, body.markdown, body.title, body.rev))

    @app.put("/api/episodes/{episode_id}/publish/level")
    def publish_level(episode_id: str, body: LevelBody):
        ep = get(episode_id)
        return publish_change(ep, lambda: publisher.set_level(ep, body.level, body.rev))

    @app.post("/api/episodes/{episode_id}/publish/names")
    def publish_name(episode_id: str, body: NameBody):
        ep = get(episode_id)
        return publish_change(ep, lambda: publisher.name(ep, body.heard, body.action))
