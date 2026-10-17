"""Sign-in (lacuna_app/auth.py): /api/auth/*, plus a gate that answers 401 to every other /api call
without a valid session, once the first account exists."""
from __future__ import annotations

from http.cookies import SimpleCookie

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth import COOKIE, Auth, AuthError
from ..i18n import tr

# reachable without signing in: the sign-in screens, the launcher's health / version checks
OPEN = {("GET", "/api/health"), ("GET", "/api/app"), ("GET", "/api/auth/status"), ("POST", "/api/auth/login"),
        ("POST", "/api/auth/register"), ("POST", "/api/auth/code"), ("POST", "/api/auth/reset"),
        ("POST", "/api/auth/logout"), ("POST", "/api/auth/_test/reset"), ("GET", "/api/auth/_test/outbox")}


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
                and (scope["method"], scope["path"]) not in OPEN and self.auth.has_accounts():
            raw = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"cookie"), "")
            if not self.auth.who(_cookie(raw)):
                return await JSONResponse({"detail": tr("请先登录")}, status_code=401)(scope, receive, send)
        return await self.app(scope, receive, send)


class Creds(BaseModel):
    email: str
    password: str
    remember: bool = True
    code: str | None = None


class CodeBody(BaseModel):
    email: str
    purpose: str


class ResetBody(BaseModel):
    email: str
    code: str
    password: str


class ConfigBody(BaseModel):
    allow_register: bool | None = None
    sender: str | None = None


class KeyBody(BaseModel):
    key: str


def register(app, ctx) -> None:
    auth: Auth = ctx.provide("auth", lambda: Auth(ctx.ws.root, mailer=ctx.option("mailer"),
                                                   skip_setup=bool(ctx.option("auth_skip_setup"))))
    app.add_middleware(_Gate, auth=auth)

    def signed_in(token, max_age) -> JSONResponse:
        res = JSONResponse({"ok": True})
        # SameSite=Strict: other websites open in the browser can't use the session
        res.set_cookie(COOKIE, token, max_age=max_age, httponly=True, samesite="strict", path="/")
        return res

    def run(fn):
        try:
            return fn()
        except AuthError as e:
            raise HTTPException(e.status, str(e))

    def me(request: Request) -> str:
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        return email

    @app.get("/api/auth/status")
    def status(request: Request):
        return auth.status(request.cookies.get(COOKIE))

    @app.post("/api/auth/login")
    def login(body: Creds):
        return signed_in(*run(lambda: auth.login(body.email, body.password, body.remember)))

    @app.post("/api/auth/register")
    def register_(body: Creds):
        return signed_in(*run(lambda: auth.register(body.email, body.password, body.code, body.remember)))

    @app.post("/api/auth/code")
    def code(body: CodeBody):
        run(lambda: auth.send_code(body.email, body.purpose))
        return {"sent": True}

    @app.post("/api/auth/reset")
    def reset(body: ResetBody):
        return signed_in(*run(lambda: auth.reset(body.email, body.code, body.password)))

    @app.post("/api/auth/logout")
    def logout(request: Request):
        auth.logout(request.cookies.get(COOKIE))
        res = JSONResponse({"ok": True})
        res.delete_cookie(COOKIE, path="/")
        return res

    @app.post("/api/auth/config")
    def config(body: ConfigBody, request: Request):
        me(request)
        run(lambda: auth.update_config(body.allow_register, body.sender))
        return auth.status(request.cookies.get(COOKIE))

    @app.post("/api/auth/resend-key")
    def resend_key(body: KeyBody, request: Request):
        me(request)
        where = run(lambda: auth.save_resend_key(body.key))
        return {"saved": True, "where": where, **auth.status(request.cookies.get(COOKIE))}

    @app.post("/api/auth/test-mail")
    def test_mail(request: Request):
        email = me(request)
        run(lambda: auth.test_mail(email))
        return {"sent": True, "to": email}

    if ctx.option("auth_test_reset"):
        # E2E only (tests/app/e2e/auth.py): forget every account so the shared test server is open again
        @app.post("/api/auth/_test/reset")
        def _test_reset(skip_setup: bool = True):
            with auth.lock:
                auth.skip_setup = skip_setup
                auth.users.clear()
                auth.sessions.clear()
                auth.codes.clear()
                auth.fails.clear()
                auth.config["allow_register"] = False
                auth._save_users()
                auth._save_sessions()
            return {"ok": True}

        @app.get("/api/auth/_test/outbox")
        def _test_outbox():
            return {"mails": getattr(auth.mailer, "outbox", [])}
