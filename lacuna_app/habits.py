"""Editing habits that follow the editor across projects (decision projects-albums, step 3): their
剪辑力度 (cut level) and the learned rules they approved.

Each signed-in person has a home folder ``<site root>/people/<key>/`` holding ``habits.json`` (the cut
level) and ``learning/rules.json`` (which learned rules are approved; learning.py). The evidence the rules
come from (review decisions, chat asks, lessons) stays with each project's episodes.

The dispatcher (routes/spaces.py) puts the signed-in person's home in ``HOME`` for the request; the
importer carries it into its worker thread. Without accounts (the desktop app) there is no home and
everything stays in the workspace folder, as before.

Per host, a project keeps only an adjustment (更狠 / 一样 / 更松) relative to the editor's level
(Leon 2026-10-20 18:24Z picked "global level + per-host adjust").
"""
from __future__ import annotations

import hashlib
from contextvars import ContextVar
from pathlib import Path

from .store import atomic_write_json, read_json

FILE = "habits.json"
LEVELS = ("gentle", "normal", "firm")
ADJUSTS = ("less", "same", "more")
SHIFT = {"less": -1, "same": 0, "more": 1}
# a host's cut_level from before the per-editor level: what it was relative to the default
ADJUST_OF_LEVEL = {"gentle": "less", "normal": "same", "firm": "more"}

HOME: ContextVar[Path | None] = ContextVar("lacuna_home", default=None)


def home_for(site_root: Path, email: str) -> Path:
    """The person's home folder (by a hash of the email, so no address shows in paths)."""
    key = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]
    return Path(site_root) / "people" / key


def current() -> Path | None:
    return HOME.get()


def level(home: Path | None = None) -> str:
    """The editor's 剪辑力度 ("normal" when unset or without accounts)."""
    home = home if home is not None else current()
    if home is None:
        return "normal"
    p = home / FILE
    try:
        v = read_json(p).get("cut_level") if p.is_file() else None
    except (OSError, ValueError, AttributeError):
        v = None
    return v if v in LEVELS else "normal"


def set_level(home: Path, value: str) -> str:
    if value not in LEVELS:
        raise ValueError(value)
    home.mkdir(parents=True, exist_ok=True)
    p = home / FILE
    try:
        doc = read_json(p) if p.is_file() else {}
    except (OSError, ValueError):
        doc = {}
    atomic_write_json(p, (doc if isinstance(doc, dict) else {}) | {"cut_level": value})
    return value


def host_level(adjust: str, base: str | None = None) -> str:
    """A host's effective level: the editor's level moved one step for 更狠 / 更松 (kept in range)."""
    base = base if base in LEVELS else level()
    i = LEVELS.index(base) + SHIFT.get(adjust, 0)
    return LEVELS[max(0, min(len(LEVELS) - 1, i))]
