"""「新成员需站长批准」 (new-user batch, Leon 2026-10-22): while it is on (beta), a show admin who invites
someone without an account sends a 搭档申请 to the site owner instead of an invite (routes/spaces.py,
routes/auth_requests.py). The owner turns it off at public launch; then a show admin's invite goes out at once,
within the plan's collaborator seats. Only the owner changes it; every change is in the event log.
"""
from __future__ import annotations

from fastapi import HTTPException, Request
from pydantic import BaseModel

from ..auth import COOKIE, Auth
from ..i18n import tr

KEY = "owner_approval"


class SwitchBody(BaseModel):
    on: bool


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth: Auth = ctx.provide("auth")

    def on() -> bool:
        return auth.db.meta(KEY) != "0"          # on unless the owner turned it off

    app.state.owner_approval = on
    auth.beta = on                               # invite mails carry the BETA plan card while it is on

    def owner(request: Request) -> str:
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        if auth.role(email) != "owner":
            raise HTTPException(403, tr("只有站长能改这个设置"))
        return email

    @app.get("/api/site/new-members")
    def get(request: Request):
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        return {"approval": on()}

    @app.put("/api/site/new-members")
    def put(body: SwitchBody, request: Request):
        owner(request)
        auth.db.set_meta(KEY, "1" if body.on else "0")      # the event log notes it (routes/events.py RULES)
        return {"approval": on()}
