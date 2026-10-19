"""Workspaces (lacuna_app/spaces.py): /api/spaces*, plus the dispatcher that sends every other /api call
to the signed-in person's current workspace and enforces their role in it.

The installation's own folder is the "main" workspace and is served by this app as before; every other
workspace gets its own app (``create_app`` on its folder, built on first use), so episodes, library,
learned rules and background jobs never mix between workspaces.
"""
from __future__ import annotations

import re
import threading
from http.cookies import SimpleCookie

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth import COOKIE, Auth, AuthError
from ..i18n import tr
from ..spaces import MAIN, SPACE_RANK, Spaces

SPACE_COOKIE = "lacuna_space"
# answered by the main app whatever the workspace: sign-in, workspaces, app version / updates / AI key
GLOBAL = ("/api/auth/", "/api/spaces", "/api/app", "/api/health")
# services bound to one workspace folder: each workspace builds its own
WS_BOUND = {"auth", "spaces", "importer", "exporter", "publisher", "posters", "library", "learning", "chat_asks",
            "lessons", "archive", "episode_index"}
# services that only hold models: one copy for every workspace
SHARED = ("dictation", "dictation_fixer")
FOR_GOOD = re.compile(r"^/api/episodes/[^/]+$")      # DELETE = delete an episode for good


def _cookies(scope) -> SimpleCookie:
    raw = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"cookie"), "")
    c = SimpleCookie()
    try:
        c.load(raw)
    except Exception:
        pass
    return c


class _Dispatch:
    def __init__(self, app, auth: Auth, spaces: Spaces, child):
        self.app, self.auth, self.spaces, self.child = app, auth, spaces, child

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/") or path.startswith(GLOBAL) \
                or not self.auth.has_accounts():
            return await self.app(scope, receive, send)
        c = _cookies(scope)
        email = self.auth.who(c[COOKIE].value if COOKIE in c else None)
        if not email:
            return await self.app(scope, receive, send)        # the sign-in gate answers 401
        sid = self.spaces.current(email, c[SPACE_COOKIE].value if SPACE_COOKIE in c else None)

        def deny(msg):
            return JSONResponse({"detail": msg}, status_code=403)(scope, receive, send)

        if sid is None:
            return await deny(tr("你还没有加入任何工作区，请联系 LACUNA 的管理员。"))
        role = self.spaces.role(sid, email)
        method = scope["method"]
        if role == "viewer" and method not in ("GET", "HEAD"):
            return await deny(tr("你在这个工作区只能试听和查看，不能修改。"))
        if role != "admin" and method == "DELETE" and FOR_GOOD.match(path):
            return await deny(tr("只有工作区管理员能彻底删除剧集。"))
        if sid == MAIN:
            return await self.app(scope, receive, send)
        return await self.child(sid)(scope, receive, send)


class SwitchBody(BaseModel):
    id: str


class NameBody(BaseModel):
    name: str


class MemberBody(BaseModel):
    email: str
    role: str | None = None        # None: remove from the workspace


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth: Auth = ctx.provide("auth")              # routes/auth.py (registered before this module)
    spaces: Spaces = ctx.provide("spaces", lambda: Spaces(ctx.ws.root))
    spaces.adopt(list(auth.users.values()))
    children: dict = {}
    lock = threading.Lock()

    def child(sid: str):
        with lock:
            if sid not in children:
                from ..server import create_app
                given = {k: v for k, v in ctx._given.items() if k not in WS_BOUND}
                given |= {"space_child": True, "models_dir": ctx.models_dir}
                for name in SHARED:
                    if ctx.provide(name) is not None:
                        given[name] = ctx.provide(name)
                folder = spaces.path(sid)
                children[sid] = create_app(folder, ctx.adapter, web_dist=folder / "_no_ui", **given)
            return children[sid]

    app.state.space_apps = children
    app.add_middleware(_Dispatch, auth=auth, spaces=spaces, child=child)

    # accounts follow into workspaces
    def joined(email: str, invite: dict | None) -> None:
        if invite is None:            # the owner's first account (also after users.json was deleted to get back in)
            if MAIN in spaces.spaces:
                spaces.set_member(MAIN, email, "admin")
            else:
                spaces.adopt([auth.users[email]])
            return
        sid = invite.get("space")
        if sid and sid != "new" and sid in spaces.spaces:
            spaces.set_member(sid, email, invite.get("space_role") or "editor")
        else:
            spaces.create(email.split("@")[0], email)

    auth.on_joined.append(joined)
    auth.on_deleted.append(spaces.forget)

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

    def site_admin(email: str) -> bool:
        return auth.role(email) in ("owner", "admin")

    def may_manage(email: str, sid: str) -> None:
        if not (site_admin(email) or spaces.role(sid, email) == "admin"):
            raise HTTPException(403, tr("只有工作区管理员能改这个工作区"))

    def invite_space(actor: str, space: str | None, role: str | None) -> dict:
        """What an invite (routes/auth.py) puts its new account into."""
        if not space or space == "new":
            return {"space": "new"}
        if space not in spaces.spaces:
            raise AuthError(tr("没有这个工作区"), 404)
        role = role or "editor"
        if role not in SPACE_RANK:
            raise AuthError(tr("没有这个角色"))
        return {"space": space, "space_role": role}

    app.state.invite_space = invite_space

    def overview(request: Request, email: str, picked: str | None = None) -> dict:
        cur = spaces.current(email, picked or request.cookies.get(SPACE_COOKIE))
        out = {"current": next((s for s in spaces.mine(email) if s["id"] == cur), None), "mine": spaces.mine(email)}
        if site_admin(email):
            out["all"] = spaces.overview()
        elif cur and spaces.role(cur, email) == "admin":
            out["all"] = [s for s in spaces.overview() if s["id"] == cur]
        return out

    @app.get("/api/spaces")
    def list_spaces(request: Request):
        return overview(request, me(request))

    @app.post("/api/spaces/switch")
    def switch(body: SwitchBody, request: Request):
        email = me(request)
        if not spaces.role(body.id, email):
            raise HTTPException(403, tr("你不在这个工作区里"))
        res = JSONResponse(overview(request, email, body.id))
        res.set_cookie(SPACE_COOKIE, body.id, max_age=365 * 86400, httponly=True, samesite="strict", path="/",
                       secure=auth.cloud)
        return res

    @app.post("/api/spaces")
    def create(body: NameBody, request: Request):
        email = me(request)
        if not site_admin(email):
            raise HTTPException(403, tr("只有管理员能新建工作区"))
        run(lambda: spaces.create(body.name, email))
        return overview(request, email)

    @app.post("/api/spaces/{sid}")
    def rename(sid: str, body: NameBody, request: Request):
        email = me(request)
        may_manage(email, sid)
        run(lambda: spaces.rename(sid, body.name))
        return overview(request, email)

    @app.post("/api/spaces/{sid}/members")
    def member(sid: str, body: MemberBody, request: Request):
        email = me(request)
        may_manage(email, sid)
        target = body.email.strip().lower()
        if body.role is not None and target not in auth.users:
            raise HTTPException(404, tr("没有这个账号：先在「成员与邀请」里邀请对方"))
        run(lambda: spaces.set_member(sid, target, body.role))
        return overview(request, email)
