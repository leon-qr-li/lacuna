"""「新成员需站长批准」 and 搭档申请 (routes/new_members.py, routes/spaces.py, routes/auth_requests.py):
in beta a show admin can't sign strangers up, the owner approves; after launch the plan's seats decide."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import make_workspace

PW = "correct horse battery"


def setup(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    mailer = FakeMailer()
    leon = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=mailer, mail_inline=True))
    leon.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    return leon, mailer


def join(leon, email, plan="basic", **space):
    link = leon.post("/api/auth/invites", json={"email": email, "plan": plan, **space}).json()["link"]
    c = TestClient(leon.app)
    assert c.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW}).status_code == 200
    return c


def show_of(c):
    """The show a new account starts with (an invite to 「新节目」)."""
    return c.get("/api/spaces").json()["mine"][0]["id"]


def register(leon, link):
    c = TestClient(leon.app)
    assert c.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW}).status_code == 200
    return c


def test_beta_a_stranger_becomes_a_request_the_owner_approves(tmp_path):
    leon, mailer = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    sid = show_of(sam)
    assert leon.get("/api/site/new-members").json() == {"approval": True}       # on by default (beta)
    people = sam.get(f"/api/spaces/{sid}/people").json()
    assert people["needs_approval"] is True and people["can_invite_new"] is False
    sent = len(mailer.outbox)
    r = sam.post(f"/api/spaces/{sid}/invite", json={"email": "Alex@example.com", "role": "editor", "lang": "en"})
    assert r.status_code == 200 and r.json()["requested"] == "alex@example.com"
    # no sign-up mail to Alex; one notice to the owner; the request shows in the show's list
    new = mailer.outbox[sent:]
    assert [m["to"] for m in new] == ["leon@example.com"]
    assert "alex@example.com" in new[0]["subject"]
    assert [x["email"] for x in r.json()["requests"]] == ["alex@example.com"]
    # asking twice files one request
    sam.post(f"/api/spaces/{sid}/invite", json={"email": "alex@example.com"})
    asks = leon.get("/api/access-requests").json()["requests"]
    assert [(a["email"], a["kind"], a["space"], a["by"]) for a in asks] == [("alex@example.com", "collab", sid, "sam@example.com")]
    # the owner approves: the invite goes into Sam's show, in the language Sam picked
    out = leon.post(f"/api/access-requests/{asks[0]['id']}", json={"action": "invite"}).json()
    assert out["requests"] == [] and out["link"]
    assert leon.post("/api/auth/invite", json={"token": out["link"].rsplit("/", 1)[1]}).json()["lang"] == "en"
    alex = register(leon, out["link"])
    mine = alex.get("/api/spaces").json()["mine"]
    assert [(s["id"], s["role"]) for s in mine] == [(sid, "editor")]             # no show of their own
    assert sam.get(f"/api/spaces/{sid}/people").json()["requests"] == []


def test_a_dismissed_request_tells_the_show_admin(tmp_path):
    leon, mailer = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    sid = show_of(sam)
    sam.post(f"/api/spaces/{sid}/invite", json={"email": "alex@example.com"})
    rid = leon.get("/api/access-requests").json()["requests"][0]["id"]
    sent = len(mailer.outbox)
    assert leon.post(f"/api/access-requests/{rid}", json={"action": "dismiss"}).json()["requests"] == []
    assert [m["to"] for m in mailer.outbox[sent:]] == ["sam@example.com"]


def test_someone_the_site_already_invited_joins_the_show_on_sign_up(tmp_path):
    leon, _ = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    sid = show_of(sam)
    link = leon.post("/api/auth/invites", json={"email": "alex@example.com", "plan": "basic"}).json()["link"]
    r = sam.post(f"/api/spaces/{sid}/invite", json={"email": "alex@example.com", "role": "viewer"}).json()
    assert r["joins_later"] == "alex@example.com"
    assert leon.get("/api/access-requests").json()["requests"] == []
    alex = register(leon, link)
    roles = {s["id"]: s["role"] for s in alex.get("/api/spaces").json()["mine"]}
    assert roles[sid] == "viewer" and len(roles) == 2                            # their own show + Sam's


def test_after_launch_show_admins_invite_within_their_plan(tmp_path):
    leon, mailer = setup(tmp_path)
    sam = join(leon, "sam@example.com")                 # 基础版: 2 collaborators
    sid = show_of(sam)
    # only the owner turns the approval off
    assert sam.put("/api/site/new-members", json={"on": False}).status_code == 403
    assert leon.put("/api/site/new-members", json={"on": False}).json() == {"approval": False}
    assert sam.get(f"/api/spaces/{sid}/people").json()["can_invite_new"] is True
    sent = len(mailer.outbox)
    a = sam.post(f"/api/spaces/{sid}/invite", json={"email": "alex@example.com"}).json()
    assert a["invited"] == "alex@example.com" and a["link"]
    assert [m["to"] for m in mailer.outbox[sent:]] == ["alex@example.com"]
    assert leon.get("/api/access-requests").json()["requests"] == []
    assert sam.post(f"/api/spaces/{sid}/invite", json={"email": "bo@example.com"}).status_code == 200
    # the third collaborator doesn't fit 基础版
    assert sam.post(f"/api/spaces/{sid}/invite", json={"email": "cy@example.com"}).status_code == 403
    # an invitee can't hand out more than a plain account
    alex = register(leon, a["link"])
    assert [s["role"] for s in alex.get("/api/spaces").json()["mine"]] == ["editor"]


def test_trial_shows_cant_invite_anyone_new(tmp_path):
    leon, _ = setup(tmp_path)
    leon.put("/api/site/new-members", json={"on": False})
    tia = join(leon, "tia@example.com", plan="trial")
    sid = show_of(tia)
    assert tia.post(f"/api/spaces/{sid}/invite", json={"email": "alex@example.com"}).status_code == 403
