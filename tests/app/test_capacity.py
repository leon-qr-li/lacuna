"""Is the server big enough? (lacuna_app/capacity.py, decision 2026-10-25-capacity-alerts): each measure against
its thresholds, the owner mailed at once (once a day per measure and level, again when it gets worse), a 容量
section in the 8:00 digest, the measures on the admin home page."""
from __future__ import annotations

import time
from collections import deque

from lacuna_app.capacity import Capacity, month_fraction, p90
from lacuna_app.import_queue import Gate

from .test_admin import OWNER, setup, sign_in

DAY = 86400
GB = 1e9


class Store(dict):
    def get(self, k, default=None):
        return super().get(k, default)

    def put(self, k, v):
        self[k] = v


class Data:
    def __init__(self, now, used=30 * GB, total=100 * GB, mem=None):
        self._now, self.used, self.total = now, used, total
        self.samples = [{"ts": now, "cpu": 10, "mem": m} for m in (mem or [])]
        self.state = None
        self.auth = type("A", (), {"users": {}})()

    def now(self):
        return self._now

    def disk(self):
        return {"used": self.used, "total": self.total, "pct": round(self.used / self.total, 4)}


def test_disk_level_by_share_and_by_days_until_full():
    t = time.time()
    data, store = Data(t - 7 * DAY, used=40 * GB), Store()
    cap = Capacity(data, store, Gate())
    cap.collect()                                     # a week ago: 40 GB
    assert cap.disk()["level"] == "ok"
    data._now, data.used = t, 61 * GB                 # 3 GB a day: 39 GB left = 13 days
    cap.collect()
    d = cap.disk()
    assert d["days_left"] == 13.0 and d["level"] == "warn"
    data.used = 85 * GB
    assert cap.disk()["level"] == "urgent"            # 15 GB left at 6.4 GB a day: under 3 days


def test_queue_p90_and_longest_wait():
    t = time.time()
    g = Gate()
    g.waits = deque([(t - 100, 60.0)] * 8 + [(t - 50, 25 * 60.0), (t - 10, 30 * 60.0)])
    store = Store()
    cap = Capacity(Data(t), store, g)
    q = cap.queue()
    assert q["p90_min"] == 25.0 and q["level"] == "act"
    cap.collect()                                     # kept between restarts, counted once
    assert len(store["queue_waits"]) == 10 and cap.queue()["p90_min"] == 25.0
    g.waits.append((t, 50 * 60.0))
    assert cap.queue()["level"] == "urgent"           # any one wait over 45 minutes


def test_hours_projected_to_the_month_end(monkeypatch):
    monkeypatch.setenv("LACUNA_CAPACITY_HOURS", "400")
    t = time.mktime((2026, 10, 16, 0, 0, 0, 0, 0, 0)) - time.timezone      # half of October (UTC)
    meter = type("M", (), {"on": True, "month_total": lambda self: 150.0})()
    data = Data(t)
    data.state = type("S", (), {"meter": meter})()
    h = Capacity(data, Store(), Gate()).hours()
    assert abs(month_fraction(t) - 15 / 31) < 0.01
    assert 300 < h["projected"] < 320 and h["level"] == "warn"          # ~310 / 400 = 78%


def test_memory_and_access_seats(monkeypatch):
    t = time.time()
    assert Capacity(Data(t, mem=[40, 88, 60]), Store(), Gate()).memory()["level"] == "act"
    assert Capacity(Data(t, mem=[]), Store(), Gate()).memory()["level"] == "ok"
    data = Data(t)
    data.auth.users = {f"u{i}@x": {} for i in range(46)}
    assert Capacity(data, Store(), Gate()).people() is None              # not in the cloud: no Access
    monkeypatch.setenv("LACUNA_CLOUD", "1")
    assert Capacity(data, Store(), Gate()).people()["level"] == "act"
    monkeypatch.setenv("LACUNA_ACCESS", "off")
    assert Capacity(data, Store(), Gate()).people() is None              # the site door is open: no seats to count


def test_p90():
    assert p90([]) == 0 and p90([5]) == 5 and p90(list(range(1, 11))) == 9


def test_capacity_alert_mails_once_a_day_and_again_when_worse(tmp_path):
    app, main, mailer = setup(tmp_path)
    auth = app.state.auth
    digest = app.state.admin_digest
    data = app.state.ctx.provide("admin_data")
    real_now, real_disk = auth.now, data.disk
    early, late = 1792852200.0, 1792854300.0     # 07:30 and 08:05 in Vancouver
    try:
        auth.now = lambda: early
        data.disk = lambda: {"used": 72 * GB, "total": 100 * GB, "pct": 0.72}
        mailer.outbox.clear()
        assert digest.tick() == ["cap:disk:warn:2026-10-24"]
        assert digest.tick() == []
        data.disk = lambda: {"used": 83 * GB, "total": 100 * GB, "pct": 0.83}
        assert digest.tick() == ["cap:disk:act:2026-10-24"]          # worse: mailed again at once
        mail = mailer.outbox[-1]
        assert mail["to"] == OWNER and "83%" in mail["text"] and "回收区" in mail["text"]
        auth.now = lambda: late
        assert digest.tick() == ["digest:2026-10-24"]
        assert "容量 · 数据盘" in mailer.outbox[-1]["text"] and "83% · 该行动" in mailer.outbox[-1]["text"]
        # the admin home page shows every measure
        auth.now = real_now
        c = sign_in(app)
        caps = c.get("/api/admin/overview").json()["capacity"]
        assert [m["key"] for m in caps] == ["disk", "queue", "hours", "memory"]
        assert caps[0]["level"] == "act" and "83%" in caps[0]["line"]
    finally:
        auth.now, data.disk = real_now, real_disk
