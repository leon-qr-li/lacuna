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

from . import show
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

    def title(self, sid: str) -> str:
        """What people see as the project's name: its show name once set, else the name it was made with."""
        try:
            name = show.load(self.path(sid)).get("show_name") or ""
        except Exception:
            name = ""
        return name or self.spaces[sid]["name"]

    def summary(self, sid: str) -> dict:
        """For the project list: how many episodes and albums, how many people, when last changed."""
        root = self.path(sid)
        eps = root / "episodes"
        dirs = [p for p in eps.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))] if eps.is_dir() else []
        try:
            albums = len((read_json(root / "albums.json") or {}).get("albums", []))
        except (OSError, ValueError):
            albums = 0
        stamps = [p.stat().st_mtime for p in dirs] + [self.spaces[sid]["created"]]
        return {"episodes": len(dirs), "albums": albums, "people": len(self.spaces[sid]["members"]),
                "updated": max(stamps)}

    def mine(self, email: str, detail: bool = False) -> list[dict]:
        rows = [{"id": s["id"], "name": self.title(s["id"]), "role": s["members"][email],
                 "by": (s.get("added_by") or {}).get(email)} | (self.summary(s["id"]) if detail else {})
                for s in self.spaces.values() if email in s["members"]]
        return sorted(rows, key=lambda r: (r["id"] != MAIN, r["name"].lower()))

    def current(self, email: str, wanted: str | None) -> str | None:
        """The workspace this person is in: the one they picked if they still belong to it, else their first."""
        if wanted and self.role(wanted, email):
            return wanted
        mine = self.mine(email)
        return mine[0]["id"] if mine else None

    def overview(self) -> list[dict]:
        return sorted(({"id": s["id"], "name": self.title(s["id"]), "created": s["created"],
                        "members": [{"email": e, "role": r} for e, r in sorted(s["members"].items())]}
                       for s in self.spaces.values()), key=lambda r: (r["id"] != MAIN, r["name"].lower()))

    # -- changes (permission checks are in routes/spaces.py)
    def _get(self, sid: str) -> dict:
        s = self.spaces.get(sid)
        if not s:
            raise AuthError(tr("没有这个项目"), 404)
        return s

    def create(self, name: str, admin: str, named: bool = True) -> dict:
        """`named` False: the project a new account starts with, whose first visit asks for its name too."""
        name = _name(name)
        with self.lock:
            sid = "sp_" + secrets.token_hex(4)
            self.path(sid).joinpath("episodes").mkdir(parents=True, exist_ok=True)
            show.write_new(self.path(sid), name if named else "")  # a new show: the first visit asks for its hosts
            self.spaces[sid] = {"id": sid, "name": name, "created": self.now(), "members": {admin: "admin"}}
            self._save()
            return self.spaces[sid]

    def rename(self, sid: str, name: str) -> None:
        with self.lock:
            self._get(sid)["name"] = _name(name)
            self._save()

    def set_member(self, sid: str, email: str, role: str | None, by: str | None = None) -> None:
        """Add, change or (role None) remove a member; a workspace always keeps one admin.
        `by`: who brought a new member in (shown to them in their project list)."""
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
                raise AuthError(tr("项目至少要留一个管理员"))
            added = s.setdefault("added_by", {})
            if role is None:
                added.pop(email, None)
            elif by and email not in s["members"] and by != email:
                added[email] = by
            s["members"] = members
            self._save()

    def forget(self, email: str) -> None:
        """An account was deleted: it leaves every workspace (what it made stays)."""
        with self.lock:
            for s in self.spaces.values():
                s["members"].pop(email, None)
                s.get("added_by", {}).pop(email, None)
            self._save()


def _name(name: str) -> str:
    n = " ".join((name or "").split())[:60]
    if not n:
        raise AuthError(tr("给项目起个名字"))
    return n
