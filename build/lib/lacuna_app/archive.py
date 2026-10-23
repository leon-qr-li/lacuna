"""Archived episodes (首检 #3): hidden from the 剧集 list, restorable, or deleted for good.

The archive is one small file, ``<workspace>/archive.json`` (``{"episodes": {id: {"at": iso}}}``);
archiving touches nothing inside the episode folder, so restoring is exact.

Deleting for good (only an archived episode) removes the episode's own files: its folder
(edits, chat, publish pack, cover, the app's copy of demo recordings), its import cache
(``imports/<id>/``: ASR, AI windows) and recordings the app copied in when they were dragged into
the import (``imported_tracks/``, import_tracks.py). It never touches:

* ``learning/`` - Leon's rule (2026-10-17): habits are never deleted, only iterated. Before the
  folder goes, the episode's review verdicts are snapshotted into ``learning/decisions/<id>.json``
  (what 「学到的规则」 learns from) and its chat log is copied to ``learning/chats/<id>.json``,
  so asks not summarized yet are not lost;
* ``exports/<id>/`` - finished files Leon may already have published;
* recordings outside the workspace (his own Riverside downloads): the app only ever read them.

Media library assets that belonged only to this episode (本集, not shared, no other episode; see
library.py) leave the library the usual way (file moved to ``library/_removed/``); shared assets
and those another episode has or uses stay, the episode just leaves their list. Archiving touches
no asset.

That evidence is filed by episode id, so once the folder is gone it is filed away under a name of its
own, ``<id>@<date>-<rand>`` (`file_away`, decision 2026-10-21-free-episode-ids): it keeps counting for
「学到的规则」 (which reads every file in those folders) and the id is free for a new episode at once,
which then starts with no review snapshot, lessons or chat of its own. Ids deleted before that change
were kept out of use instead; `free_deleted_ids` files their evidence away the same way (run at start,
when the import form asks for the next id, and before an import takes an id).
"""
from __future__ import annotations

import gc
import os
import re
import secrets
import shutil
import threading
import uuid
from pathlib import Path
from typing import Callable

from . import import_tracks
from .store import CHAT_FILE, PathError, Workspace, atomic_write_json, check_id, inside, read_json, now_iso as _now
from .i18n import tr

ARCHIVE_FILE = "archive.json"
TRASH_DIR = ".trash"          # inside episodes/: a dot name is never an episode id


LEARNING_EVIDENCE = ("decisions", "chats", "lessons", "asks")     # learning/<kind>/<episode id>.json


NOT_EPISODES = {"direct"}         # learning/asks/direct.json: rules added directly (stutter_rule_once)
FILED_AWAY = re.compile(r"@\d{4}-\d{2}-\d{2}-[0-9a-f]{4}$")


def episode_label(name: str) -> str:
    """How a learning source reads: ``EP003@2026-10-21-a1b2`` -> 「EP003（已删）」."""
    return tr("{episode_id}（已删）", episode_id=FILED_AWAY.sub("", name)) if FILED_AWAY.search(name) else name


def _evidence_ids(ws: Workspace) -> set[str]:
    seen = set()
    for kind in LEARNING_EVIDENCE:
        d = ws.root / "learning" / kind
        if d.is_dir():
            seen |= {p.name[:-len(".json")] for p in d.glob("*.json")}
    return seen


def _relabel(doc, old: str, new: str):
    """Every ``"episode": <old>`` (or ``<old>.hand_edit``) in a learning file now names `new`."""
    if isinstance(doc, list):
        return [_relabel(x, old, new) for x in doc]
    if not isinstance(doc, dict):
        return doc
    out = {}
    for k, v in doc.items():
        if k == "episode" and isinstance(v, str) and (v == old or v.startswith(old + ".")):
            v = new + v[len(old):]
        out[k] = _relabel(v, old, new)
    return out


def file_away(ws: Workspace, episode_id: str) -> str | None:
    """File a deleted episode's learning evidence under ``<id>@<date>-<rand>``, freeing the id.

    Each file is moved first (one atomic step, so nothing is ever counted twice), then the episode
    names inside it are rewritten (an unreadable file is kept as it is). Returns the new name, or
    None when there was nothing on file."""
    new = f"{episode_id}@{_now()[:10]}-{secrets.token_hex(2)}"
    moved = False
    for kind in LEARNING_EVIDENCE:
        d = ws.root / "learning" / kind
        src, dst = d / f"{episode_id}.json", d / f"{new}.json"
        old_bak = src.with_name(src.name + ".bak")
        if not src.exists():
            if old_bak.exists():                 # only the backup survived a crash: it is the evidence
                os.replace(old_bak, dst)
                moved = True
            continue
        os.replace(src, dst)
        moved = True
        try:
            atomic_write_json(dst, _relabel(read_json(dst), episode_id, new))
        except (OSError, ValueError):
            pass
        for bak in (old_bak, dst.with_name(dst.name + ".bak")):
            try:
                bak.unlink()
            except OSError:
                pass
    return new if moved else None


def free_deleted_ids(ws: Workspace) -> dict[str, str]:
    """File away the evidence of every episode that is no longer here (ids retired before deleted
    episodes freed their id). Returns old id -> new name."""
    live = set(ws.episode_ids())
    out = {}
    for eid in sorted(_evidence_ids(ws) - live - NOT_EPISODES):
        if FILED_AWAY.search(eid):
            continue
        try:
            check_id(eid)
            if (new := file_away(ws, eid)) is not None:
                out[eid] = new
        except (OSError, PathError):
            continue           # tried again next time
    return out


class ArchiveError(RuntimeError):
    """Something Leon can act on (message in the interface language)."""


class Archive:
    def __init__(self, ws: Workspace):
        self.ws = ws
        self.path = ws.root / ARCHIVE_FILE
        self.lock = threading.Lock()

    # ---- the archive list
    def _read(self) -> dict[str, dict]:
        try:
            doc = read_json(self.path)
            eps = doc.get("episodes")
            return dict(eps) if isinstance(eps, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, eps: dict[str, dict]) -> None:
        self.ws.root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, {"schema": 1, "episodes": eps})

    def archived(self) -> dict[str, dict]:
        """Archived episodes that still exist: id -> {"at": iso time}."""
        with self.lock:
            live = set(self.ws.episode_ids())
            return {k: v for k, v in self._read().items() if k in live}

    def is_archived(self, episode_id: str) -> bool:
        return episode_id in self.archived()

    def archive(self, episode_id: str) -> dict:
        check_id(episode_id)
        with self.lock:
            if episode_id not in self.ws.episode_ids():
                raise KeyError(episode_id)
            eps = self._read()
            eps.setdefault(episode_id, {"at": _now()})
            self._write(eps)
            return eps[episode_id]

    def restore(self, episode_id: str) -> None:
        with self.lock:
            eps = self._read()
            if episode_id not in eps:
                raise KeyError(episode_id)
            del eps[episode_id]
            self._write(eps)

    # ---- deleting for good
    def delete(self, episode_id: str, *, release: Callable[[str], None] = lambda _id: None,
               keep_learning: Callable[[str], None] = lambda _id: None,
               busy: Callable[[str], str | None] = lambda _id: None,
               drop_media: Callable[[str], dict] | None = None) -> dict:
        """Remove an archived episode's files (see the module docstring for what stays).

        `busy(id)` -> a reason it can't go now (an import or export running), or None;
        `keep_learning(id)` snapshots its learning evidence (must succeed, or nothing is deleted);
        `release(id)` drops the app's in-memory copy so no file is held open;
        `drop_media(id)` takes the episode out of the media library (default: Library.drop_episode).
        """
        check_id(episode_id)
        with self.lock:
            if episode_id not in self._read() or episode_id not in self.ws.episode_ids():
                raise KeyError(episode_id)
        if (why := busy(episode_id)) is not None:
            raise ArchiveError(why)
        d = self.ws.episode_dir(episode_id)
        try:
            meta = read_json(d / "episode.json")
        except (OSError, ValueError):
            meta = {}
        keep_learning(episode_id)
        self._keep_chat(episode_id, d)
        release(episode_id)
        gc.collect()      # an evicted Episode closes its sound files when collected (Windows locks them)

        # 1. the episode folder: renamed away first (one atomic step: it either all goes or stays)
        trash = self.ws.episodes_dir / TRASH_DIR
        trash.mkdir(exist_ok=True)
        gone = trash / f"{episode_id}.{uuid.uuid4().hex[:8]}"
        try:
            os.replace(d, gone)
        except OSError:
            raise ArchiveError(tr("有文件正在被使用，删不掉。关掉这一集的其他页面后再试。"))
        release(episode_id)   # again: a request from another tab may have loaded it meanwhile
        with self.lock:
            eps = self._read()
            eps.pop(episode_id, None)
            self._write(eps)
        freed = _rmtree(gone)
        try:
            filed = file_away(self.ws, episode_id)      # the id is free for a new episode from now on
        except OSError:
            filed = None                                # free_deleted_ids does it at the next import

        # 2. the import cache, so a new import under the same id starts clean
        try:
            freed += _rmtree(inside(self.ws.root, "imports", episode_id))
        except PathError:
            pass

        # 3. recordings the app copied in at import (never Leon's own files elsewhere)
        removed = []
        for p in (meta.get("raw_tracks") or {}).values():
            f = import_tracks.owned(self.ws, p)
            if f is not None and f.is_file():
                size = f.stat().st_size
                if import_tracks.remove(self.ws, f):
                    freed += size
                    removed.append(f.name)

        # 4. library assets that were only this episode's (never shared ones, never learning data)
        assets: list[str] = []
        try:
            if drop_media is None:
                from .library import Library
                drop_media = Library(self.ws).drop_episode
            assets = list(drop_media(episode_id).get("names") or [])     # file names, for the notice
        except (OSError, ValueError, KeyError):
            pass          # the episode is gone either way; a library hiccup must not undo that
        try:
            from .albums import Albums
            Albums(self.ws).drop_episode(episode_id)
        except (OSError, ValueError):
            pass
        self.empty_trash()
        return {"deleted": episode_id, "freed_bytes": freed, "tracks": removed, "assets": assets,
                "learning_filed_as": filed}

    def _keep_chat(self, episode_id: str, d: Path) -> None:
        src = d / CHAT_FILE
        if not src.is_file():
            return
        dst_dir = self.ws.root / "learning" / "chats"
        dst_dir.mkdir(parents=True, exist_ok=True)
        try:
            atomic_write_json(dst_dir / f"{episode_id}.json", read_json(src))
        except ValueError:
            shutil.copyfile(src, dst_dir / f"{episode_id}.json")     # unreadable JSON: keep the bytes

    def empty_trash(self) -> None:
        """Finish deletions a locked file stopped earlier (also run at startup)."""
        trash = self.ws.episodes_dir / TRASH_DIR
        if trash.is_dir():
            for p in trash.iterdir():
                _rmtree(p)
            try:
                trash.rmdir()
            except OSError:
                pass


def _rmtree(p: Path) -> int:
    """Delete a folder (best effort), returning the bytes freed."""
    if not p.exists():
        return 0
    size = 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                size += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    shutil.rmtree(p, ignore_errors=True)
    return size if not p.exists() else 0
