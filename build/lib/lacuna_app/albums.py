"""Albums (专辑) of a project: an optional group of episodes with a cover and a default opener / ending.

Decision: docs/decisions/2026-10-20-projects-albums.md. A project needs no album; an episode is in at
most one album, or in none ("不在专辑里"). The project itself has a default opener / ending too, and an
album's own one overrides it (Leon 2026-10-20): an album that leaves one empty uses the project's.

File ``<workspace>/albums.json`` (atomic writes, store.py)::

    {"schema": 1,
     "albums":   [{"id", "name", "about", "cover", "intro", "outro", "created"}],
     "episodes": {episode id: album id},
     "project":  {"intro", "outro"}}

``intro`` / ``outro`` are placement templates: the asset id plus the placement's tuning (music.TUNING),
or None. Covers live in ``<workspace>/albums/<album id>/cover.<ext>``.

The series rules the library kept before (library.json ``series``, "记成系列片头片尾") move here the first
time the file is read: the default rule becomes the project's opener / ending, every other rule an album
of its own (no episodes in it yet).
"""
from __future__ import annotations

import secrets
import threading
from pathlib import Path

from .i18n import tr
from .store import PathError, Workspace, atomic_write_json, check_id, read_json, now_iso as _now

SCHEMA = 1
FILE = "albums.json"
COVER_DIR = "albums"
COVER_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
MAX_COVER = 10 * 1024 ** 2
# what a template keeps of a placement (the tuning Leon gave it); library.save_series kept the same
KEEP = ("asset_id", "src_in_s", "src_out_s", "gain_db", "solo_s", "ramp_s", "bg_db", "pre_s", "bye_s", "fade_out_s",
        "overlap_s")
ROLES = ("intro", "outro")


class AlbumError(ValueError):
    """A bad request against the albums (empty name, unknown album ...); `status` is the HTTP status."""

    def __init__(self, msg: str, status: int = 422):
        super().__init__(msg)
        self.status = status


def template(p: dict | None) -> dict | None:
    """A placement (or {"asset_id": ...}) as an opener / ending template."""
    if not p or not p.get("asset_id"):
        return None
    return {k: p.get(k) for k in KEEP if k == "asset_id" or p.get(k) is not None}


def _name(name: str) -> str:
    n = " ".join((name or "").split())[:80]
    if not n:
        raise AlbumError(tr("给专辑起个名字"))
    return n


_LOCKS: dict[Path, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    """One lock per file: the library, the music page and the albums routes each make their own Albums."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(path.resolve(), threading.RLock())


class Albums:
    def __init__(self, ws: Workspace):
        self.ws = ws
        self.path = ws.root / FILE
        self.lock = _lock_for(self.path)

    # ------------------------------------------------------------------ storage
    def load(self) -> dict:
        with self.lock:
            if self.path.exists() or self.path.with_name(FILE + ".bak").exists():
                doc = read_json(self.path)
                if doc.get("schema") != SCHEMA:
                    raise ValueError(f"unsupported albums schema {doc.get('schema')}")
            else:
                doc = self._from_series()
            doc.setdefault("albums", [])
            doc.setdefault("episodes", {})
            doc.setdefault("project", {"intro": None, "outro": None})
            return doc

    def save(self, doc: dict) -> None:
        with self.lock:
            atomic_write_json(self.path, doc)

    def _from_series(self) -> dict:
        """First read: the library's series rules become the project's and albums' openers / endings."""
        doc = {"schema": SCHEMA, "albums": [], "episodes": {}, "project": {"intro": None, "outro": None}}
        lib = self.ws.root / "library" / "library.json"
        try:
            rules = list((read_json(lib) or {}).get("series") or []) if lib.exists() else []
        except (OSError, ValueError):
            rules = []
        default = next((r for r in rules if r.get("default")), None)
        for r in rules:
            pair = {role: template(r.get(role)) for role in ROLES}
            if r is default:
                doc["project"] = pair
            elif r.get("name"):
                doc["albums"].append({"id": self._new_id(doc), "name": str(r["name"])[:80], "about": "", "cover": None,
                                      "created": r.get("updated_at") or _now(), **pair})
        if rules:
            self.save(doc)
        return doc

    @staticmethod
    def _new_id(doc: dict) -> str:
        while True:
            aid = "al_" + secrets.token_hex(4)
            if not any(a["id"] == aid for a in doc["albums"]):
                return aid

    def _get(self, doc: dict, album_id: str) -> dict:
        a = next((x for x in doc["albums"] if x["id"] == album_id), None)
        if a is None:
            raise AlbumError(tr("没有这个专辑"), 404)
        return a

    # ------------------------------------------------------------------ queries
    def albums(self) -> list[dict]:
        return self.load()["albums"]

    def album_of(self, episode_id: str) -> str | None:
        doc = self.load()
        aid = doc["episodes"].get(episode_id)
        return aid if any(a["id"] == aid for a in doc["albums"]) else None

    def episodes_of(self, album_id: str) -> list[str]:
        live = set(self.ws.episode_ids())
        return sorted(e for e, a in self.load()["episodes"].items() if a == album_id and e in live)

    def defaults_for(self, episode_id: str) -> dict:
        """The opener / ending a new episode gets: its album's, else the project's, per role.
        {"album": album or None, "intro", "outro", "intro_from", "outro_from"} ("album" / "project" / None)."""
        doc = self.load()
        aid = doc["episodes"].get(episode_id)
        album = next((a for a in doc["albums"] if a["id"] == aid), None)
        out: dict = {"album": {"id": album["id"], "name": album["name"]} if album else None}
        for role in ROLES:
            t = (album or {}).get(role)
            src = "album" if t else None
            if not t:
                t = doc["project"].get(role)
                src = "project" if t else None
            out[role], out[f"{role}_from"] = t, src
        return out

    def asset_ids(self) -> set[str]:
        """Every asset an opener / ending template uses (they must survive an episode's permanent delete)."""
        doc = self.load()
        pairs = [doc["project"]] + doc["albums"]
        return {(p.get(r) or {}).get("asset_id") for p in pairs for r in ROLES} - {None}

    # ------------------------------------------------------------------ changes
    def create(self, name: str, about: str = "", intro: dict | None = None, outro: dict | None = None,
               episodes: list[str] | None = None) -> dict:
        with self.lock:
            doc = self.load()
            album = {"id": self._new_id(doc), "name": _name(name), "about": (about or "").strip()[:400], "cover": None,
                     "intro": template(intro), "outro": template(outro), "created": _now()}
            doc["albums"].append(album)
            for e in episodes or []:
                doc["episodes"][check_id(e)] = album["id"]
            self.save(doc)
            return album

    def update(self, album_id: str, **fields) -> dict:
        """`name`, `about`; `intro` / `outro`: a template, or {} to fall back to the project's."""
        with self.lock:
            doc = self.load()
            a = self._get(doc, album_id)
            if fields.get("name") is not None:
                a["name"] = _name(fields["name"])
            if fields.get("about") is not None:
                a["about"] = fields["about"].strip()[:400]
            for role in ROLES:
                if fields.get(role) is not None:
                    a[role] = template(fields[role])
            self.save(doc)
            return a

    def set_project(self, **pair) -> dict:
        """The project's own opener / ending (`intro` / `outro`: a template, or {} for none)."""
        with self.lock:
            doc = self.load()
            for role in ROLES:
                if pair.get(role) is not None:
                    doc["project"][role] = template(pair[role])
            self.save(doc)
            return doc["project"]

    def remove(self, album_id: str) -> list[str]:
        """Delete an album: its episodes stay, now in no album. Returns their ids."""
        with self.lock:
            doc = self.load()
            self._get(doc, album_id)
            doc["albums"] = [a for a in doc["albums"] if a["id"] != album_id]
            moved = sorted(e for e, a in doc["episodes"].items() if a == album_id)
            for e in moved:
                del doc["episodes"][e]
            self.save(doc)
        cover = self.cover_dir(album_id)
        if cover.is_dir():
            for p in cover.iterdir():
                p.unlink(missing_ok=True)
            cover.rmdir()
        return moved

    def assign(self, episode_id: str, album_id: str | None) -> None:
        """Put an episode into an album, or (None) into no album."""
        check_id(episode_id)
        with self.lock:
            doc = self.load()
            if album_id:
                self._get(doc, album_id)
                doc["episodes"][episode_id] = album_id
            else:
                doc["episodes"].pop(episode_id, None)
            self.save(doc)

    def drop_episode(self, episode_id: str) -> None:
        """An episode was deleted for good: forget where it was."""
        with self.lock:
            doc = self.load()
            if doc["episodes"].pop(episode_id, None) is not None:
                self.save(doc)

    # ------------------------------------------------------------------ covers
    def cover_dir(self, album_id: str) -> Path:
        try:
            return self.ws.root / COVER_DIR / check_id(album_id)
        except PathError:
            raise AlbumError(tr("没有这个专辑"), 404)

    def cover_path(self, album_id: str) -> Path | None:
        a = self._get(self.load(), album_id)
        if not a.get("cover"):
            return None
        p = self.cover_dir(album_id) / a["cover"]
        return p if p.is_file() else None

    def set_cover(self, album_id: str, data: bytes, content_type: str) -> dict:
        ext = COVER_TYPES.get(content_type)
        if not ext:
            raise AlbumError(tr("封面要是 PNG、JPG 或 WebP 图片"), 415)
        if not data:
            raise AlbumError(tr("文件是空的"))
        if len(data) > MAX_COVER:
            raise AlbumError(tr("封面图片太大（最多 10 MB）"), 413)
        with self.lock:
            doc = self.load()
            a = self._get(doc, album_id)
            d = self.cover_dir(album_id)
            d.mkdir(parents=True, exist_ok=True)
            name = f"cover_{secrets.token_hex(3)}{ext}"     # a new name: browsers don't show a cached old cover
            tmp = d / (name + ".part")
            tmp.write_bytes(data)
            tmp.replace(d / name)
            old = a.get("cover")
            a["cover"] = name
            self.save(doc)
        if old and old != name:
            (d / old).unlink(missing_ok=True)
        return a
