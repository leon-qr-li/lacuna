"""Episode naming per album (naming.py): the album's format, a preview of renaming its episodes, and the
rename itself (only when the user asks, from 专辑设置)."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .. import naming
from ..albums import Albums
from ..i18n import tr


class NamingBody(BaseModel):
    preset: str | None = Field(None, max_length=20)     # None / "": no format
    before: str = Field("", max_length=naming.MAX_PART)
    between: str = Field("", max_length=naming.MAX_PART)
    after: str = Field("", max_length=naming.MAX_PART)


def register(app, ctx) -> None:
    def albums() -> Albums:
        return ctx.provide("albums") or Albums(ctx.ws)

    def checked(body: NamingBody) -> dict | None:
        try:
            return naming.clean(body.model_dump())
        except naming.NamingError as e:
            raise HTTPException(422, str(e))

    def album(album_id: str) -> dict:
        a = next((x for x in albums().albums() if x["id"] == album_id), None)
        if a is None:
            raise HTTPException(404, tr("没有这个专辑"))
        return a

    def plan(album_id: str, fmt: dict | None) -> list[dict]:
        """Each episode of the album whose title the format changes: {"id", "before", "after"}."""
        out = []
        saved = album(album_id).get("naming")
        for eid in albums().episodes_of(album_id):
            try:
                old = str(ctx.peek(eid).meta.get("title") or eid)
            except HTTPException:
                continue
            new = naming.title(fmt, eid, naming.bare(eid, old, saved) if fmt else old)
            if fmt and new != old:
                out.append({"id": eid, "before": old, "after": new})
        return out

    @app.put("/api/albums/{album_id}/naming")
    def set_naming(album_id: str, body: NamingBody):
        fmt = checked(body)
        a = albums()
        with a.lock:
            doc = a.load()
            x = next((x for x in doc["albums"] if x["id"] == album_id), None)
            if x is None:
                raise HTTPException(404, tr("没有这个专辑"))
            if fmt:
                x["naming"] = fmt
            else:
                x.pop("naming", None)
            a.save(doc)
        return {"naming": fmt}

    @app.post("/api/albums/{album_id}/naming/preview")
    def preview_naming(album_id: str, body: NamingBody):
        """What 「把已有的剧集也改名」 would do with this format (nothing changes)."""
        album(album_id)
        return {"renames": plan(album_id, checked(body))}

    @app.post("/api/albums/{album_id}/naming/apply")
    def apply_naming(album_id: str):
        """Rename the album's episodes to its saved format."""
        fmt = album(album_id).get("naming")
        if not fmt:
            raise HTTPException(422, tr("这个专辑还没有设命名格式"))
        done = []
        for r in plan(album_id, fmt):
            try:
                ctx.peek(r["id"]).set_title(r["after"])
                done.append(r)
            except (HTTPException, OSError):
                continue
        return {"renamed": done}
