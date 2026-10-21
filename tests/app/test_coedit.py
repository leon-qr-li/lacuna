"""Two people in one episode (decision 2026-10-21-co-editing-safety-net, lacuna_app/coedit.py):
per-person undo, a version number that says when to refresh, 409 for a decision or save based on
what someone else has changed since, and who else is here."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.coedit import Presence
from lacuna_app.editor import MockEditorAdapter
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import AI_EPISODE, make_ai_workspace
from tests.app.test_spaces import PW, join

EP = f"/api/episodes/{AI_EPISODE}"


def two(tmp_path, role="editor"):
    ws = make_ai_workspace(tmp_path / "ws")
    leon = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer()))
    leon.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    pei = join(leon, "pei@example.com", space="main", space_role=role)
    return ws, leon, pei


def reviewable(c) -> list[dict]:
    return [e for e in c.get(EP).json()["edits"] if e["consequential"]]


def test_each_person_undoes_their_own_step(tmp_path):
    ws, leon, pei = two(tmp_path)
    a, b = reviewable(leon)[:2]
    r = leon.post(f"{EP}/edits/{a['id']}/review", json={"action": "restore"}).json()
    assert r["can_undo"] and r["undo_label"].endswith(a["title"])
    r = pei.post(f"{EP}/edits/{b['id']}/review", json={"action": "restore"}).json()
    assert r["undo_label"].endswith(b["title"])
    # Leon's Ctrl+Z takes back his own step, not Pei's later one
    assert leon.get(EP).json()["undo_label"].endswith(a["title"])
    r = leon.post(f"{EP}/undo", json={}).json()
    st = {e["id"]: e["status"] for e in r["edits"]}
    assert st[a["id"]] == "applied" and st[b["id"]] == "restored"
    assert not r["can_undo"] and r["can_redo"]
    assert pei.get(EP).json()["undo_label"].endswith(b["title"])        # Pei's step is still Pei's to undo
    r = leon.post(f"{EP}/redo", json={}).json()
    assert {e["id"]: e["status"] for e in r["edits"]}[a["id"]] == "restored"


def test_undo_is_refused_when_someone_changed_the_same_edit_after(tmp_path):
    ws, leon, pei = two(tmp_path)
    a = reviewable(leon)[0]
    leon.post(f"{EP}/edits/{a['id']}/review", json={"action": "restore"})
    pei.post(f"{EP}/edits/{a['id']}/review", json={"action": "apply"})
    r = leon.post(f"{EP}/undo", json={})
    assert r.status_code == 409 and "pei" in r.json()["detail"]
    assert {e["id"]: e["status"] for e in leon.get(EP).json()["edits"]}[a["id"]] == "applied"    # Pei's stays


def test_version_goes_up_and_a_stale_decision_gets_409(tmp_path):
    ws, leon, pei = two(tmp_path)
    a, b = reviewable(leon)[:2]
    seen = leon.get(EP).json()["rev"]
    assert pei.post(f"{EP}/presence", json={}).json()["rev"] == seen
    pei.post(f"{EP}/edits/{a['id']}/review", json={"action": "restore"})
    assert leon.post(f"{EP}/presence", json={}).json()["rev"] > seen        # Leon's page knows to refresh
    # Leon, still looking at the old version, decides on the edit Pei just changed: refused, nothing changes
    r = leon.post(f"{EP}/edits/{a['id']}/review", json={"action": "keep", "rev": seen})
    assert r.status_code == 409 and r.json()["stale"] is True and "pei" in r.json()["detail"]
    assert {e["id"]: e["status"] for e in leon.get(EP).json()["edits"]}[a["id"]] == "restored"
    # an edit nobody else touched goes through on the same old version
    assert leon.post(f"{EP}/edits/{b['id']}/review", json={"action": "keep", "rev": seen}).status_code == 200
    # so does his own edit, and a page that sends no version (older tabs)
    now = leon.get(EP).json()["rev"]
    assert leon.post(f"{EP}/edits/{b['id']}/review", json={"action": "restore", "rev": seen}).status_code == 200
    assert leon.post(f"{EP}/edits/{a['id']}/review", json={"action": "keep"}).status_code == 200
    assert leon.get(EP).json()["rev"] > now
    # 全部通过 on an old version, after Pei changed one of the pending edits: refused
    seen = leon.get(EP).json()["rev"]
    c = next(e for e in reviewable(pei) if not e["approved"])
    pei.post(f"{EP}/edits/{c['id']}/review", json={"action": "restore"})
    pending = [e["id"] for e in reviewable(leon) if not e["approved"]] + [c["id"]]
    r = leon.post(f"{EP}/review", json={"action": "approve", "rev": seen, "ids": pending})
    assert r.status_code == 409 and r.json()["stale"]


def test_presence_shows_the_others_only(tmp_path):
    ws, leon, pei = two(tmp_path)
    assert leon.post(f"{EP}/presence", json={}).json()["others"] == []
    assert pei.post(f"{EP}/presence", json={}).json()["others"] == [{"name": "leon"}]
    assert leon.post(f"{EP}/presence", json={}).json()["others"] == [{"name": "pei"}]
    pei.post(f"{EP}/presence", json={"leaving": True})
    assert leon.post(f"{EP}/presence", json={}).json()["others"] == []


def test_presence_forgets_a_page_that_went_quiet():
    now = [0.0]
    p = Presence(clock=lambda: now[0])
    p.hello("EP1", {"key": "a", "name": "leon"})
    assert p.hello("EP1", {"key": "b", "name": "pei"}) == [{"name": "leon"}]
    now[0] = 30.0
    assert p.hello("EP1", {"key": "b", "name": "pei"}) == []
    assert p.hello("EP1", None) == []                           # no accounts (the shared E2E server): nobody


def test_stale_show_notes_and_show_settings_are_not_overwritten(tmp_path):
    ws, leon, pei = two(tmp_path, role="admin")
    # 节目设置
    seen = leon.get("/api/show").json()
    assert pei.put("/api/show", json=seen | {"about": "Pei 写的简介"}).status_code == 200
    r = leon.put("/api/show", json=seen | {"about": "Leon 写的简介"})
    assert r.status_code == 409 and r.json()["stale"] and "pei" in r.json()["detail"]
    latest = leon.get("/api/show").json()
    assert latest["about"] == "Pei 写的简介"
    assert leon.put("/api/show", json=latest | {"about": "Leon 写的简介"}).status_code == 200
    # show notes
    leon.post(f"{EP}/publish/generate")
    for _ in range(200):
        v = leon.get(f"{EP}/publish").json()
        if v["pack"] is not None and (v["job"] or {}).get("state") != "running":
            break
        time.sleep(0.05)
    pack = v["pack"]
    assert pack is not None, v
    r = pei.put(f"{EP}/publish", json={"markdown": "# Pei 的版本\n", "rev": pack["rev"]})
    assert r.status_code == 200 and r.json()["pack"]["rev"] == pack["rev"] + 1
    r = leon.put(f"{EP}/publish", json={"markdown": "# Leon 的版本\n", "rev": pack["rev"]})
    assert r.status_code == 409 and r.json()["stale"]
    assert leon.get(f"{EP}/publish").json()["pack"]["markdown"].startswith("# Pei 的版本")
