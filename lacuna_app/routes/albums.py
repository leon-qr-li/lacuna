"""Albums (lacuna_app/albums.py): /api/albums*, an episode's album, the project's default opener / ending."""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..albums import MAX_COVER, AlbumError, Albums
from ..library import Library
from ..store import PathError, check_id
from ..i18n import tr

AID = Field(None, max_length=40)


class AlbumBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    about: str = Field("", max_length=400)
    intro: str | None = AID          # asset id of the default opener; None / "" = the project's
    outro: str | None = AID
    episodes: list[str] = Field(default_factory=list, max_length=500)


class AlbumPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    about: str | None = Field(None, max_length=400)
    intro: str | None = AID          # "" = back to the project's; None = unchanged
    outro: str | None = AID


class ProjectMusicBody(BaseModel):
    intro: str | None = AID          # "" = none; None = unchanged
    outro: str | None = AID


class EpisodeAlbumBody(BaseModel):
    album: str | None = Field(None, max_length=40)     # None: no album


def register(app, ctx) -> None:
    albums = ctx.provide("albums", lambda: Albums(ctx.ws))

    def run(fn):
        try:
            return fn()
        except AlbumError as e:
            raise HTTPException(e.status, str(e))
        except PathError:
            raise HTTPException(400, "invalid id")

    def library() -> Library:
        return ctx.provide("library") or Library(ctx.ws)

    def pick(asset_id: str | None) -> dict | None:
        """An asset id from a form as a template: None unchanged, "" none, else the asset (404 if unknown)."""
        if asset_id is None:
            return None
        if not asset_id:
            return {}
        try:
            library().asset(asset_id)
        except KeyError:
            raise HTTPException(404, "no such asset")
        return {"asset_id": asset_id}

    def view() -> dict:
        doc = albums.load()
        live = set(ctx.ws.episode_ids())
        names = {a["id"]: a["name"] for a in library().assets()}

        def music(pair: dict) -> dict:
            return {r: ({"asset_id": t["asset_id"], "name": names.get(t["asset_id"])} if (t := pair.get(r)) else None)
                    for r in ("intro", "outro")}

        rows = []
        for a in doc["albums"]:
            eps = sorted(e for e, x in doc["episodes"].items() if x == a["id"] and e in live)
            rows.append({"id": a["id"], "name": a["name"], "about": a.get("about") or "", "created": a["created"],
                         "cover_url": f"/api/albums/{a['id']}/cover?v={a['cover']}" if a.get("cover") else None,
                         "episodes": eps, "naming": a.get("naming"), **music(a)})
        return {"albums": rows, "episodes": {e: x for e, x in doc["episodes"].items() if e in live},
                "project": music(doc["project"])}

    @app.get("/api/albums")
    def list_albums():
        return view()

    @app.post("/api/albums")
    def create_album(body: AlbumBody):
        live = set(ctx.ws.episode_ids())
        if any(e not in live for e in body.episodes):
            raise HTTPException(404, tr("这一集不存在，可能已经删除了"))
        a = run(lambda: albums.create(body.name, body.about, pick(body.intro) or None, pick(body.outro) or None,
                                      body.episodes))
        return view() | {"created": a["id"]}

    @app.patch("/api/albums/project")
    def project_music(body: ProjectMusicBody):
        run(lambda: albums.set_project(intro=pick(body.intro), outro=pick(body.outro)))
        return view()

    @app.patch("/api/albums/{album_id}")
    def update_album(album_id: str, body: AlbumPatch):
        run(lambda: albums.update(album_id, name=body.name, about=body.about, intro=pick(body.intro),
                                  outro=pick(body.outro)))
        return view()

    @app.delete("/api/albums/{album_id}")
    def delete_album(album_id: str):
        """The album goes; its episodes stay (in no album) and its own media belong to the whole project."""
        moved = run(lambda: albums.remove(album_id))
        library().drop_album(album_id)
        return view() | {"moved": moved}

    @app.post("/api/albums/{album_id}/cover")
    async def album_cover(album_id: str, request: Request):
        """A cover image picked in the browser: the raw bytes, image/png, image/jpeg or image/webp."""
        ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > MAX_COVER:
                raise HTTPException(413, tr("封面图片太大（最多 10 MB）"))
        run(lambda: albums.set_cover(album_id, bytes(data), ctype))
        return view()

    @app.get("/api/albums/{album_id}/cover")
    def album_cover_file(album_id: str):
        p = run(lambda: albums.cover_path(album_id))
        if p is None:
            raise HTTPException(404, "no cover")
        return FileResponse(p, headers={"Cache-Control": "private, max-age=86400"})

    @app.post("/api/episodes/{episode_id}/album")
    def episode_album(episode_id: str, body: EpisodeAlbumBody):
        """「移到专辑」: music already placed stays as it is."""
        try:
            check_id(episode_id)
        except PathError:
            raise HTTPException(400, "invalid episode id")
        if episode_id not in ctx.ws.episode_ids():
            raise HTTPException(404, tr("这一集不存在，可能已经删除了"))
        run(lambda: albums.assign(episode_id, body.album))
        return view()
