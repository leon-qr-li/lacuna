"""用户反馈 (lacuna_app/feedback.py): the 反馈 panel, 我的反馈, the one-question prompts and a show's three questions.

For everyone signed in:
  POST /api/feedback            write one (遇到问题 / 我有个想法 / 夸一句), with the page it came from and a screenshot
  GET  /api/feedback/mine       我的反馈 and how many have an answer not looked at yet (the red dot)
  POST /api/feedback/mine/seen  they looked
  GET  /api/feedback/prompt     after an export: which question to ask now, if any
  POST /api/feedback/prompt     its answer, or 以后再说 / 不再问我
  POST /api/feedback/profile    a new show's three questions
For the site owner and admins (until the admin pages exist, decision 2026-10-24-user-feedback):
  GET  /api/feedback/all, POST /api/feedback/{id}/reply (mails the person), GET /api/feedback/{id}/shot,
  POST /api/feedback/prompt/reset (ask someone the one-question prompts again, for testing)
"""
from __future__ import annotations

import threading

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import appinfo, show
from ..auth import COOKIE, Auth, MailError
from ..feedback import Feedback, FeedbackError, reply_mail
from ..i18n import speaking, tr
from ..notice_mail import device_label
from ..spaces import Spaces
from .spaces import SPACE_COOKIE

STAFF = ("owner", "admin")


class NewBody(BaseModel):
    kind: str
    text: str = Field("", max_length=8000)
    source: str = "button"
    context: dict = Field(default_factory=dict)
    importance: str | None = None
    quote_ok: bool = False
    platforms: list[str] = Field(default_factory=list)
    shot: str | None = Field(None, max_length=9_000_000)


class PromptBody(BaseModel):
    kind: str
    outcome: str                      # sent / later / never
    answer: dict = Field(default_factory=dict)


class ProfileBody(BaseModel):
    show: str | None = None           # default: the show the person is in
    lang: str | None = None
    region: str | None = None
    editing: str | None = None


class ResetBody(BaseModel):
    email: str = Field(..., max_length=320)


class ReplyBody(BaseModel):
    text: str | None = Field(None, max_length=8000)
    status: str | None = None
    adopted: bool | None = None


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth: Auth = ctx.provide("auth")
    spaces: Spaces = ctx.provide("spaces", lambda: Spaces(ctx.ws.root))
    fb: Feedback = ctx.provide("feedback", lambda: Feedback(auth.db, ctx.ws.root, auth.now))
    auth.on_deleted.append(fb.forget)

    def me(request: Request) -> str:
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        return email

    def staff(request: Request) -> str:
        email = me(request)
        if auth.role(email) not in STAFF:
            raise HTTPException(403, tr("只有站长能看"))
        return email

    def show_of(email: str, request: Request) -> dict | None:
        sid = spaces.current(email, request.cookies.get(SPACE_COOKIE))
        return {"id": sid, "name": spaces.title(sid)} if sid else None

    def fail(e: FeedbackError):
        raise HTTPException(422, str(e))

    @app.post("/api/feedback")
    def new(body: NewBody, request: Request):
        email = me(request)
        context = dict(body.context)
        context["browser"] = device_label(request.headers.get("user-agent", ""))
        try:
            item = fb.add(email, body.kind, body.text, source=body.source, context=context, importance=body.importance,
                          quote_ok=body.quote_ok, platforms=body.platforms, shot=body.shot,
                          show=show_of(email, request), version=appinfo.current_version())
        except FeedbackError as e:
            fail(e)
        return {"id": item["id"], "items": fb.mine(email), "unread": fb.unread(email)}

    @app.get("/api/feedback/mine")
    def mine(request: Request):
        email = me(request)
        return {"items": fb.mine(email), "unread": fb.unread(email)}

    @app.post("/api/feedback/mine/seen")
    def seen(request: Request):
        email = me(request)
        fb.seen(email)
        return {"items": fb.mine(email), "unread": 0}

    def exported(email: str) -> int:
        """The person's own episodes (not in a sample show) that they started an export of."""
        uid = auth.user_id(email)
        if not uid:
            return 0
        rows = auth.db.query("SELECT DISTINCT sid, ep FROM events WHERE uid = ? AND ev = 'export.start' AND ep IS NOT NULL",
                             (uid,))
        return len({(r["sid"], r["ep"]) for r in rows if not spaces.sample(r["sid"])})

    @app.get("/api/feedback/prompt")
    def prompt(request: Request):
        email = me(request)
        if spaces.sample(spaces.current(email, request.cookies.get(SPACE_COOKIE))):
            return {"ask": None}            # the sample show's tour has its own export step
        return {"ask": fb.due(email, exported(email)), "exported": exported(email)}

    @app.post("/api/feedback/prompt")
    def answer(body: PromptBody, request: Request):
        email = me(request)
        try:
            if body.outcome == "sent":
                fb.answer(email, body.kind, body.answer, show=show_of(email, request), version=appinfo.current_version())
            fb.prompt_result(email, body.kind, body.outcome)
        except FeedbackError as e:
            fail(e)
        return {"ok": True}

    @app.post("/api/feedback/profile")
    def profile(body: ProfileBody, request: Request):
        email = me(request)
        sid = body.show or spaces.current(email, request.cookies.get(SPACE_COOKIE))
        if sid not in spaces.spaces or spaces.creator(sid) != email:
            raise HTTPException(404, tr("没有这个节目"))
        answers = body.model_dump(exclude={"show"})
        if not answers.get("lang"):
            answers["lang"] = show_language(sid)
        return fb.set_profile(email, sid, answers)

    def show_language(sid: str) -> str | None:
        """The show's own language setting (asked in its setup), for the admin next to the two answers."""
        try:
            return show.load(spaces.path(sid)).get("language")
        except Exception:          # noqa: BLE001 - a missing answer, never a failed request
            return None

    # ---------------------------------------------------------------- the site owner (admin later)
    @app.get("/api/feedback/all")
    def everything(request: Request):
        staff(request)
        items = fb.all()
        for it in items:
            sid = (it.get("show") or {}).get("id")
            it["profile"] = fb.profile(sid) if sid else None
            it["name"] = auth.name(it["email"])
        return {"items": items}

    @app.post("/api/feedback/prompt/reset")
    def reset_prompts(body: ResetBody, request: Request):
        """For testing the prompts: the person is asked again as if never asked (owner / admins)."""
        staff(request)
        email = body.email.strip().lower()
        if email not in auth.users:
            raise HTTPException(404, tr("没有这个账号"))
        fb.reset_prompts(email)
        return {"ok": True, "exported": exported(email)}

    @app.get("/api/feedback/{fid}/shot")
    def shot(fid: str, request: Request):
        email = me(request)
        item = fb.get(fid)
        if not item or (item["email"] != email and auth.role(email) not in STAFF):
            raise HTTPException(404, tr("没有这条反馈"))
        path = fb.shot_path(fid)
        if not path:
            raise HTTPException(404, tr("没有截图"))
        return FileResponse(path, media_type="image/jpeg" if path.suffix == ".jpg" else "image/png",
                            headers={"Cache-Control": "private, no-store"})

    @app.post("/api/feedback/{fid}/reply")
    def reply(fid: str, body: ReplyBody, request: Request):
        staff(request)
        try:
            item = fb.reply(fid, body.text, body.status, body.adopted)
        except FeedbackError as e:
            raise HTTPException(404 if fb.get(fid) is None else 422, str(e))
        person = auth.users.get(item["email"])
        mailed = False
        if person and (body.text or body.status or body.adopted):
            origin = app.state.invite_origin(request) if hasattr(app.state, "invite_origin") else ""
            with speaking(person.get("lang") or "zh"):
                m = reply_mail(item, f"{origin.rstrip('/')}/#/feedback")
            send(item["email"], m)
            mailed = True
        return {"item": item, "mailed": mailed}

    def send(to: str, m: dict) -> None:
        def go():
            try:
                auth.mailer.send(auth.config["sender"], to, m["subject"], m["text"], html=m["html"], inline=m["inline"])
            except (MailError, OSError) as e:
                print(f"LACUNA: feedback reply mail failed: {e}", flush=True)
        if ctx.option("mail_inline"):
            go()
        else:
            threading.Thread(target=go, name="feedback-mail", daemon=True).start()
