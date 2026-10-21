"""First-party event log: what people do in LACUNA, kept on our own server for the admin pages (batch 3).

One row per event: ``ts, uid, sid, ep, ev, props``. ``uid`` is an internal id per account (never the email),
``sid`` the show (workspace) id, ``ep`` the episode id. ``props`` holds only numbers, booleans and short
enum-like words (a category, an action): no transcript text, file names, emails or IP addresses.
Rows go to ``<root>/events/<YYYY-MM>.jsonl``; months older than ``KEEP_MONTHS`` are dropped at start.
Deleting an account forgets its uid, so its past events become anonymous.

Who is acting comes from ``ACTOR``, set per request by ``routes/events.py`` (contextvars, so it follows the
request into thread pools and import jobs that copy the context). ``track()`` anywhere in the app logs
for the current actor and never raises.
"""
from __future__ import annotations

import contextvars
import json
import math
import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .store import atomic_write_json, read_json

EVENTS_DIR = "events"
IDS_FILE = "ids.json"
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
    def __init__(self, root: Path, clock: Callable[[], float] = time.time):
        self.dir = Path(root) / EVENTS_DIR
        self.now = clock
        self.lock = threading.Lock()
        f = self.dir / IDS_FILE
        self.ids: dict[str, str] = dict(read_json(f).get("ids", {})) if f.is_file() else {}
        self._prune()

    # -- accounts
    def uid(self, email: str | None) -> str | None:
        """The account's internal id (made on first use, kept in events/ids.json)."""
        if not email:
            return None
        with self.lock:
            if email not in self.ids:
                self.ids[email] = "u_" + secrets.token_hex(6)
                self._save_ids()
            return self.ids[email]

    def forget(self, email: str) -> None:
        """The account was deleted: its past events stay, but nothing links them to the person any more."""
        with self.lock:
            if self.ids.pop(email, None) is not None:
                self._save_ids()

    def _save_ids(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.dir / IDS_FILE, {"ids": self.ids})

    # -- rows
    def _month_file(self, ts: float) -> Path:
        return self.dir / (time.strftime("%Y-%m", time.gmtime(ts)) + ".jsonl")

    def add(self, ev: str, uid: str | None, sid: str | None = None, ep: str | None = None, **props) -> dict | None:
        if not NAME.match(ev):
            return None
        ts = self.now()
        row = {"ts": round(ts, 3), "uid": uid, "sid": sid, "ep": (ep or None) and str(ep)[:64], "ev": ev,
               "props": clean_props(props)}
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self.lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            with open(self._month_file(ts), "a", encoding="utf-8") as fh:
                fh.write(line)
        return row

    def rows(self, since: float = 0.0) -> list[dict]:
        out: list[dict] = []
        for f in sorted(self.dir.glob("*.jsonl")):
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue          # a torn last line after a crash: skip it
                    if r.get("ts", 0) >= since:
                        out.append(r)
        return out

    def _prune(self) -> None:
        if not self.dir.is_dir():
            return
        t = time.gmtime(self.now())
        n = t.tm_year * 12 + t.tm_mon - 1 - KEEP_MONTHS
        oldest = f"{n // 12:04d}-{n % 12 + 1:02d}"
        for f in self.dir.glob("*.jsonl"):
            if re.match(r"^\d{4}-\d{2}$", f.stem) and f.stem < oldest:
                f.unlink(missing_ok=True)


def track(ev: str, ep: str | None = None, **props) -> None:
    """Log an event for whoever is acting now; does nothing outside a signed-in request, never raises."""
    a = ACTOR.get()
    if a is None or a.uid is None:
        return
    try:
        a.log.add(ev, a.uid, a.sid, ep, **props)
    except Exception:          # noqa: BLE001 - an event must never break the work it describes
        pass
