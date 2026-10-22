"""入门 (new-user batch, Leon 2026-10-22, recommended C + A): the welcome page, the 入门清单 and LACUNA 示例节目.

Progress is kept per person in the site database (meta ``onboard:<email>``), so it follows them to another
computer or browser. The interface ticks a step when the real thing happened (the first download, three edits
looked at …): steps of the person's own first episode are plain names (STEPS), steps done in the sample show
start with ``sample.``. Someone who already has episodes when they first get here (Leon, Pei) starts with the
guide hidden. Collaborators (no show of their own) get the short version: review, then listen.

The sample show (lacuna_app/sample.py) is a show of its own, marked in the site database, that no plan counts.
"""
from __future__ import annotations

import json
import re

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import sample
from ..auth import COOKIE, Auth
from ..i18n import tr
from ..spaces import Spaces
from .spaces import SPACE_COOKIE

STEPS = ("show", "import", "review", "chat", "music", "export")
COLLAB_STEPS = ("review", "chat")
SAMPLE_STEPS = ("ab", "decide", "chat", "music", "export")
# a step, or "card.<show id>": that show's 节目资料卡 put away (C6)
STEP = re.compile(r"^((sample\.)?[a-z]{2,12}|card\.[a-z0-9_]{2,24})$")


class MarkBody(BaseModel):
    step: str


class FlagsBody(BaseModel):
    hidden: bool | None = None
    welcomed: bool | None = None


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
        rec = {"done": [], "hidden": veteran, "welcomed": veteran}
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
        steps = COLLAB_STEPS if collab else STEPS
        return {"done": rec["done"], "hidden": rec["hidden"], "welcomed": rec["welcomed"],
                "steps": list(steps), "sample_steps": list(SAMPLE_STEPS), "collab": collab,
                "sample": {"id": sid, "lang": spaces.sample(sid), "episode": sample.EPISODE} if sid else None}

    @app.get("/api/onboarding")
    def get(request: Request):
        return view(me(request))

    @app.post("/api/onboarding/mark")
    def mark(body: MarkBody, request: Request):
        email = me(request)
        if not STEP.match(body.step):
            raise HTTPException(422, tr("没有这一步"))
        rec = record(email)
        if body.step not in rec["done"]:
            rec["done"].append(body.step)
            save(email, rec)
        return view(email)

    @app.put("/api/onboarding")
    def flags(body: FlagsBody, request: Request):
        email = me(request)
        rec = record(email)
        if body.hidden is not None:
            rec["hidden"] = body.hidden
        if body.welcomed is not None:
            rec["welcomed"] = body.welcomed
        save(email, rec)
        return view(email)

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
        rec = record(email)
        rec["done"] = [s for s in rec["done"] if not s.startswith("sample.")]
        save(email, rec)
        return into(email, sid)

    @app.delete("/api/onboarding/sample")
    def drop_sample(request: Request):
        """删除示例节目 (it can be added again from 设置)."""
        email = me(request)
        sid = spaces.sample_of(email)
        if sid:
            _drop_child(sid)
            spaces.delete(sid)
        return view(email)

    def _drop_child(sid: str) -> None:
        """A show's app caches its open episodes: forget it so the next request reads the fresh files."""
        children = getattr(app.state, "space_apps", None)
        if isinstance(children, dict):
            children.pop(sid, None)
