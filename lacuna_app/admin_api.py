"""The admin site's API and pages (decision 2026-10-24-admin-site): its own FastAPI app, reached only through
admin.<domain> (lacuna_app/admin_host.py). Nothing of the main site's routes is mounted here.

The four doors (docs: the admin security plan):

1. Cloudflare Access for the admin host (owner only, never switched off): checked by ``AdminHost`` in the cloud.
2. An admin sign-in of its own: password + authenticator code in one step, 8 hours, no "remember me"; an email
   to the owner at every sign-in. In the cloud the email Access proved must be the one signing in.
3. ``_Gate``, one check for every ``/api/admin/*`` call, deny by default: a valid admin session of a current
   owner / admin account; for changes also the ``X-Lacuna-Admin`` header and a same-origin request (other
   websites can't make the browser send one). Owner-only actions say so (``owner=True``).
4. Dangerous actions need a fresh authenticator code (``stepup=True``: 403 ``stepup`` until one is given, then
   15 minutes). Irreversible ones also need the name typed (``confirm``). Every change goes to the audit log.

Text written by users (feedback, show names) goes out as JSON data; the admin pages show it as text only, and
the page's Content-Security-Policy runs no script but ours.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai_settings, cloud, notice_mail, plans, retention, system_terms
from .admin_metrics import AI_BUDGET, AdminData
from .admin_store import AdminStore
from .appinfo import current_version
from .auth import RANK, Auth, AuthError, MailError, norm_email
from .editor import find_api_key
from .feedback import KINDS, STATUSES, Feedback, FeedbackError, reply_mail
from .i18n import set_request_lang, reset_request_lang, speaking, tr
from .spaces import Spaces
from .speedtest import SpeedTest
from .trash import TrashError

COOKIE = "lacuna_admin"
SECURE_COOKIE = "__Host-lacuna_admin"        # https: host-only, Secure, path=/ guaranteed by the browser
HEADER = "x-lacuna-admin"
STAFF = ("owner", "admin")
OPEN = {("POST", "/api/admin/auth/login"), ("GET", "/api/admin/auth/me"), ("POST", "/api/admin/auth/logout")}
MAX_TAGS = 8
# what the owner types to turn approval off, in either language
TURN_OFF = {"关掉批准", "turn off approval"}  # i18n-ignore
SOURCES = ("xiaoyuzhou", "friend", "survey", "request", "pei", "other")
DEFAULT_TEMPLATES = [
    {"id": "fixed", "title": "已修好", "text": "谢谢！这个问题已经修好了，刷新一下页面就能用。"},          # i18n-ignore
    {"id": "noted", "title": "谢谢建议，记下了", "text": "谢谢你的建议！我们记下了，排进计划以后会在这里告诉你。"},  # i18n-ignore
    {"id": "more", "title": "需要更多信息", "text": "谢谢反馈！能再说说是在哪一集、哪一步遇到的吗？方便的话附一张截图。"},  # i18n-ignore
]


# ---------------------------------------------------------------- bodies
class LoginBody(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=400)
    code: str = Field(max_length=40)


class CodeBody(BaseModel):
    code: str = Field(max_length=40)


class EndBody(BaseModel):
    id: str | None = None


class ReplyBody(BaseModel):
    text: str | None = Field(None, max_length=8000)
    status: str | None = None
    adopted: bool | None = None
    mail: bool = True


class TagsBody(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)


class NoteBody(BaseModel):
    target: str = Field(max_length=400)
    text: str = Field(min_length=1, max_length=4000)


class TemplatesBody(BaseModel):
    items: list[dict] = Field(max_length=30)


class EmailBody(BaseModel):
    email: str = Field(max_length=320)


class UserBody(BaseModel):
    role: str | None = None
    plan: str | None = None
    disabled: bool | None = None
    reset_2fa: bool = False


class ConfirmBody(BaseModel):
    confirm: str = Field("", max_length=400)


class MailBody(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=8000)


class HoursBody(BaseModel):
    hours: float = Field(gt=0, le=200)
    note: str = Field("", max_length=500)


class SwitchBody(BaseModel):
    on: bool
    confirm: str = Field("", max_length=100)


class InviteBody(BaseModel):
    email: str = Field(max_length=320)
    role: str = "member"
    source: str | None = None
    lang: str | None = None
    plan: str | None = None


class DecideBody(BaseModel):
    action: str = Field(pattern="^(invite|dismiss|waitlist)$")
    lang: str | None = None
    source: str | None = None


class HourDecideBody(BaseModel):
    action: str = Field(pattern="^(approve|decline)$")
    hours: float | None = Field(None, gt=0, le=200)


class NumberBody(BaseModel):
    value: float = Field(ge=0, le=100000)


class BetaBody(BaseModel):
    beta_end: str | None = Field(None, max_length=10)


class RetentionBody(BaseModel):
    raw_tracks: bool | None = None
    old_exports: bool | None = None


class AiBody(BaseModel):
    first_cut_batch: bool | None = None


class QuotaBody(BaseModel):
    enforce: bool | None = None
    must_fit: bool | None = None
    staff_exempt: bool | None = None
    repeat_free: bool | None = None


class NoticeBody(BaseModel):
    on: bool
    zh: str = Field("", max_length=300)
    en: str = Field("", max_length=300)
    until: str | None = Field(None, max_length=10)


class TermsBody(BaseModel):
    terms: list[str] = Field(max_length=system_terms.MAX_TERMS * 2)


class RoleBody(BaseModel):
    role: str = Field(pattern="^(admin|member)$")


def _cookie_name(secure: bool) -> str:
    return SECURE_COOKIE if secure else COOKIE


class _Gate:
    """Deny by default: every /api/admin/* call except signing in needs a valid admin session of a current owner /
    admin; changes also need the admin's own header and a same-origin request."""

    def __init__(self, app, check):
        self.app, self.check = app, check

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/admin/"):
            return await self.app(scope, receive, send)
        req = Request(scope)
        lang = set_request_lang(req.cookies.get("lacuna_lang"))
        try:
            problem = self.check(req)
            if problem:
                status, detail = problem
                return await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)
            return await self.app(scope, receive, send)
        finally:
            reset_request_lang(lang)


def build(ctx, main_app, web_dist: Path) -> FastAPI:
    auth: Auth = ctx.provide("auth")
    spaces: Spaces = ctx.provide("spaces")
    fb: Feedback = ctx.provide("feedback")
    store: AdminStore = ctx.provide("admin_store", lambda: AdminStore(auth.db, auth.now))
    def metered():
        """The audio-hour meter (routes/quota.py, registered after the admin), when this site meters."""
        m = getattr(main_app.state, "meter", None)
        return m if m is not None and m.on else None
    data: AdminData = ctx.provide("admin_data", lambda: AdminData(auth, spaces, fb, store, ctx.ws.root, main_app.state))
    secure = bool(auth.cloud)
    cookie = _cookie_name(secure)
    app = FastAPI(title="LACUNA admin", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    # ------------------------------------------------------------ who is asking
    def session_of(req: Request) -> dict | None:
        s = store.session(req.cookies.get(cookie))
        if not s:
            return None
        u = auth.users.get(s["email"])
        if not u or u.get("disabled") or u["role"] not in STAFF:
            return None
        proven = getattr(req.state, "admin_access_email", None) if hasattr(req, "state") else None
        if auth.cloud and proven != s["email"]:
            return None                    # the person Access let in is not the one signed in
        return s | {"role": u["role"]}

    def same_origin(req: Request) -> bool:
        host = (req.headers.get("host") or "").lower()
        origin = req.headers.get("origin")
        if origin and urlparse(origin).netloc.lower() != host:
            return False
        site = req.headers.get("sec-fetch-site")
        return site in (None, "same-origin", "none")

    def check(req: Request):
        key = (req.method, req.url.path)
        if req.method not in ("GET", "HEAD") and (req.headers.get(HEADER) != "1" or not same_origin(req)):
            return 403, tr("请求被拒绝")
        if key in OPEN or (test_mode and req.url.path.startswith("/api/admin/_test/")):
            return None
        s = session_of(req)
        if not s:
            return 401, tr("请先登录后台")
        req.scope.setdefault("state", {})["admin"] = s
        store.touch(s)
        return None

    test_mode = bool(ctx.option("auth_test_reset"))
    app.add_middleware(_Gate, check=check)

    def who(req: Request) -> dict:
        s = getattr(req.state, "admin", None)
        if not s:                       # never reached: the gate answers first
            raise HTTPException(401, tr("请先登录后台"))
        return s

    def need(req: Request, owner: bool = False, stepup: bool = False) -> dict:
        s = who(req)
        if owner and s["role"] != "owner":
            raise HTTPException(403, tr("只有站长能做这件事"))
        if stepup and s["stepup"] <= auth.now():
            raise HTTPException(403, detail={"code": "stepup", "message": tr("这一步要再输一次验证码")})
        return s

    def run(fn):
        try:
            return fn()
        except AuthError as e:
            raise HTTPException(e.status, str(e))
        except FeedbackError as e:
            raise HTTPException(422, str(e))

    def ip(req: Request) -> str | None:
        return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else None)

    def mail(to: str, m: dict, what: str) -> None:
        def go():
            try:
                auth.mailer.send(auth.config["sender"], to, m["subject"], m["text"], html=m.get("html"),
                                 inline=m.get("inline"))
            except (MailError, OSError) as e:
                print(f"LACUNA: admin {what} mail failed: {e}", flush=True)
        if ctx.option("mail_inline"):
            go()
        else:
            threading.Thread(target=go, name=f"admin-{what}-mail", daemon=True).start()

    def owner_email() -> str | None:
        return next((e for e, u in auth.users.items() if u["role"] == "owner"), None)

    def main_origin(req: Request) -> str:
        """The main site's address, for links in mail (invites, replies): never the admin's own."""
        public = os.environ.get("LACUNA_PUBLIC_URL", "").strip()
        if public:
            return public.rstrip("/")
        host = req.headers.get("host") or ""
        return f"{req.url.scheme}://{host.removeprefix('admin.') or 'localhost'}"

    def admin_origin(req: Request) -> str:
        return f"{req.url.scheme}://{req.headers.get('host')}"

    def own_sessions(s: dict) -> list[dict]:
        """The signed-in person's admin sessions, the browser named in words, this one marked."""
        return [x | {"agent": notice_mail.device_label(x.get("agent", "")), "country": notice_mail.country_name(x.get("country")),
                     "current": x["id"] == s["id"]}
                for x in store.sessions(s["email"])]

    # ------------------------------------------------------------ sign-in
    @app.post("/api/admin/auth/login")
    def login(body: LoginBody, req: Request):
        email = (body.email or "").strip().lower()
        where = ip(req)
        run(lambda: auth._check_lock(email, where))
        u = auth.users.get(email)
        proven = getattr(req.state, "admin_access_email", None)
        from .auth import verify_password
        ok = bool(u) and not u.get("disabled") and verify_password(body.password or "", u["hash"])
        if ok and not u.get("totp"):
            # an account without an authenticator never gets in; staff are told why, others learn nothing
            if u["role"] in STAFF:
                raise HTTPException(403, tr("后台要求两步验证：先在主站「设置 → 账号与安全」里开启，再来登录"))
            ok = False
        if ok:
            with auth.lock:
                ok = auth._second_factor(u, body.code)
        if not ok or u["role"] not in STAFF or (auth.cloud and proven != email):
            auth._fail(email, where)
            raise HTTPException(401, tr("邮箱、密码或验证码不对"))
        auth.fails.pop(email, None)
        agent = req.headers.get("user-agent", "")
        country = req.headers.get("cf-ipcountry")
        token = store.new_session(email, agent, where, country)
        store.audit(email, "admin.login", email, device=notice_mail.device_label(agent), country=country)
        when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(auth.now()))
        for to in {owner_email(), email} - {None}:
            with speaking((auth.users.get(to) or {}).get("lang") or "zh"):
                m = notice_mail.render(tr("有人登录了 LACUNA 后台"), tr("{email} 刚刚登录了后台。", email=email),
                                       [(tr("时间"), when), (tr("设备"), notice_mail.device_label(agent))]
                                       + ([(tr("大致位置"), notice_mail.country_name(country) or country)] if country else []),
                                       tr("查看后台登录"), f"{admin_origin(req)}/settings",
                                       tr("是你本人就不用管。不是你的话，马上在后台「系统设置」里退出所有后台登录，并改密码。"),
                                       tr("安全提醒 · SECURITY"))
            mail(to, m, "login")
        res = JSONResponse({"ok": True, **me_view(email)})
        res.set_cookie(cookie, token, max_age=None, httponly=True, samesite="strict", path="/", secure=secure)
        return res

    def me_view(email: str, s: dict | None = None) -> dict:
        u = auth.users[email]
        return {"email": email, "name": u.get("name"), "role": u["role"], "lang": u.get("lang"),
                "exp": s["exp"] if s else auth.now() + 8 * 3600, "stepup": s["stepup"] if s else 0,
                "owner": owner_email(), "now": auth.now()}

    @app.get("/api/admin/auth/me")
    def me(req: Request):
        s = session_of(req)
        if not s:
            raise HTTPException(401, tr("请先登录后台"))
        return me_view(s["email"], s)

    @app.post("/api/admin/auth/logout")
    def logout(req: Request):
        s = store.session(req.cookies.get(cookie))
        if s:
            store.end(s["hash"])
        res = JSONResponse({"ok": True})
        res.delete_cookie(cookie, path="/", secure=secure, httponly=True, samesite="strict")
        return res

    @app.post("/api/admin/auth/stepup")
    def stepup(body: CodeBody, req: Request):
        s = who(req)
        run(lambda: auth._check_lock(s["email"], ip(req)))
        u = auth.users[s["email"]]
        tf = u.get("totp") or {}
        from . import totp
        step = totp.match(tf.get("secret", ""), body.code, auth.now(), tf.get("last", -1)) if tf else None
        if step is None:
            auth._fail(s["email"], ip(req))
            raise HTTPException(401, tr("验证码不对"))
        with auth.lock:
            tf["last"] = step
            auth._save_users()
        until = store.step_up(s)
        store.audit(s["email"], "admin.stepup", s["email"])
        return {"stepup": until}

    @app.get("/api/admin/auth/sessions")
    def my_sessions(req: Request):
        s = who(req)
        return {"sessions": own_sessions(s)}

    @app.post("/api/admin/auth/sessions/end")
    def end_sessions(body: EndBody, req: Request):
        s = who(req)
        n = store.end_for(s["email"], body.id, keep=s["hash"])
        store.audit(s["email"], "admin.sessions.end", body.id or "others", n=n)
        return {"ended": n, "sessions": own_sessions(s)}

    # ------------------------------------------------------------ home
    @app.get("/api/admin/overview")
    def overview(req: Request):
        who(req)
        return data.overview()

    # ------------------------------------------------------------ feedback
    def fb_items() -> list[dict]:
        tags = store.get("fb_tags", {})
        notes = store.note_counts("fb:")
        users = auth.users
        out = []
        for it in fb.all():
            if it["kind"] not in KINDS:
                continue                    # the one-question answers have their own tab
            sid = (it.get("show") or {}).get("id")
            u = users.get(it["email"]) or {}
            out.append(it | {"profile": fb.profile(sid) if sid else None, "name": u.get("name"),
                             "plan": u.get("plan"), "joined": u.get("created"), "tags": tags.get(it["id"], []),
                             "notes": notes.get(f"fb:{it['id']}", 0)})
        return out

    @app.get("/api/admin/feedback")
    def feedback(req: Request):
        who(req)
        return {"items": fb_items(), "statuses": list(STATUSES), "templates": store.get("templates", DEFAULT_TEMPLATES),
                "known_tags": sorted({t for ts in store.get("fb_tags", {}).values() for t in ts})}

    @app.get("/api/admin/feedback/{fid}/shot")
    def feedback_shot(fid: str, req: Request):
        who(req)
        path = fb.shot_path(fid) if fb.get(fid) else None
        if not path:
            raise HTTPException(404, tr("没有截图"))
        return FileResponse(path, media_type="image/jpeg" if path.suffix == ".jpg" else "image/png",
                            headers={"Cache-Control": "private, no-store", "Content-Disposition": "inline"})

    @app.post("/api/admin/feedback/{fid}/reply")
    def feedback_reply(fid: str, body: ReplyBody, req: Request):
        s = who(req)
        if fb.get(fid) is None:
            raise HTTPException(404, tr("没有这条反馈"))
        item = run(lambda: fb.reply(fid, body.text, body.status, body.adopted))
        person = auth.users.get(item["email"])
        mailed = False
        if body.mail and person and (body.text or body.adopted):
            with speaking(person.get("lang") or "zh"):
                m = reply_mail(item, f"{main_origin(req).rstrip('/')}/#/feedback")
            mail(item["email"], m, "feedback-reply")
            mailed = True
        store.audit(s["email"], "feedback.reply", fid, status=body.status, adopted=body.adopted,
                    replied=bool(body.text), mailed=mailed)
        return {"item": next((x for x in fb_items() if x["id"] == fid), item), "mailed": mailed}

    @app.put("/api/admin/feedback/{fid}/tags")
    def feedback_tags(fid: str, body: TagsBody, req: Request):
        s = who(req)
        if fb.get(fid) is None:
            raise HTTPException(404, tr("没有这条反馈"))
        clean = []
        for t in body.tags:
            t = " ".join(str(t).split())[:24]
            if t and t not in clean:
                clean.append(t)
        tags = store.get("fb_tags", {})
        tags[fid] = clean
        store.put("fb_tags", {k: v for k, v in tags.items() if v})
        store.audit(s["email"], "feedback.tags", fid, tags=len(clean))
        return {"tags": clean}

    @app.post("/api/admin/feedback/prompt-reset")
    def prompt_reset(body: EmailBody, req: Request):
        s = need(req, stepup=True)
        email = body.email.strip().lower()
        if email not in auth.users:
            raise HTTPException(404, tr("没有这个账号"))
        fb.reset_prompts(email)
        store.audit(s["email"], "feedback.prompt_reset", email)
        return {"ok": True}

    @app.get("/api/admin/feedback/prompts")
    def prompts(req: Request):
        who(req)
        return data.prompts() | {"profiles": data.profiles()}

    @app.get("/api/admin/templates")
    def templates(req: Request):
        who(req)
        return {"items": store.get("templates", DEFAULT_TEMPLATES)}

    @app.put("/api/admin/templates")
    def set_templates(body: TemplatesBody, req: Request):
        s = who(req)
        items = [{"id": str(i.get("id") or n)[:40], "title": str(i.get("title") or "")[:60], "text": str(i.get("text") or "")[:4000]}
                 for n, i in enumerate(body.items) if str(i.get("title") or "").strip() and str(i.get("text") or "").strip()]
        store.put("templates", items)
        store.audit(s["email"], "templates.save", "", n=len(items))
        return {"items": items}

    # ------------------------------------------------------------ notes (feedback items and people)
    def note_target(target: str) -> str:
        kind, _, key = target.partition(":")
        if kind == "fb" and fb.get(key):
            return target
        if kind == "user" and key in auth.users:
            return target
        raise HTTPException(404, tr("没有这个对象"))

    @app.get("/api/admin/notes")
    def notes(target: str, req: Request):
        who(req)
        return {"notes": store.notes(note_target(target))}

    @app.post("/api/admin/notes")
    def add_note(body: NoteBody, req: Request):
        s = who(req)
        row = store.add_note(note_target(body.target), s["email"], body.text)
        store.audit(s["email"], "note.add", body.target)
        return {"note": row, "notes": store.notes(body.target)}

    # ------------------------------------------------------------ people
    @app.get("/api/admin/users")
    def users(req: Request):
        who(req)
        return {"users": data.users(), "plans": plans.public()}

    def user_or_404(email: str) -> dict:
        u = auth.users.get(email.strip().lower())
        if not u:
            raise HTTPException(404, tr("没有这个账号"))
        return u

    @app.get("/api/admin/users/{email}")
    def user(email: str, req: Request):
        who(req)
        u = user_or_404(email)
        e = u["email"]
        row = next((r for r in data.users() if r["email"] == e), {})
        sessions = sorted(({"created": v["created"], "seen": v.get("seen", v["created"]),
                            "device": notice_mail.device_label(v.get("agent", ""))}
                           for v in auth.sessions.values() if v["email"] == e and v["exp"] > auth.now()),
                          key=lambda x: -x["seen"])
        return {"user": row, "shows": spaces.mine(e, detail=True), "activity": data.user_activity(e),
                "sessions": sessions, "devices": len(u.get("devices") or []), "notes": store.notes(f"user:{e}"),
                "hours": store.hour_requests(email=e), "feedback": [f for f in fb.all() if f["email"] == e][:20],
                "bonus_hours": sum(float(x.get("granted") or 0) for x in store.hour_requests(email=e) if x["status"] == "approved"),
                "admin_sessions": [x | {"agent": notice_mail.device_label(x.get("agent", ""))} for x in store.sessions(e)]}

    @app.post("/api/admin/users/{email}")
    def update_user(email: str, body: UserBody, req: Request):
        u = user_or_404(email)
        s = need(req, owner=body.role is not None, stepup=True)
        run(lambda: auth.update_user(s["email"], u["email"], body.role, body.disabled, body.reset_2fa, body.plan))
        if body.disabled:
            store.end_for(u["email"])
        if body.role == "member":
            store.end_for(u["email"])
        store.audit(s["email"], "user.update", u["email"], role=body.role, plan=body.plan, disabled=body.disabled,
                    reset_2fa=body.reset_2fa)
        return user(u["email"], req)

    @app.delete("/api/admin/users/{email}")
    def delete_user(email: str, req: Request):
        u = user_or_404(email)
        s = need(req, stepup=True)
        run(lambda: auth.delete_user(s["email"], u["email"]))
        store.end_for(u["email"])
        grant = getattr(main_app.state, "grant_access", None)
        if grant:
            grant(u["email"], False)
        store.audit(s["email"], "user.delete", u["email"])
        return {"ok": True}

    @app.post("/api/admin/users/{email}/erase")
    def erase_user(email: str, body: ConfirmBody, req: Request):
        """立即彻底删除 (owner): the account and the shows only they are in go now, not in 60 days."""
        u = user_or_404(email)
        s = need(req, owner=True, stepup=True)
        target = u["email"]
        if body.confirm.strip().lower() != target:
            raise HTTPException(422, tr("输入的邮箱不对"))
        if target == s["email"]:
            raise HTTPException(403, tr("不能删除你自己"))
        alone = [sid for sid, sp in spaces.spaces.items() if set(sp["members"]) == {target}]
        for sid in alone:
            run(lambda: spaces.delete(sid, s["email"]))
        run(lambda: auth.delete_user(s["email"], target))
        spaces.trash.drop_user(target)
        for item in spaces.trash.items():
            if item["kind"] == "show" and item["id"].rsplit("-", 1)[0] in alone:
                spaces.trash.drop(item["id"])
        store.end_for(target)
        store.forget(target)
        grant = getattr(main_app.state, "grant_access", None)
        if grant:
            grant(target, False)
        store.audit(s["email"], "user.erase", target, shows=len(alone))
        return {"ok": True, "shows": len(alone)}

    @app.post("/api/admin/users/{email}/mail")
    def mail_user(email: str, body: MailBody, req: Request):
        u = user_or_404(email)
        s = who(req)
        lead = body.text.strip()
        with speaking(u.get("lang") or "zh"):
            m = notice_mail.render(body.subject.strip(), lead, [], None, None,
                                   tr("这封信来自 LACUNA 团队。直接回复就能联系到我们。"), tr("来自 LACUNA · FROM LACUNA"))
        mail(u["email"], m, "user")
        store.audit(s["email"], "user.mail", u["email"], subject=body.subject[:80])
        return {"ok": True}

    @app.post("/api/admin/users/{email}/hours")
    def give_hours(email: str, body: HoursBody, req: Request):
        u = user_or_404(email)
        s = need(req, owner=True, stepup=True)
        r = store.add_hour_request(u["email"], body.hours, body.note or "", False)
        store.decide_hours(r["id"], "approved", s["email"], body.hours)
        store.audit(s["email"], "hours.give", u["email"], hours=body.hours)
        return user(u["email"], req)

    @app.post("/api/admin/users/{email}/sessions/end")
    def end_user_sessions(email: str, req: Request):
        u = user_or_404(email)
        s = need(req, stepup=True)
        with auth.lock:
            auth._end_all(u["email"])
        store.audit(s["email"], "user.sessions.end", u["email"])
        return user(u["email"], req)

    # ------------------------------------------------------------ invites and requests
    def access_view() -> dict:
        reqs = data.requests()
        invited = store.get("invited_sources", {})
        approval = getattr(main_app.state, "owner_approval", lambda: True)()
        return {"trials": [r for r in reqs if r.get("kind") != "collab"],
                "collabs": [r | {"by_name": auth.name(r.get("by"))} for r in reqs if r.get("kind") == "collab"],
                "waitlist": data.requests("waitlist"),
                "invites": [i | {"source": invited.get(i["email"])} for i in auth.list_invites()],
                "seats": data.seats(), "approval": approval, "sources": data.sources(), "source_ids": list(SOURCES)}

    @app.get("/api/admin/access")
    def access(req: Request):
        who(req)
        return access_view()

    @app.put("/api/admin/access/approval")
    def approval(body: SwitchBody, req: Request):
        s = need(req, owner=True, stepup=True)
        if not body.on and body.confirm.strip().lower() not in TURN_OFF:
            raise HTTPException(422, tr("要输入「关掉批准」才能关"))
        auth.db.set_meta("owner_approval", "1" if body.on else "0")
        store.audit(s["email"], "site.new_members", "", on=body.on)
        return access_view()

    @app.put("/api/admin/access/seats")
    def seats(body: NumberBody, req: Request):
        s = need(req, owner=True)
        store.put("beta_seats", int(body.value))
        store.audit(s["email"], "beta.seats", "", seats=int(body.value))
        return access_view()

    def remember_source(email: str, source: str | None) -> None:
        if source in SOURCES:
            inv = store.get("invited_sources", {})
            inv[email] = source
            store.put("invited_sources", inv)

    def send_invite(actor: str, email: str, role: str, req: Request, where: dict, lang: str | None,
                    plan: str | None = None) -> dict:
        extra = dict(where)
        if plan:
            extra["plan"] = plan
        out = run(lambda: auth.invite(actor, email, role, main_origin(req), extra, lang))
        grant = getattr(main_app.state, "grant_access", None)
        if grant:
            grant(out["email"], True)
        return out

    @app.post("/api/admin/invites")
    def invite(body: InviteBody, req: Request):
        s = need(req, owner=body.role != "member")
        email = run(lambda: norm_email(body.email))
        check = getattr(main_app.state, "invite_space", None)
        where = run(lambda: check(s["email"], "new", None)) if check else {"space": "new"}
        out = send_invite(s["email"], email, body.role, req, where or {"space": "new"}, body.lang, body.plan)
        remember_source(email, body.source)
        store.audit(s["email"], "invite.send", email, role=body.role, source=body.source)
        return {"link": out["link"], "mailed": out["mailed"], "mail_error": out["mail_error"], **access_view()}

    def invite_by_id(iid: str) -> dict:
        found = [i for i in auth.invites.values() if i["hash"][:16] == iid and i["exp"] > auth.now()]
        if not found:
            raise HTTPException(404, tr("这个邀请已经没有了"))
        return found[0]

    @app.post("/api/admin/invites/{iid}/resend")
    def resend(iid: str, req: Request):
        s = who(req)
        i = invite_by_id(iid)
        if RANK.get(auth.role(s["email"]) or "", 0) <= RANK.get(i["role"], 0):
            raise HTTPException(403, tr("只有站长能做这件事"))
        where = {k: i[k] for k in ("space", "space_role", "also") if i.get(k)}
        out = send_invite(s["email"], i["email"], i["role"], req, where, i.get("lang"), i.get("plan"))
        store.audit(s["email"], "invite.resend", i["email"])
        return {"link": out["link"], "mailed": out["mailed"], "mail_error": out["mail_error"], **access_view()}

    @app.delete("/api/admin/invites/{iid}")
    def revoke(iid: str, req: Request):
        s = who(req)
        i = invite_by_id(iid)
        for email in auth.revoke_invite(i["hash"][:16]):
            if email not in auth.users:
                grant = getattr(main_app.state, "grant_access", None)
                if grant:
                    grant(email, False)
        store.audit(s["email"], "invite.revoke", i["email"])
        return access_view()

    @app.post("/api/admin/requests/{rid}")
    def decide(rid: str, body: DecideBody, req: Request):
        s = who(req)
        found = auth.db.query("SELECT * FROM access_requests WHERE id = ?", (rid,))
        if not found:
            raise HTTPException(404, tr("这个申请已经没有了"))
        from . import db as sitedb
        row = sitedb.loads(found[0]["data"])
        out: dict = {}
        if body.action == "invite":
            where = {"space": "new"}
            if row.get("kind") == "collab":
                where = run(lambda: main_app.state.invite_space(s["email"], row.get("space"), row.get("space_role")))
            sent = send_invite(s["email"], row["email"], "member", req, where, body.lang or row.get("lang"))
            remember_source(row["email"], body.source or ("request" if row.get("kind") != "collab" else None))
            out = {"link": sent["link"], "mailed": sent["mailed"], "mail_error": sent["mail_error"]}
        status = {"invite": "invited", "dismiss": "dismissed", "waitlist": "waitlist"}[body.action]
        with auth.db.tx() as c:
            c.execute("UPDATE access_requests SET status = ? WHERE id = ?", (status, rid))
        if body.action == "dismiss" and row.get("kind") == "collab" and row.get("by") in auth.users:
            asker = auth.users[row["by"]]
            with speaking(asker.get("lang") or row.get("lang") or "zh"):
                m = notice_mail.collab_declined(row["email"], row.get("show") or "")
            mail(asker["email"], m, "collab-declined")
        store.audit(s["email"], f"request.{body.action}", row["email"], kind=row.get("kind") or "trial")
        return access_view() | out

    # ------------------------------------------------------------ hours
    def hours_view() -> dict:
        rows = data.users()
        reqs = store.hour_requests()
        pay = [r for r in reqs if r.get("would_pay")]
        return {"requests": [r | {"name": auth.name(r["email"]), "plan": (auth.users.get(r["email"]) or {}).get("plan")}
                             for r in reqs if r["status"] == "new"],
                "decided": [r | {"name": auth.name(r["email"])} for r in reqs if r["status"] != "new"][:50],
                "usage": [{"email": r["email"], "name": r["name"], "plan": r["plan"], "hours": r["hours"],
                           "used": r["hours_used"], "bonus": r.get("bonus"), "once": r.get("hours_once")}
                          for r in rows if r["role"] == "member"],
                "plans": plans.public(), "beta_end": store.get("beta_end"),
                "quota": metered().settings() if metered() else None,
                "month_hours": metered().month_total() if metered() else None,
                "willing": [{"email": r["email"], "name": auth.name(r["email"]), "at": r["created"], "reason": r.get("reason"),
                             "where": "hours"} for r in pay]}

    @app.get("/api/admin/hours")
    def hours(req: Request):
        who(req)
        return hours_view()

    @app.post("/api/admin/hours/{rid}")
    def decide_hours(rid: str, body: HourDecideBody, req: Request):
        r = store.hour_request(rid)
        if not r or r["status"] != "new":
            raise HTTPException(404, tr("这个申请已经没有了"))
        s = need(req, owner=True, stepup=body.action == "approve")
        granted = float(body.hours or r["hours"]) if body.action == "approve" else 0
        store.decide_hours(rid, "approved" if body.action == "approve" else "declined", s["email"], granted)
        u = auth.users.get(r["email"])
        if u:
            with speaking(u.get("lang") or "zh"):
                if body.action == "approve":
                    m = notice_mail.render(tr("你的时长申请批下来了"), tr("这个月多给你 {n} 小时。", n=int(granted) if granted == int(granted) else granted), [],
                                           tr("打开 LACUNA"), main_origin(req), tr("谢谢你用 LACUNA。"), tr("时长 · HOURS"))
                else:
                    m = notice_mail.render(tr("关于你的时长申请"), tr("这次没能给你加时长。有问题直接回复这封信。"), [],
                                           None, None, tr("谢谢你用 LACUNA。"), tr("时长 · HOURS"))
            mail(r["email"], m, "hours")
        store.audit(s["email"], f"hours.{body.action}", r["email"], hours=granted)
        return hours_view()

    @app.put("/api/admin/hours/settings")
    def hours_settings(body: BetaBody, req: Request):
        s = need(req, owner=True)
        store.put("beta_end", body.beta_end or None)
        store.audit(s["email"], "beta.end", "", beta_end=body.beta_end)
        return hours_view()

    @app.put("/api/admin/hours/quota")
    def quota_settings(body: QuotaBody, req: Request):
        """The metering rules (quota.py), while the business model is being decided."""
        s = need(req, owner=True)
        meter = metered()
        if meter is None:
            raise HTTPException(409, tr("这个站点不计量音频时长"))
        changes = body.model_dump(exclude_none=True)
        meter.save_settings(changes)
        store.audit(s["email"], "quota.rules", "", **changes)
        return hours_view()

    # ------------------------------------------------------------ shows
    @app.get("/api/admin/shows")
    def shows(req: Request):
        who(req)
        return data.shows()

    @app.post("/api/admin/shows/{sid}/open")
    def open_show(sid: str, req: Request):
        s = who(req)
        if sid not in spaces.spaces:
            raise HTTPException(404, tr("没有这个节目"))
        store.audit(s["email"], "show.open", spaces.title(sid))
        return {"url": main_origin(req), "support": spaces.support_until(sid)}

    # ------------------------------------------------------------ recycle bin
    def trash_view() -> dict:
        sizes = data.sizes()["trash"]
        return {"items": [i | {"size": sizes.get(i["id"])} for i in spaces.trash.items()], "keep_days": 60}

    @app.get("/api/admin/trash")
    def trash(req: Request):
        who(req)
        return trash_view()

    @app.post("/api/admin/trash/{kind}/{tid}/restore")
    def restore(kind: str, tid: str, req: Request):
        s = need(req, stepup=True)
        if kind == "show":
            try:
                spaces.restore(tid)
            except TrashError:
                raise HTTPException(404, tr("回收区里没有这个节目"))
            except AuthError as e:
                raise HTTPException(e.status, str(e))
        elif kind == "user":
            try:
                rec = spaces.trash.user(tid)
            except TrashError:
                raise HTTPException(404, tr("回收区里没有这个账号"))
            run(lambda: auth.restore_user(rec["user"]))
            for sid, role in (rec.get("shows") or {}).items():
                if sid in spaces.spaces and not spaces.sample(sid):
                    spaces.set_member(sid, tid, role)
            spaces.trash.drop_user(tid)
        else:
            raise HTTPException(404, tr("没有这个对象"))
        store.audit(s["email"], f"trash.restore.{kind}", tid)
        return trash_view()

    @app.post("/api/admin/trash/{kind}/{tid}/purge")
    def purge(kind: str, tid: str, body: ConfirmBody, req: Request):
        s = need(req, owner=True, stepup=True)
        item = next((i for i in spaces.trash.items() if i["kind"] == kind and i["id"] == tid), None)
        if not item:
            raise HTTPException(404, tr("回收区里没有这个"))
        if body.confirm.strip() != (item.get("name") or item["id"]):
            raise HTTPException(422, tr("输入的名字不对"))
        if kind == "show":
            spaces.trash.drop(tid)
        else:
            spaces.trash.drop_user(tid)
        store.audit(s["email"], f"trash.purge.{kind}", item.get("name") or tid)
        return trash_view()

    # ------------------------------------------------------------ AI, growth, system
    @app.get("/api/admin/ai")
    def ai(req: Request):
        who(req)
        return data.ai()

    @app.put("/api/admin/ai/budget")
    def budget(body: NumberBody, req: Request):
        s = need(req, owner=True)
        store.put("ai_budget", round(body.value, 2))
        store.audit(s["email"], "ai.budget", "", usd=round(body.value, 2))
        return data.ai()

    @app.get("/api/admin/growth")
    def growth(req: Request, weeks: int = 8):
        who(req)
        return data.growth(max(4, min(26, weeks)))

    @app.get("/api/admin/system")
    def system(req: Request):
        who(req)
        sizes = data.sizes()
        return {"disk": data.disk(), "parts": sizes["parts"], "sizes_at": sizes["at"], "backup": data.backup(),
                "running": data.running(), "samples": data.samples, "errors": store.errors(auth.now() - 86400),
                "started": data.started, "version": current_version(), "alerts": data.alerts(),
                "cpus": os.cpu_count(), "storage": storage_view(), "ai": ai_settings.settings(auth.db)}

    def storage_view() -> dict:
        """存储与保留: cloud storage for old episodes' audio (cold.py) and how long audio is kept (retention.py)."""
        cold = getattr(main_app.state, "cold", None)
        return {"retention": retention.settings(auth.db),
                "cold": {"on": bool(cold is not None and cold.on), "moving": bool(cold is not None and cold.freezing),
                         "bytes": cold.stored_bytes([ctx.ws.root]) if cold is not None and cold.on else 0,
                         "after_days": round(cold.after_s / 86400) if cold is not None else 14}}

    @app.put("/api/admin/storage/retention")
    def retention_settings(body: RetentionBody, req: Request):
        """Raw-track retention (off during the beta) and keeping only the latest export."""
        s = need(req, owner=True)
        changes = body.model_dump(exclude_none=True)
        retention.save_settings(auth.db, changes)
        store.audit(s["email"], "storage.retention", "", **changes)
        return storage_view()

    def bucket():
        cold = getattr(main_app.state, "cold", None)
        return cold.bucket if cold is not None and cold.on else None

    speed = SpeedTest(bucket, ctx.ws.root / ".speedtest")

    @app.get("/api/admin/storage/speed")
    def speed_view(req: Request):
        """测速 (batch 7, S1): the last server ↔ cloud storage test, or the one running."""
        need(req, owner=True)
        return speed.view()

    @app.post("/api/admin/storage/speed")
    def speed_start(req: Request):
        """Send a 200 MB test file to the cloud storage and back, then delete it. Owner only; not on staging."""
        s = need(req, owner=True)
        if cloud.staging():
            raise HTTPException(409, tr("staging 站点不测速，请在正式站测。"))
        try:
            out = speed.start()
        except ValueError as e:
            raise HTTPException(409, str(e))
        store.audit(s["email"], "storage.speedtest", "")
        return out

    @app.put("/api/admin/ai")
    def ai_switches(body: AiBody, req: Request):
        """AI 省钱: the first cut through the Batch API (half price, imports slower); off by default."""
        s = need(req, owner=True)
        changes = body.model_dump(exclude_none=True)
        out = ai_settings.save_settings(auth.db, changes)
        store.audit(s["email"], "ai.settings", "", **changes)
        return out

    # ------------------------------------------------------------ settings
    def settings_view(s: dict) -> dict:
        key, where = find_api_key()
        staff = [{"email": e, "name": u.get("name"), "role": u["role"], "twofa": bool(u.get("totp")),
                  "last_admin": store.last_login(e)} for e, u in auth.users.items() if u["role"] in STAFF]
        return {"notice": store.get("notice", {"on": False, "zh": "", "en": "", "until": None}),
                "maintenance": store.get("maintenance", {"on": False}),
                "staff": sorted(staff, key=lambda x: x["role"] != "owner"),
                "sessions": own_sessions(s),
                "terms": system_terms.load(ctx.ws.root), "mail": auth.mail_status(),
                "key": {"present": bool(key), "source": where if key else None},
                "turnstile": bool(os.environ.get("TURNSTILE_SITE_KEY")),
                "access": cloud.access_required() if cloud.enabled() else None, "cloud": cloud.enabled(),
                "digest": {"hour": 8, "tz": "America/Vancouver", "last": store.get("digest_last")},
                "budget": float(store.get("ai_budget", AI_BUDGET))}

    @app.get("/api/admin/settings")
    def settings(req: Request):
        return settings_view(who(req))

    @app.put("/api/admin/settings/notice")
    def notice(body: NoticeBody, req: Request):
        s = who(req)
        store.put("notice", {"on": body.on, "zh": body.zh.strip(), "en": body.en.strip(), "until": body.until or None,
                             "at": auth.now()})
        store.audit(s["email"], "site.notice", "", on=body.on)
        return settings_view(s)

    @app.put("/api/admin/settings/maintenance")
    def maintenance(body: SwitchBody, req: Request):
        s = need(req, owner=True, stepup=True)
        store.put("maintenance", {"on": body.on, "at": auth.now(), "by": s["email"]})
        store.audit(s["email"], "site.maintenance", "", on=body.on)
        return settings_view(s)

    @app.put("/api/admin/settings/terms")
    def terms(body: TermsBody, req: Request):
        s = who(req)
        system_terms.save(ctx.ws.root, body.terms, s["email"])
        store.audit(s["email"], "site.terms", "", n=len(body.terms))
        return settings_view(s)

    @app.post("/api/admin/settings/test-mail")
    def test_mail(req: Request):
        s = who(req)
        run(lambda: auth.test_mail(s["email"]))
        store.audit(s["email"], "mail.test", s["email"])
        return {"sent": True, "to": s["email"]}

    @app.put("/api/admin/settings/staff/{email}")
    def staff_role(email: str, body: RoleBody, req: Request):
        u = user_or_404(email)
        s = need(req, owner=True, stepup=True)
        run(lambda: auth.update_user(s["email"], u["email"], role=body.role))
        if body.role == "member":
            store.end_for(u["email"])
        store.audit(s["email"], "staff.role", u["email"], role=body.role)
        return settings_view(s)

    # ------------------------------------------------------------ audit
    @app.get("/api/admin/audit")
    def audit(req: Request, before: float | None = None, limit: int = 200):
        who(req)
        return {"rows": store.audit_rows(limit, before)}

    if test_mode:
        @app.get("/api/admin/_test/code")
        def _test_code(email: str):
            """E2E only: the authenticator code an account would show now (next unused step)."""
            from . import totp
            u = auth.users.get(email.lower()) or {}
            tf = u.get("totp") or {}
            if not tf:
                raise HTTPException(404)
            step = max(int(auth.now() // totp.STEP), tf.get("last", -1) + 1)
            return {"code": totp.code_at(tf["secret"], step)}

        @app.post("/api/admin/_test/clear")
        def _test_clear():
            """E2E only: the site-wide switches set in the admin (notice, maintenance) back off, so a spec that
            stopped halfway leaves nothing on the main site for the next one."""
            store.put("notice", {"on": False, "zh": "", "en": "", "until": None})
            store.put("maintenance", {"on": False})
            return {"ok": True}

        @app.post("/api/admin/_test/seed")
        def _test_seed(req: Request, password: str = "correct horse battery"):
            """E2E only, on a server with no accounts (after /api/auth/_test/reset): the owner with an
            authenticator, a member invited by them, and one piece of feedback from the member."""
            from . import totp
            owner, member = "leon@example.com", "pei@example.com"
            run(lambda: auth.register_first(owner, password, None, False, name="Leon"))
            secret = auth.start_2fa(owner)["secret"]
            run(lambda: auth.confirm_2fa(owner, totp.code_at(secret, int(auth.now() // totp.STEP) - 1)))
            link = run(lambda: auth.invite(owner, member, "member", main_origin(req), {"space": "new"}, "zh"))["link"]
            run(lambda: auth.register_invite(link.rsplit("/", 1)[1], password, False, name="Pei"))
            run(lambda: fb.add(member, "bug", "<b>导出按钮</b> 点了没反应", context={"page": "/export"}))  # i18n-ignore
            return {"owner": owner, "member": member}

    # ------------------------------------------------------------ the pages
    @app.get("/api/version")
    def version():
        return {"version": current_version()}

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def no_api(rest: str):
        raise HTTPException(404)

    page = web_dist / "admin.html"
    if (web_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if page.is_file():
            return FileResponse(page, headers={"Cache-Control": "no-store"})
        return Response("<p>LACUNA admin. Build the UI: <code>cd web && npm run build</code></p>", media_type="text/html")

    return app
