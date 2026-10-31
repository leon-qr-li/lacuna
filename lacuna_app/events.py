"""First-party event log: what people do in LACUNA, kept on our own server for the admin pages (batch 3).

One row per event: ``ts, uid, sid, ep, ev, props``. ``uid`` is the account's internal id (never the email),
``sid`` the show (workspace) id, ``ep`` the episode id. ``props`` holds only numbers, booleans and short
enum-like words (a category, an action): no transcript text, file names, emails or IP addresses.
Rows go to the site database (``events`` table); rows older than ``KEEP_MONTHS`` are dropped at start.
Deleting an account deletes the only link from its uid to the person, so its past events become anonymous.

Who is acting comes from ``ACTOR``, set per request by ``routes/events.py`` (contextvars, so it follows the
request into thread pools and import jobs that copy the context). ``track()`` anywhere in the app logs
for the current actor and never raises; ``note()`` adds numbers to the row the request itself logs.
"""
from __future__ import annotations

import contextvars
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from . import db as sitedb

KEEP_MONTHS = 13
NAME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
WORD = re.compile(r"^[A-Za-z0-9_.:-]{1,48}$")
MAX_PROPS = 12


@dataclass(frozen=True)
class Actor:
    log: "EventLog"
    uid: str | None
    sid: str | None


ACTOR: contextvars.ContextVar[Actor | None] = contextvars.ContextVar("lacuna_event_actor", default=None)
# details for the row the request's own event gets (routes/events.py sets a fresh dict per request; `note` fills it)
NOTE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("lacuna_event_note", default=None)


def clean_props(props: dict[str, Any]) -> dict[str, Any]:
    """Numbers, booleans and short words only; anything else is dropped, never logged."""
    out: dict[str, Any] = {}
    for k, v in props.items():
        if len(out) >= MAX_PROPS or not isinstance(k, str) or not WORD.match(k):
            continue
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, int):
            out[k] = v
        elif isinstance(v, float) and math.isfinite(v):
            out[k] = round(v, 3)
        elif isinstance(v, str) and WORD.match(v) and "@" not in v:
            out[k] = v
    return out


class EventLog:
    """Rows in the site database's ``events`` table (lacuna_app/db.py). `uid_of` gives an account's
    internal id (Auth.user_id); a deleted account's id no longer leads to anyone."""

    def __init__(self, database: sitedb.DB, uid_of: Callable[[str | None], str | None],
                 clock: Callable[[], float] = time.time):
        self.db = database
        self.uid = uid_of
        self.now = clock
        self._prune()

    def add(self, ev: str, uid: str | None, sid: str | None = None, ep: str | None = None, **props) -> dict | None:
        if not NAME.match(ev):
            return None
        row = {"ts": round(self.now(), 3), "uid": uid, "sid": sid, "ep": (ep or None) and str(ep)[:64], "ev": ev,
               "props": clean_props(props)}
        with self.db.tx() as c:
            c.execute("INSERT INTO events (ts, uid, sid, ep, ev, props) VALUES (?,?,?,?,?,?)",
                      (row["ts"], uid, sid, row["ep"], ev, sitedb.dumps(row["props"])))
        return row

    def rows(self, since: float = 0.0) -> list[dict]:
        return [{"ts": r["ts"], "uid": r["uid"], "sid": r["sid"], "ep": r["ep"], "ev": r["ev"],
                 "props": sitedb.loads(r["props"])}
                for r in self.db.query("SELECT * FROM events WHERE ts >= ? ORDER BY id", (since,))]

    def _prune(self) -> None:
        """Raw events older than KEEP_MONTHS go (the admin pages keep their own totals)."""
        cutoff = self.now() - KEEP_MONTHS * 31 * 86400
        with self.db.tx() as c:
            c.execute("DELETE FROM events WHERE ts < ?", (cutoff,))


def track(ev: str, ep: str | None = None, **props) -> None:
    """Log an event for whoever is acting now; does nothing outside a signed-in request, never raises."""
    a = ACTOR.get()
    if a is None or a.uid is None:
        return
    try:
        a.log.add(ev, a.uid, a.sid, ep, **props)
    except Exception:          # noqa: BLE001 - an event must never break the work it describes
        pass


def note(**props) -> None:
    """Numbers for the event this request logs when it ends (e.g. how many seconds a cut took out): they go in
    the same row, so a detail never costs a write of its own. Does nothing outside a request."""
    n = NOTE.get()
    if n is not None:
        n.update(props)
