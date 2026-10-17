"""Workspace layout, path safety and crash-safe JSON persistence.

Layout (user-chosen root, e.g. ``C:\\Projects\\LACUNA_Workspace``)::

    <workspace>/episodes/<episode_id>/episode.json   metadata (title, tracks, demo flag ...)
    <workspace>/episodes/<episode_id>/state.json     lacuna_core Project + edit list + history
    <workspace>/episodes/<episode_id>/publish.json   publish pack: title, show notes (phase 9)
    <workspace>/episodes/<episode_id>/poster.json    cover versions as SVG (phase 10; previews in posters/)
    <workspace>/episodes/<episode_id>/raw/           original recordings (never written)

The app only ever writes ``state.json``, ``publish.json``, ``poster.json`` (and their ``.bak``) and the
``posters/`` preview cache inside an episode folder.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

STATE_FILE = "state.json"
META_FILE = "episode.json"
PUBLISH_FILE = "publish.json"   # phase 9 publish pack (title, show notes), see publish.py
POSTER_FILE = "poster.json"     # phase 10 cover versions (SVG), see poster.py

# Episode ids are folder names. Unicode letters are fine (EP001_样本集); separators, dot-dot,
# drive letters and control characters are not.
_BAD_ID = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


class PathError(ValueError):
    """A user-supplied name would escape the workspace."""


def check_id(name: str) -> str:
    if not name or len(name) > 120 or name.startswith(".") or _BAD_ID.search(name) or name.strip() != name:
        raise PathError(f"invalid id {name!r}")
    return name


def inside(root: Path, *parts: str) -> Path:
    """Join `parts` under `root` and prove the result stays inside it (symlinks resolved)."""
    root = root.resolve()
    p = root.joinpath(*parts).resolve()
    if p != root and root not in p.parents:
        raise PathError(f"path escapes {root}")
    return p


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.episodes_dir = self.root / "episodes"

    def ensure(self) -> "Workspace":
        self.episodes_dir.mkdir(parents=True, exist_ok=True)
        return self

    def episode_dir(self, episode_id: str) -> Path:
        return inside(self.episodes_dir, check_id(episode_id))

    def episode_ids(self) -> list[str]:
        if not self.episodes_dir.is_dir():
            return []
        return sorted(p.name for p in self.episodes_dir.iterdir()
                      if (p / META_FILE).is_file() and (p / STATE_FILE).is_file())


def atomic_write_json(path: Path, data, *, protected: tuple[Path, ...] = ()) -> None:
    """Write JSON so that a crash leaves either the old or the new file, never a torn one.

    temp file in the same directory -> fsync -> keep previous as .bak -> os.replace.
    `protected` paths (source media) are refused outright.
    """
    path = Path(path)
    for p in protected:
        if Path(p).resolve() == path.resolve():
            raise PathError("refusing to write over source media")
    text = json.dumps(data, ensure_ascii=False, indent=1)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            bak = path.with_name(path.name + ".bak")
            try:
                os.replace(path, bak)
            except OSError:
                pass
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_json(path: Path):
    """Read JSON, falling back to the .bak copy if the main file is missing or corrupt."""
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        bak = path.with_name(path.name + ".bak")
        if bak.exists():
            return json.loads(bak.read_text(encoding="utf-8"))
        raise
