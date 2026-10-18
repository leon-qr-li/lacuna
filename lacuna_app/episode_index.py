"""The home page's episode list without loading every episode.

Each list row is a few numbers from `Episode.summary()`. They are kept in
``<workspace>/episodes/.index.json`` together with the size and modification time of the
episode's ``episode.json`` and ``state.json``; a row is recomputed only when one of those files
changed (or the episode is in memory anyway, which is free). So opening the home page with a
hundred episodes reads one small file instead of a hundred episodes.

The index is a cache: deleting it, or copying episode folders around, only costs one rebuild.
"""
from __future__ import annotations

import threading
from typing import Callable

from .episode import Episode
from .store import META_FILE, STATE_FILE, Workspace, atomic_write_json, read_json

INDEX_FILE = ".index.json"      # inside episodes/; a dot name is never an episode id
SCHEMA = 1
FIELDS = ("id", "title", "demo", "duration", "raw_duration", "pending_review")


def _stamp(ws: Workspace, eid: str) -> list[int]:
    d = ws.episode_dir(eid)
    out: list[int] = []
    for name in (META_FILE, STATE_FILE):
        st = (d / name).stat()
        out += [st.st_mtime_ns, st.st_size]
    return out


class EpisodeIndex:
    def __init__(self, ws: Workspace, loaded: Callable[[str], Episode | None], peek: Callable[[str], Episode]):
        """`loaded(id)`: the episode if already in memory, else None; `peek(id)`: load it."""
        self.ws, self.loaded, self.peek = ws, loaded, peek
        self.path = ws.episodes_dir / INDEX_FILE
        self.lock = threading.Lock()

    def _read(self) -> dict:
        try:
            doc = read_json(self.path)
            if doc.get("schema") == SCHEMA and isinstance(doc.get("rows"), dict):
                return doc["rows"]
        except (OSError, ValueError):
            pass
        return {}

    def rows(self) -> list[dict]:
        with self.lock:
            cached = self._read()
            rows: dict[str, dict] = {}
            out: list[dict] = []
            for eid in self.ws.episode_ids():
                try:
                    ep = self.loaded(eid)
                    if ep is not None:
                        with ep.lock:     # stamp and summary of the same saved state
                            stamp = _stamp(self.ws, eid)
                            s = ep.summary()
                            row = {k: s[k] for k in FIELDS}
                    else:
                        stamp = _stamp(self.ws, eid)
                        hit = cached.get(eid)
                        if hit and hit.get("stamp") == stamp:
                            row = hit["row"]
                        else:
                            s = self.peek(eid).summary()
                            row = {k: s[k] for k in FIELDS}
                    rows[eid] = {"stamp": stamp, "row": row}
                    out.append(row)
                except Exception as e:   # a broken episode must not hide the others
                    out.append({"id": eid, "title": eid, "error": str(e)})
            if rows != cached:
                try:
                    atomic_write_json(self.path, {"schema": SCHEMA, "rows": rows})
                except OSError:
                    pass                 # only a cache: next listing rebuilds what it needs
            return out
