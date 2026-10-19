"""节目设置 (lacuna_app/show.py): GET / PUT /api/show, the current workspace's show profile."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .. import show


class HostBody(BaseModel):
    tag: str | None = Field(None, max_length=2)
    name: str = Field("", max_length=80)
    color: str | None = Field(None, max_length=20)
    cut_level: str | None = Field(None, max_length=20)
    style: str = Field("", max_length=1000)


class PublishBody(BaseModel):
    ximalaya: bool = False
    album: str = Field("", max_length=160)


class ShowBody(BaseModel):
    show_name: str = Field("", max_length=160)
    about: str = Field("", max_length=400)
    language: str = Field("zh", max_length=8)
    footer: str = Field("", max_length=1200)
    hosts: list[HostBody] = Field(default_factory=list, max_length=20)
    publish: PublishBody = Field(default_factory=PublishBody)


def register(app, ctx) -> None:
    @app.get("/api/show")
    def get_show():
        return show.view(show.load(ctx.ws.root))

    @app.put("/api/show")
    def put_show(body: ShowBody):
        try:
            return show.view(show.save(ctx.ws.root, body.model_dump()))
        except show.ShowError as e:
            raise HTTPException(400, str(e))
