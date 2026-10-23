"""System terms (系统专有名词, decision `transcript-terms`): names every project's transcripts must spell
right, kept once for the whole installation and changed only by the site owner / admins (设置 page).

Project terms (项目设置, show.json ``terms``) are each project's own; these come on top for everyone,
e.g. ChatGPT, which the recogniser writes as 拆GPT. File ``<installation>/system_terms.json`` (atomic
write, store.py). Until someone saves the list, ``DEFAULT`` applies (Leon asked for these two, 2026-10-20).
"""
from __future__ import annotations

from pathlib import Path

from .store import atomic_write_json, read_json

FILE = "system_terms.json"
SCHEMA = 1
MAX_TERMS = 200
MAX_LEN = 40
DEFAULT = ["ChatGPT", "Claude Code"]


def installation_root(ws_root: str | Path) -> Path:
    """The installation's folder for any workspace: extra ones live at ``<root>/spaces/<id>`` (spaces.py)."""
    root = Path(ws_root)
    return root.parent.parent if root.parent.name == "spaces" else root


def clean(terms) -> list[str]:
    out, seen = [], set()
    for t in terms if isinstance(terms, list) else []:
        t = " ".join(str(t or "").split())[:MAX_LEN]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:MAX_TERMS]


def load(ws_root: str | Path) -> list[str]:
    p = installation_root(ws_root) / FILE
    if not (p.is_file() or p.with_name(FILE + ".bak").is_file()):
        return list(DEFAULT)
    try:
        return clean(read_json(p).get("terms"))
    except (OSError, ValueError, AttributeError):
        return list(DEFAULT)


def save(ws_root: str | Path, terms: list[str], by: str | None = None) -> list[str]:
    terms = clean(terms)
    atomic_write_json(installation_root(ws_root) / FILE, {"schema": SCHEMA, "terms": terms, "by": by})
    return terms
