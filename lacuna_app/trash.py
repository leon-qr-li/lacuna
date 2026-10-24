"""回收区: what is "deleted for good" is kept 60 days, so LACUNA's owner or admins can bring it back when someone
deleted by mistake (Leon 2026-10-24, decision 2026-10-24-deleted-kept-60-days). After that it is gone.

A deleted show: ``<root>/trash/<sid>-<time>/`` holds its files (``files/``), its picture and ``record.json`` (its
record in the site database, who deleted it, when). Restoring moves the files back to exactly where they were,
so the absolute paths in its episodes (source tracks, media) stay right. The first show of an installation
("main") has its files at the root itself: only its own entries (SHOW_ENTRIES) move.

A deleted account: its account record and the shows it was in, in the site database (meta ``trash_user:<email>``).
What it taught LACUNA (``people/<hash>``) was never removed, so a restored account has its rules and 剪辑力度.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Callable

from .store import atomic_write_json, read_json

KEEP_S = 60 * 86400
DIR = "trash"
USER_KEY = "trash_user:"
# what a show's folder holds (lacuna_app modules; .bak copies come along): only these leave the root
SHOW_ENTRIES = ("episodes", "imports", "exports", "library", "learning", "albums", "imported_tracks",
                "albums.json", "archive.json", "names.json", "show.json", "ai_usage.jsonl", ".rule-stutter-2026-10-20")


class TrashError(Exception):
    pass


class Trash:
    def __init__(self, root: Path, db, clock: Callable[[], float] = time.time):
        self.root = Path(root)
        self.dir = self.root / DIR
        self.db = db
        self.now = clock

    # -- shows
    def put_show(self, sid: str, record: dict, folder: Path, picture: Path | None, by: str | None) -> str:
        tid = f"{sid}-{int(self.now())}"
        d = self.dir / tid
        d.mkdir(parents=True)
        files = d / "files"
        if folder == self.root:
            files.mkdir()
            moved = [n for n in _entries(self.root) if n in SHOW_ENTRIES or n.removesuffix(".bak") in SHOW_ENTRIES]
            for n in moved:
                os.replace(self.root / n, files / n)
            home = "."
        else:
            if folder.is_dir():
                os.replace(folder, files)
            else:
                files.mkdir()
            home = folder.relative_to(self.root).as_posix()
        if picture and picture.is_file():
            shutil.copy2(picture, d / "picture.png")
        atomic_write_json(d / "record.json", {"kind": "show", "id": tid, "sid": sid, "name": record.get("name"),
                                              "home": home, "deleted_at": self.now(), "by": by, "show": record})
        return tid

    def show(self, tid: str) -> dict:
        f = self.dir / _id(tid) / "record.json"
        if not f.is_file():
            raise TrashError("not found")
        return read_json(f)

    def take_show(self, tid: str, picture: Path) -> dict:
        """The files back where they were; the show's record is returned for the site database."""
        rec = self.show(tid)
        d = self.dir / _id(tid)
        files = d / "files"
        if rec["home"] == ".":
            names = _entries(files)
            for n in names:            # the running app may have made empty folders again in the meantime
                t = self.root / n
                if t.exists() and not (t.is_dir() and not any(t.iterdir())):
                    raise TrashError(f"{n} exists")
            for n in names:
                t = self.root / n
                if t.is_dir():
                    t.rmdir()
                os.replace(files / n, t)
        else:
            home = self.root / rec["home"]
            if home.exists():
                raise TrashError("folder exists")
            home.parent.mkdir(parents=True, exist_ok=True)
            os.replace(files, home)
        if (d / "picture.png").is_file():
            picture.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(d / "picture.png", picture)
        shutil.rmtree(d, ignore_errors=True)
        return rec["show"]

    # -- accounts
    def put_user(self, email: str, user: dict, shows: dict[str, str], by: str | None) -> None:
        self.db.set_meta(USER_KEY + email, json.dumps({"user": user, "shows": shows, "deleted_at": self.now(),
                                                         "by": by}, ensure_ascii=False))

    def user(self, email: str) -> dict:
        raw = self.db.meta(USER_KEY + email)
        if not raw:
            raise TrashError("not found")
        return json.loads(raw)

    def drop_user(self, email: str) -> None:
        self.db.set_meta(USER_KEY + email, "")

    def drop(self, tid: str) -> None:
        """A deleted show goes for good now, not after 60 days (the admin's 立即清除, owner only)."""
        d = self.dir / _id(tid)
        if not (d / "record.json").is_file():
            raise TrashError("not found")
        shutil.rmtree(d, ignore_errors=True)

    # -- both
    def items(self) -> list[dict]:
        """What can still be brought back, newest first, with the days left."""
        self.purge()
        out = []
        for d in (self.dir.iterdir() if self.dir.is_dir() else []):
            try:
                rec = read_json(d / "record.json")
            except (OSError, ValueError):
                continue
            out.append({"kind": "show", "id": rec["id"], "name": rec.get("name"), "by": rec.get("by"),
                        "deleted_at": rec["deleted_at"], "left_days": self._left(rec["deleted_at"])})
        for r in self.db.query("SELECT key, value FROM meta WHERE key LIKE ? AND value != ''", (USER_KEY + "%",)):
            rec = json.loads(r["value"])
            email = r["key"][len(USER_KEY):]
            out.append({"kind": "user", "id": email, "name": email, "by": rec.get("by"),
                        "deleted_at": rec["deleted_at"], "left_days": self._left(rec["deleted_at"])})
        return sorted(out, key=lambda x: -x["deleted_at"])

    def purge(self) -> int:
        """Whatever was deleted more than 60 days ago goes for good. Returns how many."""
        n = 0
        cut = self.now() - KEEP_S
        for d in (list(self.dir.iterdir()) if self.dir.is_dir() else []):
            try:
                at = read_json(d / "record.json")["deleted_at"]
            except (OSError, ValueError, KeyError):
                continue
            if at < cut:
                shutil.rmtree(d, ignore_errors=True)
                n += 1
        for r in self.db.query("SELECT key, value FROM meta WHERE key LIKE ? AND value != ''", (USER_KEY + "%",)):
            if json.loads(r["value"])["deleted_at"] < cut:
                self.db.set_meta(r["key"], "")
                n += 1
        return n

    def _left(self, at: float) -> int:
        return max(0, int((at + KEEP_S - self.now()) // 86400))


def _entries(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def _id(tid: str) -> str:
    if not tid or "/" in tid or "\\" in tid or tid.startswith("."):
        raise TrashError("not found")
    return tid
