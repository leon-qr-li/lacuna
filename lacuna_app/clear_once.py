"""One-time clean-out of the cloud workspace (Leon, 2026-10-19; decision cloud-clean-out).

Leon's recordings are no longer on his computer, so the cloud copy of every episode is of no use to
him. He asked to delete everything except habits and the rules LACUNA learned, then test from
scratch, and confirmed the list in writing (thread 「声音播放不了」, 2026-10-19 22:03Z, EP001 included).
Run once, at startup, on the main workspace of the cloud server (production and staging), never on
the desktop app or another person's workspace:

* every episode goes the way 「永久删除」 sends it (archive.py): its review verdicts and chat are
  snapshotted into ``learning/`` first, so 「学到的规则」 keeps everything it learned;
* then the media library (music, jingles, clips, series rules), finished exports, the import cache
  and the app's copies of recordings.

Kept: ``learning/`` (habits, rules, per-episode lessons), accounts and invites (``auth/``), other
workspaces (``spaces/``), the show settings, corrected names, the AI usage log and speech models.
A marker file makes it run once; it is written only when every episode went, so an episode that
could not be cleared (its learning could not be saved) is tried again at the next start and nothing
else is touched until then. The nightly encrypted backup still holds the data from before.
This module goes away in a later release, once both sites have run it.
"""
from __future__ import annotations

import logging
from typing import Callable

from .archive import Archive, ArchiveError, _rmtree
from .store import Workspace, now_iso

log = logging.getLogger("lacuna.clear_once")

MARKER = ".cleared-2026-10-19"
FOLDERS = ("library", "exports", "imports", "imported_tracks")


def done(ws: Workspace) -> bool:
    return (ws.root / MARKER).exists()


def run(ws: Workspace, *, keep_learning: Callable[[str], None], release: Callable[[str], None]) -> dict:
    """Clear the workspace (see the module docstring); returns what went and what could not."""
    archive = Archive(ws)
    deleted, failed = [], []
    for eid in ws.episode_ids():
        try:
            archive.archive(eid)
            archive.delete(eid, keep_learning=keep_learning, release=release, drop_media=lambda _id: {})
            deleted.append(eid)
        except Exception as e:         # keep this episode (and everything else) for the next start
            failed.append(eid)
            if eid in ws.episode_ids():
                try:
                    archive.restore(eid)
                except KeyError:
                    pass
            log.warning("clean-out: episode %s kept (%s)", eid, type(e).__name__)
    if failed:
        return {"deleted": deleted, "failed": failed, "freed_bytes": 0}
    freed = sum(_rmtree(ws.root / name) for name in FOLDERS)
    (ws.root / MARKER).write_text(now_iso() + "\n", encoding="utf-8")
    return {"deleted": deleted, "failed": [], "freed_bytes": freed}
