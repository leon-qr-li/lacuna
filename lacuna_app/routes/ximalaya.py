"""「喜马拉雅版」 show notes (backlog item 26): the publish pack in three layouts for the 喜马拉雅 editor."""
from __future__ import annotations

import traceback

from fastapi import HTTPException
from fastapi.responses import FileResponse

from .. import ximalaya
from ..cloud import server_path
from ..publish import episode_label
from ..store import inside
from .publish import publisher_of
from ..i18n import tr


def register(app, ctx) -> None:
    get = ctx.get
    publisher = publisher_of(ctx)

    def folder(episode_id: str):
        return inside(ctx.ws.root, "exports", episode_id, "publish", "ximalaya")

    @app.get("/api/episodes/{episode_id}/publish/ximalaya")
    def ximalaya_get(episode_id: str):
        ep = get(episode_id)
        view = publisher.view(ep)
        pack = view["pack"]
        if pack is None:
            return {"styles": None, "dir": None, "stale": False, "notes": []}
        notes = []
        try:
            styles = ximalaya.build(pack["markdown"], episode_label(ep.id), folder(ep.id))
        except Exception:      # noqa: BLE001 - no images is still a usable 喜马拉雅版
            traceback.print_exc()
            styles = ximalaya.build(pack["markdown"], episode_label(ep.id))
            notes.append(tr("设计图没画出来，「图文」这一版先用纯文字。"))
        return {"styles": styles, "dir": server_path(folder(ep.id)), "stale": pack["stale"], "notes": notes}

    @app.get("/api/episodes/{episode_id}/publish/ximalaya/{name}")
    def ximalaya_image(episode_id: str, name: str):
        get(episode_id)
        if name not in ximalaya.IMAGES:
            raise HTTPException(404, "unknown image")
        path = folder(episode_id) / name
        if not path.is_file():
            raise HTTPException(404, tr("这张图还没有生成"))
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-cache"})
