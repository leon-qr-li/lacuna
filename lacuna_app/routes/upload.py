"""上传喜马拉雅 (phase 11): one checklist of what is ready to upload by hand, plus the cover download."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse

from ..upload import checklist, cover_path, save_cover
from ..i18n import tr


def register(app, ctx) -> None:
    # publish, poster and export register before this module (name order) and build these services
    def services():
        return ctx.provide("publisher"), ctx.provide("posters"), ctx.provide("exporter")

    @app.get("/api/episodes/{episode_id}/upload")
    def upload_get(episode_id: str):
        ep = ctx.get(episode_id)
        publisher, posters, exporter = services()
        from ..music import EpisodeMusic
        return checklist(ep, exporter.dir_for(ep.id), publisher.view(ep), posters.load(ep),
                         EpisodeMusic(ctx.ws, ep).export_key())

    def chosen_cover(ep):
        _, posters, _ = services()
        try:
            return cover_path(posters.load(ep), posters.cover_dir(ep.id))
        except FileNotFoundError:
            raise HTTPException(404, tr("还没选封面"))

    @app.post("/api/episodes/{episode_id}/upload/save-cover")
    def upload_save_cover(episode_id: str):
        """「下载封面」 also drops the cover into the episode's export folder, next to the audio."""
        ep = ctx.get(episode_id)
        _, _, exporter = services()
        try:
            out = save_cover(chosen_cover(ep), exporter.dir_for(ep.id), ep.id)
        except OSError as e:
            raise HTTPException(500, str(e))
        return {"path": str(out), "folder": str(out.parent), "name": out.name}

    @app.get("/api/episodes/{episode_id}/upload/cover.jpg")
    def upload_cover(episode_id: str):
        ep = ctx.get(episode_id)
        path = chosen_cover(ep)
        name = f"{ep.id}_cover.jpg"
        ascii_name = name.encode("ascii", "replace").decode().replace("?", "_")
        disp = f"attachment; filename=\"{ascii_name}\"; filename*=utf-8''{quote(name)}"
        return FileResponse(path, media_type="image/jpeg", headers={"Content-Disposition": disp})
