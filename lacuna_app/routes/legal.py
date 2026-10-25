"""用户条款和隐私政策 (lacuna_app/legal.py): POST /api/auth/agree, the 「条款已更新」 screen's 同意并继续.

The current version and the one the person agreed to come with /api/auth/status (`legal`). Creating an account
records the agreement itself (routes/auth.py register).
"""
from __future__ import annotations

from fastapi import HTTPException, Request
from pydantic import BaseModel

from ..auth import COOKIE, Auth, AuthError
from ..i18n import tr


class AgreeBody(BaseModel):
    version: str


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth: Auth = ctx.provide("auth")

    @app.post("/api/auth/agree")
    def agree(body: AgreeBody, request: Request):
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        try:
            auth.agree(email, body.version)
        except AuthError as e:
            raise HTTPException(e.status, str(e))
        return {"ok": True, "agreed": body.version}
