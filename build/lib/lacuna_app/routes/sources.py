"""``POST /api/episodes/{id}/sources``: upload a recording the episode is missing (lacuna_app/sources.py)."""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from soundfile import LibsndfileError

from .. import sources, upload_parts
from ..i18n import tr
from ..import_tracks import MAX_TRACK
from ..store import PathError


def register(app, ctx) -> None:
    ws, get = ctx.ws, ctx.get

    @app.exception_handler(LibsndfileError)
    async def _unreadable(_req, exc: LibsndfileError):
        # a recording that can't be opened (gone, damaged): say so instead of a bare 500
        return JSONResponse({"detail": tr("读不了这一集的原始音轨。请在这一集页面顶上重新上传原始音轨。")}, status_code=409)

    @app.post("/api/episodes/{episode_id}/sources")
    async def upload_source(episode_id: str, request: Request, name: str, part: str = ""):
        # octet-stream only, so no other web page can post here without the browser's CORS preflight
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/octet-stream":
            raise HTTPException(415, "expected application/octet-stream")
        ep = get(episode_id)
        if not ep.missing_sources():
            raise HTTPException(409, tr("这一集的原始音轨都在，不用再上传。"))

        async def capped():
            size = 0
            async for chunk in upload_parts.source(request, ws, part):
                size += len(chunk)
                if size > MAX_TRACK:
                    raise HTTPException(413, tr("文件太大"))
                yield chunk
        try:
            filled = await sources.receive(ep, name, capped())
        except sources.NotMissing:
            raise HTTPException(422, tr("{name} 不是这一集缺的原始音轨（内容对不上）。请选当初导入这一集用的那个文件。", name=name))
        except PathError:
            raise HTTPException(422, tr("不是音频文件：{name}", name=name))
        except upload_parts.PartError:
            raise HTTPException(422, tr("上传没有完成，请重新上传"))
        return {"filled": filled, "episode": ep.summary()}
