"""套餐与用量 (lacuna_app/plans.py): ``GET /api/plan``, the signed-in person's plan, its limits and what they use.

Audio hours are counted from batch 5 on (quota.py): ``hours`` says what this account used this month (the
trial: ever), its allowance with the extra hours it got, and what is left.
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from .. import plans
from ..auth import COOKIE
from ..i18n import tr


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return

    @app.get("/api/plan")
    def my_plan(request: Request):
        auth, spaces = app.state.auth, getattr(app.state, "spaces", None)
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        u = auth.users[email]
        plan = u.get("plan") or plans.DEFAULT
        made = [sid for sid in (spaces.spaces if spaces else {}) if spaces.creator(sid) == email]
        meter = ctx.provide("meter")
        hours = meter.account(email) if meter is not None and meter.on else None
        return {"plan": plan, "free": bool(u.get("plan_free")), "limits": next(x for x in plans.public() if x["id"] == plan),
                "shows": len(made), "hours_used": hours["used"] if hours else None, "hours": hours,
                "collaborators": [{"id": sid, "name": spaces.title(sid), "count": spaces.collaborators(sid)}
                                  for sid in made],
                "plans": plans.public()}
