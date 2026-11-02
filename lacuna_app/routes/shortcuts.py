"""自定义快捷键 (decision 2026-11-02-custom-shortcuts): GET / PUT /api/shortcuts, the signed-in person's own keys.

Only the keys someone changed are kept (action id -> up to 2 keys, an empty list = the action is off); the web
app holds the actions and their defaults (web/src/features/shortcuts/keys.ts). Stored as ``shortcuts.json`` in
the person's home folder (habits.py), so they follow them to every computer; without accounts, in the
workspace folder. Answered by the main app for whoever is signed in (routes/spaces.py lists it as global).
"""
from __future__ import annotations

import re

from fastapi import HTTPException, Request
from pydantic import BaseModel

from .. import habits
from ..auth import COOKIE
from ..i18n import tr
from ..store import atomic_write_json, read_json

FILE = "shortcuts.json"
MAX_ACTIONS = 64
ACTION = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
# "Mod+Shift+Z", "G", "ArrowLeft", "?", "Space": modifiers in a fixed order, then one key name
KEY = re.compile(r"^(Mod\+)?(Alt\+)?(Shift\+)?([A-Za-z0-9]{1,12}|[!-/:-@\[-`{-~])$")


class ShortcutsBody(BaseModel):
    keys: dict[str, list[str]]


def clean(raw: object) -> dict[str, list[str]]:
    """Valid entries only: a known shape, at most 2 different keys per action."""
    out: dict[str, list[str]] = {}
    if not isinstance(raw, dict):
        return out
    for a, ks in list(raw.items())[:MAX_ACTIONS]:
        if not isinstance(a, str) or not ACTION.match(a) or not isinstance(ks, list):
            continue
        seen: list[str] = []
        for k in ks:
            if isinstance(k, str) and KEY.match(k) and k not in seen:
                seen.append(k)
        out[a] = seen[:2]
    return out


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return

    def home(request: Request):
        auth = ctx.provide("auth")
        if auth is None or not auth.has_accounts():
            return ctx.ws.root
        email = auth.who(request.cookies.get(COOKIE))
        if not email:
            raise HTTPException(401, tr("请先登录"))
        return habits.home_for(ctx.ws.root, email)

    def load(request: Request) -> dict[str, list[str]]:
        p = home(request) / FILE
        try:
            return clean(read_json(p).get("keys")) if p.is_file() else {}
        except (OSError, ValueError, AttributeError):
            return {}

    @app.get("/api/shortcuts")
    def get_shortcuts(request: Request):
        return {"keys": load(request)}

    @app.put("/api/shortcuts")
    def put_shortcuts(body: ShortcutsBody, request: Request):
        if len(body.keys) > MAX_ACTIONS:
            raise HTTPException(422, tr("快捷键太多了"))
        h = home(request)
        h.mkdir(parents=True, exist_ok=True)
        atomic_write_json(h / FILE, {"keys": clean(body.keys)})
        return get_shortcuts(request)
