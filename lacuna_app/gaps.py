"""间隙: a silent stretch opened between two sentences while editing (docs/decisions/2026-10-30-edit-gaps.md).

* Stored on its own, ``<episode>/gaps.json``: the voice edit (edits, cuts, the EDL) is never touched.
* A gap sits at a point of the conversation anchored in *base* samples (like an interlude), so it moves
  with later voice edits; removing it gives back exactly the episode as it was.
* The time is opened in the final mix (`music.layout`): an empty gap is silence; 「给间隙自动配乐」 puts an
  interlude into it (``gap_id`` on the placement), which plays inside the gap's length, fading in and out.
"""
from __future__ import annotations

import threading
import uuid

from .store import atomic_write_json, now_iso, read_json

FILE = "gaps.json"
SCHEMA = 1
DEFAULT_S = 15.0          # Leon 2026-10-30
MIN_S, MAX_S = 1.0, 300.0

_lock = threading.Lock()  # gaps.json is written from more than one route


def clamp_len(v: float) -> float:
    return round(min(max(float(v), MIN_S), MAX_S), 2)


def load(ep) -> list[dict]:
    path = ep.dir / FILE
    if not path.exists() and not path.with_name(FILE + ".bak").exists():
        return []
    doc = read_json(path)
    if doc.get("schema") != SCHEMA:
        raise ValueError(f"unsupported gaps schema {doc.get('schema')}")
    return doc["gaps"]


def _save(ep, gaps: list[dict]) -> None:
    gaps.sort(key=lambda g: g["at_base"])
    atomic_write_json(ep.dir / FILE, {"schema": SCHEMA, "gaps": gaps},
                      protected=tuple(m.path for m in ep.media.values()))


def add(ep, at_base: int, len_s: float = DEFAULT_S) -> dict:
    with _lock:
        gaps = load(ep)
        if any(g["at_base"] == at_base for g in gaps):     # one gap per point: the same click twice
            raise ValueError("gap exists")
        g = {"id": "gap_" + uuid.uuid4().hex[:8], "at_base": int(at_base), "len_s": clamp_len(len_s),
             "created_at": now_iso()}
        gaps.append(g)
        _save(ep, gaps)
        return g


def update(ep, gid: str, len_s: float) -> dict:
    with _lock:
        gaps = load(ep)
        g = next((x for x in gaps if x["id"] == gid), None)
        if g is None:
            raise KeyError(gid)
        g["len_s"] = clamp_len(len_s)
        _save(ep, gaps)
        return g


def remove(ep, gid: str) -> dict:
    with _lock:
        gaps = load(ep)
        g = next((x for x in gaps if x["id"] == gid), None)
        if g is None:
            raise KeyError(gid)
        _save(ep, [x for x in gaps if x["id"] != gid])
        return g
