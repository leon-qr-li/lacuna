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

Because that evidence is filed by episode id, a deleted episode's id is retired for good
(`retired_ids`): a new import never takes it, or its review snapshot, lessons and chat would be
overwritten by (or mixed into) the new episode's.
"""
from __future__ import annotations

import gc
import os
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


def retired_ids(ws: Workspace) -> set[str]:
    """Ids of deleted episodes: their learning evidence is still on file, the episode is not."""
    seen = set()
    for kind in LEARNING_EVIDENCE:
        d = ws.root / "learning" / kind
        if d.is_dir():
            seen |= {p.stem for p in d.glob("*.json")}
    return seen - set(ws.episode_ids())


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
        self.empty_trash()
        return {"deleted": episode_id, "freed_bytes": freed, "tracks": removed, "assets": assets}

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
