"""申请试用 (decision 2026-10-21-app-sign-in): someone without an account asks for one on the sign-in page.

``POST /api/access-requests`` is open (no sign-in), behind the Turnstile check when it is on, and limited:
one request per email per day, ``PER_IP`` per address per day. The site owner gets an email; the owner
and site admins see the list in 设置 → 成员与邀请 and send the invite (or dismiss it) with one click.
The answer never says whether the email already has an account.
"""
from __future__ import annotations

import secrets
import threading

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .. import db as sitedb
from .. import notice_mail
from ..auth import COOKIE, RANK, Auth, AuthError, MailError, norm_email
from ..i18n import speaking, tr

DAY = 86400
PER_IP = 5


class RequestBody(BaseModel):
    email: str = Field(max_length=254)
    show: str = Field("", max_length=80)
    note: str = Field("", max_length=500)
    turnstile: str | None = None
    lang: str | None = None


class DecideBody(BaseModel):
    action: str = Field(pattern="^(invite|dismiss)$")
    lang: str | None = None


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth: Auth = ctx.provide("auth")
    db = auth.db
    lock = threading.Lock()
    by_ip: dict[str, list[float]] = {}

    def admin(request: Request) -> str:
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        if RANK[auth.role(email)] < RANK["admin"]:
            raise HTTPException(403, tr("只有站长和站点管理员能管理成员和邀请"))
        return email

    def rows(status: str = "new") -> list[dict]:
        return [sitedb.loads(r["data"]) | {"id": r["id"], "status": r["status"]}
                for r in db.query("SELECT * FROM access_requests WHERE status = ? ORDER BY created DESC", (status,))]

    def notify(row: dict, request: Request) -> None:
        owner = next((u for u in auth.users.values() if u["role"] == "owner"), None)
        if not owner:
            return
        origin = app.state.invite_origin(request) if hasattr(app.state, "invite_origin") else ""
        with speaking(owner.get("lang") or "zh"):
            m = notice_mail.access_request(row["email"], row["show"], row["note"], f"{origin.rstrip('/')}/#/settings/members")

        def send():
            try:
                auth.mailer.send(auth.config["sender"], owner["email"], m["subject"], m["text"], html=m["html"])
            except (MailError, OSError) as e:
                print(f"LACUNA: access-request mail failed: {e}", flush=True)
        if ctx.option("mail_inline"):
            send()
        else:
            threading.Thread(target=send, name="access-request-mail", daemon=True).start()

    @app.post("/api/access-requests")
    def ask(body: RequestBody, request: Request):
        check = getattr(app.state, "human_check", None)
        if check and not check(body.turnstile, request):
            raise HTTPException(400, tr("请先完成人机验证"))
        try:
            email = norm_email(body.email)
        except AuthError as e:
            raise HTTPException(e.status, str(e))
        now = auth.now()
        addr = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "")
        with lock:
            recent = by_ip[addr] = [t for t in by_ip.get(addr, []) if now - t < DAY]
            if len(recent) >= PER_IP:
                raise HTTPException(429, tr("今天申请太多次了，明天再试"))
            same = db.query("SELECT 1 FROM access_requests WHERE email = ? AND created > ?", (email, now - DAY))
            if same:
                return {"ok": True}          # already asked today: the same answer, nothing new
            recent.append(now)
        row = {"email": email, "show": " ".join(body.show.split())[:80], "note": body.note.strip()[:500],
               "created": now, "lang": body.lang if body.lang in ("zh", "en") else None}
        rid = "ar_" + secrets.token_hex(6)
        with db.tx() as c:
            c.execute("INSERT INTO access_requests (id, email, created, status, data) VALUES (?,?,?,?,?)",
                      (rid, email, now, "new", sitedb.dumps(row)))
        if email not in auth.users:
            notify(row, request)
        return {"ok": True}

    @app.get("/api/access-requests")
    def listing(request: Request):
        admin(request)
        return {"requests": [r for r in rows() if r["email"] not in auth.users]}

    @app.post("/api/access-requests/{rid}")
    def decide(rid: str, body: DecideBody, request: Request):
        """Invite: a sign-up link (default plan, a show of their own), mailed like any invite; or dismiss."""
        actor = admin(request)
        found = db.query("SELECT * FROM access_requests WHERE id = ?", (rid,))
        if not found:
            raise HTTPException(404, tr("这个申请已经没有了"))
        row = sitedb.loads(found[0]["data"])
        out: dict = {}
        if body.action == "invite":
            try:
                sent = auth.invite(actor, row["email"], "member", app.state.invite_origin(request), {"space": "new"},
                                   body.lang or row.get("lang"))
            except AuthError as e:
                raise HTTPException(e.status, str(e))
            grant = getattr(app.state, "grant_access", None)
            if grant:
                grant(sent["email"], True)
            out = {"link": sent["link"], "mailed": sent["mailed"], "mail_error": sent["mail_error"]}
        with db.tx() as c:
            c.execute("UPDATE access_requests SET status = ? WHERE id = ?",
                      ("invited" if body.action == "invite" else "dismissed", rid))
        return {"requests": [r for r in rows() if r["email"] not in auth.users], **out}
