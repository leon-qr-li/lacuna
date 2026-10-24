"""New-episode import (phase 4, D41): local ASR → features → Claude first cut → review."""
from __future__ import annotations

from typing import Annotated

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .. import import_tracks, upload_parts
from ..archive import free_deleted_ids
from ..importer import ImportBusy, ImportError_, Importer, check_track
from ..server import next_episode_id
from ..store import META_FILE, PathError, read_json
from ..i18n import tr


class TrackBody(BaseModel):
    path: str = Field(min_length=1, max_length=2000)


class ImportBody(BaseModel):
    id: str = Field(min_length=1, max_length=120, description="episode id = folder name, e.g. EP002")
    title: str = Field("", max_length=200)
    tracks: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        min_length=1, max_length=6, description="path of each host's raw track, in the show's host order")
    language: str | None = Field(None, max_length=8, description="what the hosts speak (zh / en); default: the show's")
    album: str | None = Field(None, max_length=40, description="the album the new episode goes into (albums.py); none by default")


def register(app, ctx) -> None:
    ws = ctx.ws
    importer = ctx.provide("importer", lambda: Importer(ws, models_dir=ctx.models_dir))

    def tracks_in_use() -> list[str]:
        paths = importer.track_paths()
        for eid in ws.episode_ids():
            try:
                paths += list((read_json(ws.episode_dir(eid) / META_FILE).get("raw_tracks") or {}).values())
            except (OSError, ValueError, PathError):
                continue
        return paths

    import_tracks.prune(ws, tracks_in_use())

    @app.post("/api/imports/tracks")
    async def upload_track(request: Request, name: str, part: str = ""):
        """A raw track dragged into (or picked in) the import form: the raw bytes, copied into the
        workspace (import_tracks.py). Octet-stream only, so no other web page can post here without
        the browser's CORS preflight."""
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/octet-stream":
            raise HTTPException(415, "expected application/octet-stream")
        from ..importer import AUDIO_EXT
        from pathlib import Path
        if Path(name).suffix.lower() not in AUDIO_EXT:
            raise HTTPException(422, tr("不是音频文件：{name}", name=name))
        try:
            import_tracks.prune(ws, tracks_in_use())       # copies from forms nobody finished
        except OSError:
            pass
        try:
            target = import_tracks.new_target(ws, name)
        except PathError:
            raise HTTPException(422, tr("不是音频文件：{name}", name=name))
        size = 0
        try:
            if part:            # sent in pieces: move the finished file into place (no second copy)
                try:
                    size = upload_parts.take(ws, part, target, import_tracks.MAX_TRACK)
                except upload_parts.PartError as e:
                    if str(e) == "too big":
                        raise HTTPException(413, tr("文件太大"))
                    raise
            else:
                with target.open("wb") as f:
                    async for chunk in upload_parts.source(request, ws, part):
                        size += len(chunk)
                        if size > import_tracks.MAX_TRACK:
                            raise HTTPException(413, tr("文件太大"))
                        f.write(chunk)
            if not size:
                raise HTTPException(422, tr("文件是空的"))
            return {"track": check_track(target)}
        except upload_parts.PartError:
            import_tracks.remove(ws, target)
            raise HTTPException(422, tr("上传没有完成，请重新上传"))
        except BaseException:
            import_tracks.remove(ws, target)
            raise

    @app.post("/api/imports/tracks/remove")
    def remove_track(body: TrackBody):
        """The form let go of a copied track (replaced or cancelled); only copies are ever removed."""
        if body.path in tracks_in_use():
            return {"removed": False}
        return {"removed": import_tracks.remove(ws, body.path)}

    @app.get("/api/imports")
    def imports():
        try:
            free_deleted_ids(ws)
        except OSError:
            pass
        return {"jobs": importer.status(), "next_id": next_episode_id(ws.episode_ids() + [j["id"] for j in importer.status()])}

    @app.post("/api/imports")
    def start_import(body: ImportBody):
        from ..cloud import enabled as cloud_enabled
        # on the shared server a track is always an upload: never read a path on the server itself
        if cloud_enabled() and not all(import_tracks.owned(ws, p) for p in body.tracks):
            raise HTTPException(422, tr("请先上传音轨"))
        from ..albums import AlbumError, Albums
        albums = Albums(ws)
        if body.album and not any(a["id"] == body.album for a in albums.albums()):
            raise HTTPException(422, tr("没有这个专辑"))
        try:
            job = importer.start(body.id.strip(), body.title, body.tracks, language=body.language)
            try:
                albums.assign(body.id.strip(), body.album or None)
            except (AlbumError, PathError, OSError):
                pass        # the episode just lands in no album
            return {"job": job}
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
            raise HTTPException(409, tr("这一集没有在导入"))
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
