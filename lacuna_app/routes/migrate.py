"""Move the desktop workspace to the shared server (lacuna_app/migrate.py): /api/migrate*.

Cloud only, the owner only, into the main workspace only.
"""
from __future__ import annotations

import threading

from fastapi import HTTPException, Request
from pydantic import BaseModel

from .. import cloud, migrate, upload_parts
from ..auth import COOKIE
from ..exporter import Exporter
from ..i18n import tr
from ..importer import Importer

RESTART_EXIT = 76     # the container restarts; the app loads the moved workspace


class FinishBody(BaseModel):
    files: int
    bytes: int


def register(app, ctx) -> None:
    ws = ctx.ws
    if ws.root.parent.name == "spaces":       # another workspace's own app: never a migration target
        return

    def owner_only(request: Request) -> None:
        auth = ctx.provide("auth")
        if not cloud.enabled() or auth is None:
            raise HTTPException(404, "Not Found")
        email = auth.who(request.cookies.get(COOKIE))
        if not email or auth.role(email) != "owner":
            raise HTTPException(403, tr("只有所有者能改这项设置"))

    def busy() -> bool:
        importer = ctx.provide("importer", lambda: Importer(ws, models_dir=ctx.models_dir))
        exporter = ctx.provide("exporter", lambda: Exporter(ws))
        return bool(importer._running or exporter._running)

    @app.get("/api/migrate")
    def migrate_status(request: Request):
        owner_only(request)
        have = migrate.staged(ws)
        return {"staged": have, "episodes": len(ws.episode_ids())}

    @app.post("/api/migrate/file")
    async def migrate_file(request: Request, path: str, part: str = ""):
        owner_only(request)
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/octet-stream":
            raise HTTPException(415, "expected application/octet-stream")
        try:
            rel = migrate.clean_path(path)
        except migrate.MigrateError:
            raise HTTPException(422, tr("文件名不能用：{name}", name=path))
        if rel is None:
            return {"skipped": True}
        dst = migrate.target(ws, rel)
        tmp = dst.with_name(dst.name + ".uploading")
        try:
            with tmp.open("wb") as f:
                async for chunk in upload_parts.source(request, ws, part):
                    f.write(chunk)
            tmp.replace(dst)
        except upload_parts.PartError:
            tmp.unlink(missing_ok=True)
            raise HTTPException(422, tr("上传没有完成，请重新上传"))
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return {"size": dst.stat().st_size}

    @app.post("/api/migrate/finish")
    def migrate_finish(request: Request, body: FinishBody):
        owner_only(request)
        if busy():
            raise HTTPException(409, tr("还有导入或导出在进行，做完再搬。"))
        try:
            out = migrate.finish(ws, body.files, body.bytes)
        except migrate.NotAWorkspace:
            raise HTTPException(422, tr("这个文件夹里没有剧集也没有素材库。请选电脑上的 LACUNA_Workspace 文件夹。"))
        except migrate.MigrateError:
            raise HTTPException(422, tr("文件没有传全，请再点一次「开始搬」接着传。"))
        threading.Timer(0.5, lambda: app.state.restart(RESTART_EXIT)).start()
        return out | {"restarting": True}

    @app.post("/api/migrate/cancel")
    def migrate_cancel(request: Request):
        owner_only(request)
        migrate.cancel(ws)
        return {"ok": True}
