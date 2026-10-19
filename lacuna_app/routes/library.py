"""Media library (phase 6a, D45/D48): upload, uses, credit lookup, scopes (公共 / 本集)."""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .. import upload_parts
from ..library import Library, LibraryError, lookup_credit
from ..store import PathError, check_id
from ..i18n import tr

MAX_UPLOAD = 4 * 1024 ** 3   # a 2-hour 48 kHz stereo WAV is ~1.4 GB


class AssetBody(BaseModel):
    note: str | None = Field(None, max_length=500)
    kind: str | None = Field(None, pattern="^(intro|outro|interlude|bed|dialogue|trailer|other)$")
    credit: dict | None = None
    confirm: bool = False


class ScopeBody(BaseModel):
    action: str = Field(pattern="^(move|share|add)$", description="move: this episode only; share: every episode; add: one more episode")
    episode: str | None = Field(None, max_length=120)


def library_of(ctx) -> Library:
    """Shared with the music module."""
    return ctx.provide("library", lambda: Library(ctx.ws))


def asset_or_404(library: Library, asset_id: str) -> dict:
    try:
        return library.asset(asset_id)
    except KeyError:
        raise HTTPException(404, "no such asset")


def register(app, ctx) -> None:
    library = library_of(ctx)
    credit_client = ctx.option("credit_client")

    def episode_or_404(episode_id: str) -> str:
        """An existing episode's id (400 malformed, 404 unknown)."""
        try:
            check_id(episode_id)
        except (PathError, ValueError):
            raise HTTPException(400, "invalid episode id")
        if episode_id not in ctx.ws.episode_ids():
            raise HTTPException(404, "no such episode")
        return episode_id

    def episodes() -> list[dict]:
        """The episodes an asset can belong to (titles for the scope labels and pickers)."""
        from .archive import archive_of
        index = ctx.provide("episode_index")
        rows = index.rows() if index is not None else [{"id": e, "title": e} for e in ctx.ws.episode_ids()]
        archived = archive_of(ctx).archived()
        return [{"id": r["id"], "title": r.get("title") or r["id"], "archived": r["id"] in archived} for r in rows]

    @app.get("/api/library")
    def library_view(episode: str | None = None):
        """`episode`: only what that episode's music page offers (shared + its own)."""
        from ..editor import find_api_key, sdk_installed
        if episode:
            episode_or_404(episode)
        lookup = credit_client is not None or (bool(find_api_key()[0]) and sdk_installed())
        return library.view(episode or None) | {"lookup": lookup, "episodes": episodes()}

    @app.post("/api/library/assets/{asset_id}/scope")
    def library_scope(asset_id: str, body: ScopeBody):
        """「挪到某一集」 (move) / 「设为公共」 (share) / 「也加到另一集」 (add)."""
        asset_or_404(library, asset_id)
        if body.action != "share":
            if not body.episode:
                raise HTTPException(422, "episode is required")
            episode_or_404(body.episode)
        try:
            if body.action == "move":
                a = library.move_to(asset_id, body.episode)
            elif body.action == "add":
                a = library.add_to_episode(asset_id, body.episode)
            else:
                a = library.make_shared(asset_id)
        except KeyError:
            raise HTTPException(404, "no such asset")
        message = None
        if body.action == "move" and len(a["episodes"]) > 1:
            titles = {e["id"]: e["title"] for e in episodes()}
            message = tr("{episodes} 的配乐已经用了它，所以那边也留着。",
                         episodes="、".join(titles.get(e, e) for e in a["episodes"][1:]))
        return {"asset": library.asset_view(a), "message": message}

    @app.post("/api/library/upload")
    async def library_upload(request: Request, name: str, kind: str = "other", note: str = "", episode: str = "",
                             part: str = ""):
        """A file dragged into (or picked in) the browser, raw bytes in the body. It is written
        straight into the library folder; nothing leaves this machine. The octet-stream type is
        required so another web page can't post here without the browser's CORS preflight."""
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/octet-stream":
            raise HTTPException(415, "expected application/octet-stream")
        if len(note) > 500:
            raise HTTPException(422, "note too long")
        if episode:          # added on an episode's music page, or into an episode on the library page
            episode_or_404(episode)
        try:
            target = library.upload_target(name, kind)
        except LibraryError as e:
            raise HTTPException(422, str(e))
        try:
            size = 0
            with target.open("wb") as f:
                async for chunk in upload_parts.source(request, ctx.ws, part):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, tr("文件太大"))
                    f.write(chunk)
            if not size:
                raise HTTPException(422, tr("文件是空的"))
            asset, duplicate = await run_in_threadpool(library.add_upload, target, kind, note.strip(),
                                                       episode or None)
        except HTTPException:
            target.unlink(missing_ok=True)
            raise
        except upload_parts.PartError:
            target.unlink(missing_ok=True)
            raise HTTPException(422, tr("上传没有完成，请重新上传"))
        except Exception as e:
            target.unlink(missing_ok=True)
            raise HTTPException(422, tr("读不了这个音频文件：{name}", name=name) if not isinstance(e, LibraryError) else str(e))
        return {"asset": library.asset_view(asset), "duplicate": duplicate}

    @app.post("/api/library/scan")
    def library_scan():
        library.ensure_dirs()
        try:
            return {"added": library.scan()} | library.view() | {"lookup": credit_client is not None}
        except LibraryError as e:
            raise HTTPException(422, str(e))

    @app.patch("/api/library/assets/{asset_id}")
    def library_update(asset_id: str, body: AssetBody):
        try:
            return {"asset": library.asset_view(library.update(asset_id, note=body.note, kind=body.kind,
                                                               credit=body.credit, confirm=body.confirm))}
        except KeyError:
            raise HTTPException(404, "no such asset")
        except LibraryError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/library/assets/{asset_id}/lookup")
    def library_lookup(asset_id: str):
        asset_or_404(library, asset_id)
        out = lookup_credit(library, asset_id, client=credit_client)
        if out.get("usage"):
            ctx.log_usage(f"library:{asset_id}", out["usage"])
        return out

    @app.delete("/api/library/assets/{asset_id}")
    def library_remove(asset_id: str):
        asset_or_404(library, asset_id)
        library.remove(asset_id)
        return {"ok": True}

    @app.get("/api/library/assets/{asset_id}/audio")
    def library_audio(asset_id: str):
        a = asset_or_404(library, asset_id)
        try:
            p = library.path_of(a)
        except PathError:
            raise HTTPException(404, "file missing")
        if not p.is_file():
            raise HTTPException(404, "file missing")
        return FileResponse(p, headers={"Cache-Control": "private, max-age=3600"})

    @app.post("/api/library/open")
    def library_open():
        library.ensure_dirs()
        import os, subprocess, sys
        d = str(library.dir)
        if sys.platform == "win32":
            os.startfile(d)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"folder": d}
