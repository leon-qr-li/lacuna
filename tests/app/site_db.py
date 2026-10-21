"""Test helpers for the site database (lacuna_app/db.py)."""
from __future__ import annotations

from pathlib import Path

from lacuna_app import db as sitedb

TABLES = ("users", "sessions", "invites", "config", "shows", "show_members", "access_requests")


def stored(root: str | Path) -> str:
    """Everything the site database keeps about accounts and shows, as one text (to look for secrets in)."""
    db = sitedb.at(root)
    return "\n".join(" ".join(str(v) for v in tuple(r)) for t in TABLES for r in db.query(f"SELECT * FROM {t}"))


def shows(root: str | Path) -> list[dict]:
    return [sitedb.loads(r["data"]) for r in sitedb.at(root).query("SELECT data FROM shows")]

