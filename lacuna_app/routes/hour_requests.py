"""「想要更多时长」 (decision 2026-10-24-admin-site): a signed-in person asks the owner for more audio hours this month,
from 设置 → 套餐与用量. The owner approves or declines it in the admin (never automatic) and the person gets an
email. Under /api/plan/ so every show answers it (routes/spaces.py GLOBAL).

  GET  /api/plan/hours     my requests (newest first)
  POST /api/plan/hours     ask: hours, why, and whether they'd pay for more
"""
from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .. import notice_mail
from ..admin_store import AdminStore
from ..auth import COOKIE, Auth, MailError
from ..i18n import speaking, tr

PER_MONTH = 3


class AskBody(BaseModel):
    hours: float = Field(gt=0, le=50)
    reason: str = Field("", max_length=1000)
    would_pay: bool = False


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth: Auth = ctx.provide("auth")
    store: AdminStore = ctx.provide("admin_store", lambda: AdminStore(auth.db, auth.now))

    def me(request: Request) -> str:
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        return email

    def mine(email: str) -> list[dict]:
        return [{k: r.get(k) for k in ("id", "created", "status", "hours", "reason", "granted")}
                for r in store.hour_requests(email=email)]

    @app.get("/api/plan/hours")
    def listing(request: Request):
        return {"requests": mine(me(request))}

    @app.post("/api/plan/hours")
    def ask(body: AskBody, request: Request):
        email = me(request)
        reqs = store.hour_requests(email=email)
        if any(r["status"] == "new" for r in reqs):
            raise HTTPException(409, tr("上一个申请还在等 LACUNA 回复"))
        month = time.strftime("%Y-%m", time.gmtime(auth.now()))
        if sum(1 for r in reqs if time.strftime("%Y-%m", time.gmtime(r["created"])) == month) >= PER_MONTH:
            raise HTTPException(429, tr("这个月已经申请过 {n} 次了", n=PER_MONTH))
        store.add_hour_request(email, round(body.hours, 1), body.reason, body.would_pay)
        owner = next((u for u in auth.users.values() if u["role"] == "owner"), None)
        admin_url = getattr(app.state, "admin_url", None)
        if owner and owner["email"] != email:
            with speaking(owner.get("lang") or "zh"):
                m = notice_mail.render(tr("新的加时长申请：{email}", email=email),
                                       tr("{email} 想这个月多要 {n} 小时。", email=email, n=int(body.hours) if body.hours == int(body.hours) else body.hours),
                                       [(tr("理由"), body.reason.strip() or "—")],
                                       tr("去后台处理") if admin_url else None, f"{admin_url}/hours" if admin_url else None,
                                       tr("每一条都由你批，不会自动加时长。"), tr("时长 · HOURS"))

            def go():
                try:
                    auth.mailer.send(auth.config["sender"], owner["email"], m["subject"], m["text"], html=m["html"],
                                     inline=m["inline"])
                except (MailError, OSError) as e:
                    print(f"LACUNA: hour request mail failed: {e}", flush=True)
            if ctx.option("mail_inline"):
                go()
            else:
                threading.Thread(target=go, name="hours-mail", daemon=True).start()
        return {"requests": mine(email)}
