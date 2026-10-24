"""The admin site's own records (decision 2026-10-24-admin-site), in the site database next to everything else:

* ``admin_sessions``: sign-ins to admin.<domain>. Separate from the main site's sessions: a main-site cookie
  never opens the admin, an admin cookie never opens the main site. 8 hours, no "remember me". ``stepup``:
  until when a dangerous action needs no new authenticator code (15 minutes after the last one).
* ``admin_audit``: every change made in the admin and every admin sign-in. There is no way to delete a row.
* ``admin_notes``: notes only staff see, on a feedback item or a person.
* ``hour_requests``: 「想要更多时长」 from a user, approved or declined by the owner (never automatic).
* ``admin_errors``: the server's 5xx answers (method, path with ids blanked, status), 30 days.
* settings in ``meta`` under ``admin:`` (budget, notice, maintenance, templates, tags, sources ...).
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from typing import Any, Callable

from . import db as sitedb

SESSION_S = 8 * 3600
STEPUP_S = 15 * 60
ERRORS_KEEP_S = 30 * 86400
NOTE_MAX = 4000

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_sessions (hash TEXT PRIMARY KEY, email TEXT NOT NULL, created REAL NOT NULL,
                                           exp REAL NOT NULL, stepup REAL NOT NULL DEFAULT 0, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admin_audit (id INTEGER PRIMARY KEY, ts REAL NOT NULL, email TEXT NOT NULL,
                                        action TEXT NOT NULL, target TEXT NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS admin_audit_ts ON admin_audit(ts);
CREATE TABLE IF NOT EXISTS admin_notes (id TEXT PRIMARY KEY, target TEXT NOT NULL, ts REAL NOT NULL,
                                        email TEXT NOT NULL, text TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS admin_notes_target ON admin_notes(target, ts);
CREATE TABLE IF NOT EXISTS hour_requests (id TEXT PRIMARY KEY, email TEXT NOT NULL, created REAL NOT NULL,
                                          status TEXT NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS hour_requests_email ON hour_requests(email, created);
CREATE TABLE IF NOT EXISTS admin_errors (id INTEGER PRIMARY KEY, ts REAL NOT NULL, method TEXT NOT NULL,
                                         path TEXT NOT NULL, status INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS admin_errors_ts ON admin_errors(ts);
"""

# ids in paths, blanked so the same endpoint counts once: /api/episodes/EP012/peaks -> /api/episodes/…/peaks
_ID = re.compile(r"/(?=[^/]*\d)[^/]{3,}")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def path_shape(path: str) -> str:
    return _ID.sub("/…", path)[:120]


class AdminStore:
    def __init__(self, database: sitedb.DB, clock: Callable[[], float] = time.time):
        self.db = database
        self.now = clock
        with self.db.tx() as c:
            c.executescript_inside(SCHEMA)
        with self.db.tx() as c:
            c.execute("DELETE FROM admin_sessions WHERE exp < ?", (self.now(),))
            c.execute("DELETE FROM admin_errors WHERE ts < ?", (self.now() - ERRORS_KEEP_S,))

    # ---------------------------------------------------------------- settings
    def get(self, key: str, default: Any = None) -> Any:
        raw = self.db.meta(f"admin:{key}")
        if not raw:
            return default
        try:
            return json.loads(raw)
        except ValueError:
            return default

    def put(self, key: str, value: Any) -> None:
        self.db.set_meta(f"admin:{key}", sitedb.dumps(value))

    # ---------------------------------------------------------------- sessions
    def new_session(self, email: str, agent: str = "", ip: str | None = None, country: str | None = None) -> str:
        token = secrets.token_urlsafe(32)
        now = self.now()
        data = {"agent": (agent or "")[:200], "ip": ip, "country": country, "seen": now}
        with self.db.tx() as c:
            c.execute("DELETE FROM admin_sessions WHERE exp < ?", (now,))
            c.execute("INSERT INTO admin_sessions (hash, email, created, exp, stepup, data) VALUES (?,?,?,?,0,?)",
                      (_sha(token), email, now, now + SESSION_S, sitedb.dumps(data)))
        return token

    def session(self, token: str | None) -> dict | None:
        """The session for a cookie, or None (unknown, expired)."""
        if not token or len(token) > 200:
            return None
        rows = self.db.query("SELECT * FROM admin_sessions WHERE hash = ?", (_sha(token),))
        if not rows or rows[0]["exp"] <= self.now():
            return None
        r = rows[0]
        return {"id": r["hash"][:16], "hash": r["hash"], "email": r["email"], "created": r["created"],
                "exp": r["exp"], "stepup": r["stepup"], **sitedb.loads(r["data"])}

    def touch(self, s: dict) -> None:
        if self.now() - s.get("seen", 0) < 60:
            return
        data = {k: s.get(k) for k in ("agent", "ip", "country")} | {"seen": self.now()}
        with self.db.tx() as c:
            c.execute("UPDATE admin_sessions SET data = ? WHERE hash = ?", (sitedb.dumps(data), s["hash"]))

    def step_up(self, s: dict) -> float:
        until = self.now() + STEPUP_S
        with self.db.tx() as c:
            c.execute("UPDATE admin_sessions SET stepup = ? WHERE hash = ?", (until, s["hash"]))
        return until

    def end(self, token_hash: str) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM admin_sessions WHERE hash = ?", (token_hash,))

    def end_for(self, email: str, sid: str | None = None, keep: str | None = None) -> int:
        rows = [r for r in self.db.query("SELECT hash FROM admin_sessions WHERE email = ?", (email,))
                if r["hash"] != keep and (sid is None or r["hash"][:16] == sid)]
        with self.db.tx() as c:
            for r in rows:
                c.execute("DELETE FROM admin_sessions WHERE hash = ?", (r["hash"],))
        return len(rows)

    def sessions(self, email: str | None = None) -> list[dict]:
        now = self.now()
        q = "SELECT * FROM admin_sessions WHERE exp > ?" + (" AND email = ?" if email else "") + " ORDER BY created DESC"
        rows = self.db.query(q, (now, email) if email else (now,))
        return [{"id": r["hash"][:16], "email": r["email"], "created": r["created"], "exp": r["exp"],
                 **{k: v for k, v in sitedb.loads(r["data"]).items() if k != "ip"}} for r in rows]

    # ---------------------------------------------------------------- audit
    def audit(self, email: str, action: str, target: str = "", **data) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO admin_audit (ts, email, action, target, data) VALUES (?,?,?,?,?)",
                      (self.now(), email, action, str(target)[:200], sitedb.dumps(data)))

    def audit_rows(self, limit: int = 200, before: float | None = None) -> list[dict]:
        rows = self.db.query("SELECT * FROM admin_audit WHERE ts < ? ORDER BY ts DESC, id DESC LIMIT ?",
                             (before if before else self.now() + 1, max(1, min(limit, 1000))))
        return [{"id": r["id"], "ts": r["ts"], "email": r["email"], "action": r["action"], "target": r["target"],
                 **{"data": sitedb.loads(r["data"])}} for r in rows]

    def last_login(self, email: str) -> float | None:
        r = self.db.query("SELECT MAX(ts) AS t FROM admin_audit WHERE email = ? AND action = 'admin.login'", (email,))
        return r[0]["t"] if r else None

    # ---------------------------------------------------------------- notes
    def notes(self, target: str) -> list[dict]:
        return [dict(r) for r in self.db.query("SELECT * FROM admin_notes WHERE target = ? ORDER BY ts DESC", (target,))]

    def note_counts(self, prefix: str) -> dict[str, int]:
        return {r["target"]: r["n"] for r in self.db.query(
            "SELECT target, COUNT(*) AS n FROM admin_notes WHERE target LIKE ? GROUP BY target", (prefix + "%",))}

    def add_note(self, target: str, email: str, text: str) -> dict:
        nid = "nt_" + secrets.token_hex(6)
        row = {"id": nid, "target": target, "ts": self.now(), "email": email, "text": text.strip()[:NOTE_MAX]}
        with self.db.tx() as c:
            c.execute("INSERT INTO admin_notes (id, target, ts, email, text) VALUES (?,?,?,?,?)",
                      (nid, target, row["ts"], email, row["text"]))
        return row

    def drop_notes(self, target: str) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM admin_notes WHERE target = ?", (target,))

    # ---------------------------------------------------------------- hour requests
    def hour_requests(self, status: str | None = None, email: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM hour_requests WHERE 1=1", []
        if status:
            q, args = q + " AND status = ?", args + [status]
        if email:
            q, args = q + " AND email = ?", args + [email]
        return [{"id": r["id"], "email": r["email"], "created": r["created"], "status": r["status"],
                 **sitedb.loads(r["data"])} for r in self.db.query(q + " ORDER BY created DESC", args)]

    def add_hour_request(self, email: str, hours: float, reason: str, would_pay: bool) -> dict:
        rid = "hr_" + secrets.token_hex(6)
        data = {"hours": hours, "reason": reason.strip()[:1000], "would_pay": bool(would_pay)}
        with self.db.tx() as c:
            c.execute("INSERT INTO hour_requests (id, email, created, status, data) VALUES (?,?,?,?,?)",
                      (rid, email, self.now(), "new", sitedb.dumps(data)))
        return self.hour_request(rid)

    def hour_request(self, rid: str) -> dict | None:
        rows = self.db.query("SELECT * FROM hour_requests WHERE id = ?", (rid,))
        if not rows:
            return None
        r = rows[0]
        return {"id": r["id"], "email": r["email"], "created": r["created"], "status": r["status"],
                **sitedb.loads(r["data"])}

    def decide_hours(self, rid: str, status: str, by: str, granted: float = 0) -> dict:
        req = self.hour_request(rid)
        data = {k: v for k, v in (req or {}).items() if k not in ("id", "email", "created", "status")}
        data |= {"decided_by": by, "decided_at": self.now(), "granted": granted}
        with self.db.tx() as c:
            c.execute("UPDATE hour_requests SET status = ?, data = ? WHERE id = ?", (status, sitedb.dumps(data), rid))
        return self.hour_request(rid)

    def forget(self, email: str) -> None:
        """An account deleted: its hour requests and the notes about it go too (the audit keeps the email)."""
        with self.db.tx() as c:
            c.execute("DELETE FROM hour_requests WHERE email = ?", (email,))
            c.execute("DELETE FROM admin_notes WHERE target = ?", (f"user:{email}",))

    # ---------------------------------------------------------------- server errors
    def error(self, method: str, path: str, status: int) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO admin_errors (ts, method, path, status) VALUES (?,?,?,?)",
                      (self.now(), method, path_shape(path), status))

    def errors(self, since: float) -> list[dict]:
        rows = self.db.query("SELECT method, path, status, COUNT(*) AS n, MAX(ts) AS last FROM admin_errors "
                             "WHERE ts >= ? GROUP BY method, path, status ORDER BY n DESC LIMIT 50", (since,))
        return [dict(r) for r in rows]
