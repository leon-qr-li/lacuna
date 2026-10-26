"""回收区 (lacuna_app/trash.py): deleted shows and accounts, kept 60 days; LACUNA's owner and admins list them
and bring them back (decision 2026-10-24-deleted-kept-60-days). Under /api/site/ (one list for the whole site)."""
from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request

from ..auth import COOKIE, Auth, AuthError
from ..i18n import tr
from ..spaces import Spaces
from ..trash import TrashError

SWEEP_S = 6 * 3600


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth: Auth = ctx.provide("auth")
    spaces: Spaces = ctx.provide("spaces", lambda: Spaces(ctx.ws.root))
    trash = spaces.trash

    # an account about to be deleted: keep it, and the shows it was in, for 60 days
    auth.on_deleting.append(lambda email, rec, by: trash.put_user(email, rec, spaces.memberships(email), by))

    trash.purge()

    def sweep():
        while True:
            time.sleep(SWEEP_S)
            try:
                trash.purge()
            except Exception:       # a sweep that failed tries again next time
                pass

    if not ctx.option("no_trash_sweep"):
        threading.Thread(target=sweep, daemon=True, name="trash-sweep").start()

    def staff(request: Request) -> str:
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        if auth.role(email) not in ("owner", "admin"):
            raise HTTPException(403, tr("只有站长和管理员能看回收区"))
        return email

    def listing() -> dict:
        return {"items": trash.items(), "keep_days": 60}

    @app.get("/api/site/trash")
    def items(request: Request):
        staff(request)
        return listing()

    @app.post("/api/site/trash/show/{tid}/restore")
    def restore_show(tid: str, request: Request):
        staff(request)
        try:
            spaces.restore(tid)
        except TrashError:
            raise HTTPException(404, tr("回收区里没有这个节目"))
        except AuthError as e:
            raise HTTPException(e.status, str(e))
        return listing()

    @app.post("/api/site/trash/user/{email}/restore")
    def restore_user(email: str, request: Request):
        me = staff(request)
        try:
            rec = trash.user(email)
        except TrashError:
            raise HTTPException(404, tr("回收区里没有这个账号"))
        if rec["user"].get("role") in ("owner", "admin") and auth.role(me) != "owner":
            raise HTTPException(403, tr("只有站长能恢复管理员的账号"))     # appointing admins is the owner's
        try:
            auth.restore_user(rec["user"])
        except AuthError as e:
            raise HTTPException(e.status, str(e))
        for sid, role in (rec.get("shows") or {}).items():
            if sid in spaces.spaces and not spaces.sample(sid):
                spaces.set_member(sid, email, role)
        trash.drop_user(email)
        return listing()
