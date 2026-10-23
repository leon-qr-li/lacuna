"""System terms (decision `transcript-terms`): GET for everyone signed in, PUT for the site owner / admins.
Under /api/app/ so the main app answers whatever workspace the person is in (routes/spaces.py GLOBAL)."""
from __future__ import annotations

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .. import system_terms
from ..auth import COOKIE, RANK
from ..i18n import tr


class TermsBody(BaseModel):
    terms: list[str] = Field(max_length=system_terms.MAX_TERMS * 2)


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth = ctx.provide("auth")
    root = ctx.ws.root

    def admin(request: Request) -> tuple[bool, str | None]:
        """(may change the list, who). Before the first account exists (a desktop install) anyone may."""
        if not auth.has_accounts():
            return True, None
        email = auth.who(request.cookies.get(COOKIE))
        return bool(email) and RANK.get(auth.role(email) or "", 0) >= RANK["admin"], email

    @app.get("/api/app/terms")
    def get_terms(request: Request):
        return {"terms": system_terms.load(root), "can_edit": admin(request)[0]}

    @app.put("/api/app/terms")
    def put_terms(request: Request, body: TermsBody):
        ok, email = admin(request)
        if not ok:
            raise HTTPException(403, tr("只有站长和站点管理员能改系统专有名词"))
        return {"terms": system_terms.save(root, body.terms, email), "can_edit": True}
