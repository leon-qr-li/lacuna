"""Raw tracks dragged into (or picked in) the import form (首检 #4).

A browser never tells the page where a dropped file lives, so the file's bytes are sent to the
local app (127.0.0.1 only) and kept as ``<workspace>/imported_tracks/<token>/<name>``; the import
then reads that copy like any other raw track (read-only, D29). Nothing leaves this machine.

Copies no import or episode uses are pruned after a day (a form that was abandoned); removing an
archived episode for good deletes its copies (archive.py).
"""
from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path
from typing import Iterable

from .store import PathError, Workspace, inside

TRACKS_DIR = "imported_tracks"
MAX_TRACK = 8 * 1024 ** 3          # a 3-hour 48 kHz 32-bit float WAV is ~2 GB; leave room
STALE_S = 24 * 3600
_BAD = '\\/:*?"<>|\x00'


def tracks_dir(ws: Workspace) -> Path:
    return ws.root / TRACKS_DIR


def safe_name(name: str) -> str:
    n = "".join("_" if c in _BAD or ord(c) < 32 else c for c in Path(name.replace("\\", "/")).name).strip(" .")
    if not n:
        raise PathError("empty file name")
    return n[:150]


def new_target(ws: Workspace, name: str) -> Path:
    """Where an incoming file goes: a fresh folder per file, keeping its own name (shown in the UI)."""
    d = tracks_dir(ws) / uuid.uuid4().hex[:12]
    d.mkdir(parents=True, exist_ok=True)
    return d / safe_name(name)


def owned(ws: Workspace, path: str | Path) -> Path | None:
    """`path` as one of our copies, or None when it is anywhere else (Leon's own files)."""
    root = tracks_dir(ws)
    try:
        p = Path(path).resolve()
        rel = p.relative_to(root.resolve())
        return inside(root, *rel.parts) if len(rel.parts) == 2 else None
    except (ValueError, PathError, OSError):
        return None


def remove(ws: Workspace, path: str | Path) -> bool:
    """Delete one of our copies (the form dropped it); never anything outside imported_tracks/."""
    p = owned(ws, path)
    if p is None or not p.is_file():
        return False
    shutil.rmtree(p.parent, ignore_errors=True)
    return True


def prune(ws: Workspace, in_use: Iterable[str], now: float | None = None) -> list[str]:
    """Remove copies older than a day that no import job or episode refers to."""
    root = tracks_dir(ws)
    if not root.is_dir():
        return []
    keep = {str(Path(p).resolve()) for p in in_use if p}
    now = time.time() if now is None else now
    out = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        files = list(d.iterdir())
        if any(str(f.resolve()) in keep for f in files):
            continue
        try:
            age = now - max([d.stat().st_mtime] + [f.stat().st_mtime for f in files])
        except OSError:
            continue
        if age > STALE_S:
            shutil.rmtree(d, ignore_errors=True)
            out.append(d.name)
    return out
