"""How long audio is kept (lacuna_app/retention.py, decision 2026-10-25-audio-retention): only the latest export
(older ones go 7 days after a newer one), raw tracks 12 months after last use with a reminder 30 days before, and
nothing deleted while the owner leaves raw-track deletion off (the beta)."""
from __future__ import annotations

import os
import time
from pathlib import Path

from lacuna_app import Workspace, retention
from lacuna_app.cold import STORE_FILE, last_used
from lacuna_app.retention import EXPORT_GRACE_S, RAW_KEEP_S, WARN_BEFORE_S, old_exports, raw_tracks, state

from .synth import EPISODE, make_workspace
from .test_admin import OWNER, WRITE, setup, sign_in, step_up

DAY = 86400


def export(ws: Workspace, stamp: str, at: float) -> list[Path]:
    d = ws.root / "exports" / EPISODE
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for ext in (".wav", ".mp3", ".json"):
        p = d / f"{EPISODE}_{stamp}{ext}"
        p.write_bytes(b"x" * 100)
        os.utime(p, (at, at))
        out.append(p)
    return out


def test_only_the_latest_export_stays_seven_days_after_a_newer_one(tmp_path):
    ws = Workspace(make_workspace(tmp_path / "ws"))
    now = time.time()
    a = export(ws, "20261001-100000", now - 30 * DAY)
    b = export(ws, "20261010-100000", now - 8 * DAY)
    c = export(ws, "20261020-100000", now - 2 * DAY)
    assert old_exports(ws, EPISODE, now) == 200           # a's wav + mp3 (b is newer than a by > 7 days)
    assert not a[0].exists() and not a[1].exists() and a[2].exists()     # the record stays
    assert all(p.exists() for p in b + c)                  # c is only 2 days old: b stays for now
    assert old_exports(ws, EPISODE, now + 6 * DAY) == 200 and not b[0].exists() and c[0].exists()


def test_old_exports_in_cloud_storage_leave_the_record(tmp_path):
    ws = Workspace(make_workspace(tmp_path / "ws"))
    now = time.time()
    a = export(ws, "20261001-100000", now - 30 * DAY)
    export(ws, "20261010-100000", now - 20 * DAY)
    a[0].unlink()
    a[1].unlink()      # moved to cloud storage
    d = ws.episode_dir(EPISODE)
    rel = f"exports/{EPISODE}/{a[0].name}"
    import json
    (d / STORE_FILE).write_text(json.dumps({"cold": True, "files": [{"rel": rel, "size": 100, "sha256": "0", "key": "audio/0"}]}))
    old_exports(ws, EPISODE, now)
    assert json.loads((d / STORE_FILE).read_text())["files"] == []


def test_raw_tracks_reminder_then_deletion_and_opening_starts_again(tmp_path):
    ws = Workspace(make_workspace(tmp_path / "ws"))
    d = ws.episode_dir(EPISODE)
    used = last_used(d)
    assert raw_tracks(ws, EPISODE)
    assert state(ws, EPISODE, used + RAW_KEEP_S - WARN_BEFORE_S - DAY) == "keep"
    t = used + RAW_KEEP_S - WARN_BEFORE_S + DAY
    assert state(ws, EPISODE, t) == "warn"
    sent = []
    shows = [(ws, lambda _e: False, {"email": OWNER, "title": "洛城二三事"})]

    def on():
        from lacuna_app import db as sitedb
        return sitedb.DB(tmp_path / "site.db")
    db = on()
    retention.save_settings(db, {"raw_tracks": True})
    out = retention.sweep(shows, db, lambda show, eps: sent.append((show, eps)), now=t)
    assert out["warned"] == 1 and sent[0][1][0]["id"] == EPISODE
    assert state(ws, EPISODE, t + DAY) == "wait"
    # 12 months are up, and the reminder went out 30 days ago: the raw tracks go, the episode stays
    t2 = max(used + RAW_KEEP_S, t + WARN_BEFORE_S) + DAY
    files = [ws.root / r for r in raw_tracks(ws, EPISODE)]
    out = retention.sweep(shows, db, lambda *a: sent.append(a), now=t2)
    assert out["deleted"] == 1 and not any(f.exists() for f in files)
    assert (d / "state.json").exists() and (d / "episode.json").exists() and state(ws, EPISODE, t2) == "gone"
    assert len(sent) == 1


def test_opening_after_the_reminder_keeps_the_tracks(tmp_path):
    ws = Workspace(make_workspace(tmp_path / "ws"))
    d = ws.episode_dir(EPISODE)
    used = last_used(d)
    t = used + RAW_KEEP_S - WARN_BEFORE_S + DAY
    retention.atomic_write_json(d / retention.RECORD_FILE, {"warned_at": t})
    import json
    (d / "used.json").write_text(json.dumps({"at": t + DAY}))      # opened the day after the reminder
    assert state(ws, EPISODE, used + RAW_KEEP_S + 5 * DAY) == "keep"


def test_nothing_is_deleted_while_raw_track_deletion_is_off(tmp_path):
    from lacuna_app import db as sitedb
    ws = Workspace(make_workspace(tmp_path / "ws"))
    db = sitedb.DB(tmp_path / "site.db")
    assert retention.settings(db) == {"raw_tracks": False, "old_exports": True}
    files = [ws.root / r for r in raw_tracks(ws, EPISODE)]
    far = time.time() + 5 * RAW_KEEP_S
    out = retention.sweep([(ws, lambda _e: False, {"email": OWNER})], db, lambda *a: (_ for _ in ()).throw(AssertionError), now=far)
    assert out["deleted"] == 0 and out["warned"] == 0 and all(f.exists() for f in files)


def test_the_owner_sets_retention_in_the_admin_and_the_reminder_is_mailed(tmp_path, monkeypatch):
    app, main, mailer = setup(tmp_path)
    c = sign_in(app)
    step_up(app, c)
    s = c.get("/api/admin/system").json()["storage"]
    assert s["retention"] == {"raw_tracks": False, "old_exports": True}
    assert s["cold"]["on"] is False and s["cold"]["after_days"] == 14
    r = c.put("/api/admin/storage/retention", json={"raw_tracks": True}, headers=WRITE)
    assert r.status_code == 200 and r.json()["retention"]["raw_tracks"] is True
    # the hourly round, 11 months and a day after the episode was last used: the creator gets the reminder
    ws = Workspace(tmp_path / "ws")
    d = ws.episode_dir(EPISODE)
    t = last_used(d) + RAW_KEEP_S - WARN_BEFORE_S + DAY
    real = retention.sweep
    monkeypatch.setattr(retention, "sweep", lambda *a, **k: real(*a, **k, now=t))
    app.state.storage_upkeep()
    mails = [m for m in mailer.outbox if "原始音轨" in m["subject"]]
    assert mails and mails[0]["to"] == OWNER
