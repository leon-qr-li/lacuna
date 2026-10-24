"""站内公告 and 维护模式, set in the admin (decision 2026-10-24-admin-site), seen on the main site.

``GET /api/site/notice`` (signed in): the notice in the person's language while it is on (until its date), and
whether maintenance is on. While maintenance is on, starting a new upload or import answers 503 with
「正在维护…」; what already runs finishes (the middleware sits outside the workspace dispatcher, so it sees every
show's requests, and inside the cloud gate).
"""
from __future__ import annotations

import json
import re
import time

from fastapi import HTTPException, Request

from ..auth import COOKIE, Auth
from ..i18n import lang, tr

# new work that maintenance pauses: uploads and imports (resume included); everything else keeps working
PAUSED = [("POST", re.compile(p)) for p in (r"^/api/imports$", r"^/api/imports/tracks$", r"^/api/imports/[^/]+/resume$",
                                              r"^/api/uploads/parts$", r"^/api/library/upload$")]


def _setting(auth: Auth, key: str, default):
    raw = auth.db.meta(f"admin:{key}")
    try:
        return json.loads(raw) if raw else default
    except ValueError:
        return default


class _Pause:
    def __init__(self, app, auth: Auth):
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and any(m == scope["method"] and rx.match(scope["path"]) for m, rx in PAUSED) \
                and _setting(self.auth, "maintenance", {}).get("on"):
            from fastapi.responses import JSONResponse
            return await JSONResponse({"detail": tr("正在维护，几分钟后再试。已经在跑的任务不受影响。"), "maintenance": True},
                                      status_code=503)(scope, receive, send)
        return await self.app(scope, receive, send)


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth: Auth = ctx.provide("auth")
    # just inside the cloud gate (people reach maintenance only once they are let in), still outside the
    # workspace dispatcher (routes/spaces.py) so every show's uploads pause
    from starlette.middleware import Middleware
    stack = app.user_middleware
    gate = next((i for i, m in enumerate(stack) if m.cls.__name__ == "CloudGate"), -1)
    stack.insert(gate + 1, Middleware(_Pause, auth=auth))

    @app.get("/api/site/notice")
    def notice(request: Request):
        if not auth.who(request.cookies.get(COOKIE)):
            raise HTTPException(401, tr("请先登录"))
        n = _setting(auth, "notice", {})
        text = (n.get("en") if lang() == "en" else n.get("zh")) or n.get("zh") or n.get("en") or ""
        until = n.get("until")
        live = bool(n.get("on") and text and (not until or time.strftime("%Y-%m-%d", time.gmtime(auth.now())) <= until))
        return {"notice": {"text": text, "at": n.get("at")} if live else None,
                "maintenance": bool(_setting(auth, "maintenance", {}).get("on"))}
