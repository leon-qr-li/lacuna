"""The admin's emails to the owner (decision 2026-10-24-admin-site): one 每日汇总 at 8:00 Vancouver time, and an
alert at once for what can't wait (disk over 70%, AI spending at 80% / 100% of the monthly budget, no backup for
26 hours, 3 imports failed in a row). Each alert goes out once (per day, the budget ones once per month).

The AI budget only warns: LACUNA never stops working because of it. The real ceiling is the spending limit the
owner sets in the Anthropic Console.

``tick`` runs every ``EVERY_S`` in a background thread (routes/admin.py); it also takes the CPU / memory sample
the 系统健康 page draws.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from . import notice_mail
from .capacity import describe
from .i18n import speaking, tr

EVERY_S = 300
DIGEST_HOUR = 8


def vancouver(ts: float) -> datetime:
    """Local time in Vancouver (Pacific; daylight time from the 2nd Sunday of March to the 1st Sunday of November)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(ts, ZoneInfo("America/Vancouver"))
    except Exception:          # noqa: BLE001 - no tz database in the image: the rule itself
        u = datetime.fromtimestamp(ts, timezone.utc)

        def sunday(month: int, nth: int) -> datetime:
            d = datetime(u.year, month, 1, tzinfo=timezone.utc)
            d += timedelta(days=(6 - d.weekday()) % 7)
            return d + timedelta(weeks=nth - 1)
        start = sunday(3, 2) + timedelta(hours=10)
        end = sunday(11, 1) + timedelta(hours=9)
        off = -7 if start <= u < end else -8
        return u.astimezone(timezone(timedelta(hours=off)))


def _gb(n: float) -> str:
    return f"{n / 1e9:.1f} GB"


CAPACITY_NAMES = {"disk": lambda: tr("数据盘"), "queue": lambda: tr("导入排队"), "hours": lambda: tr("本月音频"),
                  "memory": lambda: tr("内存"), "people": lambda: tr("Access 名额")}


def _cap(m: dict) -> str:
    """One measure in the digest: its number, and its level when not fine."""
    k = m["key"]
    if k == "disk":
        v = f"{round(m['value'] * 100)}%" + (tr("，约 {d} 天写满", d=round(m["days_left"])) if m.get("days_left") is not None else "")
    elif k == "queue":
        v = tr("90% 等待 ≤ {p} 分钟，最长 {l} 分钟", p=m["p90_min"], l=m["longest_min"])
    elif k == "hours":
        v = tr("{u} / {b} 小时（月底约 {p}）", u=m["used"], b=round(m["budget"]), p=m["projected"])
    elif k == "memory":
        v = "—" if m["peak"] is None else f"{round(m['peak'])}%"
    else:
        v = f"{m['accounts']} / {m['seats']}"
    grade = {"warn": tr("注意"), "act": tr("该行动"), "urgent": tr("紧急")}.get(m["level"])
    return f"{v} · {grade}" if grade else v


class Digest:
    def __init__(self, auth, store, data, origin: str, send):
        self.auth, self.store, self.data, self.origin, self.send = auth, store, data, origin.rstrip("/"), send

    def owner(self) -> dict | None:
        return next((u for u in self.auth.users.values() if u["role"] == "owner"), None)

    def tick(self) -> list[str]:
        """One round: sample, alerts, the daily digest. Returns what was sent (for tests)."""
        self.data.sample()
        self.data.capacity.collect()
        sent = []
        owner = self.owner()
        if not owner:
            return sent
        now = self.auth.now()
        local = vancouver(now)
        day = local.strftime("%Y-%m-%d")
        for a in self.data.alerts():
            key = {"disk": f"disk:{day}", "backup": f"backup:{day}", "imports": f"imports:{day}",
                   "capacity": f"cap:{a.get('measure')}:{a.get('grade')}:{day}"}.get(a["kind"])
            if a["kind"] == "ai":
                pct = 100 if a["spent"] >= a["budget"] else 80
                key = f"ai{pct}:{local.strftime('%Y-%m')}"
            if not key:
                continue
            seen = self.store.get("alerts_sent", {})
            if key in seen:
                continue
            seen = {k: v for k, v in seen.items() if now - v < 40 * 86400} | {key: now}
            self.store.put("alerts_sent", seen)
            with speaking(owner.get("lang") or "zh"):
                self.send(owner["email"], self.alert_mail(a), "alert")
            sent.append(key)
        if local.hour >= DIGEST_HOUR and self.store.get("digest_last") != day:
            self.store.put("digest_last", day)
            with speaking(owner.get("lang") or "zh"):
                self.send(owner["email"], self.digest_mail(), "digest")
            sent.append(f"digest:{day}")
        return sent

    def alert_mail(self, a: dict) -> dict:
        if a["kind"] == "disk":
            lead = tr("服务器磁盘已用 {pct}%（{used} / {total}）。先清回收区，或者准备扩容。",
                      pct=round(a["pct"] * 100), used=_gb(a["used"]), total=_gb(a["total"]))
        elif a["kind"] == "ai":
            lead = tr("这个月 AI 已经花了 ${spent}，到了预算 ${budget} 的 {pct}%。LACUNA 不会因此停下；真正的上限在 AI 服务商控制台里。",
                      spent=f"{a['spent']:.2f}", budget=f"{a['budget']:.0f}", pct=round(a["spent"] / a["budget"] * 100))
        elif a["kind"] == "capacity":
            grade = {"warn": tr("注意"), "act": tr("该行动"), "urgent": tr("紧急")}.get(a.get("grade"), "")
            line, advice = describe(a["m"])          # again, in the owner's language
            return notice_mail.render(tr("LACUNA 容量提醒（{grade}）", grade=grade), line + tr("。"), [],
                                      tr("打开后台"), f"{self.origin}/", advice + " " + tr("同一件事一天只提醒一次，升级时马上再提醒。"),
                                      tr("容量 · CAPACITY"))
        elif a["kind"] == "backup":
            lead = tr("超过 26 小时没有新的备份了。请看一下备份任务。") if a.get("at") else tr("还没有找到任何备份记录。请看一下备份任务。")
        else:
            lead = tr("最近 {n} 次导入都失败了。", n=a.get("n", 3))
        return notice_mail.render(tr("LACUNA 后台提醒"), lead, [], tr("打开后台"), f"{self.origin}/system",
                                  tr("同一件事一天只提醒一次。"), tr("提醒 · ALERT"))

    def digest_mail(self) -> dict:
        o = self.data.overview()
        t, k = o["todo"], o["kpi"]
        rows = [(tr("新反馈"), str(t["fb"])), (tr("加时长申请"), str(t["hours"])), (tr("试用申请"), str(t["trial"])),
                (tr("协作者申请"), str(t["collab"])), (tr("账号总数"), f"{k['accounts']['value']}（+{k['accounts']['delta']}）"),
                (tr("周活跃"), str(k["wau"]["value"])), (tr("本周导出"), str(k["exports"]["value"])),
                (tr("本月 AI 花费"), f"${k['ai']['value']:.2f} / ${k['ai']['budget']:.0f}"),
                (tr("磁盘"), f"{round(k['disk']['value'] * 100)}%")]
        rows += [(tr("容量 · {name}", name=CAPACITY_NAMES[m["key"]]()), _cap(m)) for m in o.get("capacity", [])]
        n = sum(t.values())
        lead = tr("今天有 {n} 件事等你处理。", n=n) if n else tr("今天没有要你处理的事。")
        return notice_mail.render(tr("LACUNA 每日汇总"), lead, rows, tr("打开后台"), self.origin,
                                  tr("每天早上 8 点（温哥华时间）发一次。"), tr("每日汇总 · DAILY"))

    def loop(self) -> None:
        while True:
            time.sleep(EVERY_S)         # first round after a while: a start (or a test) sends nothing at once
            try:
                self.tick()
            except Exception as e:      # noqa: BLE001 - a failed round tries again next time
                print(f"LACUNA: admin digest round failed: {e}", flush=True)
