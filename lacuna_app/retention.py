"""How long audio is kept (decision 2026-10-25-audio-retention, Leon 2026-10-25).

* **Exports: only the latest.** An episode's export files (``exports/<id>/<id>_<stamp>.wav|mp3``) are deleted 7 days
  after a newer export of the same episode exists. Each export's record (the ``.json``: which edits, loudness) stays.
* **Raw tracks: 12 months after the episode was last used** (opened, edited, exported; cold.last_used). 30 days
  before, the show's creator gets an email listing the episodes; using one of them (just opening it) starts its 12
  months again. Only the recordings go: the transcript, the edits, the show notes and the latest export stay for
  good, and the episode page asks for the original files if someone wants to edit it again (sources.py).
  A raw track still in cloud storage is dropped from the episode's audio_store.json; the store's daily clean-up
  then deletes it from R2.
* **During the beta nothing is deleted**: deleting raw tracks is a setting (``raw_tracks``), off by default, that
  the owner turns on in the admin (系统健康 → 存储与保留). With it off no reminder goes out either.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Iterable

from . import cold
from .store import Workspace, atomic_write_json, read_json

EXPORT_GRACE_S = 7 * 86400
RAW_KEEP_S = 365 * 86400
WARN_BEFORE_S = 30 * 86400
RECORD_FILE = "retention.json"
SETTINGS_KEY = "retention"
DEFAULTS = {"raw_tracks": False, "old_exports": True}
_STAMP = re.compile(r"_(\d{8}-\d{6})$")


def settings(db) -> dict:
    import json
    try:
        saved = json.loads(db.meta(f"admin:{SETTINGS_KEY}") or "{}")
    except ValueError:
        saved = {}
    return DEFAULTS | {k: bool(v) for k, v in (saved or {}).items() if k in DEFAULTS}


def save_settings(db, changes: dict) -> dict:
    from . import db as sitedb
    s = settings(db) | {k: bool(v) for k, v in changes.items() if k in DEFAULTS}
    db.set_meta(f"admin:{SETTINGS_KEY}", sitedb.dumps(s))
    return s


# ------------------------------------------------------------------ exports
def old_exports(ws: Workspace, episode_id: str, now: float) -> int:
    """Delete export files with a newer export more than 7 days old; returns the bytes freed."""
    d = ws.root / "exports" / episode_id
    if not d.is_dir():
        return 0
    by_stem: dict[str, list[Path]] = {}
    for p in d.iterdir():
        if p.is_file() and _STAMP.search(p.stem):
            by_stem.setdefault(p.stem, []).append(p)
    stems = sorted(by_stem, key=lambda s: _STAMP.search(s).group(1))
    freed = 0
    gone: set[str] = set()
    for older, newer in zip(stems, stems[1:]):
        try:
            since = min(p.stat().st_mtime for p in by_stem[newer])
        except (OSError, ValueError):
            continue
        if now - since < EXPORT_GRACE_S:
            continue
        for p in by_stem[older]:
            if p.suffix.lower() in cold.EXPORT_SUFFIXES:
                try:
                    size = p.stat().st_size
                    p.unlink()
                    freed += size
                except OSError:
                    pass
        gone.add(older)
    # an episode in cloud storage: its old exports leave its record (the store's clean-up deletes them in R2)
    if (store := cold.store_of(ws.episode_dir(episode_id))).get("files"):
        rels = {f"exports/{episode_id}/{s}{x}" for s in stems[:-1] for x in cold.EXPORT_SUFFIXES}
        old = [f for f in store["files"] if f["rel"] in rels and _older_than_grace(f["rel"], by_stem, stems, now)]
        if old:
            store["files"] = [f for f in store["files"] if f not in old]
            atomic_write_json(ws.episode_dir(episode_id) / cold.STORE_FILE, store)
    return freed


def _older_than_grace(rel: str, by_stem: dict, stems: list[str], now: float) -> bool:
    stem = Path(rel).stem
    if stem not in stems or stem == stems[-1]:
        return False
    newer = stems[stems.index(stem) + 1]
    try:
        return now - min(p.stat().st_mtime for p in by_stem[newer]) >= EXPORT_GRACE_S
    except (OSError, ValueError):
        return False


# ------------------------------------------------------------------ raw tracks
def raw_tracks(ws: Workspace, episode_id: str) -> list[str]:
    """The episode's recordings (cold.referenced without the exports), relative to the show folder."""
    return [r for r in cold.referenced(ws, episode_id) if not r.startswith("exports/")]


def record(ep_dir: Path) -> dict:
    try:
        r = read_json(Path(ep_dir) / RECORD_FILE)
        return r if isinstance(r, dict) else {}
    except (OSError, ValueError):
        return {}


def state(ws: Workspace, episode_id: str, now: float) -> str:
    """"keep", "warn" (reminder due), "wait" (reminded; not yet), "delete" or "gone" (already deleted)."""
    d = ws.episode_dir(episode_id)
    rec = record(d)
    used = cold.last_used(d)
    if rec.get("deleted_at") and rec["deleted_at"] >= used:
        return "gone"
    if not raw_tracks(ws, episode_id):
        return "keep"
    due = used + RAW_KEEP_S
    if now < due - WARN_BEFORE_S:
        return "keep"
    warned = rec.get("warned_at")
    if not warned or warned < used:
        return "warn"
    return "delete" if now >= due and now - warned >= WARN_BEFORE_S else "wait"


def delete_raw(ws: Workspace, episode_id: str, now: float) -> int:
    """Delete the episode's recordings (local copies, and its cloud copies from its record); returns bytes freed."""
    d = ws.episode_dir(episode_id)
    rels = raw_tracks(ws, episode_id)
    freed = 0
    for rel in rels:
        p = ws.root / rel
        try:
            size = p.stat().st_size
            p.unlink()
            freed += size
        except OSError:
            pass
    store = cold.store_of(d)
    if store.get("files"):
        store["files"] = [f for f in store["files"] if f["rel"] not in rels]
        atomic_write_json(d / cold.STORE_FILE, store)
    atomic_write_json(d / RECORD_FILE, record(d) | {"deleted_at": now, "files": rels})
    return freed


def sweep(shows: Iterable[tuple[Workspace, Callable[[str], bool], dict]], db, notify: Callable[[dict, list[dict]], None],
          now: float | None = None) -> dict:
    """One round over every show. `shows`: (workspace, busy(episode id), {"email", "title"} of the show's creator);
    `notify(show, episodes)` sends the 30-day reminder."""
    now = time.time() if now is None else now
    s = settings(db)
    out = {"exports_freed": 0, "warned": 0, "deleted": 0, "raw_freed": 0}
    for ws, busy, show in shows:
        try:
            ids = ws.episode_ids()
        except OSError:
            continue
        due: list[dict] = []
        for eid in ids:
            if busy(eid):
                continue
            if s["old_exports"]:
                out["exports_freed"] += old_exports(ws, eid, now)
            if not s["raw_tracks"]:
                continue
            st = state(ws, eid, now)
            d = ws.episode_dir(eid)
            if st == "warn":
                try:
                    title = read_json(d / "episode.json").get("title") or eid
                except (OSError, ValueError):
                    title = eid
                due.append({"id": eid, "title": title, "on": cold.last_used(d) + RAW_KEEP_S})
            elif st == "delete":
                out["raw_freed"] += delete_raw(ws, eid, now)
                out["deleted"] += 1
        if due and show.get("email"):
            notify(show, due)            # an exception here leaves the episodes un-reminded: tried again next round
            for e in due:
                d = ws.episode_dir(e["id"])
                atomic_write_json(d / RECORD_FILE, record(d) | {"warned_at": now})
            out["warned"] += len(due)
    return out
