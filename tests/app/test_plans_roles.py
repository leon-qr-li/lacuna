"""Plans (lacuna_app/plans.py) and roles (routes/spaces.py), decisions 2026-10-21-plans and 2026-10-21-roles."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.app.synth import EPISODE
from tests.app.test_spaces import PW, join, setup


def test_basic_plan_has_one_show_and_two_collaborators(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com", plan="basic")            # gets a show of their own on joining
    assert beta.get("/api/auth/status").json()["plan"] == "basic"
    r = beta.post("/api/spaces", json={"name": "第二个"})
    assert r.status_code == 403 and "基础版" in r.json()["detail"]
    own = beta.get("/api/spaces").json()["current"]["id"]
    for e in ("a@example.com", "b@example.com", "c@example.com"):
        join(leon, e, plan="pro")
    assert beta.post(f"/api/spaces/{own}/invite", json={"email": "a@example.com"}).status_code == 200
    assert beta.post(f"/api/spaces/{own}/members", json={"email": "b@example.com", "role": "viewer"}).status_code == 200
    r = beta.post(f"/api/spaces/{own}/invite", json={"email": "c@example.com"})
    assert r.status_code == 403 and "2 位协作者" in r.json()["detail"]
    # changing someone already in the show is not a new collaborator
    assert beta.post(f"/api/spaces/{own}/members", json={"email": "b@example.com", "role": "editor"}).status_code == 200
    # the site owner moves them to 专业版: room for more
    assert leon.post("/api/auth/users/beta@example.com", json={"plan": "pro"}).status_code == 200
    assert beta.post(f"/api/spaces/{own}/invite", json={"email": "c@example.com"}).status_code == 200
    assert beta.post("/api/spaces", json={"name": "第二个"}).status_code == 200


def test_trial_cannot_invite_and_plan_page(tmp_path):
    ws, leon = setup(tmp_path)
    t = join(leon, "trial@example.com", plan="trial")
    join(leon, "x@example.com")
    own = t.get("/api/spaces").json()["current"]["id"]
    r = t.post(f"/api/spaces/{own}/invite", json={"email": "x@example.com"})
    assert r.status_code == 403 and "不能邀请协作者" in r.json()["detail"]
    p = t.get("/api/plan").json()
    assert p["plan"] == "trial" and p["limits"]["hours"] == 1 and p["limits"]["hours_once"] is True
    assert p["shows"] == 1 and p["hours_used"] == 0 and p["hours"]["allowance"] == 1 and p["hours"]["once"] is True
    assert [x["id"] for x in p["plans"]] == ["trial", "basic", "pro"]
    assert leon.get("/api/plan").json() | {} and leon.get("/api/plan").json()["plan"] == "pro"   # the owner
    assert leon.get("/api/plan").json()["free"] is True


def test_only_admins_set_plans(tmp_path):
    ws, leon = setup(tmp_path)
    pei = join(leon, "pei@example.com", space="main", space_role="editor")
    assert pei.post("/api/auth/users/pei@example.com", json={"plan": "pro"}).status_code == 403
    assert leon.post("/api/auth/users/pei@example.com", json={"plan": "gold"}).status_code == 400
    assert leon.post("/api/auth/invites", json={"email": "z@example.com", "plan": "gold"}).status_code == 400
    users = {u["email"]: u for u in leon.get("/api/auth/users").json()["users"]}
    assert users["pei@example.com"]["plan"] == "pro" and users["leon@example.com"]["plan"] == "pro"


def test_show_settings_are_for_its_managers(tmp_path):
    ws, leon = setup(tmp_path)
    pei = join(leon, "pei@example.com", space="main", space_role="editor")
    r = pei.put("/api/show", json={"show_name": "改名"})
    assert r.status_code == 403 and "节目设置" in r.json()["detail"]
    assert pei.patch("/api/albums/project", json={"intro": None}).status_code == 403
    assert pei.post(f"/api/episodes/{EPISODE}/undo", json={}).status_code != 403        # editing is theirs


def test_site_staff_cannot_open_or_manage_other_shows(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    own = beta.get("/api/spaces").json()["current"]["id"]
    # the owner sees the show exists, but can't go in, see its people, or change it
    assert any(s["id"] == own for s in leon.get("/api/spaces").json()["all"])
    assert leon.post("/api/spaces/switch", json={"id": own}).status_code == 403
    assert leon.get(f"/api/spaces/{own}/people").status_code == 403
    assert leon.post(f"/api/spaces/{own}", json={"name": "x"}).status_code == 403
    assert leon.post(f"/api/spaces/{own}/members", json={"email": "leon@example.com", "role": "admin"}).status_code == 403


def test_support_access_lets_staff_look_for_seven_days(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    own = beta.get("/api/spaces").json()["current"]["id"]
    r = beta.post(f"/api/spaces/{own}/support", json={"on": True})
    assert r.status_code == 200 and r.json()["support_until"] > 0
    row = next(m for m in leon.get("/api/spaces").json()["mine"] if m["id"] == own)
    assert row["role"] == "viewer" and row["support"] is True
    assert leon.get("/api/spaces").json()["current"]["id"] == "main"     # never lands there by itself
    assert leon.post("/api/spaces/switch", json={"id": own}).status_code == 200
    assert leon.get("/api/episodes").status_code == 200
    assert leon.post("/api/albums", json={"name": "x"}).status_code == 403    # look only
    # an ordinary member of another show doesn't get in; turning it off ends it
    other = join(leon, "other@example.com")
    assert other.post("/api/spaces/switch", json={"id": own}).status_code == 403
    beta.post(f"/api/spaces/{own}/support", json={"on": False})
    assert leon.post("/api/spaces/switch", json={"id": own}).status_code == 403
    # only the show's managers turn it on
    assert leon.post(f"/api/spaces/{own}/support", json={"on": True}).status_code == 403


def test_support_access_ends_by_itself(tmp_path):
    from lacuna_app.spaces import SUPPORT_S
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    own = beta.get("/api/spaces").json()["current"]["id"]
    beta.post(f"/api/spaces/{own}/support", json={"on": True})
    sp = leon.app.state.spaces
    real = sp.now
    sp.now = lambda: real() + SUPPORT_S + 1
    try:
        assert sp.role(own, "leon@example.com") is None
    finally:
        sp.now = real
