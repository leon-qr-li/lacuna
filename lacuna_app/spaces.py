"""Workspaces: who owns which episodes, library and learned rules.

A workspace is a complete LACUNA workspace folder (episodes, library 公共 + 本集, learning/, rules,
ai_usage.jsonl), so everything in it is shared by its members and invisible to everyone else. The
installation's own folder is the first workspace ("main"; Leon's data stays where it is); others live in
``<root>/spaces/<id>/``. ``routes/spaces.py`` sends each request to the signed-in person's current
workspace. Decision: docs/decisions/2026-10-19-workspaces.md.

Roles inside a workspace: admin (members, rename, delete episodes for good), editor (all editing work),
viewer (listen and read only). Site owner and admins (auth.py) manage every workspace.

Storage: the site database (lacuna_app/db.py), tables shows + show_members. ``<root>/auth/spaces.json``,
used before, is read into it once and left in place for 30 days.

Site owner and admins see the list of shows but not what is in them, unless a show's manager turns on
「允许 LACUNA 支持查看」: then, for SUPPORT_S, they may open it read-only (decision 2026-10-21-roles).

Each project has a square picture (uploaded, ``<root>/auth/pictures/<id>.png``) or else its own solid colour
(``color``, picked at creation so projects look different). A project manager can archive it: it moves to
「已归档」 and is read-only for everyone until restored. Only its creator or the site owner can then delete it
for good, typing its name (decision projects-archive-delete).
"""
from __future__ import annotations

import secrets
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

from . import db as sitedb
from . import show
from .auth import AuthError
from .i18n import tr
from .store import read_json

MAIN = "main"
SPACE_RANK = {"viewer": 1, "editor": 2, "admin": 3}
# a project's colour while it has no picture: solid, readable under white text in both themes, far apart
COLORS = ("#E2583E", "#3D7BF0", "#1F9D74", "#9A55E8", "#E0A21A", "#D93E7F", "#2AA5B8", "#6C7A3A", "#C9682D", "#5A5FD6")
PICTURE_PX = 256
SUPPORT_S = 7 * 86400
KEEP_OLD_S = 30 * 86400


class Spaces:
    def __init__(self, root: Path, clock: Callable[[], float] = time.time):
        self.root = Path(root)
        self.file = self.root / "auth" / "spaces.json"
        self.now = clock
        self.lock = threading.RLock()
        self.db = sitedb.at(self.root)
        self.staff: Callable[[str], bool] = lambda email: False    # site owner / admin (set by routes/spaces.py)
        if self.db.meta("shows_from_json") is None:
            data = read_json(self.file) if self.file.exists() else None
            self.spaces: dict[str, dict] = {s["id"]: s for s in (data or {}).get("spaces", [])}
            self._save()
            self.db.set_meta("shows_from_json", str(self.now()))
        self.spaces = {r["id"]: sitedb.loads(r["data"]) for r in self.db.query("SELECT data, id FROM shows")}
        moved = float(self.db.meta("shows_from_json") or 0)
        if moved and self.now() - moved > KEEP_OLD_S:
            for f in (self.file, self.file.with_name("spaces.json.bak")):
                f.unlink(missing_ok=True)
        if any("color" not in x for x in self.spaces.values()):       # projects from before colours
            for x in sorted(self.spaces.values(), key=lambda x: x.get("created", 0)):
                x.setdefault("color", self._free_color())
            self._save()

    def _save(self) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM show_members")
            c.execute("DELETE FROM shows")
            c.executemany("INSERT INTO shows (id, name, created, created_by, archived, data) VALUES (?,?,?,?,?,?)",
                          [(x["id"], x["name"], x["created"], self.creator(x["id"]), int(bool(x.get("archived"))),
                            sitedb.dumps(x)) for x in self.spaces.values()])
            c.executemany("INSERT INTO show_members (show_id, email, role) VALUES (?,?,?)",
                          [(x["id"], e, r) for x in self.spaces.values() for e, r in x["members"].items()])

    def adopt(self, users: list[dict]) -> None:
        """First start with workspaces: the existing folder becomes "main", with every existing account in
        it (owner and admins as workspace admins, the rest as editors), so nothing changes for them."""
        with self.lock:
            if MAIN in self.spaces or not users:
                return
            owner = next((u for u in users if u["role"] == "owner"), users[0])
            self.spaces[MAIN] = {"id": MAIN, "name": owner["email"].split("@")[0], "created": self.now(),
                                 "members": {u["email"]: "admin" if u["role"] in ("owner", "admin") else "editor"
                                             for u in users},
                                 "created_by": owner["email"], "color": self._free_color()}
            self._save()

    def _free_color(self) -> str:
        """The least used colour (the first of those): a new project looks different from the others."""
        used = [x.get("color") for x in self.spaces.values()]
        return min(COLORS, key=lambda c: (used.count(c), COLORS.index(c)))

    # -- queries
    def picture_file(self, sid: str) -> Path:
        return self.root / "auth" / "pictures" / f"{sid}.png"

    def creator(self, sid: str) -> str | None:
        """Who made the project (older ones: their first manager nobody else brought in)."""
        s = self.spaces[sid]
        if s.get("created_by"):
            return s["created_by"]
        added = s.get("added_by") or {}
        return next((e for e, r in s["members"].items() if r == "admin" and e not in added), None)

    def archived(self, sid: str | None) -> bool:
        return bool(self.spaces.get(sid or "", {}).get("archived"))

    def path(self, sid: str) -> Path:
        return self.root if sid == MAIN else self.root / "spaces" / sid

    def role(self, sid: str | None, email: str | None) -> str | None:
        """Their role in the show; site staff get "viewer" while the show allows LACUNA support to look."""
        s = self.spaces.get(sid or "")
        if not s:
            return None
        r = s["members"].get(email or "")
        if r is None and email and self.support_until(sid) and self.staff(email):
            return "viewer"
        return r

    def support_until(self, sid: str | None) -> float | None:
        """While 「允许 LACUNA 支持查看」 is on: until when (it turns itself off after SUPPORT_S)."""
        until = (self.spaces.get(sid or "") or {}).get("support_until")
        return until if until and until > self.now() else None

    def set_support(self, sid: str, on: bool, by: str) -> None:
        with self.lock:
            s = self._get(sid)
            if on:
                s["support_until"] = self.now() + SUPPORT_S
                s["support_by"] = by
            else:
                s.pop("support_until", None)
                s.pop("support_by", None)
            self._save()

    def owned(self, email: str) -> int:
        """How many shows this person made (archived ones too): what their plan's show limit counts."""
        return sum(1 for sid in self.spaces if self.creator(sid) == email)

    def collaborators(self, sid: str) -> int:
        """People in the show besides the one who made it: what the maker's plan's collaborator limit counts."""
        c = self.creator(sid)
        return sum(1 for e in self._get(sid)["members"] if e != c)

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

    def look(self, sid: str) -> dict:
        """How the project shows: its colour, its picture's address (None: the colour), archived or not."""
        s = self.spaces[sid]
        pic = self.picture_file(sid)
        url = f"/api/spaces/{sid}/picture?v={int(pic.stat().st_mtime)}" if pic.is_file() else None
        return {"color": s.get("color") or COLORS[0], "picture": url, "archived": bool(s.get("archived"))}

    def mine(self, email: str, detail: bool = False) -> list[dict]:
        """Their shows, plus (site staff) the shows that currently allow LACUNA support to look."""
        rows = [{"id": s["id"], "name": self.title(s["id"]), "role": self.role(s["id"], email),
                 "by": (s.get("added_by") or {}).get(email), "support": email not in s["members"]}
                | self.look(s["id"]) | (self.summary(s["id"]) if detail else {})
                for s in self.spaces.values() if self.role(s["id"], email)]
        return sorted(rows, key=lambda r: (r["id"] != MAIN, r["name"].lower()))

    def current(self, email: str, wanted: str | None) -> str | None:
        """The workspace this person is in: the one they picked if they still belong to it (archived ones
        too: they can still be opened and read), else their first one that is not archived."""
        if wanted and self.role(wanted, email):
            return wanted
        mine = self.mine(email)
        live = [m for m in mine if not m["archived"] and not m["support"]] or mine
        return live[0]["id"] if live else None

    def overview(self) -> list[dict]:
        return sorted(({"id": s["id"], "name": self.title(s["id"]), "created": s["created"],
                        "members": [{"email": e, "role": r} for e, r in sorted(s["members"].items())]}
                       for s in self.spaces.values()), key=lambda r: (r["id"] != MAIN, r["name"].lower()))

    # -- changes (permission checks are in routes/spaces.py)
    def _get(self, sid: str) -> dict:
        s = self.spaces.get(sid)
        if not s:
            raise AuthError(tr("没有这个节目"), 404)
        return s

    def create(self, name: str, admin: str, named: bool = True) -> dict:
        """`named` False: the project a new account starts with, whose first visit asks for its name too."""
        name = _name(name)
        with self.lock:
            sid = "sp_" + secrets.token_hex(4)
            self.path(sid).joinpath("episodes").mkdir(parents=True, exist_ok=True)
            show.write_new(self.path(sid), name if named else "")  # a new show: the first visit asks for its hosts
            self.spaces[sid] = {"id": sid, "name": name, "created": self.now(), "members": {admin: "admin"},
                                "created_by": admin, "color": self._free_color()}
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
                raise AuthError(tr("节目至少要留一个管理员"))
            added = s.setdefault("added_by", {})
            if role is None:
                added.pop(email, None)
            elif by and email not in s["members"] and by != email:
                added[email] = by
            s["members"] = members
            self._save()

    def set_picture(self, sid: str, data: bytes) -> None:
        """An uploaded picture, cut to the middle square and made PICTURE_PX wide (PNG)."""
        self._get(sid)
        from PIL import Image, ImageOps
        import io
        try:
            im = Image.open(io.BytesIO(data))
            im = ImageOps.exif_transpose(im).convert("RGBA")
        except Exception as e:          # noqa: BLE001 - Pillow raises many kinds on a bad file
            raise AuthError(tr("这不是一张能打开的图片")) from e
        im = ImageOps.fit(im, (PICTURE_PX, PICTURE_PX), Image.LANCZOS)
        out = self.picture_file(sid)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        im.save(tmp, "PNG", optimize=True)
        tmp.replace(out)

    def drop_picture(self, sid: str) -> None:
        self._get(sid)
        self.picture_file(sid).unlink(missing_ok=True)

    def archive(self, sid: str, by: str, on: bool = True) -> None:
        """Archive (read-only for everyone, listed under 已归档) or restore."""
        with self.lock:
            s = self._get(sid)
            if on:
                s["archived"] = {"at": self.now(), "by": by}
            else:
                s.pop("archived", None)
            self._save()

    def delete(self, sid: str) -> None:
        """For good: the project's folder, picture and record. MAIN (the installation's own folder) never."""
        with self.lock:
            self._get(sid)
            if sid == MAIN:
                raise AuthError(tr("这个节目是 LACUNA 的主节目，不能删除"))
            folder = self.path(sid)
            del self.spaces[sid]
            self._save()
        self.picture_file(sid).unlink(missing_ok=True)
        if folder.is_dir() and folder.parent == self.root / "spaces":
            shutil.rmtree(folder, ignore_errors=True)

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
        raise AuthError(tr("给节目起个名字"))
    return n
