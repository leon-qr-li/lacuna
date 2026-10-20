"""剪辑习惯 (lacuna_app/habits.py): GET / PUT /api/habits, the signed-in editor's own 剪辑力度, used in every
project. Answered by the main app for whoever is signed in (routes/spaces.py lists it as global)."""
from __future__ import annotations

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .. import habits
from ..auth import COOKIE
from ..i18n import tr


class HabitsBody(BaseModel):
    cut_level: str = Field(pattern="^(gentle|normal|firm)$")


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return

    def home(request: Request):
        auth = ctx.provide("auth")
        if auth is None or not auth.has_accounts():
            return ctx.ws.root
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        return habits.home_for(ctx.ws.root, email)

    @app.get("/api/habits")
    def get_habits(request: Request):
        return {"cut_level": habits.level(home(request)), "levels": list(habits.LEVELS)}

    @app.put("/api/habits")
    def put_habits(body: HabitsBody, request: Request):
        habits.set_level(home(request), body.cut_level)
        return get_habits(request)
