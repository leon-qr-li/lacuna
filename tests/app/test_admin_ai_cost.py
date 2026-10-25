"""AI cost per audio hour in the admin counts only episodes imported this month (Leon 2026-10-25 saw $172.92)."""
from __future__ import annotations

import time

from lacuna_app.admin_metrics import AI_HOUR_TARGET, AdminData


class Spaces:
    spaces = {"s1": {}}

    def creator(self, sid):
        return "leon@example.com"


class Auth:
    users = {"leon@example.com": {"id": "u1", "role": "owner"}}

    def name(self, email):
        return "Leon"


class Store:
    def get(self, key, default):
        return default


class DB:
    def query(self, q, args=()):
        return [{"n": 0}]


def data(lines, events):
    d = object.__new__(AdminData)
    now = time.time()
    d.spaces, d.auth, d.store, d.db, d.now = Spaces(), Auth(), Store(), DB(), lambda: now
    d.usage_lines = lambda since: [x | {"ts": now - 60, "sid": "s1"} for x in lines]
    d.events = lambda since, evs=None: [e for e in events if evs is None or e["ev"] in evs]
    return d


def test_chat_on_an_older_episode_does_not_blow_up_the_cost_per_hour():
    lines = [{"episode": "EP013", "cost_usd": 14.0},                  # chat on an episode imported last month
             {"episode": "EP014", "cost_usd": 3.0}, {"episode": "EP014", "cost_usd": 0.8}]
    events = [{"ev": "import.done", "sid": "s1", "ep": "EP014", "uid": "u1", "props": {"audio_s": 3600}}]
    a = data(lines, events).ai()
    assert a["spent"] == 17.8
    assert a["per_hour"] == 3.8 and a["unmetered"] == 14.0 and a["target"] == AI_HOUR_TARGET
    assert a["top"][0]["cost"] == 17.8 and a["top"][0]["per_hour"] == 3.8


def test_no_import_this_month_means_no_cost_per_hour():
    a = data([{"episode": "EP013", "cost_usd": 2.0}], []).ai()
    assert a["per_hour"] is None and a["unmetered"] == 2.0
