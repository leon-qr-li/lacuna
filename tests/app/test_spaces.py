"""Workspaces: who sees which episodes, library and learned rules (lacuna_app/spaces.py, routes/spaces.py)."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app import db as sitedb
from lacuna_app.editor import MockEditorAdapter
from tests.app import site_db
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import EPISODE, make_workspace

PW = "correct horse battery"


def setup(tmp_path):
    ws = make_workspace(tmp_path / "ws")           # Leon's existing workspace, with one episode
    mailer = FakeMailer()
    leon = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=mailer))
    leon.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    return ws, leon


def join(leon, email, **space):
    """A new account through an invite; 专业版 unless `plan` says otherwise (test_plans.py tests the limits)."""
    link = leon.post("/api/auth/invites", json={"email": email, "plan": "pro", **space}).json()["link"]
    c = TestClient(leon.app)
    assert c.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW}).status_code == 200
    return c


def ids(c):
    return [e["id"] for e in c.get("/api/episodes").json()["episodes"]]


def test_existing_data_is_the_owners_main_workspace(tmp_path):
    ws, leon = setup(tmp_path)
    sp = leon.get("/api/spaces").json()
    assert {k: sp["current"][k] for k in ("id", "name", "role")} == {"id": "main", "name": "洛城二三事", "role": "admin"}
    assert sp["current"]["episodes"] == 1
    assert ids(leon) == [EPISODE]
    assert (ws / "episodes" / EPISODE).is_dir()           # nothing moved


def test_beta_user_gets_an_empty_private_workspace(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    sp = beta.get("/api/spaces").json()
    assert sp["current"]["role"] == "admin" and sp["current"]["id"].startswith("sp_")
    assert [s["id"] for s in sp["all"]] == [sp["current"]["id"]]      # a workspace admin sees only their own
    assert ids(beta) == []                                 # can't see Leon's episodes
    assert beta.get(f"/api/episodes/{EPISODE}").status_code == 404
    assert beta.get("/api/library").status_code == 200
    # their folder is separate; can't switch into main
    assert (ws / "spaces" / sp["current"]["id"] / "episodes").is_dir()
    assert beta.post("/api/spaces/switch", json={"id": "main"}).status_code == 403
    # Leon doesn't see theirs either, but as site owner he sees the workspace exists
    assert ids(leon) == [EPISODE]
    assert len(leon.get("/api/spaces").json()["all"]) == 2


def test_co_host_shares_the_main_workspace(tmp_path):
    ws, leon = setup(tmp_path)
    pei = join(leon, "pei@example.com", space="main", space_role="editor")
    cur = pei.get("/api/spaces").json()["current"]
    assert (cur["id"], cur["role"], cur["by"]) == ("main", "editor", None)
    assert ids(pei) == [EPISODE]
    # editors work, but only workspace admins delete episodes for good
    assert pei.delete(f"/api/episodes/{EPISODE}").status_code == 403
    assert pei.post("/api/spaces/main/members", json={"email": "leon@example.com", "role": "viewer"}).status_code == 403


def test_viewer_can_listen_but_not_change(tmp_path):
    ws, leon = setup(tmp_path)
    guest = join(leon, "guest@example.com", space="main", space_role="viewer")
    assert ids(guest) == [EPISODE]
    assert guest.get(f"/api/episodes/{EPISODE}").status_code == 200
    r = guest.post(f"/api/episodes/{EPISODE}/undo")
    assert r.status_code == 403 and "只能试听" in r.json()["detail"]


def test_switching_and_membership(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    own = beta.get("/api/spaces").json()["current"]["id"]
    # Leon creates a second workspace of his own and switches to it
    sp = leon.post("/api/spaces", json={"name": "试验节目"}).json()
    new = next(s["id"] for s in sp["mine"] if s["name"] == "试验节目")
    assert leon.post("/api/spaces/switch", json={"id": new}).json()["current"]["id"] == new
    assert ids(leon) == []
    assert leon.post("/api/spaces/switch", json={"id": "main"}).status_code == 200
    assert ids(leon) == [EPISODE]
    # add beta to main as viewer, they switch over
    leon.post("/api/spaces/main/members", json={"email": "beta@example.com", "role": "viewer"})
    assert [s["id"] for s in beta.get("/api/spaces").json()["mine"]] == ["main", own]
    assert beta.get("/api/spaces").json()["current"]["id"] == "main"      # main listed first
    beta.post("/api/spaces/switch", json={"id": own})
    assert ids(beta) == []
    # removed from main: falls back to their own
    leon.post("/api/spaces/main/members", json={"email": "beta@example.com", "role": None})
    beta.post("/api/spaces/switch", json={"id": own})
    assert beta.post("/api/spaces/switch", json={"id": "main"}).status_code == 403
    # a workspace keeps an admin; unknown accounts can't be added
    assert leon.post("/api/spaces/main/members", json={"email": "leon@example.com", "role": None}).status_code == 400
    assert leon.post("/api/spaces/main/members", json={"email": "who@example.com", "role": "editor"}).status_code == 404
    # deleting the account removes it from every workspace
    leon.delete("/api/auth/users/beta@example.com")
    assert all("beta@example.com" not in s["members"] for s in site_db.shows(ws))
    assert not sitedb.at(ws).query("SELECT * FROM show_members WHERE email = 'beta@example.com'")


def test_learned_rules_stay_in_their_workspace(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    assert leon.get("/api/learning").status_code == 200
    own = beta.get("/api/spaces").json()["current"]["id"]
    beta.get("/api/learning")
    assert leon.app.state.space_apps[own].state.workspace.root == (ws / "spaces" / own).resolve()


def test_desktop_without_accounts_is_untouched(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    c = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer()))
    assert ids(c) == [EPISODE]
    assert not site_db.shows(ws)


def test_existing_accounts_adopted_on_upgrade(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    (ws / "auth").mkdir()
    (ws / "auth" / "users.json").write_text(json.dumps({"users": [
        {"email": "leon@example.com", "hash": "x", "created": 1, "owner": True},
        {"email": "pei@example.com", "hash": "x", "created": 2, "owner": False}]}))
    app = create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer())
    main = app.state.spaces.spaces["main"]
    assert main["members"] == {"leon@example.com": "admin", "pei@example.com": "editor"}


def test_new_owner_after_users_file_deleted_gets_main(tmp_path):
    ws, leon = setup(tmp_path)
    with sitedb.at(ws).tx() as c:                     # the documented way back in when locked out
        c.execute("DELETE FROM users")
    c = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer()))
    c.post("/api/auth/register", json={"email": "new@example.com", "password": PW})
    assert c.get("/api/spaces").json()["current"]["id"] == "main" and ids(c) == [EPISODE]


def test_cloud_access_check_also_guards_other_workspaces(tmp_path, monkeypatch):
    """The Cloudflare Access gate (lacuna_app/cloud.py) still checks calls that go to a beta workspace."""
    import time

    from lacuna_app import totp
    from tests.app.test_cloud import AccessVerifier, AUD, TEAM, hdr, rsa, token, jwt
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    verifier = AccessVerifier(TEAM, AUD, fetch_keys=lambda url: {"keys": [jwk | {"kid": "k1", "alg": "RS256"}]})
    monkeypatch.setenv("LACUNA_CLOUD", "1")
    app = create_app(tmp_path / "ws", MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer(),
                     access_verifier=verifier)
    h = hdr(token(key))
    leon = TestClient(app, base_url="https://testserver", headers=h)

    def signed_up(c, r):
        out = r.json()
        code = totp.code_at(out["secret"], int(time.time() // totp.STEP))
        assert c.post("/api/auth/2fa/enroll", json={"ticket": out["ticket"], "code": code}).status_code == 200

    setup = (tmp_path / "ws" / "auth" / "setup-code.txt").read_text().strip()
    signed_up(leon, leon.post("/api/auth/register", json={"email": "leon@example.com", "password": PW, "setup_code": setup}))
    link = leon.post("/api/auth/invites", json={"email": "beta@example.com"}).json()["link"]
    beta = TestClient(app, base_url="https://testserver", headers=h)
    signed_up(beta, beta.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW}))
    assert beta.get("/api/episodes").status_code == 200
    beta.headers.pop("Cf-Access-Jwt-Assertion")
    assert beta.get("/api/episodes").status_code == 403          # session cookie alone is not enough


def test_cloud_access_check_comes_first_on_every_path(tmp_path, monkeypatch):
    """Even calls the workspace dispatcher would answer itself need a valid Access token."""
    from tests.app.test_cloud import AccessVerifier, AUD, TEAM
    monkeypatch.setenv("LACUNA_CLOUD", "1")
    verifier = AccessVerifier(TEAM, AUD, fetch_keys=lambda url: {"keys": []})
    app = create_app(tmp_path / "ws", MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer(),
                     access_verifier=verifier)
    c = TestClient(app, base_url="https://testserver")
    for path in ("/", "/api/spaces", "/api/episodes", "/api/auth/status", "/api/whatever", "/nothing/here"):
        assert c.get(path).status_code == 403, path
    assert c.post("/api/spaces/switch", json={"id": "main"}).status_code == 403
    # outermost after the admin-host split (decision admin-site), which only takes the admin address
    assert [m.cls.__name__ for m in app.user_middleware[:2]] == ["AdminHost", "CloudGate"]


def test_anyone_starts_a_project_and_invites_collaborators(tmp_path):
    """邀请协作 (decision projects-albums): projects are workspaces; any account may start one and manage it;
    existing accounts join at once, new people only through a site admin's invite."""
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    made = beta.post("/api/spaces", json={"name": "片场夜谈"})
    assert made.status_code == 200
    sid = made.json()["created"]
    assert made.json()["current"]["id"] == sid               # moved straight into it
    assert made.json()["current"]["name"] == "片场夜谈"        # the name is the new show's name
    assert beta.get("/api/show").json()["show_name"] == "片场夜谈"
    assert beta.get("/api/show").json()["needs_setup"] is True
    # beta brings Leon (who has an account) in as an editor; Leon sees who invited him
    r = beta.post(f"/api/spaces/{sid}/invite", json={"email": "leon@example.com", "role": "editor"})
    assert r.status_code == 200 and r.json()["joined"] == "leon@example.com"
    row = next(s for s in leon.get("/api/spaces").json()["mine"] if s["id"] == sid)
    assert (row["role"], row["by"], row["people"]) == ("editor", "beta@example.com", 2)
    # beta can't sign up strangers: while 新成员需站长批准 is on it becomes a 搭档申请 for the owner
    # (test_new_members.py); the site owner invites at once, and the invite waits in the project's list
    asked = beta.post(f"/api/spaces/{sid}/invite", json={"email": "new@example.com"}).json()
    assert asked["requested"] == "new@example.com" and "link" not in asked
    out = leon.post("/api/spaces/main/invite", json={"email": "pei@example.com", "role": "viewer"}).json()
    assert out["invited"] == "pei@example.com" and out["link"]
    people = leon.get("/api/spaces/main/people").json()
    assert [(i["email"], i["role"]) for i in people["invites"]] == [("pei@example.com", "viewer")]
    assert people["can_invite_new"] is True
    assert beta.get(f"/api/spaces/{sid}/people").json()["can_invite_new"] is False
    # beta can't see or withdraw main's invites; Leon withdraws it
    assert beta.get("/api/spaces/main/people").status_code == 403
    iid = people["invites"][0]["id"]
    assert beta.delete(f"/api/spaces/main/invites/{iid}").status_code == 403
    assert leon.delete(f"/api/spaces/main/invites/{iid}").json()["invites"] == []
    # the invite email's language is the inviter's pick (the sign-up page opens in it)
    en = leon.post("/api/spaces/main/invite", json={"email": "sam@example.com", "role": "editor", "lang": "en"}).json()
    assert leon.post("/api/auth/invite", json={"token": en["link"].rsplit("/", 1)[1]}).json()["lang"] == "en"
