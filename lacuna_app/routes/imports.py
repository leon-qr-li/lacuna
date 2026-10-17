"""New-episode import (phase 4, D41): local ASR → features → Claude first cut → review."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..importer import ImportBusy, ImportError_, Importer, list_dir
from ..server import next_episode_id


class ImportBody(BaseModel):
    id: str = Field(min_length=1, max_length=120, description="episode id = folder name, e.g. EP002")
    title: str = Field("", max_length=200)
    leon: str = Field(min_length=1, max_length=2000, description="path of Leon's raw track")
    pei: str = Field(min_length=1, max_length=2000, description="path of Pei's raw track")


def register(app, ctx) -> None:
    ws = ctx.ws
    importer = ctx.provide("importer", lambda: Importer(ws))

    @app.get("/api/fs")
    def browse(path: str | None = None):
        try:
            return list_dir(path, ws.root)
        except ImportError_ as e:
            raise HTTPException(404, str(e))

    @app.get("/api/imports")
    def imports():
        return {"jobs": importer.status(), "next_id": next_episode_id(ws.episode_ids() + [j["id"] for j in importer.status()])}

    @app.post("/api/imports")
    def start_import(body: ImportBody):
        try:
            return {"job": importer.start(body.id.strip(), body.title, body.leon, body.pei)}
        except ImportBusy as e:
            raise HTTPException(409, str(e))
        except ImportError_ as e:
            raise HTTPException(422, str(e))

    @app.get("/api/imports/{episode_id}")
    def import_status(episode_id: str):
        j = importer.status(episode_id)
        if j is None:
            raise HTTPException(404, "no such import")
        return {"job": j}

    @app.post("/api/imports/{episode_id}/resume")
    def resume_import(episode_id: str):
        try:
            return {"job": importer.resume(episode_id)}
        except KeyError:
            raise HTTPException(404, "no such import")
        except ImportBusy as e:
            raise HTTPException(409, str(e))

    @app.post("/api/imports/{episode_id}/cancel")
    def cancel_import(episode_id: str):
        try:
            importer.cancel(episode_id)
        except KeyError:
            raise HTTPException(409, "这一集没有在导入")
        return {"job": importer.status(episode_id)}

    @app.delete("/api/imports/{episode_id}")
    def forget_import(episode_id: str):
        try:
            importer.forget(episode_id)
        except KeyError:
            raise HTTPException(404, "no such import")
        except ImportBusy as e:
            raise HTTPException(409, str(e))
        return {"ok": True}
