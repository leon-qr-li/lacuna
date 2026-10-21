"""The site database (lacuna_app/db.py): accounts and shows move in from the old JSON files once, nothing lost."""
from __future__ import annotations

import json
import sqlite3

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app import db as sitedb
from lacuna_app.auth import Auth, hash_password
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.spaces import Spaces
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import make_workspace

PW = "correct horse battery"


def old_install(root):
    """An installation from before the database: users.json, sessions.json, spaces.json."""
    d = root / "auth"
    d.mkdir(parents=True)
    (d / "users.json").write_text(json.dumps({"users": [
        {"email": "leon@example.com", "hash": hash_password(PW), "created": 1, "role": "owner", "verified": True},
        {"email": "pei@example.com", "hash": hash_password(PW), "created": 2, "role": "member", "verified": True}],
        "config": {"sender": "LACUNA <noreply@lacunastudio.app>"},
        "invites": [{"hash": "h" * 64, "email": "new@example.com", "role": "member", "by": "leon@example.com",
                     "created": 1, "exp": 9e12}]}))
    (d / "sessions.json").write_text(json.dumps({"sessions": {"s" * 64: {"email": "pei@example.com", "exp": 9e12,
                                                                         "created": 1, "seen": 1}}}))
    (d / "spaces.json").write_text(json.dumps({"spaces": [
        {"id": "main", "name": "洛城二三事", "created": 1, "created_by": "leon@example.com", "color": "#E2583E",
         "members": {"leon@example.com": "admin", "pei@example.com": "editor"}}]}))


def test_old_files_move_in_once_and_stay_for_a_rollback(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    old_install(ws)
    a = Auth(ws, FakeMailer())
    assert set(a.users) == {"leon@example.com", "pei@example.com"}
    # everyone who had an account keeps a free 专业版, and gets an internal id
    assert all(u["plan"] == "pro" and u["plan_free"] and u["id"].startswith("u_") for u in a.users.values())
    assert list(a.sessions) == ["s" * 64] and [i["email"] for i in a.invites.values()] == ["new@example.com"]
    sp = Spaces(ws)
    assert sp.spaces["main"]["members"] == {"leon@example.com": "admin", "pei@example.com": "editor"}
    # the JSON files stay where they were (an older version rolled back to still finds them) ...
    assert (ws / "auth" / "users.json").is_file() and (ws / "auth" / "spaces.json").is_file()
    # ... and are read only once: later changes live in the database
    a.update_user("leon@example.com", "pei@example.com", disabled=True)
    assert Auth(ws, FakeMailer()).users["pei@example.com"]["disabled"] is True
    rows = sitedb.at(ws).query("SELECT email, role, plan FROM users ORDER BY created")
    assert [tuple(r) for r in rows] == [("leon@example.com", "owner", "pro"), ("pei@example.com", "member", "pro")]
    assert [tuple(r) for r in sitedb.at(ws).query("SELECT show_id, email, role FROM show_members ORDER BY email")] == \
        [("main", "leon@example.com", "admin"), ("main", "pei@example.com", "editor")]


def test_old_files_go_after_30_days(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    old_install(ws)
    Auth(ws, FakeMailer(), clock=lambda: 1_000_000.0)
    Spaces(ws, clock=lambda: 1_000_000.0)
    Auth(ws, FakeMailer(), clock=lambda: 1_000_000.0 + 29 * 86400)
    assert (ws / "auth" / "users.json").exists()
    Auth(ws, FakeMailer(), clock=lambda: 1_000_000.0 + 31 * 86400)
    Spaces(ws, clock=lambda: 1_000_000.0 + 31 * 86400)
    assert not (ws / "auth" / "users.json").exists() and not (ws / "auth" / "sessions.json").exists()
    assert not (ws / "auth" / "spaces.json").exists()
    assert set(Auth(ws, FakeMailer()).users) == {"leon@example.com", "pei@example.com"}


def test_signing_in_works_on_the_moved_accounts(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    old_install(ws)
    c = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer()))
    assert c.post("/api/auth/login", json={"email": "pei@example.com", "password": PW}).status_code == 200
    assert c.get("/api/spaces").json()["current"]["id"] == "main"


def test_snapshot_is_a_consistent_copy(tmp_path):
    db = sitedb.at(tmp_path)
    db.set_meta("x", "1")
    out = db.snapshot()
    with sqlite3.connect(out) as copy:
        assert copy.execute("SELECT value FROM meta WHERE key = 'x'").fetchone() == ("1",)
        assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    with db.lock:          # the copy-in-progress exists only while a snapshot holds the lock (one may be timed)
        assert not out.with_suffix(".tmp").exists()


def test_a_failed_change_writes_nothing(tmp_path):
    db = sitedb.at(tmp_path)
    try:
        with db.tx() as c:
            c.execute("INSERT INTO meta (key, value) VALUES ('a', '1')")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert db.meta("a") is None
