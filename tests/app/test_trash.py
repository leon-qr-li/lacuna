"""回收区 (lacuna_app/trash.py, routes/trash.py): a show or account deleted for good is kept 60 days and the
site owner can bring it back; the first show ("main") is deleted like any other (Leon 2026-10-24)."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from lacuna_app import create_app, habits
from lacuna_app import db as sitedb
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.trash import KEEP_S, Trash
from tests.app.e2e.auth import FakeMailer
from tests.app.test_spaces import EPISODE, PW, ids, join, setup


def make(c, name):
    return c.post("/api/spaces", json={"name": name}).json()["created"]


def delete(c, sid, name):
    c.post(f"/api/spaces/{sid}/archive", json={"archived": True})
    return c.request("DELETE", f"/api/spaces/{sid}", json={"confirm": name})


def test_a_deleted_show_is_kept_and_comes_back(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    sid = make(beta, "要删的")
    (ws / "spaces" / sid / "episodes" / "E1").mkdir(parents=True)
    (ws / "spaces" / sid / "episodes" / "E1" / "x.json").write_text("{}", encoding="utf-8")
    assert delete(beta, sid, "要删的").status_code == 200
    assert not (ws / "spaces" / sid).exists()
    # only site staff see the 回收区
    assert beta.get("/api/site/trash").status_code == 403
    items = leon.get("/api/site/trash").json()["items"]
    assert [(x["kind"], x["name"], x["by"], x["left_days"]) for x in items] == [("show", "要删的", "beta@example.com", 59)]
    r = leon.post(f"/api/site/trash/show/{items[0]['id']}/restore")
    assert r.status_code == 200 and r.json()["items"] == []
    assert (ws / "spaces" / sid / "episodes" / "E1" / "x.json").is_file()
    back = next(m for m in beta.get("/api/spaces").json()["mine"] if m["id"] == sid)
    assert back["archived"] and back["name"] == "要删的"         # archived, as it was; a manager restores it
    assert leon.post(f"/api/site/trash/show/{items[0]['id']}/restore").status_code == 404


def test_the_first_show_is_deleted_like_any_other(tmp_path):
    ws, leon = setup(tmp_path)
    make(leon, "另一个")
    rules = habits.home_for(ws, "leon@example.com")
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "marker.txt").write_text("mine", encoding="utf-8")
    leon.post("/api/spaces/switch", json={"id": "main"})
    name = leon.get("/api/spaces").json()["current"]["name"]
    assert delete(leon, "main", name).status_code == 200
    # its own entries left the root; the site's (accounts, people's rules, other shows) did not
    assert not (ws / "episodes").exists() or not any((ws / "episodes").iterdir())
    assert (ws / "auth").is_dir() and (ws / "spaces").is_dir() and (rules / "marker.txt").is_file()
    assert "main" not in [m["id"] for m in leon.get("/api/spaces").json()["mine"]]
    # a restart doesn't make it again
    again = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer()))
    again.cookies = leon.cookies
    assert "main" not in [m["id"] for m in again.get("/api/spaces").json()["mine"]]
    # restored: the episode where it was, openable again
    tid = again.get("/api/site/trash").json()["items"][0]["id"]
    assert again.post(f"/api/site/trash/show/{tid}/restore").status_code == 200
    assert (ws / "episodes" / EPISODE).is_dir()
    again.post("/api/spaces/main/archive", json={"archived": False})
    again.post("/api/spaces/switch", json={"id": "main"})
    assert ids(again) == [EPISODE]


def test_a_deleted_account_comes_back_with_its_shows(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    own = beta.get("/api/spaces").json()["current"]["id"]
    leon.post("/api/spaces/main/members", json={"email": "beta@example.com", "role": "editor"})
    assert leon.delete("/api/auth/users/beta@example.com").status_code == 200
    items = leon.get("/api/site/trash").json()["items"]
    assert [(x["kind"], x["id"]) for x in items] == [("user", "beta@example.com")]
    assert leon.post("/api/site/trash/user/beta@example.com/restore").status_code == 200
    c = TestClient(leon.app)
    assert c.post("/api/auth/login", json={"email": "beta@example.com", "password": PW}).status_code == 200
    mine = {m["id"]: m["role"] for m in c.get("/api/spaces").json()["mine"]}
    assert mine.get(own) == "admin" and mine.get("main") == "editor"
    assert leon.get("/api/site/trash").json()["items"] == []


def test_after_60_days_it_is_gone(tmp_path):
    now = [1_000_000.0]
    db = sitedb.at(tmp_path)
    t = Trash(tmp_path, db, lambda: now[0])
    (tmp_path / "spaces" / "sp_a").mkdir(parents=True)
    tid = t.put_show("sp_a", {"id": "sp_a", "name": "A"}, tmp_path / "spaces" / "sp_a", None, "x@example.com")
    t.put_user("y@example.com", {"email": "y@example.com"}, {}, "x@example.com")
    now[0] += KEEP_S - 60
    assert len(t.items()) == 2
    now[0] += 120
    assert t.purge() == 2 and t.items() == [] and not (tmp_path / "trash" / tid).exists()
    assert json.loads(db.meta("trash_user:y@example.com") or "null") is None
