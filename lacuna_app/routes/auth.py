"""Sign-in (lacuna_app/auth.py): /api/auth/*, plus a gate that answers 401 to every other /api call
without a valid session (once the first account exists) and 403 to owner-only calls from anyone else."""
from __future__ import annotations

import os
from http.cookies import SimpleCookie

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import threading
import time

from .. import cloud as cloudflare
from .. import legal, notice_mail, turnstile
from ..auth import COOKIE, RANK, Auth, AuthError
from ..i18n import speaking, tr

# reachable without signing in: the sign-in screens, the host's health / version checks
OPEN = {("GET", "/api/health"), ("GET", "/api/app"), ("GET", "/api/auth/status"), ("POST", "/api/auth/login"),
        ("POST", "/api/auth/register"), ("POST", "/api/auth/code"), ("POST", "/api/auth/reset"),
        ("POST", "/api/auth/2fa"), ("POST", "/api/auth/2fa/enroll"), ("POST", "/api/auth/invite"),
        ("POST", "/api/auth/logout"), ("POST", "/api/auth/_test/reset"), ("GET", "/api/auth/_test/outbox"),
        ("POST", "/api/access-requests")}
# the whole installation: the AI key (a setting for everyone) is the owner's
OWNER_ONLY = {("POST", "/api/app/api-key")}


def cloud_mode() -> bool:
    """`LACUNA_CLOUD=1`: the server runs on the internet (docs/decisions/2026-10-19-invites-roles-2fa.md)."""
    return cloudflare.enabled()


def _cookie(raw: str) -> str | None:
    c = SimpleCookie()
    try:
        c.load(raw)
    except Exception:   # a malformed cookie from another app on localhost
        return None
    return c[COOKIE].value if COOKIE in c else None


class _Gate:
    def __init__(self, app, auth: Auth):
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/") \
                and (scope["method"], scope["path"]) not in OPEN and (self.auth.has_accounts() or self.auth.cloud):
            # in the cloud even a fresh server with no account yet is closed: only the sign-up screen answers
            raw = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"cookie"), "")
            email = self.auth.who(_cookie(raw))
            if not email:
                return await JSONResponse({"detail": tr("请先登录")}, status_code=401)(scope, receive, send)
            if (scope["method"], scope["path"]) in OWNER_ONLY and self.auth.role(email) != "owner":
                return await JSONResponse({"detail": tr("只有站长能改这项设置")}, status_code=403)(scope, receive, send)
        return await self.app(scope, receive, send)


class Creds(BaseModel):
    email: str
    password: str
    remember: bool = True
    turnstile: str | None = None    # Cloudflare Turnstile's token (lacuna_app/turnstile.py), when it is on


class RegisterBody(BaseModel):
    password: str
    email: str | None = None        # first account
    setup_code: str | None = None   # first account in the cloud
    invite: str | None = None       # everyone else
    remember: bool = True
    name: str = ""                  # what others see (the interface asks for it; new-user batch Q12)
    agree: str | None = None        # the 用户条款 / 隐私政策 version the box was ticked for (lacuna_app/legal.py)


class NameBody(BaseModel):
    name: str = Field(max_length=200)


class CodeBody(BaseModel):
    email: str
    purpose: str


class ResetBody(BaseModel):
    email: str
    code: str
    password: str


class TicketBody(BaseModel):
    ticket: str
    code: str


class InviteToken(BaseModel):
    token: str


class OwnCode(BaseModel):
    code: str


class PasswordBody(BaseModel):
    old: str
    new: str


class SessionBody(BaseModel):
    id: str | None = None           # None: every other device


class ConfigBody(BaseModel):
    sender: str | None = None


class KeyBody(BaseModel):
    key: str


class InviteBody(BaseModel):
    email: str
    role: str = "member"
    space: str | None = None        # workspace to join (routes/spaces.py): "new" = a workspace of their own
    space_role: str | None = None
    lang: str | None = None         # the email's language (zh / en); default the inviter's interface
    plan: str | None = None         # lacuna_app/plans.py; default 基础版


class UserBody(BaseModel):
    role: str | None = None
    disabled: bool | None = None
    reset_2fa: bool = False
    plan: str | None = None


def register(app, ctx) -> None:
    if ctx.option("space_child"):     # a workspace's own app (routes/spaces.py): sign-in is the main app's
        return
    cloud = ctx.option("auth_cloud")
    auth: Auth = ctx.provide("auth", lambda: Auth(ctx.ws.root, mailer=ctx.option("mailer"),
                                                   skip_setup=bool(ctx.option("auth_skip_setup")),
                                                   cloud=cloud_mode() if cloud is None else bool(cloud)))
    app.add_middleware(_Gate, auth=auth)
    # Cloudflare Turnstile on sign-in and 申请试用: on when the server has its keys (tests pass a fake)
    human = ctx.option("turnstile") or (turnstile.Verifier() if turnstile.site_key() else None)
    human_key = ctx.option("turnstile_site_key") or turnstile.site_key()
    app.state.human_check = lambda token, request: human is None or human.ok(token, ip(request) or (
        request.client.host if request.client else None))

    def new_device_mail(email: str, request: Request) -> None:
        """A sign-in from a browser + system this account hasn't used: tell its owner by email (in the
        background; a mail failure never stops the sign-in)."""
        if not auth.note_device(email, agent(request)):
            return
        u = auth.users.get(email) or {}
        when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(auth.now()))
        with speaking(u.get("lang") or "zh"):
            m = notice_mail.new_device(email, notice_mail.device_label(agent(request)), when,
                                       notice_mail.country_name(request.headers.get("cf-ipcountry")),
                                       f"{origin(request).rstrip('/')}/#/settings/account")

        def send():
            try:
                auth.mailer.send(auth.config["sender"], email, m["subject"], m["text"], html=m["html"],
                                 inline=m["inline"])
            except Exception as e:      # noqa: BLE001 - mail is best-effort here
                print(f"LACUNA: new-device mail failed: {e}", flush=True)
        if ctx.option("mail_inline"):
            send()
        else:
            threading.Thread(target=send, name="new-device-mail", daemon=True).start()

    def finish(out: dict, request: Request | None = None) -> JSONResponse:
        """A step result; when it holds a session, set the cookie and keep the token out of the body."""
        body = {k: v for k, v in out.items() if k != "session"}
        res = JSONResponse({"ok": True, **body})
        if "session" in out:
            token, max_age = out["session"]
            # SameSite=Strict: other websites open in the browser can't use the session; Secure in the cloud
            res.set_cookie(COOKIE, token, max_age=max_age, httponly=True, samesite="strict", path="/",
                           secure=auth.cloud)
            email = auth.who(token)
            if email and request is not None:
                new_device_mail(email, request)
        return res

    def run(fn):
        try:
            return fn()
        except AuthError as e:
            raise HTTPException(e.status, str(e))

    def token(request: Request) -> str | None:
        return request.cookies.get(COOKIE)

    def me(request: Request) -> str:
        email = auth.who(token(request))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        return email

    def at_least(request: Request, role: str) -> str:
        email = me(request)
        if RANK[auth.role(email)] < RANK[role]:
            raise HTTPException(403, tr("只有站长能改这项设置") if role == "owner" else tr("只有站长和站点管理员能管理成员和邀请"))
        return email

    def ip(request: Request) -> str | None:
        # in the cloud every request comes through Cloudflare, which names the visitor's address
        if not auth.cloud:
            return None
        return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else None)

    def owner(request: Request) -> str | None:
        """The owner's email when Cloudflare Access proved this request comes from it (cloud only)."""
        e = cloudflare.owner_email()
        return e if e and cloudflare.access_email(request) == e else None

    def agent(request: Request) -> str:
        return request.headers.get("user-agent", "")

    def origin(request: Request) -> str:
        public = os.environ.get("LACUNA_PUBLIC_URL", "").strip()     # the cloud site's own address
        if public:
            return public
        o = request.headers.get("origin")
        return o if o and o != "null" else str(request.base_url).rstrip("/")

    def access(email: str, allow: bool) -> None:
        """Keep Cloudflare Access's invite list in step (lacuna_app/cloud.py; nothing happens on the desktop).
        A failure there must not undo the invite: the owner can still add the email in Cloudflare."""
        try:
            (cloudflare.access_allow if allow else cloudflare.access_revoke)(email)
        except Exception as e:      # network, Cloudflare API
            print(f"LACUNA: Cloudflare Access update for {email} failed: {e}", flush=True)

    # 邀请协作 (routes/spaces.py) sends project invites with the same link and Access list
    app.state.invite_origin = origin
    app.state.grant_access = access

    @app.get("/api/auth/status")
    def status(request: Request):
        out = auth.status(token(request)) | {"turnstile": human_key}
        if out.get("first") and owner(request):
            out["setup_code"] = False          # Access proved it is the owner: no code to type
            out["owner_email"] = owner(request)
        return out

    @app.post("/api/auth/login")
    def login(body: Creds, request: Request):
        if not app.state.human_check(body.turnstile, request):
            raise HTTPException(400, tr("请先完成人机验证，再登录"))
        return finish(run(lambda: auth.login(body.email, body.password, body.remember, ip(request), agent(request))), request)

    @app.post("/api/auth/2fa")
    def second_step(body: TicketBody, request: Request):
        return finish(run(lambda: auth.second_step(body.ticket, body.code, ip(request))), request)

    @app.post("/api/auth/2fa/enroll")
    def enroll(body: TicketBody, request: Request):
        return finish(run(lambda: auth.enroll(body.ticket, body.code, ip(request))), request)

    @app.post("/api/auth/invite")
    def invite_info(body: InviteToken):
        i = run(lambda: auth.invite_info(body.token))
        return {"email": i["email"], "role": i["role"], "by": i["by"], "by_name": auth.name(i["by"]), "exp": i["exp"],
                "lang": i.get("lang")}

    @app.post("/api/auth/register")
    def register_(body: RegisterBody, request: Request):
        if auth.cloud and body.agree != legal.VERSION:     # on the internet an account needs the box ticked
            raise HTTPException(400, tr("请先阅读并勾选同意用户条款和隐私政策"))
        if body.invite:
            return finish(run(lambda: auth.register_invite(body.invite, body.password, body.remember, agent(request),
                                                           name=body.name, agreed=body.agree)), request)
        return finish(run(lambda: auth.register_first(body.email or "", body.password, body.setup_code, body.remember,
                                                      agent(request), proven=owner(request), name=body.name,
                                                      agreed=body.agree)), request)

    @app.post("/api/auth/name")
    def set_name(body: NameBody, request: Request):
        """The signed-in person's name (设置 → 账号, or once for accounts made before it was asked)."""
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        run(lambda: auth.set_name(email, body.name))
        return {"name": auth.name(email)}

    @app.post("/api/auth/code")
    def code(body: CodeBody, request: Request):
        run(lambda: auth.send_code(body.email, body.purpose, ip(request)))
        return {"sent": True}

    @app.post("/api/auth/reset")
    def reset(body: ResetBody, request: Request):
        return finish(run(lambda: auth.reset(body.email, body.code, body.password, agent(request))), request)

    @app.post("/api/auth/logout")
    def logout(request: Request):
        auth.logout(token(request))
        res = JSONResponse({"ok": True})
        res.delete_cookie(COOKIE, path="/")
        return res

    # -- my account
    @app.post("/api/auth/password")
    def password(body: PasswordBody, request: Request):
        email = me(request)
        run(lambda: auth.change_password(email, body.old, body.new, token(request)))
        return {"ok": True}

    @app.post("/api/auth/2fa/setup")
    def setup_2fa(request: Request):
        return auth.start_2fa(me(request))

    @app.post("/api/auth/2fa/confirm")
    def confirm_2fa(body: OwnCode, request: Request):
        email = me(request)
        return {"recovery": run(lambda: auth.confirm_2fa(email, body.code)), **auth.status(token(request))}

    @app.post("/api/auth/2fa/recovery")
    def new_recovery(body: OwnCode, request: Request):
        email = me(request)
        return {"recovery": run(lambda: auth.new_recovery(email, body.code))}

    @app.post("/api/auth/2fa/off")
    def off_2fa(body: OwnCode, request: Request):
        email = me(request)
        run(lambda: auth.disable_2fa(email, body.code))
        return auth.status(token(request))

    @app.get("/api/auth/sessions")
    def sessions(request: Request):
        return {"sessions": auth.list_sessions(me(request), token(request))}

    @app.post("/api/auth/sessions/end")
    def end_sessions(body: SessionBody, request: Request):
        n = auth.end_sessions(me(request), token(request), body.id)
        return {"ended": n, "sessions": auth.list_sessions(me(request), token(request))}

    # -- members and invites (owner, admins)
    def people() -> dict:
        return {"users": auth.list_users(), "invites": auth.list_invites()}

    @app.get("/api/auth/users")
    def users(request: Request):
        at_least(request, "admin")
        return people()

    @app.post("/api/auth/invites")
    def invite(body: InviteBody, request: Request):
        email = at_least(request, "admin")
        check = getattr(app.state, "invite_space", None)     # set by routes/spaces.py
        extra = run(lambda: check(email, body.space, body.space_role)) if check else None
        if body.plan:
            extra = (extra or {}) | {"plan": body.plan}
        out = run(lambda: auth.invite(email, body.email, body.role, origin(request), extra, body.lang))
        access(out["email"], True)
        return {**out, **people()}

    @app.delete("/api/auth/invites/{iid}")
    def revoke(iid: str, request: Request):
        at_least(request, "admin")
        for email in auth.revoke_invite(iid):
            if email not in auth.users:
                access(email, False)
        return people()

    @app.post("/api/auth/users/{email}")
    def update_user(email: str, body: UserBody, request: Request):
        actor = at_least(request, "admin")
        run(lambda: auth.update_user(actor, email.lower(), body.role, body.disabled, body.reset_2fa, body.plan))
        return people()

    @app.delete("/api/auth/users/{email}")
    def delete_user(email: str, request: Request):
        actor = at_least(request, "admin")
        run(lambda: auth.delete_user(actor, email.lower()))
        access(email.lower(), False)
        return people()

    # -- email (owner)
    @app.post("/api/auth/config")
    def config(body: ConfigBody, request: Request):
        at_least(request, "owner")
        run(lambda: auth.update_config(body.sender))
        return auth.status(token(request))

    @app.post("/api/auth/resend-key")
    def resend_key(body: KeyBody, request: Request):
        at_least(request, "owner")
        where = run(lambda: auth.save_resend_key(body.key))
        return {"saved": True, "where": where, **auth.status(token(request))}

    @app.post("/api/auth/test-mail")
    def test_mail(request: Request):
        email = at_least(request, "owner")
        run(lambda: auth.test_mail(email))
        return {"sent": True, "to": email}

    if ctx.option("auth_test_reset"):
        # E2E only (tests/app/e2e/auth.py): forget every account so the shared test server is open again
        @app.post("/api/auth/_test/reset")
        def _test_reset(skip_setup: bool = True, cloud: bool = False):
            with auth.lock:
                auth.skip_setup = skip_setup
                auth.cloud = cloud
                auth.users.clear()
                auth.sessions.clear()
                auth.codes.clear()
                auth.code_sends.clear()
                auth.code_burnt.clear()
                auth.fails.clear()
                auth.tickets.clear()
                auth.invites.clear()
                auth.pending_totp.clear()
                auth.setup_code = None
                auth._save_users()
                auth._save_sessions()
            with auth.db.tx() as c:
                c.execute("DELETE FROM access_requests")
            return {"ok": True}

        @app.get("/api/auth/_test/outbox")
        def _test_outbox():
            return {"mails": getattr(auth.mailer, "outbox", [])}
