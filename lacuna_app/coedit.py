"""Several people in one episode at once: the safety net (decision 2026-10-21-co-editing-safety-net).

Edits were already safe to make together (each one a small server-side step under the episode's lock,
in base-recording coordinates, overlaps refused). What this adds:

* who is making a request (`EDITOR`, set by the dispatcher in routes/spaces.py from the sign-in), so
  undo history and saves can say whose step it was;
* `StaleError`: a save based on something another person has changed since (a review decision on an
  edit they just changed, show notes or 节目设置 they just saved) is refused with 409 and ``stale``, and
  the page loads the latest instead of quietly overwriting it;
* `Presence`: who else has this episode open right now (a heartbeat every few seconds), in memory only.

Live co-editing (changes pushed to every screen, cursors) is option B of the assessment, not this.
Without accounts (a local install) there is one editor and none of this shows.
"""
from __future__ import annotations

import hashlib
import threading
import time
from contextvars import ContextVar

from .episode import ConflictError

EDITOR: ContextVar[dict | None] = ContextVar("lacuna_editor", default=None)
SEEN_S = 20.0          # a page that has not said hello for this long has left


def editor_for(email: str) -> dict:
    """``{"key": <hash>, "name": <what others see>}`` for a signed-in person (no address in files)."""
    email = email.strip().lower()
    return {"key": hashlib.sha256(email.encode()).hexdigest()[:16], "name": email.split("@")[0]}


def current() -> dict | None:
    return EDITOR.get()


def me() -> str | None:
    """The signed-in person's key, or None without accounts."""
    e = EDITOR.get()
    return e["key"] if e else None


def stamp() -> dict:
    """Who made a change, for history entries and saved files: ``{"by": key, "by_name": name}``."""
    e = EDITOR.get()
    return {"by": e["key"], "by_name": e["name"]} if e else {}


class StaleError(ConflictError):
    """The change is based on an older version than the one on file (answered 409 with ``stale``)."""


class Presence:
    """Who has which episode open: (episode, person) -> last heartbeat. One per workspace."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.seen: dict[str, dict[str, dict]] = {}

    def hello(self, episode_id: str, editor: dict | None) -> list[dict]:
        """Note that `editor` is here; returns the others here now, longest-present first. Without
        accounts (`editor` None) there is nobody to show."""
        if not editor:
            return []
        now = self.clock()
        with self.lock:
            here = self.seen.setdefault(episode_id, {})
            for k in [k for k, v in here.items() if now - v["at"] > SEEN_S]:
                del here[k]
            was = here.get(editor["key"])
            here[editor["key"]] = {"name": editor["name"], "at": now, "since": was["since"] if was else now}
            return [{"name": v["name"]} for k, v in sorted(here.items(), key=lambda kv: kv[1]["since"])
                    if k != editor["key"]]

    def bye(self, episode_id: str, editor: dict | None) -> None:
        if editor:
            with self.lock:
                self.seen.get(episode_id, {}).pop(editor["key"], None)
