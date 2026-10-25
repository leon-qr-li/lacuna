"""Audio hours: what each account's shows use a month, against its allowance (decision ai-included-hour-quota,
batch 5; rules in decision 2026-10-24-hour-metering).

The business model is not settled yet, so every rule below is a setting the owner can change in the admin
(``Meter.settings``, stored in the site database); the defaults are Claude's recommendation:

* An import is counted once it succeeds (its first cut is made): the episode's length (the longest track).
  A failed or cancelled import costs nothing; resuming one costs nothing extra.
* The same files imported again in the same month (the episode deleted and imported anew) are not counted twice.
* Whose hours: the account that made the show (plans.py); collaborators spend that account's hours.
* Allowance a month = the plan's hours (the trial: once, ever) + hours the owner approved this month
  (「想要更多时长」 or given from a person's page) + the bonus for feedback adopted this month (feedback.py).
* An import may start while any hours are left (``must_fit`` off), so the last episode of a month may go over;
  with nothing left it is refused with a clear message. Site staff are counted but never refused.
* A month is a calendar month in UTC.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Callable

from . import db as sitedb
from . import plans
from .i18n import tr

SCHEMA = """
CREATE TABLE IF NOT EXISTS audio_usage (id TEXT PRIMARY KEY, email TEXT NOT NULL, month TEXT NOT NULL, at REAL NOT NULL,
                                        show_id TEXT, episode TEXT NOT NULL, hours REAL NOT NULL, sig TEXT NOT NULL,
                                        data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS audio_usage_email ON audio_usage(email, month);
"""
SETTINGS_KEY = "quota"
DEFAULTS: dict[str, Any] = {
    "enforce": True,          # refuse an import when the account has no hours left
    "must_fit": False,        # True: refuse unless the whole episode fits in what is left
    "staff_exempt": True,     # the site owner's and admins' own shows are counted, never refused
    "repeat_free": True,      # the same files imported again in the same month count once
}


class QuotaError(Exception):
    """No audio hours left; the message says so and what to do."""


def month_of(ts: float) -> str:
    return time.strftime("%Y-%m", time.gmtime(ts))


def signature(tracks: dict) -> str:
    """The same files: the same names, sizes and lengths (a re-upload makes new copies, so not the paths)."""
    parts = sorted(f"{t.get('name')}|{t.get('size')}|{t.get('duration')}" for t in tracks.values())
    return "/".join(parts)


def hours_of(tracks: dict) -> float:
    return round(max((t.get("duration") or 0 for t in tracks.values()), default=0) / 3600, 3)


class Meter:
    """Lives with the main app; every show's importer calls it (routes/imports.py). `state` is the main
    app's state: auth and spaces are read from it when needed (they register after this)."""

    def __init__(self, state: Any, clock: Callable[[], float] | None = None):
        self.state = state
        self._clock = clock
        self._ready = False

    # ---------------------------------------------------------------- plumbing
    @property
    def auth(self):
        return getattr(self.state, "auth", None)

    @property
    def spaces(self):
        return getattr(self.state, "spaces", None)

    def now(self) -> float:
        if self._clock:
            return self._clock()
        return self.auth.now() if self.auth is not None else time.time()

    @property
    def on(self) -> bool:
        """Only a site with accounts meters (a development checkout without sign-in does not)."""
        return self.auth is not None and self.spaces is not None and self.auth.has_accounts()

    @property
    def db(self) -> sitedb.DB:
        d = self.auth.db
        if not self._ready:
            with d.tx() as c:
                c.executescript_inside(SCHEMA)
            self._ready = True
        return d

    def settings(self) -> dict:
        try:
            saved = sitedb.loads(self.db.query("SELECT value FROM meta WHERE key = ?", (f"admin:{SETTINGS_KEY}",))[0]["value"])
        except (IndexError, ValueError, TypeError):
            saved = {}
        return DEFAULTS | {k: v for k, v in (saved or {}).items() if k in DEFAULTS}

    def save_settings(self, changes: dict) -> dict:
        s = self.settings() | {k: bool(v) for k, v in changes.items() if k in DEFAULTS}
        with self.db.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"admin:{SETTINGS_KEY}", sitedb.dumps(s)))
        return s

    def show_of(self, folder: Path) -> str | None:
        sp = self.spaces
        if sp is None:
            return None
        root = Path(folder).resolve()
        for sid in list(sp.spaces):
            try:
                if sp.path(sid).resolve() == root:
                    return sid
            except (OSError, KeyError):
                continue
        return None

    def payer(self, folder: Path) -> tuple[str | None, str | None]:
        """(show id, the account whose hours it spends)."""
        sid = self.show_of(folder)
        return sid, (self.spaces.creator(sid) if sid else None)

    # ---------------------------------------------------------------- the numbers
    def used(self, email: str, month: str | None = None) -> float:
        """Hours counted for `email` in `month` (None: ever)."""
        if month is None:
            rows = self.db.query("SELECT COALESCE(SUM(hours), 0) AS h FROM audio_usage WHERE email = ?", (email,))
        else:
            rows = self.db.query("SELECT COALESCE(SUM(hours), 0) AS h FROM audio_usage WHERE email = ? AND month = ?",
                                 (email, month))
        return round(float(rows[0]["h"]), 3)

    def bonus(self, email: str, month: str) -> dict:
        """Extra hours this month: approved requests (or hours given) and adopted feedback."""
        granted = 0.0
        for r in self.db.query("SELECT status, data FROM hour_requests WHERE email = ?", (email,)) \
                if self._has("hour_requests") else []:
            d = sitedb.loads(r["data"]) or {}
            if r["status"] == "approved" and d.get("decided_at") and month_of(d["decided_at"]) == month:
                granted += float(d.get("granted") or 0)
        feedback = 0.0
        for r in self.db.query("SELECT data FROM feedback WHERE email = ?", (email,)) if self._has("feedback") else []:
            d = sitedb.loads(r["data"]) or {}
            if d.get("adopted") and d.get("adopted_at") and month_of(d["adopted_at"]) == month:
                feedback += float(d.get("bonus_hours") or 0)
        return {"granted": round(granted, 2), "feedback": round(feedback, 2)}

    def _has(self, table: str) -> bool:
        return bool(self.db.query("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)))

    def account(self, email: str, now: float | None = None) -> dict:
        """What 设置 → 套餐与用量 and the admin show: used / allowance this month (the trial: ever)."""
        now = self.now() if now is None else now
        month = month_of(now)
        u = self.auth.users.get(email) or {}
        plan = u.get("plan") or plans.DEFAULT
        lim = plans.limits(plan)
        once = bool(lim.get("hours_once"))
        bonus = self.bonus(email, month)
        base = lim.get("hours")
        allowance = None if base is None else round(float(base) + bonus["granted"] + bonus["feedback"], 2)
        used = self.used(email, None if once else month)
        return {"plan": plan, "month": month, "once": once, "base": base, "bonus": bonus, "allowance": allowance,
                "used": round(used, 2), "left": None if allowance is None else round(allowance - used, 2),
                "staff": u.get("role") in ("owner", "admin")}

    # ---------------------------------------------------------------- what the importer calls
    def allow(self, folder: Path, tracks: dict) -> None:
        """Before an import starts or resumes; raises QuotaError when the show's account has nothing left."""
        if not self.on:
            return
        s = self.settings()
        if not s["enforce"]:
            return
        sid, email = self.payer(folder)
        if not email or email not in self.auth.users:
            return
        a = self.account(email)
        if a["allowance"] is None or (a["staff"] and s["staff_exempt"]):
            return
        need = hours_of(tracks)
        if s["repeat_free"] and self._repeat(email, a["month"], signature(tracks)):
            need = 0.0
        left = a["left"]
        if need == 0:
            return
        if left <= 0 or (s["must_fit"] and need > left + 1e-6):
            mine = self._viewer_is(email)
            if left <= 0:
                msg = (tr("这个月的 {n} 小时音频额度已经用完了。", n=_num(a["allowance"])) if not a["once"]
                       else tr("免费体验的 {n} 小时已经用完了。", n=_num(a["allowance"])))
            else:
                msg = tr("这一集 {need} 小时，本月额度只剩 {left} 小时。", need=_num(need), left=_num(left))
            if mine:
                msg += " " + tr("可以在「设置 → 套餐与用量」点「想要更多时长」。")
            else:
                msg += " " + tr("用的是创建这个节目的人的额度，请让 TA 在「设置 → 套餐与用量」点「想要更多时长」。")
            raise QuotaError(msg)

    def _viewer_is(self, email: str) -> bool:
        """Is the person starting the import the one whose hours it spends?"""
        from . import coedit
        who = coedit.EDITOR.get(None)
        return not who or who.get("key") == coedit.editor_for(email)["key"]

    def _repeat(self, email: str, month: str, sig: str) -> bool:
        return bool(self.db.query("SELECT 1 FROM audio_usage WHERE email = ? AND month = ? AND sig = ? AND hours > 0",
                                  (email, month, sig)))

    def charge(self, folder: Path, episode_id: str, job: dict) -> dict | None:
        """An import succeeded: count its hours against the show's account (once per job run)."""
        if not self.on:
            return None
        sid, email = self.payer(folder)
        if not email:
            return None
        tracks = job.get("tracks") or {}
        now = self.now()
        month = month_of(now)
        sig = signature(tracks)
        hours = hours_of(tracks)
        repeat = self.settings()["repeat_free"] and self._repeat(email, month, sig)
        row = {"id": uuid.uuid4().hex, "email": email, "month": month, "at": now, "show_id": sid, "episode": episode_id,
               "hours": 0.0 if repeat else hours, "sig": sig,
               "data": sitedb.dumps({"audio_h": hours, "repeat": repeat, "tracks": len(tracks),
                                     "language": job.get("language")})}
        with self.db.tx() as c:
            c.execute("INSERT INTO audio_usage (id, email, month, at, show_id, episode, hours, sig, data) "
                      "VALUES (:id, :email, :month, :at, :show_id, :episode, :hours, :sig, :data)", row)
        return row

    def rows(self, email: str | None = None, month: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM audio_usage WHERE 1=1", []
        if email:
            q, args = q + " AND email = ?", args + [email]
        if month:
            q, args = q + " AND month = ?", args + [month]
        return [dict(r) | {"data": sitedb.loads(r["data"])} for r in self.db.query(q + " ORDER BY at DESC", args)]

    def month_total(self, month: str | None = None) -> float:
        month = month or month_of(self.now())
        rows = self.db.query("SELECT COALESCE(SUM(json_extract(data, '$.audio_h')), 0) AS h FROM audio_usage WHERE month = ?",
                             (month,))
        return round(float(rows[0]["h"]), 2)

    def forget(self, email: str) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM audio_usage WHERE email = ?", (email,))


def _num(x: float) -> str:
    x = round(float(x), 1)
    return str(int(x)) if x == int(x) else str(x)
