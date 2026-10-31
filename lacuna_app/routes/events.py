"""Event log (lacuna_app/events.py): who is acting on each request, and one event per successful change.

``install`` puts ``EventsMiddleware`` between the cloud gate and the workspace dispatcher (routes/spaces.py
calls it), so it sees every workspace's requests once. Reads (GET) are not events. A request that changed
something (2xx) and matches ``RULES`` logs that event; signing in is noticed by the session cookie the
response sets, a new account by ``Auth.on_joined``. Events with details the URL can't tell (AI edits kept or restored, an import's length and
result) are logged where they happen with ``events.track``; numbers for the request's own row with ``events.note``.

A change that failed (5xx, or a 4xx other than 401 / 403 / 404: a bad value, a conflict, over quota) is logged as
``<event>.failed`` with its status, so the admin's 用户动态 shows it in red (decision 2026-10-31-admin-user-activity).
The row is written in a worker thread after the response went out: the user never waits for it and the event
loop never waits for the disk.
"""
from __future__ import annotations

import asyncio
import re
from http.cookies import SimpleCookie

from ..auth import COOKIE, Auth
from ..events import ACTOR, NOTE, Actor, EventLog

SPACE_COOKIE = "lacuna_space"      # routes/spaces.py
QUIET = (401, 403, 404)            # not signed in, not allowed, gone: refusals, not failures of the person's work
EP = r"/api/episodes/(?P<ep>[^/]+)"

# (method, path, event): the first match wins
RULES: list[tuple[str, re.Pattern, str]] = [(m, re.compile(f"^{p}$"), e) for m, p, e in [
    ("POST", r"/api/auth/invites?", "invite.send"),
    ("POST", r"/api/spaces", "show.create"),
    ("POST", r"/api/spaces/[^/]+/invite", "show.invite"),
    ("PUT", r"/api/site/new-members", "site.new_members"),
    ("POST", r"/api/access-requests/[^/]+", "request.decide"),
    ("POST", r"/api/spaces/[^/]+/archive", "show.archive"),
    ("DELETE", r"/api/spaces/[^/]+", "show.delete"),
    ("POST", r"/api/albums", "album.create"),
    ("POST", r"/api/imports", "import.start"),
    ("POST", r"/api/imports/(?P<ep>[^/]+)/resume", "import.resume"),
    ("POST", r"/api/imports/(?P<ep>[^/]+)/cancel", "import.cancel"),
    ("POST", EP + r"/ops", "edit.manual"),
    ("POST", EP + r"/manual/cut", "edit.manual"),
    ("POST", EP + r"/fillers/cut", "edit.fillers"),
    ("POST", EP + r"/undo", "edit.undo"),
    ("POST", EP + r"/redo", "edit.redo"),
    ("POST", EP + r"/chat", "chat.message"),
    ("POST", EP + r"/proposals/[^/]+/approve", "chat.approve"),
    ("POST", EP + r"/proposals/[^/]+/discard", "chat.discard"),
    ("POST", EP + r"/transcript/fix", "transcript.fix"),
    ("POST", EP + r"/levels/auto", "levels.auto"),
    ("POST", EP + r"/levels/[^/]+", "levels.set"),
    ("POST", EP + r"/music/auto", "music.auto"),
    ("POST", EP + r"/music", "music.add"),
    ("POST", EP + r"/music/chat", "music.chat"),
    ("POST", EP + r"/export", "export.start"),
    ("POST", EP + r"/publish/generate", "publish.generate"),
    ("PUT", EP + r"/publish", "publish.save"),
    ("POST", EP + r"/poster/generate", "poster.generate"),
    ("POST", EP + r"/poster/[^/]+/choose", "poster.choose"),
    ("POST", EP + r"/lessons/run", "lessons.run"),
    ("POST", EP + r"/lessons/[^/]+", "lessons.decide"),
    ("POST", EP + r"/remember", "rule.remember"),
    ("POST", r"/api/learning/rules", "rule.update"),
    ("POST", EP + r"/archive", "episode.archive"),
    ("DELETE", EP, "episode.delete"),
    ("POST", r"/api/library/upload", "library.upload"),
    ("POST", r"/api/dictation", "dictation.use"),
]]


def match(method: str, path: str) -> tuple[str, str | None] | None:
    for m, rx, ev in RULES:
        if m == method:
            hit = rx.match(path)
            if hit:
                return ev, hit.groupdict().get("ep")
    return None


def _cookies(scope) -> SimpleCookie:
    raw = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"cookie"), "")
    c = SimpleCookie()
    try:
        c.load(raw)
    except Exception:
        pass
    return c


def _new_session(headers) -> str | None:
    """The session token a response sets (sign-in, sign-up), or None."""
    for k, v in headers or []:
        if k.lower() == b"set-cookie":
            c = SimpleCookie()
            try:
                c.load(v.decode("latin-1"))
            except Exception:
                continue
            if COOKIE in c and c[COOKIE].value:
                return c[COOKIE].value
    return None


class EventsMiddleware:
    def __init__(self, app, log: EventLog, auth: Auth, spaces):
        self.app, self.log, self.auth, self.spaces = app, log, auth, spaces

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            return await self.app(scope, receive, send)
        c = _cookies(scope)
        email = self.auth.who(c[COOKIE].value) if COOKIE in c else None
        sid = None
        if email and self.spaces is not None:
            sid = self.spaces.current(email, c[SPACE_COOKIE].value if SPACE_COOKIE in c else None)
        token = ACTOR.set(Actor(self.log, self.log.uid(email), sid))
        extra: dict = {}
        ntoken = NOTE.set(extra)
        seen: dict = {}

        async def watch(msg):
            if msg["type"] == "http.response.start":
                seen["status"] = msg["status"]
                seen["session"] = _new_session(msg.get("headers"))
            await send(msg)

        try:
            await self.app(scope, receive, watch)
        finally:
            ACTOR.reset(token)
            NOTE.reset(ntoken)
            if seen.get("session") or (email and match(scope["method"], scope["path"])):
                try:
                    await asyncio.to_thread(self._after, scope, email, sid, seen, extra)
                except Exception:          # noqa: BLE001 - logging must never break a request
                    pass

    def _after(self, scope, email, sid, seen, extra=None) -> None:
        status = seen.get("status", 500)
        method, path = scope["method"], scope["path"]
        hit = match(method, path)
        if 200 <= status < 300 and seen.get("session"):
            who = self.auth.who(seen["session"])
            if who:
                self.log.add("user.login", self.log.uid(who), None)
            return
        if not (hit and email):
            return
        if 200 <= status < 300:
            self.log.add(hit[0], self.log.uid(email), sid, hit[1], **(extra or {}))
        elif status >= 500 or (400 <= status < 500 and status not in QUIET):
            self.log.add(hit[0] + ".failed", self.log.uid(email), sid, hit[1], status=status)


def install(app, ctx, auth: Auth, spaces) -> EventLog:
    """Called by routes/spaces.py right after it adds the workspace dispatcher (so this runs outside it)."""
    log: EventLog = ctx.provide("events", lambda: EventLog(auth.db, auth.user_id))
    auth.on_joined.append(lambda email, invite: log.add("user.signup", log.uid(email), None, invited=invite is not None))
    app.add_middleware(EventsMiddleware, log=log, auth=auth, spaces=spaces)
    return log


def register(app, ctx) -> None:
    """Nothing to route: the middleware is installed by routes/spaces.py (see ``install``)."""
