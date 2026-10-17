"""Mastered export (D36): WAV + MP3 into <workspace>/exports/<episode>/."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..episode import ConflictError
from ..exporter import ExportBusy, Exporter
from ..music import EpisodeMusic
from ..store import PathError


class ExportBody(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["mp3", "wav"], min_length=1)
    mp3_kbps: int = Field(128, ge=64, le=320)
    channels: int = Field(2, ge=1, le=2)


def register(app, ctx) -> None:
    get = ctx.get
    exporter = ctx.provide("exporter", lambda: Exporter(ctx.ws))

    @app.post("/api/episodes/{episode_id}/export")
    def start_export(episode_id: str, body: ExportBody):
        ep = get(episode_id)
        try:
            return {"job": exporter.start(ep, body.formats, body.mp3_kbps, body.channels)}
        except ExportBusy as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            if isinstance(e, ConflictError):
                raise
            raise HTTPException(422, str(e))

    @app.get("/api/episodes/{episode_id}/export")
    def export_status(episode_id: str):
        ep = get(episode_id)
        job = exporter.status(episode_id)
        if job and job.get("music_version"):     # the music changed after this export
            job["music_stale"] = job["music_version"] != EpisodeMusic(ctx.ws, ep).export_key()
        return {"job": job}

    @app.get("/api/episodes/{episode_id}/exports/{name}")
    def export_file(episode_id: str, name: str):
        get(episode_id)
        try:
            path = exporter.file_path(episode_id, name)
        except (PathError, FileNotFoundError):
            raise HTTPException(404, "no such export file")
        # ASCII fallback first, then the UTF-8 name (episode ids are often Chinese)
        ascii_name = path.name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
        disp = f"attachment; filename=\"{ascii_name}\"; filename*=utf-8''{quote(path.name)}"
        return FileResponse(path, headers={"Content-Disposition": disp})

    @app.post("/api/episodes/{episode_id}/exports/open")
    def open_exports(episode_id: str):
        get(episode_id)
        return {"folder": exporter.open_folder(episode_id)}
