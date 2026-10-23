"""``POST /api/uploads/parts``: one piece of a big file (lacuna_app/upload_parts.py)."""
from __future__ import annotations

from fastapi import HTTPException, Request

from .. import upload_parts


def register(app, ctx) -> None:
    ws = ctx.ws

    @app.post("/api/uploads/parts")
    async def upload_piece(request: Request, id: str, offset: int = 0):
        # octet-stream only, so no other web page can post here without the browser's CORS preflight
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/octet-stream":
            raise HTTPException(415, "expected application/octet-stream")
        try:
            return {"size": await upload_parts.write_piece(ws, id, offset, request.stream())}
        except upload_parts.PartError as e:
            raise HTTPException(422, str(e))
