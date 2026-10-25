"""Is the server big enough? (decision 2026-10-25-capacity-alerts, Leon 2026-10-25; thresholds from
docs/服务器容量与扩容预算_2026-10-20.md section 4.2). The admin's 5-minute round (admin_digest.py) collects, the
admin home page shows each measure against its thresholds, the 8:00 digest carries a 容量 section, and a measure
that crosses a threshold mails the owner at once (once a day per measure and level; a higher level mails again).

Measures, each at "ok", "warn" (注意), "act" (该行动) or "urgent" (紧急):

* disk: used share of the data disk, and days until full at the last 7 days' pace;
* queue: imports waiting for the speech-recognition slot (import_queue.py): 7-day p90 of the wait, the longest
  wait now;
* hours: audio hours imported this month on every show (quota.py), projected to the month's end, against what
  this server can process in a month (about 100 hours per core, ``LACUNA_CAPACITY_HOURS``);
* memory: peak of the server's memory in the readings kept (12 hours);
* people: accounts against Cloudflare Access's 50 free seats (only while Access is in front of the site).

AI spending has its own alert (admin_metrics.py, budget). Each measure says what to do: grow the disk, move the
next step of docs/服务器容量与扩容预算 forward, hold new invites.
"""
from __future__ import annotations

import calendar
import os
import time
from typing import Any

from . import cloud
from .i18n import tr

DAY = 86400
LEVELS = ("ok", "warn", "act", "urgent")
ACCESS_SEATS = 50
WAITS_KEPT_S = 7 * DAY


def _level(value: float, warn: float, act: float, urgent: float | None = None) -> str:
    if urgent is not None and value >= urgent:
        return "urgent"
    if value >= act:
        return "act"
    return "warn" if value >= warn else "ok"


def _worst(*levels: str) -> str:
    return max(levels, key=LEVELS.index)


def p90(xs: list[float]) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))]


def month_fraction(now: float) -> float:
    """How much of the current (UTC) month has gone, 0..1."""
    t = time.gmtime(now)
    days = calendar.monthrange(t.tm_year, t.tm_mon)[1]
    return min(1.0, max(1 / (days * 24), ((t.tm_mday - 1) * DAY + t.tm_hour * 3600 + t.tm_min * 60) / (days * DAY)))


class Capacity:
    """`data`: AdminData (disk, samples, the main app's state); `store`: AdminStore (history kept between restarts)."""

    def __init__(self, data: Any, store: Any, gate: Any = None):
        self.data, self.store = data, store
        if gate is None:
            from .import_queue import GATE as gate
        self.gate = gate

    @property
    def now(self) -> float:
        return self.data.now()

    def budget_hours(self) -> float:
        try:
            return float(os.environ.get("LACUNA_CAPACITY_HOURS") or (os.cpu_count() or 4) * 100)
        except ValueError:
            return 400.0

    # ---------------------------------------------------------------- collecting (every 5 minutes)
    def collect(self) -> None:
        now = self.now
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        hist = [h for h in self.store.get("disk_hist", []) if now - h["ts"] < 30 * DAY]
        if not hist or hist[-1]["day"] != day:
            d = self.data.disk()
            hist.append({"day": day, "ts": now, "used": d["used"]})
            self.store.put("disk_hist", hist)
        seen = self.store.get("queue_waits", [])
        last = max((w[0] for w in seen), default=0.0)
        new = [[ts, round(s, 1)] for ts, s in list(self.gate.waits) if ts > last]
        if new or (seen and now - seen[0][0] > WAITS_KEPT_S):
            self.store.put("queue_waits", [w for w in seen + new if now - w[0] < WAITS_KEPT_S][-2000:])

    # ---------------------------------------------------------------- the measures
    def disk(self) -> dict:
        d = self.data.disk()
        hist = self.store.get("disk_hist", [])
        week = [h for h in hist if self.now - h["ts"] <= 8 * DAY]
        days_left = None
        if len(week) >= 2 and week[-1]["ts"] > week[0]["ts"]:
            per_day = (d["used"] - week[0]["used"]) / ((self.now - week[0]["ts"]) / DAY)
            if per_day > 0:
                days_left = round((d["total"] - d["used"]) / per_day, 1)
        lv = _level(d["pct"], 0.70, 0.80, 0.90)
        if days_left is not None:
            lv = _worst(lv, "urgent" if days_left < 3 else "act" if days_left < 10 else "warn" if days_left < 21 else "ok")
        return {"key": "disk", "level": lv, "value": d["pct"], "used": d["used"], "total": d["total"], "days_left": days_left}

    def queue(self) -> dict:
        kept = self.store.get("queue_waits", [])
        last = max((w[0] for w in kept), default=0.0)
        waits = [s for _ts, s in kept] + [s for ts, s in list(self.gate.waits) if ts > last]
        load = self.gate.load()
        pct90 = p90(waits) / 60
        longest = max([load.get("longest", 0.0)] + waits) / 60 if waits or load.get("longest") else 0.0
        lv = _worst(_level(pct90, 10, 20), "urgent" if longest > 45 else "ok")
        return {"key": "queue", "level": lv, "p90_min": round(pct90, 1), "longest_min": round(longest, 1),
                "waiting": load["waiting"], "running": load["running"]}

    def hours(self) -> dict:
        meter = getattr(self.data.state, "meter", None) if self.data.state is not None else None
        used = meter.month_total() if meter is not None and meter.on else 0.0
        budget = self.budget_hours()
        projected = round(used / month_fraction(self.now), 1)
        share = projected / budget if budget else 0.0
        return {"key": "hours", "level": _level(share, 0.6, 0.8, 1.0), "used": round(used, 1), "projected": projected,
                "budget": budget}

    def memory(self) -> dict:
        peak = max((s["mem"] for s in self.data.samples if s.get("mem") is not None), default=None)
        return {"key": "memory", "level": "ok" if peak is None else _level(peak, 75, 85), "peak": peak}

    def people(self) -> dict | None:
        if not (cloud.enabled() and cloud.access_required()):
            return None
        n = len(self.data.auth.users)
        return {"key": "people", "level": _level(n, 40, 45, ACCESS_SEATS), "accounts": n, "seats": ACCESS_SEATS}

    def measures(self) -> list[dict]:
        out = [self.disk(), self.queue(), self.hours(), self.memory()]
        if (p := self.people()) is not None:
            out.append(p)
        for m in out:
            m["line"], m["advice"] = describe(m)
        return out

    def alerts(self) -> list[dict]:
        """Measures past a threshold, as alerts (admin_metrics.alerts)."""
        return [{"level": "bad" if m["level"] in ("act", "urgent") else "warn", "kind": "capacity", "measure": m["key"],
                 "grade": m["level"], "line": m["line"], "advice": m["advice"], "m": m}
                for m in self.measures() if m["level"] != "ok"]


def _gb(n: float) -> str:
    return f"{n / 1e9:.0f} GB"


def describe(m: dict) -> tuple[str, str]:
    """(what it is now, what to do), in the reader's language."""
    k = m["key"]
    if k == "disk":
        line = tr("数据盘已用 {pct}%（{used} / {total}）", pct=round(m["value"] * 100), used=_gb(m["used"]), total=_gb(m["total"]))
        if m.get("days_left") is not None:
            line += tr("，按最近 7 天的速度约 {d} 天后写满", d=round(m["days_left"]))
        return line, tr("先清回收区；不够就在 DigitalOcean 把数据盘再扩 50–100 GB（在线扩，约 15 分钟，每 100 GB 每月 +$10）。")
    if k == "queue":
        line = tr("导入排队：近 7 天 90% 的等待在 {p} 分钟以内，最长 {l} 分钟；现在 {w} 集在等", p=m["p90_min"], l=m["longest_min"], w=m["waiting"])
        return line, tr("该把同时识别的数量从 1 调到 2，并把服务器升到 8 核 16 GB（扩容路线第 3 步，每月约 +$64）。")
    if k == "hours":
        line = tr("本月已处理 {u} 小时音频，按现在的速度月底约 {p} 小时（这台服务器每月约 {b} 小时）",
                  u=m["used"], p=m["projected"], b=round(m["budget"]))
        return line, tr("准备扩容路线的下一步（升到 8 核 16 GB 或加识别工作机）；在那之前可以先暂停发新邀请。")
    if k == "memory":
        peak = "—" if m["peak"] is None else round(m["peak"])
        return tr("内存最高用到 {p}%", p=peak), tr("内存吃紧时最容易整站掉线：先确认同时识别是 1 个，再考虑升到 16 GB 内存。")
    return (tr("账号 {n} 个，Cloudflare Access 免费名额 {s} 个", n=m["accounts"], s=m["seats"]),
            tr("到 50 个以后每人每月 $7：在那之前把登录改成只用 LACUNA 自己的登录（关掉 Access），或者暂停发新邀请。"))
