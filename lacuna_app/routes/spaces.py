"""Workspaces (lacuna_app/spaces.py): /api/spaces*, plus the dispatcher that sends every other /api call
to the signed-in person's current workspace and enforces their role in it.

The installation's own folder is the "main" workspace and is served by this app as before; every other
workspace gets its own app (``create_app`` on its folder, built on first use), so episodes, library,
learned rules and background jobs never mix between workspaces.
"""
from __future__ import annotations

import re
import shutil
import threading
import time
from http.cookies import SimpleCookie

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .. import cloud, habits, plans
from ..appinfo import current_version
from ..auth import COOKIE, Auth, AuthError
from ..i18n import tr
from ..learning import LEARN_DIR, RULES_FILE
from ..spaces import MAIN, SPACE_RANK, Spaces
from ..store import atomic_write_json, read_json
from . import events as events_routes
from .auth import _cookie

SPACE_COOKIE = "lacuna_space"
# answered by the main app whatever the workspace: sign-in, workspaces, app version / updates / AI key
GLOBAL = ("/api/auth/", "/api/spaces", "/api/app", "/api/health", "/api/habits")
# services bound to one workspace folder: each workspace builds its own
WS_BOUND = {"auth", "spaces", "importer", "exporter", "publisher", "posters", "library", "learning", "chat_asks",
            "lessons", "archive", "episode_index"}
# services that only hold models: one copy for every workspace
SHARED = ("dictation", "dictation_fixer")
FOR_GOOD = re.compile(r"^/api/episodes/[^/]+$")      # DELETE = delete an episode for good
# 节目设置 (name, hosts, opener / ending, publishing): the show's managers only (decision 2026-10-21-roles)
SETTINGS = {("PUT", "/api/show"), ("PATCH", "/api/albums/project")}


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
        self.moved = False

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/"):
            return await self.app(scope, receive, send)
        if not self.auth.has_accounts():
            # no accounts (a fresh or desktop install): habits and approved rules live in the folder itself
            token = habits.HOME.set(self.spaces.root)
            try:
                return await self.app(scope, receive, send)
            finally:
                habits.HOME.reset(token)
        if not self.moved:
            # at the first request, not at registration: start-up jobs registered after this module (such
            # as stutter_rule_once) may still approve rules into the project's own file first
            habits_moved(self.spaces)
            self.moved = True
        if path.startswith(GLOBAL):
            return await self.app(scope, receive, send)
        c = _cookies(scope)
        email = self.auth.who(c[COOKIE].value if COOKIE in c else None)
        if not email:
            return await self.app(scope, receive, send)        # the sign-in gate answers 401
        sid = self.spaces.current(email, c[SPACE_COOKIE].value if SPACE_COOKIE in c else None)

        def deny(msg):
            return JSONResponse({"detail": msg}, status_code=403)(scope, receive, send)

        if sid is None:
            return await deny(tr("你还没有节目。先建一个节目，或者请别人邀请你协作。"))
        role = self.spaces.role(sid, email)
        method = scope["method"]
        if role == "viewer" and method not in ("GET", "HEAD"):
            return await deny(tr("你在这个节目里只能试听和查看，不能修改。"))
        if self.spaces.archived(sid) and method not in ("GET", "HEAD"):
            return await deny(tr("这个节目已归档，只能查看。恢复后才能修改。"))
        if role != "admin" and method == "DELETE" and FOR_GOOD.match(path):
            return await deny(tr("只有节目管理员能彻底删除剧集。"))
        if role != "admin" and (method, path) in SETTINGS:
            return await deny(tr("只有节目管理员能改节目设置。"))
        # whose learned rules and 剪辑力度 apply: the signed-in person's own, in every project (habits.py)
        token = habits.HOME.set(habits.home_for(self.spaces.root, email))
        try:
            if sid == MAIN:
                return await self.app(scope, receive, send)
            return await self.child(sid)(scope, receive, send)
        finally:
            habits.HOME.reset(token)


def habits_moved(spaces: Spaces) -> None:
    """Once per project: the learned rules approved in it (learning/rules.json, from before rules followed
    the editor) become its managers' own. A rule a manager already has stays as theirs; the project's file
    is left in place."""
    marker = spaces.root / "auth" / "habits_moved.json"
    done = set(read_json(marker).get("spaces", [])) if marker.is_file() else set()
    todo = [sid for sid in spaces.spaces if sid not in done]
    if not todo:
        return
    for sid in todo:
        src = spaces.path(sid) / LEARN_DIR / RULES_FILE
        if src.is_file():
            try:
                old = read_json(src)
            except (OSError, ValueError):
                old = None
            for email, role in (spaces.spaces[sid]["members"] or {}).items():
                if role != "admin" or not isinstance(old, dict):
                    continue
                dst = habits.home_for(spaces.root, email) / LEARN_DIR / RULES_FILE
                mine = read_json(dst) if dst.is_file() else {"schema": 1, "rules": {}}
                mine.setdefault("rules", {})
                for rid, st in (old.get("rules") or {}).items():
                    mine["rules"].setdefault(rid, st)
                eps = set(mine.get("accepted_as_is", [])) | set(old.get("accepted_as_is", []))
                if eps:
                    mine["accepted_as_is"] = sorted(eps)
                dst.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(dst, mine)
        done.add(sid)
    marker.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(marker, {"spaces": sorted(done)})


class SwitchBody(BaseModel):
    id: str


class NameBody(BaseModel):
    name: str


class ArchiveBody(BaseModel):
    archived: bool = True


class SupportBody(BaseModel):
    on: bool


class DeleteBody(BaseModel):
    confirm: str            # the project's name, typed


PICTURE_MAX = 10 * 1024 * 1024


class MemberBody(BaseModel):
    email: str
    role: str | None = None        # None: remove from the workspace
    lang: str | None = None        # invite email's language (zh / en)


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth: Auth = ctx.provide("auth")              # routes/auth.py (registered before this module)
    spaces: Spaces = ctx.provide("spaces", lambda: Spaces(ctx.ws.root))
    spaces.adopt(list(auth.users.values()))
    spaces.staff = lambda email: auth.role(email) in ("owner", "admin")
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
    # the event log sees every workspace's requests: outside the dispatcher, inside the cloud gate (routes/events.py)
    events_routes.install(app, ctx, auth, spaces)
    # in the cloud the Cloudflare Access check (routes/cloud.py) must come before anything else, this
    # dispatcher included: install it once more on the outside (the inner one and each workspace's own
    # app check again, which costs one cached signature check)
    cloud.install(app, lambda raw: bool(auth.who(_cookie(raw))), current_version,
                  verifier=ctx.option("access_verifier"))

    # accounts follow into workspaces
    def joined(email: str, invite: dict | None) -> None:
        if invite is None:            # the owner's first account (also after users.json was deleted to get back in)
            if MAIN in spaces.spaces:
                spaces.set_member(MAIN, email, "admin")
            else:
                spaces.adopt([auth.users[email]])
            habits_moved(spaces)
            return
        habits_moved(spaces)          # an install that just got its first accounts
        sid = invite.get("space")
        if sid and sid != "new" and sid in spaces.spaces:
            spaces.set_member(sid, email, invite.get("space_role") or "editor")
        else:
            spaces.create(email.split("@")[0], email, named=False)

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
        """The show's own managers. Site owner and admins don't manage other people's shows (decision
        2026-10-21-roles): they can't see what is in them."""
        if spaces.role(sid, email) != "admin":
            raise HTTPException(403, tr("只有节目管理员能改这个节目"))

    def plan_of(email: str | None) -> str:
        return (auth.users.get(email or "") or {}).get("plan") or plans.DEFAULT

    def room_for(sid: str, newcomer: str) -> None:
        """A new collaborator fits in the plan of the show's maker (someone already in it always does)."""
        if newcomer in spaces.spaces[sid]["members"]:
            return
        try:
            plans.check_collaborators(plan_of(spaces.creator(sid)), spaces.collaborators(sid))
        except plans.PlanLimit as e:
            raise HTTPException(403, str(e))

    def live(sid: str) -> None:
        if spaces.archived(sid):
            raise HTTPException(403, tr("这个节目已归档，只能查看。恢复后才能修改。"))

    def may_delete(email: str, sid: str) -> bool:
        """Deleting for good: the project's creator or LACUNA's owner, never the main project."""
        return sid != MAIN and (spaces.creator(sid) == email or auth.role(email) == "owner")

    def invite_space(actor: str, space: str | None, role: str | None) -> dict:
        """What an invite (routes/auth.py) puts its new account into."""
        if not space or space == "new":
            return {"space": "new"}
        if space not in spaces.spaces:
            raise AuthError(tr("没有这个节目"), 404)
        role = role or "editor"
        if role not in SPACE_RANK:
            raise AuthError(tr("没有这个角色"))
        try:
            plans.check_collaborators(plan_of(spaces.creator(space)), spaces.collaborators(space))
        except plans.PlanLimit as e:
            raise AuthError(str(e), 403)
        return {"space": space, "space_role": role, "space_name": spaces.title(space)}

    app.state.invite_space = invite_space

    def overview(request: Request, email: str, picked: str | None = None) -> dict:
        cur = spaces.current(email, picked or request.cookies.get(SPACE_COOKIE))
        mine = [m | {"can_delete": may_delete(email, m["id"])} for m in spaces.mine(email, detail=True)]
        out = {"current": next((s for s in mine if s["id"] == cur), None), "mine": mine}
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
            raise HTTPException(403, tr("你不在这个节目里"))
        res = JSONResponse(overview(request, email, body.id))
        res.set_cookie(SPACE_COOKIE, body.id, max_age=365 * 86400, httponly=True, samesite="strict", path="/",
                       secure=auth.cloud)
        return res

    @app.post("/api/spaces")
    def create(body: NameBody, request: Request):
        """Anyone signed in may start a project of their own (they manage it); they are moved into it."""
        email = me(request)
        try:
            plans.check_shows(plan_of(email), spaces.owned(email))
        except plans.PlanLimit as e:
            raise HTTPException(403, str(e))
        made = run(lambda: spaces.create(body.name, email))
        res = JSONResponse(overview(request, email, made["id"]) | {"created": made["id"]})
        res.set_cookie(SPACE_COOKIE, made["id"], max_age=365 * 86400, httponly=True, samesite="strict", path="/",
                       secure=auth.cloud)
        return res

    @app.post("/api/spaces/{sid}")
    def rename(sid: str, body: NameBody, request: Request):
        email = me(request)
        may_manage(email, sid)
        live(sid)
        run(lambda: spaces.rename(sid, body.name))
        return overview(request, email)

    @app.post("/api/spaces/{sid}/members")
    def member(sid: str, body: MemberBody, request: Request):
        email = me(request)
        may_manage(email, sid)
        live(sid)
        target = body.email.strip().lower()
        if body.role is not None and target not in auth.users:
            raise HTTPException(404, tr("没有这个账号：先在「成员与邀请」里邀请对方"))
        if body.role is not None:
            room_for(sid, target)
        run(lambda: spaces.set_member(sid, target, body.role, by=email))
        return overview(request, email)

    # -- 邀请协作: one project's collaborators and the invites waiting for them
    def people(sid: str) -> dict:
        s = spaces.spaces.get(sid)
        if not s:
            raise HTTPException(404, tr("没有这个节目"))
        return {"id": sid, "name": spaces.title(sid), "support_until": spaces.support_until(sid),
                "plan": plan_of(spaces.creator(sid)), "collaborators": spaces.collaborators(sid),
                "members": [{"email": e, "role": r} for e, r in sorted(s["members"].items())],
                "invites": [{"id": i["id"], "email": i["email"], "role": i.get("space_role") or "editor",
                             "exp": i["exp"]} for i in auth.list_invites() if i.get("space") == sid],
                "can_invite_new": False}

    def people_for(email: str, sid: str) -> dict:
        return people(sid) | {"can_invite_new": site_admin(email)}

    @app.get("/api/spaces/{sid}/people")
    def list_people(sid: str, request: Request):
        email = me(request)
        if not spaces.role(sid, email):
            raise HTTPException(403, tr("你不在这个节目里"))
        return people_for(email, sid)

    @app.post("/api/spaces/{sid}/support")
    def support(sid: str, body: SupportBody, request: Request):
        """「允许 LACUNA 支持查看」: site owner and admins may open this show read-only for 7 days."""
        email = me(request)
        may_manage(email, sid)
        run(lambda: spaces.set_support(sid, body.on, email))
        return people_for(email, sid)

    @app.post("/api/spaces/{sid}/invite")
    def invite(sid: str, body: MemberBody, request: Request):
        """By email: someone with an account joins at once; anyone else gets a sign-up link for this project,
        which only the site's owner and admins may send (the site stays invite-only)."""
        email = me(request)
        may_manage(email, sid)
        live(sid)
        target = body.email.strip().lower()
        role = body.role or "editor"
        if role not in SPACE_RANK:
            raise HTTPException(422, tr("没有这个角色"))
        out: dict = {}
        if target in auth.users:
            room_for(sid, target)
            run(lambda: spaces.set_member(sid, target, role, by=email))
            out = {"joined": target}
        elif site_admin(email):
            sent = run(lambda: auth.invite(email, target, "member", app.state.invite_origin(request), {"space": sid, "space_role": role, "space_name": spaces.title(sid)}, body.lang))
            grant = getattr(app.state, "grant_access", None)       # routes/auth.py: Cloudflare Access list
            if grant:
                grant(sent["email"], True)
            out = {"invited": sent["email"], "link": sent["link"], "mailed": sent["mailed"],
                   "mail_error": sent["mail_error"]}
        else:
            raise HTTPException(403, tr("这个邮箱还没有 LACUNA 账号。现在只有 LACUNA 管理员能邀请新人注册。"))
        return people_for(email, sid) | out

    @app.delete("/api/spaces/{sid}/invites/{iid}")
    def withdraw(sid: str, iid: str, request: Request):
        email = me(request)
        may_manage(email, sid)
        if not any(i["id"] == iid and i.get("space") == sid for i in auth.list_invites()):
            raise HTTPException(404, tr("这个邀请已经没有了"))
        gone = auth.revoke_invite(iid)
        drop = getattr(app.state, "grant_access", None)
        if drop:
            for e in gone:
                if e not in auth.users:
                    drop(e, False)
        return people_for(email, sid)

    # -- the project's picture, archive (已归档, read-only) and deleting it for good
    @app.get("/api/spaces/{sid}/picture")
    def picture(sid: str, request: Request):
        email = me(request)
        if sid not in spaces.spaces or not spaces.role(sid, email):
            raise HTTPException(404, tr("没有这个节目"))
        f = spaces.picture_file(sid)
        if not f.is_file():
            raise HTTPException(404, tr("这个节目还没有图片"))
        # the address carries ?v=<mtime>, so a new picture is a new address
        return FileResponse(f, media_type="image/png", headers={"Cache-Control": "private, max-age=31536000"})

    @app.post("/api/spaces/{sid}/picture")
    async def set_picture(sid: str, request: Request):
        """The picture as the request body (any image Pillow opens); it is cut to a centred square."""
        email = me(request)
        may_manage(email, sid)
        live(sid)
        data = await request.body()
        if not data:
            raise HTTPException(422, tr("这不是一张能打开的图片"))
        if len(data) > PICTURE_MAX:
            raise HTTPException(413, tr("图片太大了（最大 10 MB）"))
        run(lambda: spaces.set_picture(sid, data))
        return overview(request, email)

    @app.delete("/api/spaces/{sid}/picture")
    def drop_picture(sid: str, request: Request):
        email = me(request)
        may_manage(email, sid)
        live(sid)
        run(lambda: spaces.drop_picture(sid))
        return overview(request, email)

    @app.post("/api/spaces/{sid}/archive")
    def archive(sid: str, body: ArchiveBody, request: Request):
        email = me(request)
        may_manage(email, sid)
        run(lambda: spaces.archive(sid, email, body.archived))
        return overview(request, email)

    @app.delete("/api/spaces/{sid}")
    def delete(sid: str, body: DeleteBody, request: Request):
        """For good, only from 已归档, only by its creator or LACUNA's owner, with the name typed. What its
        editors taught LACUNA in it (learning/, the evidence behind learned rules) is first copied into the
        deleting person's own store; learned rules and 剪辑力度 are theirs already (habits.py)."""
        email = me(request)
        if sid not in spaces.spaces:
            raise HTTPException(404, tr("没有这个节目"))
        if not may_delete(email, sid):
            raise HTTPException(403, tr("只有节目的创建者或 LACUNA 的所有者能永久删除节目"))
        if not spaces.archived(sid):
            raise HTTPException(409, tr("先把节目归档，才能永久删除"))
        if body.confirm.strip() != spaces.title(sid):
            raise HTTPException(422, tr("节目名称不对，没有删除"))
        if not [m for m in spaces.mine(email) if m["id"] != sid]:
            raise HTTPException(409, tr("这是你唯一的节目。先新建一个节目，再删除这个"))
        learned = spaces.path(sid) / LEARN_DIR
        if learned.is_dir():
            keep = habits.home_for(spaces.root, email) / LEARN_DIR / "from_projects" / \
                f"{sid}-{time.strftime('%Y%m%d-%H%M%S')}"
            shutil.copytree(learned, keep, ignore=shutil.ignore_patterns(RULES_FILE), dirs_exist_ok=True)
        for i in auth.list_invites():
            if i.get("space") == sid:
                auth.revoke_invite(i["id"])
        with lock:
            children.pop(sid, None)
        run(lambda: spaces.delete(sid))
        res = JSONResponse(overview(request, email) | {"deleted": sid})
        if request.cookies.get(SPACE_COOKIE) == sid:
            res.delete_cookie(SPACE_COOKIE, path="/")
        return res
