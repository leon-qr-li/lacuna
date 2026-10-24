"""入门 (new-user batch, Leon 2026-10-22): the welcome page and LACUNA 示例节目 with its bubble tour.

The tour on first login is the only guide (Leon 2026-10-24): the 入门清单 and 节目资料卡 that followed it on the
show's home are gone. What is kept per person, in the site database (meta ``onboard:<email>``, so it follows them
to another computer or browser): whether they got past the welcome page and where the tour is. Someone who
already has episodes when they first get here (Leon, Pei) skips the welcome page; so do collaborators (no show
of their own).

The sample show (lacuna_app/sample.py) is a show of its own, marked in the site database, that no plan counts.
"""
from __future__ import annotations

import json

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import sample
from ..auth import COOKIE, Auth
from ..i18n import tr
from ..spaces import Spaces
from .spaces import SPACE_COOKIE

class FlagsBody(BaseModel):
    welcomed: bool | None = None
    tour: str | None = Field(None, pattern=r"^(~?[a-z0-9]{1,12}|)$")   # where the sample tour is ("~step" = paused there, "" = finished)


class SampleBody(BaseModel):
    lang: str = "en"


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth: Auth = ctx.provide("auth")
    spaces: Spaces = ctx.provide("spaces", lambda: Spaces(ctx.ws.root))
    root = ctx.ws.root

    def me(request: Request) -> str:
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        return email

    def key(email: str) -> str:
        return f"onboard:{email}"

    def record(email: str) -> dict:
        raw = auth.db.meta(key(email))
        if raw:
            try:
                return json.loads(raw)
            except ValueError:
                pass
        mine = [m for m in spaces.mine(email, detail=True) if not m["sample"] and not m["support"]]
        veteran = any(m["episodes"] for m in mine)
        rec = {"welcomed": veteran}
        save(email, rec)
        return rec

    def save(email: str, rec: dict) -> None:
        auth.db.set_meta(key(email), json.dumps(rec, ensure_ascii=False))

    def view(email: str) -> dict:
        rec = record(email)
        own = [sid for sid, s in spaces.spaces.items()
               if spaces.creator(sid) == email and not spaces.sample(sid)]
        collab = None
        if not own:
            joined = [sid for sid, s in spaces.spaces.items() if email in s["members"] and not spaces.sample(sid)]
            if joined:
                sid = joined[0]
                by = (spaces.spaces[sid].get("added_by") or {}).get(email) or spaces.creator(sid)
                collab = {"show": spaces.title(sid), "by": auth.name(by) or (by or "").split("@")[0]}
        sid = spaces.sample_of(email)
        return {"welcomed": rec["welcomed"], "tour": rec.get("tour"), "collab": collab,
                "sample": {"id": sid, "lang": spaces.sample(sid), "episode": sample.EPISODE} if sid else None}

    @app.get("/api/onboarding")
    def get(request: Request):
        return view(me(request))

    @app.put("/api/onboarding")
    def flags(body: FlagsBody, request: Request):
        email = me(request)
        rec = record(email)
        if body.welcomed is not None:
            rec["welcomed"] = body.welcomed
        if body.tour is not None:
            rec["tour"] = body.tour
        save(email, rec)
        return view(email)

    def forget_tour(email: str) -> None:
        """The tour's place goes with the sample it was made in."""
        rec = record(email)
        rec.pop("done", None)   # the old 入门清单's ticks (before 2026-10-24)
        rec["tour"] = None
        save(email, rec)

    def into(email: str, sid: str) -> JSONResponse:
        res = JSONResponse(view(email))
        res.set_cookie(SPACE_COOKIE, sid, max_age=365 * 86400, httponly=True, samesite="strict", path="/",
                       secure=auth.cloud)
        return res

    @app.post("/api/onboarding/sample")
    def add_sample(body: SampleBody, request: Request):
        """先用示例集试一遍: their sample show (made the first time), and they are moved into it."""
        email = me(request)
        sid = spaces.sample_of(email)
        if not sid:
            lang = body.lang if body.lang in sample.LANGS else "en"
            made = spaces.create(sample.NAME[lang], email, sample=lang)
            sid = made["id"]
            try:
                sample.give(root, spaces.path(sid), lang)
            except Exception:
                spaces.delete(sid)
                raise
            # a new sample starts the tour from step 1, whatever an earlier (deleted) sample left behind
            forget_tour(email)
            # its own folder: the child app for it is made on first use
        return into(email, sid)

    @app.post("/api/onboarding/sample/reset")
    def reset_sample(request: Request):
        """重置示例: the episode as the first cut left it; the coach starts over."""
        email = me(request)
        sid = spaces.sample_of(email)
        if not sid:
            raise HTTPException(404, tr("你还没有示例节目"))
        _drop_child(sid)
        sample.reset(root, spaces.path(sid), spaces.sample(sid))
        forget_tour(email)
        return into(email, sid)

    @app.delete("/api/onboarding/sample")
    def drop_sample(request: Request):
        """删除示例节目 (it can be added again from 设置)."""
        email = me(request)
        sid = spaces.sample_of(email)
        if sid:
            _drop_child(sid)
            spaces.delete(sid)
            forget_tour(email)
        return view(email)

    def forget_person(email: str) -> None:
        """An account was deleted: its sample show and its 入门 progress go too, so the same email invited
        again starts as a new person (new sample, tour from step 1) instead of finding the old ones."""
        sid = spaces.sample_of(email)
        if sid:
            _drop_child(sid)
            spaces.delete(sid)
        auth.db.set_meta(key(email), "")

    auth.on_deleted.append(forget_person)

    def sweep_departed() -> None:
        """Accounts deleted before forget_person existed (2026-10-23) left their sample show and 入门 progress
        behind; the same email invited again found them. Cleared at start (only samples and progress)."""
        if not auth.users:
            return
        for sid in [sid for sid in list(spaces.spaces) if spaces.sample(sid) and spaces.creator(sid) not in auth.users]:
            spaces.delete(sid)
        for r in auth.db.query("SELECT key FROM meta WHERE key LIKE 'onboard:%' AND value != ''"):
            if r["key"].split(":", 1)[1] not in auth.users:
                auth.db.set_meta(r["key"], "")

    sweep_departed()

    def _drop_child(sid: str) -> None:
        """A show's app caches its open episodes: forget it so the next request reads the fresh files."""
        children = getattr(app.state, "space_apps", None)
        if isinstance(children, dict):
            children.pop(sid, None)
