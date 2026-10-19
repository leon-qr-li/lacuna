"""Workspaces: who owns which episodes, library and learned rules.

A workspace is a complete LACUNA workspace folder (episodes, library 公共 + 本集, learning/, rules,
ai_usage.jsonl), so everything in it is shared by its members and invisible to everyone else. The
installation's own folder is the first workspace ("main"; Leon's data stays where it is); others live in
``<root>/spaces/<id>/``. ``routes/spaces.py`` sends each request to the signed-in person's current
workspace. Decision: docs/decisions/2026-10-19-workspaces.md.

Roles inside a workspace: admin (members, rename, delete episodes for good), editor (all editing work),
viewer (listen and read only). Site owner and admins (auth.py) manage every workspace.

File: ``<root>/auth/spaces.json`` (atomic writes, store.py).
"""
from __future__ import annotations

import secrets
import threading
import time
from pathlib import Path
from typing import Callable

from .auth import AuthError
from .i18n import tr
from .store import atomic_write_json, read_json

MAIN = "main"
SPACE_RANK = {"viewer": 1, "editor": 2, "admin": 3}


class Spaces:
    def __init__(self, root: Path, clock: Callable[[], float] = time.time):
        self.root = Path(root)
        self.file = self.root / "auth" / "spaces.json"
        self.now = clock
        self.lock = threading.RLock()
        data = read_json(self.file) if self.file.exists() else None
        self.spaces: dict[str, dict] = {s["id"]: s for s in (data or {}).get("spaces", [])}

    def _save(self) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.file, {"spaces": list(self.spaces.values())})

    def adopt(self, users: list[dict]) -> None:
        """First start with workspaces: the existing folder becomes "main", with every existing account in
        it (owner and admins as workspace admins, the rest as editors), so nothing changes for them."""
        with self.lock:
            if MAIN in self.spaces or not users:
                return
            owner = next((u for u in users if u["role"] == "owner"), users[0])
            self.spaces[MAIN] = {"id": MAIN, "name": owner["email"].split("@")[0], "created": self.now(),
                                 "members": {u["email"]: "admin" if u["role"] in ("owner", "admin") else "editor"
                                             for u in users}}
            self._save()

    # -- queries
    def path(self, sid: str) -> Path:
        return self.root if sid == MAIN else self.root / "spaces" / sid

    def role(self, sid: str | None, email: str | None) -> str | None:
        s = self.spaces.get(sid or "")
        return s["members"].get(email or "") if s else None

    def mine(self, email: str) -> list[dict]:
        rows = [{"id": s["id"], "name": s["name"], "role": s["members"][email]}
                for s in self.spaces.values() if email in s["members"]]
        return sorted(rows, key=lambda r: (r["id"] != MAIN, r["name"].lower()))

    def current(self, email: str, wanted: str | None) -> str | None:
        """The workspace this person is in: the one they picked if they still belong to it, else their first."""
        if wanted and self.role(wanted, email):
            return wanted
        mine = self.mine(email)
        return mine[0]["id"] if mine else None

    def overview(self) -> list[dict]:
        return sorted(({"id": s["id"], "name": s["name"], "created": s["created"],
                        "members": [{"email": e, "role": r} for e, r in sorted(s["members"].items())]}
                       for s in self.spaces.values()), key=lambda r: (r["id"] != MAIN, r["name"].lower()))

    # -- changes (permission checks are in routes/spaces.py)
    def _get(self, sid: str) -> dict:
        s = self.spaces.get(sid)
        if not s:
            raise AuthError(tr("没有这个工作区"), 404)
        return s

    def create(self, name: str, admin: str) -> dict:
        name = _name(name)
        with self.lock:
            sid = "sp_" + secrets.token_hex(4)
            self.path(sid).joinpath("episodes").mkdir(parents=True, exist_ok=True)
            self.spaces[sid] = {"id": sid, "name": name, "created": self.now(), "members": {admin: "admin"}}
            self._save()
            return self.spaces[sid]

    def rename(self, sid: str, name: str) -> None:
        with self.lock:
            self._get(sid)["name"] = _name(name)
            self._save()

    def set_member(self, sid: str, email: str, role: str | None) -> None:
        """Add, change or (role None) remove a member; a workspace always keeps one admin."""
        with self.lock:
            s = self._get(sid)
            if role is not None and role not in SPACE_RANK:
                raise AuthError(tr("没有这个角色"))
            members = dict(s["members"])
            if role is None:
                members.pop(email, None)
            else:
                members[email] = role
            if s["members"] and not any(r == "admin" for r in members.values()):
                raise AuthError(tr("工作区至少要留一个管理员"))
            s["members"] = members
            self._save()

    def forget(self, email: str) -> None:
        """An account was deleted: it leaves every workspace (what it made stays)."""
        with self.lock:
            for s in self.spaces.values():
                s["members"].pop(email, None)
            self._save()


def _name(name: str) -> str:
    n = " ".join((name or "").split())[:60]
    if not n:
        raise AuthError(tr("给工作区起个名字"))
    return n
