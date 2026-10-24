"""What the admin pages show, computed from what the site already keeps (decision 2026-10-24-admin-site): accounts
and sessions (auth.py), shows (spaces.py), the event log (events.py), feedback (feedback.py), each show's
``ai_usage.jsonl`` (cost per LACUNA call), the disk, and the jobs running now. Numbers and short words only:
no audio, transcript or chat text ever leaves the shows for the admin.

Folder sizes take a while on a big disk: they are measured in the background (``sizes``), at most every
``SIZE_EVERY_S``, and the pages show the last measurement.
"""
from __future__ import annotations

import calendar
import json
import os
import shutil
import statistics
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import db as sitedb
from . import plans
from .feedback import KINDS

WEEK = 7 * 86400
DAY = 86400
SIZE_EVERY_S = 30 * 60
SILENT_DAYS = 14          # 沉默用户 (decision: 14 days)
STUCK_DAYS = 14
BETA_SEATS = 20           # beta 名额, counted by show (decision)
AI_BUDGET = 300.0         # monthly warning in USD (decision 7); the hard limit is in the Anthropic Console
DISK_WARN = 0.70
BACKUP_MARK = Path(os.environ.get("LACUNA_BACKUP_MARK", "/data/backup-canary.json"))
SAMPLES = 144             # CPU / memory every 5 minutes: 12 hours
# folders of a show, grouped for 磁盘用在哪
PART = {"imported_tracks": "raw", "imports": "raw", "recordings": "raw", "exports": "exports", "episodes": "episodes",
        "library": "music"}
# event families for 功能使用率
FEATURES = [("chat", ("chat.message",)), ("notes", ("publish.generate",)), ("poster", ("poster.generate",)),
            ("music", ("music.auto", "music.add", "music.chat")), ("levels", ("levels.auto", "levels.set")),
            ("coedit", ("show.invite",)), ("rules", ("rule.remember", "rule.update", "lessons.run"))]
ACTIVITY = ("user.signup", "import.start", "import.done", "import.error", "export.start", "show.create",
            "invite.send", "publish.generate", "poster.generate")


def _month_start(now: float) -> float:
    d = datetime.fromtimestamp(now, timezone.utc)
    return datetime(d.year, d.month, 1, tzinfo=timezone.utc).timestamp()


def _iso_ts(s: str) -> float | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError:
        return None


def _du(path: Path) -> int:
    total = 0
    stack = [path]
    while stack:
        p = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(Path(e.path))
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def feature_of(line: dict) -> str:
    """Which part of LACUNA a usage line paid for."""
    kind = line.get("kind")
    if kind in ("publish", "poster"):
        return "notes" if kind == "publish" else "poster"
    if kind == "first_cut":
        return "first_cut"
    if line.get("purpose"):
        return "rules"
    return "chat"


class AdminData:
    def __init__(self, auth, spaces, feedback, store, root: Path, app_state=None, clock=None):
        self.auth, self.spaces, self.fb, self.store = auth, spaces, feedback, store
        self.root = Path(root)
        self.state = app_state
        self.now = clock or auth.now
        self.db: sitedb.DB = auth.db
        self.started = time.time()
        self._sizes: dict = {"at": None, "shows": {}, "parts": {}, "trash": {}}
        self._size_lock = threading.Lock()
        self.samples: list[dict] = []

    # ---------------------------------------------------------------- shared
    def uid_map(self) -> dict[str, str]:
        return {u["id"]: e for e, u in self.auth.users.items() if u.get("id")}

    def events(self, since: float, evs: tuple[str, ...] | None = None) -> list[dict]:
        q, args = "SELECT ts, uid, sid, ep, ev, props FROM events WHERE ts >= ?", [since]
        if evs:
            q += f" AND ev IN ({','.join('?' * len(evs))})"
            args += list(evs)
        return [dict(r) for r in self.db.query(q + " ORDER BY ts", args)]

    def staff_emails(self) -> set[str]:
        return {e for e, u in self.auth.users.items() if u["role"] in ("owner", "admin")}

    def usage_lines(self, since: float) -> list[dict]:
        """Every LACUNA call since `since`, from each show's ai_usage.jsonl, with its show."""
        out = []
        for sid in list(self.spaces.spaces):
            f = self.spaces.path(sid) / "ai_usage.jsonl"
            try:
                if not f.is_file() or f.stat().st_mtime < since:
                    continue
                with open(f, encoding="utf-8") as fh:
                    for raw in fh:
                        try:
                            line = json.loads(raw)
                        except ValueError:
                            continue
                        ts = _iso_ts(line.get("at", ""))
                        if ts is not None and ts >= since:
                            out.append(line | {"ts": ts, "sid": sid})
            except OSError:
                continue
        return out

    def last_active(self) -> dict[str, float]:
        """email -> last time they did anything (an event, or a session seen)."""
        ids = self.uid_map()
        out: dict[str, float] = {}
        for r in self.db.query("SELECT uid, MAX(ts) AS t FROM events WHERE uid IS NOT NULL GROUP BY uid"):
            e = ids.get(r["uid"])
            if e:
                out[e] = r["t"]
        for s in self.auth.sessions.values():
            e = s["email"]
            out[e] = max(out.get(e, 0), s.get("seen", s["created"]))
        return out

    # ---------------------------------------------------------------- disk + sizes
    def disk(self) -> dict:
        try:
            d = shutil.disk_usage(self.root)
            return {"used": d.used, "total": d.total, "pct": round(d.used / d.total, 4) if d.total else 0}
        except OSError:
            return {"used": 0, "total": 0, "pct": 0}

    def sizes(self, wait: bool = False) -> dict:
        """Folder sizes: the last measurement; a new one starts in the background when it is old."""
        stale = self._sizes["at"] is None or time.time() - self._sizes["at"] > SIZE_EVERY_S
        if stale and self._size_lock.acquire(blocking=False):
            def measure():
                try:
                    shows, parts = {}, Counter()
                    for sid in list(self.spaces.spaces):
                        p = self.spaces.path(sid)
                        total = 0
                        names = [] if not p.is_dir() else [n for n in os.listdir(p)
                                                            if not (sid == "main" and n in ("spaces", "trash", "auth", "models", "tmp"))]
                        for n in names:
                            q = p / n
                            size = _du(q) if q.is_dir() else (q.stat().st_size if q.is_file() else 0)
                            total += size
                            parts[PART.get(n, "other")] += size
                        shows[sid] = total
                    trash = {}
                    tdir = self.root / "trash"
                    for d in (tdir.iterdir() if tdir.is_dir() else []):
                        trash[d.name] = _du(d)
                    parts["trash"] += sum(trash.values())
                    self._sizes = {"at": time.time(), "shows": shows, "parts": dict(parts), "trash": trash}
                finally:
                    self._size_lock.release()
            if wait:
                measure()
            else:
                threading.Thread(target=measure, name="admin-sizes", daemon=True).start()
        return self._sizes

    def sample(self) -> None:
        """One CPU / memory reading (the whole server, from /proc), kept for 12 hours."""
        s = {"ts": self.now(), "cpu": None, "mem": None}
        try:
            load = float(Path("/proc/loadavg").read_text().split()[0])
            s["cpu"] = round(min(100.0, load / (os.cpu_count() or 1) * 100), 1)
        except (OSError, ValueError, IndexError):
            pass
        try:
            info = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
            total = int(info["MemTotal"].split()[0])
            avail = int(info["MemAvailable"].split()[0])
            s["mem"] = round((1 - avail / total) * 100, 1)
        except (OSError, ValueError, KeyError):
            pass
        self.samples = (self.samples + [s])[-SAMPLES:]

    def backup(self) -> dict:
        try:
            at = _iso_ts(json.loads(BACKUP_MARK.read_text()).get("at", ""))
        except (OSError, ValueError, AttributeError):
            at = None
        snap = self.root / "lacuna-snapshot.db"
        return {"at": at, "snapshot": snap.stat().st_mtime if snap.is_file() else None}

    # ---------------------------------------------------------------- jobs running now
    def running(self) -> list[dict]:
        out = []
        apps = [("main", self.state)] if self.state is not None else []
        apps += [(sid, a.state) for sid, a in list(getattr(self.state, "space_apps", {}).items())]
        for sid, st in apps:
            imp = getattr(st, "importer", None)
            for j in list(getattr(imp, "jobs", {}).values()) if imp else []:
                if j.get("state") in ("queued", "running"):
                    out.append({"sid": sid, "show": self._title(sid), "kind": "import", "episode": j.get("title") or j["id"],
                                "state": j["state"], "progress": j.get("progress"), "started": _iso_ts(j.get("started") or j.get("created") or "")})
            exp = getattr(st, "exporter", None)
            if exp is not None and getattr(exp, "_running", None):
                out.append({"sid": sid, "show": self._title(sid), "kind": "export", "episode": exp._running, "state": "running",
                            "progress": None, "started": None})
        return out

    def _title(self, sid: str) -> str:
        try:
            return self.spaces.title(sid)
        except Exception:      # noqa: BLE001 - a show deleted a moment ago
            return sid

    # ---------------------------------------------------------------- counts for the home page
    def todo(self) -> dict:
        fb = self.db.query(f"SELECT COUNT(*) AS n FROM feedback WHERE status = 'received' AND kind IN ({','.join('?' * len(KINDS))})",
                           KINDS)[0]["n"]
        reqs = self.requests()
        return {"fb": fb, "hours": len(self.store.hour_requests("new")),
                "trial": sum(1 for r in reqs if r.get("kind") != "collab"),
                "collab": sum(1 for r in reqs if r.get("kind") == "collab")}

    def requests(self, status: str = "new") -> list[dict]:
        return [sitedb.loads(r["data"]) | {"id": r["id"], "status": r["status"], "created": r["created"]}
                for r in self.db.query("SELECT * FROM access_requests WHERE status = ? ORDER BY created DESC", (status,))
                if r["email"] not in self.auth.users]

    def ai_month(self) -> dict:
        now = self.now()
        start = _month_start(now)
        lines = self.usage_lines(start)
        spent = round(sum(float(x.get("cost_usd") or 0) for x in lines), 2)
        d = datetime.fromtimestamp(now, timezone.utc)
        days = calendar.monthrange(d.year, d.month)[1]
        elapsed = max(1.0, (now - start) / DAY)
        daily = [0.0] * days
        for x in lines:
            i = min(days - 1, int((x["ts"] - start) // DAY))
            daily[i] += float(x.get("cost_usd") or 0)
        cum, run = [], 0.0
        for i in range(min(days, int(elapsed) + 1)):
            run += daily[i]
            cum.append(round(run, 2))
        budget = float(self.store.get("ai_budget", AI_BUDGET))
        return {"spent": spent, "forecast": round(spent / elapsed * days, 2), "days": days, "cumulative": cum,
                "budget": budget, "lines": lines, "month": d.strftime("%Y-%m")}

    def weekly(self, rows: list[dict], weeks: int = 8, distinct_uid: bool = False) -> list[int]:
        now = self.now()
        out = []
        for i in range(weeks):
            a, b = now - (weeks - i) * WEEK, now - (weeks - 1 - i) * WEEK
            sel = [r for r in rows if a <= r["ts"] < b]
            out.append(len({r["uid"] for r in sel if r["uid"]}) if distinct_uid else len(sel))
        return out

    def overview(self) -> dict:
        now = self.now()
        ev = self.events(now - 8 * WEEK)
        acts = [r for r in ev if r["ev"] != "user.login"]
        wau = self.weekly(acts, distinct_uid=True)
        exports = self.weekly([r for r in ev if r["ev"] == "export.start"])
        created = sorted(u["created"] for u in self.auth.users.values())
        accounts = [sum(1 for c in created if c < now - (7 - i) * WEEK) for i in range(8)]
        ai = self.ai_month()
        disk = self.disk()
        ids = self.uid_map()
        recent = [{"ts": r["ts"], "ev": r["ev"], "who": ids.get(r["uid"]), "name": self.auth.name(ids.get(r["uid"])),
                   "show": self._title(r["sid"]) if r["sid"] in self.spaces.spaces else None, "ep": r["ep"]}
                  for r in reversed(ev) if r["ev"] in ACTIVITY][:12]
        for f in self.db.query("SELECT id, created, email FROM feedback ORDER BY created DESC LIMIT 6"):
            recent.append({"ts": f["created"], "ev": "feedback", "who": f["email"], "name": self.auth.name(f["email"]),
                           "show": None, "ep": None})
        for r in self.requests()[:6]:
            recent.append({"ts": r["created"], "ev": "request." + ("collab" if r.get("kind") == "collab" else "trial"),
                           "who": r["email"], "name": None, "show": r.get("show"), "ep": None})
        recent = sorted(recent, key=lambda x: -x["ts"])[:12]
        return {"todo": self.todo(), "alerts": self.alerts(disk, ai),
                "kpi": {"accounts": {"value": len(created), "delta": sum(1 for c in created if c >= now - WEEK), "spark": accounts},
                        "wau": {"value": wau[-1], "delta": wau[-1] - wau[-2], "spark": wau},
                        "exports": {"value": exports[-1], "delta": exports[-1] - exports[-2], "spark": exports},
                        "ai": {"value": ai["spent"], "forecast": ai["forecast"], "budget": ai["budget"], "spark": ai["cumulative"][-8:] or [0]},
                        "disk": {"value": disk["pct"], "used": disk["used"], "total": disk["total"]}},
                "wau": wau, "ai": {k: ai[k] for k in ("spent", "forecast", "days", "cumulative", "budget")},
                "activity": recent}

    def alerts(self, disk: dict | None = None, ai: dict | None = None) -> list[dict]:
        disk = disk or self.disk()
        ai = ai or self.ai_month()
        out = []
        if disk["pct"] >= DISK_WARN:
            out.append({"level": "warn", "kind": "disk", "pct": disk["pct"], "used": disk["used"], "total": disk["total"]})
        if ai["budget"] and ai["spent"] >= 0.8 * ai["budget"]:
            out.append({"level": "bad" if ai["spent"] >= ai["budget"] else "warn", "kind": "ai",
                        "spent": ai["spent"], "budget": ai["budget"]})
        b = self.backup()
        if b["at"] is not None and self.now() - b["at"] > 26 * 3600:
            out.append({"level": "warn", "kind": "backup", "at": b["at"]})
        fails = self.import_fail_streak()
        if fails >= 3:
            out.append({"level": "warn", "kind": "imports", "n": fails})
        errs = sum(e["n"] for e in self.store.errors(self.now() - DAY))
        if errs:
            out.append({"level": "info", "kind": "errors", "n": errs})
        if self.store.get("maintenance", {}).get("on"):
            out.append({"level": "info", "kind": "maintenance"})
        return out

    def import_fail_streak(self) -> int:
        rows = self.db.query("SELECT ev FROM events WHERE ev IN ('import.done', 'import.error') ORDER BY ts DESC LIMIT 10")
        n = 0
        for r in rows:
            if r["ev"] != "import.error":
                break
            n += 1
        return n

    # ---------------------------------------------------------------- users
    def users(self) -> list[dict]:
        last = self.last_active()
        month = _month_start(self.now())
        cost = Counter()
        for x in self.usage_lines(month):
            c = self.spaces.creator(x["sid"]) if x["sid"] in self.spaces.spaces else None
            if c:
                cost[c] += float(x.get("cost_usd") or 0)
        made: dict[str, list[str]] = defaultdict(list)
        member: Counter = Counter()
        for sid, s in list(self.spaces.spaces.items()):
            if s.get("sample"):
                continue
            c = self.spaces.creator(sid)
            if c:
                made[c].append(sid)
            for e in s["members"]:
                member[e] += 1
        sizes = self.sizes()["shows"]
        eps = {sid: self._episodes(sid) for sid in list(self.spaces.spaces)}
        sources = self.store.get("sources", {})
        out = []
        for e, u in self.auth.users.items():
            seen = last.get(e)
            out.append({"email": e, "name": u.get("name"), "role": u["role"], "plan": u.get("plan") or plans.DEFAULT,
                        "free": bool(u.get("plan_free")), "created": u["created"], "disabled": bool(u.get("disabled")),
                        "twofa": bool(u.get("totp")), "last": seen, "lang": u.get("lang"),
                        "silent": seen is None or self.now() - seen >= SILENT_DAYS * DAY,
                        "shows": member[e], "made": len(made[e]), "episodes": sum(eps[s] for s in made[e]),
                        "ai": round(cost[e], 2), "size": sum(sizes.get(s, 0) for s in made[e]),
                        "source": sources.get(e) or ("invited" if u.get("invited_by") else None),
                        "invited_by": u.get("invited_by"), "hours_used": None,
                        "hours": (plans.limits(u.get("plan")) or {}).get("hours")})
        return sorted(out, key=lambda r: (-{"owner": 3, "admin": 2}.get(r["role"], 1), -(r["last"] or 0)))

    def _episodes(self, sid: str) -> int:
        d = self.spaces.path(sid) / "episodes"
        try:
            return sum(1 for p in d.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
        except OSError:
            return 0

    def user_activity(self, email: str, limit: int = 40) -> list[dict]:
        uid = self.auth.user_id(email)
        if not uid:
            return []
        rows = self.db.query("SELECT ts, sid, ep, ev, props FROM events WHERE uid = ? ORDER BY ts DESC LIMIT ?", (uid, limit))
        return [{"ts": r["ts"], "ev": r["ev"], "ep": r["ep"], "props": sitedb.loads(r["props"]),
                 "show": self._title(r["sid"]) if r["sid"] in self.spaces.spaces else None} for r in rows]

    # ---------------------------------------------------------------- shows
    def shows(self) -> dict:
        sizes = self.sizes()
        last: dict[str, float] = {}
        for r in self.db.query("SELECT sid, MAX(ts) AS t FROM events WHERE sid IS NOT NULL GROUP BY sid"):
            last[r["sid"]] = r["t"]
        rows, votes = [], Counter()
        voters = 0
        from . import show as show_mod
        for sid, s in list(self.spaces.spaces.items()):
            try:
                prof = show_mod.load(self.spaces.path(sid))
            except Exception:     # noqa: BLE001 - a broken show.json must not hide the list
                prof = {}
            wish = (prof.get("publish") or {}).get("auto_wish") or []
            if wish and not s.get("sample"):
                voters += 1
                votes.update(wish)
            rows.append({"id": sid, "name": self._title(sid), "creator": self.spaces.creator(sid),
                         "members": len(s["members"]), "episodes": self._episodes(sid), "created": s["created"],
                         "last": last.get(sid), "size": sizes["shows"].get(sid), "archived": bool(s.get("archived")),
                         "sample": bool(s.get("sample")), "support": self.spaces.support_until(sid),
                         "language": prof.get("language")})
        rows.sort(key=lambda r: -(r["last"] or r["created"]))
        return {"shows": rows, "stuck": self.stuck(), "votes": dict(votes), "voters": voters,
                "sizes_at": sizes["at"]}

    def stuck(self) -> list[dict]:
        """Episodes whose import failed, or that nobody touched for 14 days without being exported."""
        now = self.now()
        ids = self.uid_map()
        last: dict[tuple, dict] = {}
        for r in self.db.query("SELECT ts, uid, sid, ep, ev FROM events WHERE ep IS NOT NULL AND sid IS NOT NULL ORDER BY ts"):
            key = (r["sid"], r["ep"])
            st = last.setdefault(key, {"exported": False, "failed": False})
            st.update(ts=r["ts"], who=ids.get(r["uid"]), ev=r["ev"])
            if r["ev"] == "export.start":
                st["exported"] = True
            if r["ev"] in ("import.error", "import.interrupted"):
                st["failed"] = True
            elif r["ev"] == "import.done":
                st["failed"] = False
        out = []
        for (sid, ep), st in last.items():
            if sid not in self.spaces.spaces or self.spaces.sample(sid):
                continue
            idle = now - st["ts"]
            if st["failed"] or (not st["exported"] and idle >= STUCK_DAYS * DAY):
                out.append({"sid": sid, "show": self._title(sid), "ep": ep, "last": st["ts"], "who": st.get("who"),
                            "ev": st["ev"], "why": "failed" if st["failed"] else "idle"})
        return sorted(out, key=lambda r: r["last"])[:100]

    # ---------------------------------------------------------------- seats and sources
    def seats(self) -> dict:
        staff = self.staff_emails()
        used = [sid for sid, s in list(self.spaces.spaces.items())
                if not s.get("sample") and self.spaces.creator(sid) not in staff and sid != "main"]
        return {"used": len(used), "total": int(self.store.get("beta_seats", BETA_SEATS))}

    def sources(self) -> list[dict]:
        sources = self.store.get("sources", {})
        invited = self.store.get("invited_sources", {})
        last = self.last_active()
        rows: dict[str, dict] = {}
        for e, src in invited.items():
            r = rows.setdefault(src, {"source": src, "invited": 0, "joined": 0, "week4": 0})
            r["invited"] += 1
        for e, src in sources.items():
            u = self.auth.users.get(e)
            r = rows.setdefault(src, {"source": src, "invited": 0, "joined": 0, "week4": 0})
            if not u:
                continue
            r["joined"] += 1
            if self.now() - u["created"] >= 4 * WEEK and (last.get(e) or 0) >= u["created"] + 3 * WEEK:
                r["week4"] += 1
        return sorted(rows.values(), key=lambda r: -r["invited"])

    # ---------------------------------------------------------------- AI
    def ai(self) -> dict:
        m = self.ai_month()
        lines = m.pop("lines")
        by_feat, by_user = Counter(), Counter()
        refusals = 0
        for x in lines:
            c = float(x.get("cost_usd") or 0)
            by_feat[feature_of(x)] += c
            who = self.spaces.creator(x["sid"]) if x["sid"] in self.spaces.spaces else None
            by_user[who or "—"] += c
            if x.get("refusal"):
                refusals += 1
        start = _month_start(self.now())
        audio = Counter()
        fails = 0
        ids = self.uid_map()
        for r in self.events(start, ("import.done", "import.error")):
            if r["ev"] == "import.error":
                fails += 1
                continue
            p = sitedb.loads(r["props"]) if isinstance(r["props"], str) else r["props"]
            sid = r["sid"]
            who = self.spaces.creator(sid) if sid in self.spaces.spaces else ids.get(r["uid"])
            audio[who or "—"] += float(p.get("audio_s") or 0) / 3600
        hours = sum(audio.values())
        top = [{"email": e, "name": self.auth.name(e), "cost": round(c, 2), "hours": round(audio.get(e, 0), 2),
                "per_hour": round(c / audio[e], 2) if audio.get(e) else None} for e, c in by_user.most_common(10)]
        # AI edits kept vs restored at review, by category (first cut only), this month and last
        keep: dict[str, Counter] = defaultdict(Counter)
        for r in self.events(self.now() - 60 * DAY, ("review.decide",)):
            p = sitedb.loads(r["props"]) if isinstance(r["props"], str) else r["props"]
            if p.get("source") != "first_cut":
                continue
            keep[p.get("category") or "other"][p.get("action") or "?"] += 1
        accuracy = []
        for cat, c in keep.items():
            restored = c.get("restore", 0) + c.get("restored", 0)
            total = sum(c.values())
            accuracy.append({"category": cat, "kept": round(1 - restored / total, 3) if total else None, "n": total})
        rules = self.db.query("SELECT COUNT(*) AS n FROM events WHERE ev IN ('rule.remember', 'lessons.decide') AND ts >= ?", (start,))[0]["n"]
        return m | {"per_hour": round(m["spent"] / hours, 2) if hours else None, "target": 1.8, "hours": round(hours, 2),
                    "features": {k: round(v, 2) for k, v in by_feat.items()}, "top": top,
                    "fails": {"imports": fails, "refusals": refusals}, "accuracy": sorted(accuracy, key=lambda a: -a["n"]),
                    "rules_month": rules, "calls": len(lines)}

    # ---------------------------------------------------------------- growth
    def growth(self, weeks: int = 8) -> dict:
        now = self.now()
        ev = self.events(now - max(weeks, 6) * WEEK - 30 * DAY)
        ids = self.uid_map()
        acts = [r for r in ev if r["ev"] != "user.login"]
        wau = self.weekly(acts, weeks, distinct_uid=True)
        signups = self.weekly([r for r in ev if r["ev"] == "user.signup"], weeks)
        # activation: exported a first episode within 7 days of signing up (accounts at least 7 days old)
        first_export: dict[str, float] = {}
        for r in self.db.query("SELECT uid, MIN(ts) AS t FROM events WHERE ev = 'export.start' GROUP BY uid"):
            if r["uid"] in ids:
                first_export[ids[r["uid"]]] = r["t"]
        members = [u for u in self.auth.users.values() if u["role"] == "member"]
        old = [u for u in members if now - u["created"] >= 7 * DAY]
        activated = [u for u in old if first_export.get(u["email"], 1e18) - u["created"] <= 7 * DAY]
        month = [r for r in acts if r["ts"] >= now - 30 * DAY]
        active_month = {r["uid"] for r in month if r["uid"]}
        eps_month = {(r["sid"], r["ep"]) for r in month if r["ev"] == "export.start"}
        langs = Counter((u.get("lang") or "zh") for u in self.auth.users.values())
        # the episode funnel (all time): first time each step happened, per episode
        first: dict[tuple, dict[str, float]] = defaultdict(dict)
        for r in self.db.query("SELECT ts, sid, ep, ev FROM events WHERE ep IS NOT NULL AND ev IN "
                               "('import.start','import.done','review.batch','review.decide','export.start','publish.generate') ORDER BY ts"):
            step = {"review.batch": "review", "review.decide": "review"}.get(r["ev"], r["ev"])
            first[(r["sid"], r["ep"])].setdefault(step, r["ts"])
        steps = ["import.start", "import.done", "review", "export.start", "publish.generate"]
        funnel = [{"step": s, "n": sum(1 for f in first.values() if s in f)} for s in steps]
        durations = []
        for a, b in zip(steps, steps[1:]):
            d = [f[b] - f[a] for f in first.values() if a in f and b in f and f[b] >= f[a]]
            durations.append({"from": a, "to": b, "median": statistics.median(d) if d else None, "n": len(d)})
        uses = []
        for name, evs in FEATURES:
            users = {r["uid"] for r in month if r["ev"] in evs and r["uid"]}
            uses.append({"feature": name, "pct": round(len(users) / len(active_month), 3) if active_month else None})
        # weekly retention by signup week (the last 6 weeks)
        by_uid: dict[str, list[float]] = defaultdict(list)
        for r in acts:
            if r["uid"]:
                by_uid[r["uid"]].append(r["ts"])
        cohorts = []
        for i in range(6):
            a, b = now - (6 - i) * WEEK, now - (5 - i) * WEEK
            group = [u for u in self.auth.users.values() if a <= u["created"] < b]
            row = []
            for n in range(6 - i):
                lo, hi = a + n * WEEK, a + (n + 1) * WEEK
                kept = sum(1 for u in group if any(lo <= t < hi for t in by_uid.get(u.get("id"), [])))
                row.append(round(kept / len(group), 3) if group else None)
            cohorts.append({"start": a, "size": len(group), "weeks": row})
        regions = Counter()
        for r in self.db.query("SELECT data FROM feedback_profiles"):
            reg = sitedb.loads(r["data"]).get("region")
            if reg:
                regions[reg] += 1
        return {"wau": wau, "signups": signups,
                "activation": {"rate": round(len(activated) / len(old), 3) if old else None, "of": len(old), "n": len(activated)},
                "per_user_month": round(len(eps_month) / len(active_month), 2) if active_month else None,
                "active_month": len(active_month), "langs": dict(langs), "funnel": funnel, "durations": durations,
                "features": uses, "cohorts": cohorts, "regions": dict(regions)}

    # ---------------------------------------------------------------- feedback extras
    def prompts(self) -> dict:
        rows = self.db.query("SELECT created, email, kind, data FROM feedback WHERE kind IN ('rate', 'pmf', 'nps') ORDER BY created DESC")
        rate, pmf, nps, saved = Counter(), Counter(), Counter(), Counter()
        quotes = []
        for r in rows:
            d = sitedb.loads(r["data"])
            if r["kind"] == "rate" and d.get("stars"):
                rate[d["stars"]] += 1
                if d.get("saved"):
                    saved[d["saved"]] += 1
            elif r["kind"] == "pmf" and d.get("choice"):
                pmf[d["choice"]] += 1
            elif r["kind"] == "nps" and d.get("score") is not None:
                nps[int(d["score"])] += 1
            if d.get("text"):
                quotes.append({"kind": r["kind"], "at": r["created"], "email": r["email"], "name": self.auth.name(r["email"]),
                               "text": d["text"], "stars": d.get("stars"), "choice": d.get("choice"), "score": d.get("score")})
        n = sum(nps.values())
        promoters = sum(v for k, v in nps.items() if k >= 9)
        detractors = sum(v for k, v in nps.items() if k <= 6)
        return {"rate": {str(k): v for k, v in rate.items()}, "saved": dict(saved), "pmf": dict(pmf),
                "nps": {"scores": {str(k): v for k, v in nps.items()}, "n": n,
                        "score": round((promoters - detractors) / n * 100) if n else None,
                        "promoters": promoters, "passives": n - promoters - detractors, "detractors": detractors},
                "quotes": quotes[:100]}

    def profiles(self) -> dict:
        out = {"region": Counter(), "editing": Counter(), "lang": Counter()}
        n = 0
        for r in self.db.query("SELECT data FROM feedback_profiles"):
            d = sitedb.loads(r["data"])
            n += 1
            for k in out:
                if d.get(k):
                    out[k][d[k]] += 1
        return {"n": n, **{k: dict(v) for k, v in out.items()}}
