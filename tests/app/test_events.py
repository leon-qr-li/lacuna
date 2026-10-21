"""First-party event log (lacuna_app/events.py, routes/events.py): who did what, without personal data."""
from __future__ import annotations

import contextvars
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app import db as sitedb
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.events import ACTOR, Actor, EventLog, clean_props, track
from lacuna_app.routes.events import match
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import AI_EPISODE, make_ai_workspace

PW = "correct horse battery"


def setup(tmp_path):
    ws = make_ai_workspace(tmp_path / "ws")
    leon = TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent"), mailer=FakeMailer()))
    assert leon.post("/api/auth/register", json={"email": "leon@example.com", "password": PW}).status_code == 200
    return ws, leon, leon.app.state.events


def join(leon, email, **space):
    link = leon.post("/api/auth/invites", json={"email": email, **space}).json()["link"]
    c = TestClient(leon.app)
    assert c.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW}).status_code == 200
    return c


def evs(log, **where):
    return [r for r in log.rows() if all(r.get(k) == v for k, v in where.items())]


def test_props_keep_numbers_and_words_only():
    p = clean_props({"n": 3, "s": 1.23456, "ok": True, "kind": "filler", "title": "游戏 那个", "who": "a@b.com",
                     "nan": float("nan"), "list": [1], "none": None, "bad key": 1})
    assert p == {"n": 3, "s": 1.235, "ok": True, "kind": "filler"}


def test_rules_match_paths():
    assert match("POST", "/api/episodes/EP001/undo") == ("edit.undo", "EP001")
    assert match("POST", "/api/episodes/EP001/music/auto") == ("music.auto", "EP001")
    assert match("DELETE", "/api/episodes/EP001") == ("episode.delete", "EP001")
    assert match("POST", "/api/imports") == ("import.start", None)
    assert match("GET", "/api/episodes/EP001") is None


def test_signup_and_login_use_an_internal_id_never_the_email(tmp_path):
    ws, leon, log = setup(tmp_path)
    leon.post("/api/auth/logout")
    assert leon.post("/api/auth/login", json={"email": "leon@example.com", "password": PW}).status_code == 200
    uid = log.uid("leon@example.com")
    assert uid.startswith("u_")
    assert [r["ev"] for r in evs(log, uid=uid)] == ["user.signup", "user.login", "user.login"]
    assert evs(log, ev="user.signup")[0]["props"] == {"invited": False}
    raw = "".join(log.db.query("SELECT group_concat(uid || sid || ev || props, '') AS t FROM events")[0]["t"] or "")
    assert "@" not in raw and "leon" not in raw


def test_changes_are_events_reads_and_refusals_are_not(tmp_path):
    ws, leon, log = setup(tmp_path)
    ep = f"/api/episodes/{AI_EPISODE}"
    s = leon.get(ep).json()
    first = s["review"][0]
    assert leon.post(f"{ep}/edits/{first}/review", json={"action": "restore"}).status_code == 200
    assert leon.post(f"{ep}/review", json={"action": "approve"}).status_code == 200
    assert leon.post(f"{ep}/undo", json={}).status_code == 200
    guest = join(leon, "guest@example.com", space="main", space_role="viewer")
    assert guest.post(f"{ep}/undo", json={}).status_code == 403
    rows = [r for r in log.rows() if not r["ev"].startswith(("user.", "invite."))]
    assert [r["ev"] for r in rows] == ["review.decide", "review.batch", "edit.undo"]
    assert all(r["ep"] == AI_EPISODE and r["sid"] == "main" and r["uid"] == log.uid("leon@example.com") for r in rows)
    assert rows[0]["props"]["action"] == "restore" and rows[0]["props"]["source"]
    assert rows[1]["props"] == {"action": "approve", "edits": 3, "changed": 3, "ai": 3}
    assert not evs(log, uid=log.uid("guest@example.com"), ev="edit.undo")


def test_other_shows_are_logged_with_their_own_show_id(tmp_path):
    ws, leon, log = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    sid = beta.get("/api/spaces").json()["current"]["id"]
    assert beta.post("/api/albums", json={"name": "第一季"}).status_code == 200
    row = evs(log, ev="album.create")[0]
    assert (row["uid"], row["sid"]) == (log.uid("beta@example.com"), sid)
    assert (ws / "lacuna.db").is_file() and not (ws / "spaces" / sid / "lacuna.db").exists()   # one log per site


def test_deleting_an_account_makes_its_events_anonymous(tmp_path):
    ws, leon, log = setup(tmp_path)
    join(leon, "bob@example.com")
    uid = log.uid("bob@example.com")
    assert leon.delete("/api/auth/users/bob@example.com").status_code == 200
    assert log.uid("bob@example.com") is None
    assert not log.db.query("SELECT * FROM users WHERE id = ?", (uid,))
    assert evs(log, uid=uid)                     # the counts stay, unlinked from the person


def test_track_follows_the_request_into_worker_threads(tmp_path):
    log = EventLog(sitedb.at(tmp_path), lambda e: None)
    token = ACTOR.set(Actor(log, "u_1", "main"))
    try:
        t = threading.Thread(target=contextvars.copy_context().run, args=(track, "import.done", "EP9"),
                             kwargs={"audio_s": 3600.0})
        t.start()
        t.join()
    finally:
        ACTOR.reset(token)
    track("import.done", "EP9")                  # no actor: nothing
    assert [(r["uid"], r["ep"], r["props"]) for r in log.rows()] == [("u_1", "EP9", {"audio_s": 3600.0})]


def test_bad_names_are_refused_and_old_rows_dropped(tmp_path):
    log = EventLog(sitedb.at(tmp_path), lambda e: None, clock=lambda: 1_000.0)
    assert log.add("Not A Name", "u_1") is None
    log.add("edit.undo", "u_1")
    EventLog(sitedb.at(tmp_path), lambda e: None, clock=lambda: 1_000.0 + 500 * 86400)
    assert log.rows() == []
