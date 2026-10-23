"""节目设置 (lacuna_app/show.py): GET / PUT /api/show, the current workspace's show profile."""
from __future__ import annotations

import threading

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .. import show
from ..coedit import StaleError
from ..i18n import tr


class HostBody(BaseModel):
    tag: str | None = Field(None, max_length=2)
    name: str = Field("", max_length=80)
    color: str | None = Field(None, max_length=20)
    cut_level: str | None = Field(None, max_length=20)      # before per-editor levels; read as an adjust
    cut_adjust: str | None = Field(None, max_length=10)     # 更狠 / 一样 / 更松 (habits.py)
    style: str = Field("", max_length=1000)


class PublishBody(BaseModel):
    ximalaya: bool = False
    album: str = Field("", max_length=160)
    platforms: list[str] | None = Field(None, max_length=20)   # left out = keep the stored ones
    auto_wish: list[str] | None = Field(None, max_length=20)   # 自动发布 wishes; left out = keep the stored ones


class ShowBody(BaseModel):
    show_name: str = Field("", max_length=160)
    about: str = Field("", max_length=400)
    language: str = Field("zh", max_length=8)
    footer: str = Field("", max_length=1200)
    hosts: list[HostBody] = Field(default_factory=list, max_length=20)
    publish: PublishBody = Field(default_factory=PublishBody)
    terms: list[str] | None = Field(None, max_length=200)    # 专有名词; left out = keep the stored ones
    rev: int | None = None          # the version the page showed; someone saved since -> 409 (coedit.py)


def register(app, ctx) -> None:
    lock = threading.Lock()

    @app.get("/api/show")
    def get_show():
        return show.view(show.load(ctx.ws.root))

    @app.put("/api/show")
    def put_show(body: ShowBody):
        try:
            data = body.model_dump()
            if body.terms is None:
                data.pop("terms")
            seen = data.pop("rev")
            with lock:
                now = show.load(ctx.ws.root)
                if seen is not None and seen != now.get("rev", 0):
                    raise StaleError(tr("{name} 刚刚修改了节目设置。页面已更新为最新内容，你的本次修改未保存，请在最新内容上重新修改。",
                                        name=now.get("by_name") or tr("其他成员")))
                return show.view(show.save(ctx.ws.root, data))
        except show.ShowError as e:
            raise HTTPException(400, str(e))
