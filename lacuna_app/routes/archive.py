"""Archiving episodes (首检 #3): archive / restore / delete for good. See lacuna_app/archive.py."""
from __future__ import annotations

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from ..archive import Archive, ArchiveError
from ..learning import Learning
from ..i18n import tr


def archive_of(ctx) -> Archive:
    """Shared with routes/episodes.py, which leaves archived episodes out of the 剧集 list."""
    return ctx.provide("archive", lambda: Archive(ctx.ws))


def register(app, ctx) -> None:
    archive = archive_of(ctx)
    archive.empty_trash()

    def known(episode_id: str) -> None:
        ctx.peek(episode_id)          # 400 bad id / 404 no such episode

    @app.get("/api/archive")
    def archived_list():
        marks = archive.archived()
        rows = [r | {"archived_at": marks[r["id"]]["at"]} for r in ctx.provide("episode_index").rows()
                if r["id"] in marks]
        return {"episodes": sorted(rows, key=lambda r: r["archived_at"], reverse=True)}

    @app.post("/api/episodes/{episode_id}/archive")
    def archive_episode(episode_id: str):
        known(episode_id)
        return {"archived": episode_id} | archive.archive(episode_id)

    @app.post("/api/episodes/{episode_id}/restore")
    def restore_episode(episode_id: str):
        known(episode_id)
        try:
            archive.restore(episode_id)
        except KeyError:
            raise HTTPException(409, tr("这一集没有归档"))
        return {"restored": episode_id}

    def busy(episode_id: str) -> str | None:
        imp = ctx.provide("importer")
        j = imp.status(episode_id) if imp else None
        if j and j.get("state") in ("queued", "running"):
            return tr("这一集正在导入，等它做完或取消后再删")
        exp = ctx.provide("exporter")
        j = exp.status(episode_id) if exp else None
        if j and j.get("state") == "running":
            return tr("这一集正在导出，等它做完再删")
        return None

    def keep_learning(episode_id: str) -> None:
        # the review verdicts 「学到的规则」 learns from, snapshotted before the folder goes
        ctx.provide("learning", lambda: Learning(ctx.ws)).overview([ctx.peek(episode_id)])

    def release(episode_id: str) -> None:
        with ctx.lock:
            ctx.episodes.pop(episode_id, None)
            ctx._alive.pop(episode_id, None)
        imp = ctx.provide("importer")
        if imp is not None:
            imp.drop(episode_id)

    @app.delete("/api/episodes/{episode_id}")
    async def delete_episode(episode_id: str):
        known(episode_id)
        if not archive.is_archived(episode_id):
            raise HTTPException(409, tr("先归档，才能永久删除"))
        try:
            return await run_in_threadpool(archive.delete, episode_id, release=release,
                                           keep_learning=keep_learning, busy=busy)
        except ArchiveError as e:
            raise HTTPException(409, str(e))
        except KeyError:
            raise HTTPException(404, "no such episode")
