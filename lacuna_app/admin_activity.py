"""用户动态 in the admin (decision 2026-10-31-admin-user-activity): what one account did lately, read from the
event log (lacuna_app/events.py) that the main site already writes. Nothing here writes for the user: the
page only reads, by the ``events_uid (uid, ts)`` index.

``window`` gives the rows of one time window, newest first, each with its show's and episode's names (the
episode's title from its ``episode.json``, nothing else of it). Sessions, days, merged repeats and filters are
the page's work (web/src/admin/activity/), so they follow the viewer's time zone.

Looking is recorded too: the first look at an account in ``LOOK_S`` goes to the audit log as ``user.activity``,
so a later admin can see who looked at whom (a drawer opened ten times is one line, not ten).
"""
from __future__ import annotations

import threading
from pathlib import Path

from . import db as sitedb
from .store import META_FILE, check_id, read_json

DAY = 86400
MAX_DAYS = 31
MAX_ROWS = 1000
LOOK_S = 30 * 60


class Activity:
    def __init__(self, data, store):
        """`data`: AdminData (auth, spaces, db, clock); `store`: AdminStore (the audit log)."""
        self.data, self.store = data, store
        self._looked: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def window(self, email: str, before: float | None = None, days: int = 7) -> dict:
        """Rows of [before - days, before), newest first; ``older`` says whether anything is left before them."""
        uid = self.data.auth.user_id(email)
        end = float(before) if before else self.data.now() + 1
        start = end - max(1, min(int(days), MAX_DAYS)) * DAY
        if not uid:
            return {"rows": [], "start": start, "end": end, "older": False}
        db: sitedb.DB = self.data.db
        rows = db.query("SELECT ts, sid, ep, ev, props FROM events WHERE uid = ? AND ts >= ? AND ts < ? "
                        "ORDER BY ts DESC, id DESC LIMIT ?", (uid, start, end, MAX_ROWS))
        if len(rows) == MAX_ROWS:          # a very busy week: the window ends at the oldest row we kept
            start = rows[-1]["ts"]
        older = bool(db.query("SELECT 1 FROM events WHERE uid = ? AND ts < ? LIMIT 1", (uid, start)))
        return {"rows": self._named(rows), "start": start, "end": end, "older": older}

    def latest(self, email: str, limit: int = 40) -> list[dict]:
        """The account's last `limit` rows however old (the drawer's 最近动态)."""
        uid = self.data.auth.user_id(email)
        if not uid:
            return []
        return self._named(self.data.db.query("SELECT ts, sid, ep, ev, props FROM events WHERE uid = ? "
                                              "ORDER BY ts DESC, id DESC LIMIT ?", (uid, limit)))

    def looked(self, admin: str, email: str) -> None:
        """Audit a look at `email`'s activity, at most once per LOOK_S for each admin and account."""
        now = self.data.now()
        with self._lock:
            key = (admin, email)
            if now - self._looked.get(key, -LOOK_S) < LOOK_S:
                return
            self._looked[key] = now
        self.store.audit(admin, "user.activity", email)

    # ---------------------------------------------------------------- names
    def _named(self, rows) -> list[dict]:
        names: dict = {}
        return [{"ts": r["ts"], "ev": r["ev"], "sid": r["sid"], "show": self._show(r["sid"], names), "ep": r["ep"],
                 "title": self._episode(r["sid"], r["ep"], names), "props": sitedb.loads(r["props"])} for r in rows]

    def _show(self, sid: str | None, names: dict) -> str | None:
        if not sid:
            return None
        if ("s", sid) not in names:
            spaces = self.data.spaces
            names[("s", sid)] = self.data._title(sid) if sid in spaces.spaces else None
        return names[("s", sid)]

    def _episode(self, sid: str | None, ep: str | None, names: dict) -> str | None:
        if not sid or not ep:
            return None
        key = ("e", sid, ep)
        if key not in names:
            names[key] = None
            try:
                check_id(ep)
                if sid in self.data.spaces.spaces:
                    meta = read_json(Path(self.data.spaces.path(sid)) / "episodes" / ep / META_FILE)
                    t = (meta or {}).get("title") if isinstance(meta, dict) else None
                    names[key] = str(t)[:120] if t else None
            except Exception:      # noqa: BLE001 - a deleted episode or a bad id shows as its id
                pass
        return names[key]
