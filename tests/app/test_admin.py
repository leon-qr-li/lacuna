"""The admin site (decision 2026-10-24-admin-site): its own address, its own sign-in, the step-up code, owner-only
and typed-confirm actions, the request checks, security headers, and the main-site pieces it drives
(站内公告, 维护模式, 想要更多时长, the daily digest and alerts)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lacuna_app import create_app, totp
from lacuna_app.editor import MockEditorAdapter
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import make_workspace

PW = "correct horse battery"
OWNER, MEMBER = "leon@example.com", "sam@example.com"
WRITE = {"x-lacuna-admin": "1"}


def code(app, email: str) -> str:
    """The authenticator code the person's phone would show next (never a used step)."""
    auth = app.state.auth
    tf = auth.users[email]["totp"]
    return totp.code_at(tf["secret"], max(int(auth.now() // totp.STEP), tf.get("last", -1) + 1))


def turn_on_2fa(app, email: str) -> None:
    auth = app.state.auth
    secret = auth.start_2fa(email)["secret"]
    auth.confirm_2fa(email, totp.code_at(secret, int(auth.now() // totp.STEP) - 1))


def setup(tmp_path, **svc):
    ws = make_workspace(tmp_path / "ws")
    mailer = FakeMailer()
    app = create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=mailer, mail_inline=True,
                     no_admin_loop=True, **svc)
    main = TestClient(app)
    assert main.post("/api/auth/register", json={"email": OWNER, "password": PW, "name": "Leon"}).status_code == 200
    turn_on_2fa(app, OWNER)
    return app, main, mailer


def admin_client(app) -> TestClient:
    return TestClient(app, base_url="http://admin.localhost")


def sign_in(app, email: str = OWNER) -> TestClient:
    c = admin_client(app)
    r = c.post("/api/admin/auth/login", json={"email": email, "password": PW, "code": code(app, email)}, headers=WRITE)
    assert r.status_code == 200, r.text
    return c


def join(app, main, email: str = MEMBER) -> TestClient:
    link = main.post("/api/auth/invites", json={"email": email, "plan": "basic"}).json()["link"]
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW, "name": "Sam"}).status_code == 200
    return c


def step_up(app, c: TestClient, email: str = OWNER) -> None:
    assert c.post("/api/admin/auth/stepup", json={"code": code(app, email)}, headers=WRITE).status_code == 200


# ------------------------------------------------------------------ the address
def test_the_main_site_never_answers_the_admin_and_the_admin_never_answers_the_main_site(tmp_path):
    app, main, _ = setup(tmp_path)
    for path in ("/api/admin", "/api/admin/overview", "/api/admin/auth/login", "/api/admin/_test/code?email=x"):
        assert main.get(path).status_code == 404, path
    assert main.post("/api/admin/auth/login", json={}).status_code == 404
    c = admin_client(app)
    # the main site's API does not exist on the admin address, signed in or not
    assert c.get("/api/episodes").status_code == 404
    assert c.get("/api/auth/status").status_code == 404
    signed = sign_in(app)
    assert signed.get("/api/spaces").status_code == 404
    assert signed.get("/api/version").status_code == 200


def test_every_admin_answer_carries_strict_security_headers(tmp_path):
    app, _, _ = setup(tmp_path)
    c = admin_client(app)
    for r in (c.get("/"), c.get("/api/admin/overview"), c.post("/api/admin/auth/login", json={}, headers=WRITE)):
        h = r.headers
        assert "frame-ancestors 'none'" in h["content-security-policy"] and "script-src 'self'" in h["content-security-policy"]
        assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
        assert h["referrer-policy"] == "no-referrer" and "noindex" in h["x-robots-tag"]
    assert c.get("/api/admin/overview").headers["cache-control"] == "no-store"


# ------------------------------------------------------------------ who gets in
def test_only_staff_with_a_password_and_a_fresh_code_get_in(tmp_path):
    app, main, mailer = setup(tmp_path)
    join(app, main)
    turn_on_2fa(app, MEMBER)
    c = admin_client(app)
    assert c.get("/api/admin/overview").status_code == 401
    assert c.get("/api/admin/auth/me").status_code == 401
    bad = c.post("/api/admin/auth/login", json={"email": OWNER, "password": PW, "code": "000000"}, headers=WRITE)
    assert bad.status_code == 401
    wrong = c.post("/api/admin/auth/login", json={"email": OWNER, "password": "nope nope nope", "code": code(app, OWNER)},
                   headers=WRITE)
    assert wrong.status_code == 401
    # a member with a correct password and code: the same answer as a wrong password
    m = c.post("/api/admin/auth/login", json={"email": MEMBER, "password": PW, "code": code(app, MEMBER)}, headers=WRITE)
    assert m.status_code == 401 and m.json()["detail"] == bad.json()["detail"]
    # the main site's session cookie is not an admin session
    assert main.cookies
    stolen = admin_client(app)
    for k, v in main.cookies.items():
        stolen.cookies.set(k, v)
    assert stolen.get("/api/admin/overview").status_code == 401
    # the owner: in, with an 8-hour session and a sign-in alert mail
    mailer.outbox.clear()
    me = sign_in(app)
    who = me.get("/api/admin/auth/me").json()
    assert who["role"] == "owner" and abs(who["exp"] - who["now"] - 8 * 3600) < 5
    assert [m["to"] for m in mailer.outbox] == [OWNER] and "后台" in mailer.outbox[0]["subject"]
    assert me.get("/api/admin/overview").status_code == 200
    # the same code again is refused (no replay)
    used = app.state.auth.users[OWNER]["totp"]["last"]
    replay = totp.code_at(app.state.auth.users[OWNER]["totp"]["secret"], used)
    assert admin_client(app).post("/api/admin/auth/login", json={"email": OWNER, "password": PW, "code": replay},
                                  headers=WRITE).status_code == 401


def test_staff_without_two_step_sign_in_are_told_to_turn_it_on(tmp_path):
    app, main, _ = setup(tmp_path)
    join(app, main)
    app.state.auth.update_user(OWNER, MEMBER, role="admin")
    r = admin_client(app).post("/api/admin/auth/login", json={"email": MEMBER, "password": PW, "code": "123456"},
                               headers=WRITE)
    assert r.status_code == 403 and "两步验证" in r.json()["detail"]


def test_a_member_made_admin_loses_the_admin_at_once_when_made_member_again(tmp_path):
    app, main, _ = setup(tmp_path)
    join(app, main)
    turn_on_2fa(app, MEMBER)
    app.state.auth.update_user(OWNER, MEMBER, role="admin")
    sam = sign_in(app, MEMBER)
    assert sam.get("/api/admin/overview").status_code == 200
    app.state.auth.update_user(OWNER, MEMBER, role="member")
    assert sam.get("/api/admin/overview").status_code == 401


def test_sign_out_and_ending_other_sessions(tmp_path):
    app, _, _ = setup(tmp_path)
    a, b = sign_in(app), sign_in(app)
    rows = a.get("/api/admin/auth/sessions").json()["sessions"]
    assert len(rows) == 2 and sum(x["current"] for x in rows) == 1
    assert a.post("/api/admin/auth/sessions/end", json={}, headers=WRITE).json()["ended"] == 1
    assert b.get("/api/admin/overview").status_code == 401 and a.get("/api/admin/overview").status_code == 200
    assert a.post("/api/admin/auth/logout", headers=WRITE).status_code == 200
    assert a.get("/api/admin/overview").status_code == 401


# ------------------------------------------------------------------ request checks
def test_changes_need_the_admin_header_and_the_same_origin(tmp_path):
    app, main, _ = setup(tmp_path)
    c = sign_in(app)
    body = {"on": True, "zh": "今晚维护", "en": "Maintenance tonight", "until": None}
    assert c.put("/api/admin/settings/notice", json=body).status_code == 403                       # no header
    assert c.put("/api/admin/settings/notice", json=body,
                 headers=WRITE | {"origin": "https://evil.example"}).status_code == 403
    assert c.put("/api/admin/settings/notice", json=body,
                 headers=WRITE | {"sec-fetch-site": "cross-site"}).status_code == 403
    assert c.put("/api/admin/settings/notice", json=body,
                 headers=WRITE | {"origin": "http://admin.localhost"}).status_code == 200
    # and the main site shows it to a signed-in person
    assert main.get("/api/site/notice").json()["notice"]["text"] == "今晚维护"


def test_dangerous_actions_need_the_code_again_for_fifteen_minutes(tmp_path):
    app, main, _ = setup(tmp_path)
    join(app, main)
    c = sign_in(app)
    r = c.post(f"/api/admin/users/{MEMBER}", json={"plan": "pro"}, headers=WRITE)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "stepup"
    assert c.post("/api/admin/auth/stepup", json={"code": "000000"}, headers=WRITE).status_code == 401
    step_up(app, c)
    assert c.post(f"/api/admin/users/{MEMBER}", json={"plan": "pro"}, headers=WRITE).status_code == 200
    assert app.state.auth.users[MEMBER]["plan"] == "pro"
    auth = app.state.auth
    real = auth.now
    auth.now = lambda: real() + 15 * 60 + 1
    try:
        r = c.post(f"/api/admin/users/{MEMBER}", json={"plan": "basic"}, headers=WRITE)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "stepup"
    finally:
        auth.now = real
    actions = [r["action"] for r in c.get("/api/admin/audit").json()["rows"]]
    assert "admin.stepup" in actions and "user.update" in actions and "admin.login" in actions


def test_owner_only_actions_refuse_an_admin(tmp_path):
    app, main, _ = setup(tmp_path)
    join(app, main)
    join(app, main, "kim@example.com")
    turn_on_2fa(app, MEMBER)
    app.state.auth.update_user(OWNER, MEMBER, role="admin")
    sam = sign_in(app, MEMBER)
    step_up(app, sam, MEMBER)
    for method, path, body in (
            ("put", "/api/admin/settings/maintenance", {"on": True}),
            ("put", "/api/admin/access/approval", {"on": False, "confirm": "关掉批准"}),
            ("put", "/api/admin/access/seats", {"value": 99}),
            ("put", "/api/admin/ai/budget", {"value": 1}),
            ("post", "/api/admin/users/kim@example.com/hours", {"hours": 5}),
            ("post", "/api/admin/users/kim@example.com/erase", {"confirm": "kim@example.com"}),
            ("put", "/api/admin/settings/staff/kim@example.com", {"role": "admin"})):
        r = getattr(sam, method)(path, json=body, headers=WRITE)
        assert r.status_code == 403, (path, r.text)
    # an admin can still do the everyday work
    assert sam.put("/api/admin/settings/notice", json={"on": False, "zh": "", "en": "", "until": None},
                   headers=WRITE).status_code == 200


def test_typed_confirmations(tmp_path):
    app, main, _ = setup(tmp_path)
    join(app, main)
    c = sign_in(app)
    step_up(app, c)
    assert c.put("/api/admin/access/approval", json={"on": False, "confirm": "yes"}, headers=WRITE).status_code == 422
    assert c.put("/api/admin/access/approval", json={"on": False, "confirm": "Turn off approval"},
                 headers=WRITE).json()["approval"] is False
    assert c.put("/api/admin/access/approval", json={"on": True, "confirm": ""}, headers=WRITE).json()["approval"] is True
    assert c.post(f"/api/admin/users/{MEMBER}/erase", json={"confirm": "sam"}, headers=WRITE).status_code == 422
    assert c.post(f"/api/admin/users/{OWNER}/erase", json={"confirm": OWNER}, headers=WRITE).status_code == 403
    r = c.post(f"/api/admin/users/{MEMBER}/erase", json={"confirm": MEMBER.upper()}, headers=WRITE)
    assert r.status_code == 200 and r.json()["shows"] == 1
    assert MEMBER not in app.state.auth.users
    assert not [i for i in c.get("/api/admin/trash").json()["items"] if MEMBER in (i.get("name") or "") + i["id"]]


def test_delete_goes_to_the_recycle_bin_and_comes_back(tmp_path):
    app, main, _ = setup(tmp_path)
    join(app, main)
    c = sign_in(app)
    step_up(app, c)
    assert c.delete(f"/api/admin/users/{MEMBER}", headers=WRITE).status_code == 200
    items = c.get("/api/admin/trash").json()["items"]
    user = next(i for i in items if i["kind"] == "user")
    assert c.post(f"/api/admin/trash/user/{user['id']}/purge", json={"confirm": "wrong"}, headers=WRITE).status_code == 422
    assert c.post(f"/api/admin/trash/user/{user['id']}/restore", headers=WRITE).status_code == 200
    assert MEMBER in app.state.auth.users


# ------------------------------------------------------------------ what the pages show
def test_feedback_reply_adopt_tags_and_notes_come_back_as_plain_text(tmp_path):
    app, main, mailer = setup(tmp_path)
    sam = join(app, main)
    fid = sam.post("/api/feedback", json={"kind": "idea", "text": "<script>alert(1)</script> 能不能标记别剪"}).json()["id"]
    c = sign_in(app)
    item = next(i for i in c.get("/api/admin/feedback").json()["items"] if i["id"] == fid)
    assert item["text"].startswith("<script>")          # stored and sent as text; React renders it as text
    assert c.get("/").headers["content-security-policy"].count("'unsafe-eval'") == 0
    mailer.outbox.clear()
    r = c.post(f"/api/admin/feedback/{fid}/reply", json={"text": "好主意，下个版本做", "status": "planned", "adopted": True,
                                                          "mail": True}, headers=WRITE)
    assert r.status_code == 200 and r.json()["mailed"] and [m["to"] for m in mailer.outbox] == [MEMBER]
    mine = sam.get("/api/feedback/mine").json()["items"][0]
    assert mine["status"] == "planned" and mine["replies"][-1]["text"] == "好主意，下个版本做"
    tags = c.put(f"/api/admin/feedback/{fid}/tags", json={"tags": ["  AI   剪错 ", "AI 剪错", "x" * 40]}, headers=WRITE)
    assert tags.json()["tags"] == ["AI 剪错", "x" * 24]
    assert c.post("/api/admin/notes", json={"target": f"fb:{fid}", "text": "和陈的那条是一回事"}, headers=WRITE).status_code == 200
    assert c.get(f"/api/admin/notes?target=fb:{fid}").json()["notes"][0]["text"] == "和陈的那条是一回事"
    assert c.post("/api/admin/notes", json={"target": "fb:nope", "text": "x"}, headers=WRITE).status_code == 404
    # notes and tags are the admin's: never in the person's own view
    assert "notes" not in mine and "tags" not in mine


def test_the_admin_never_hands_out_audio_or_transcripts(tmp_path):
    app, main, _ = setup(tmp_path)
    c = sign_in(app)
    for path in ("/api/admin/shows", "/api/admin/users", "/api/admin/overview", "/api/admin/system"):
        body = c.get(path).text
        assert ".wav" not in body and "words" not in body, path
    sid = c.get("/api/admin/shows").json()["shows"][0]["id"]
    assert c.post(f"/api/admin/shows/{sid}/open", headers=WRITE).json()["url"]
    assert c.get("/api/episodes").status_code == 404


def test_every_page_answers(tmp_path):
    app, main, _ = setup(tmp_path)
    sam = join(app, main)
    sam.post("/api/feedback", json={"kind": "bug", "text": "x"})
    c = sign_in(app)
    for path in ("overview", "feedback", "feedback/prompts", "templates", "users", f"users/{MEMBER}", "access", "hours",
                 "shows", "trash", "ai", "growth?weeks=13", "system", "settings", "audit"):
        r = c.get(f"/api/admin/{path}")
        assert r.status_code == 200, (path, r.text)
    assert c.get("/api/admin/users/nobody@example.com").status_code == 404


def test_invites_from_the_admin(tmp_path):
    app, main, mailer = setup(tmp_path)
    c = sign_in(app)
    r = c.post("/api/admin/invites", json={"email": "new@example.com", "role": "member", "source": "xiaoyuzhou",
                                           "plan": "basic", "lang": "en"}, headers=WRITE)
    assert r.status_code == 200, r.text
    assert r.json()["link"].startswith("http://localhost/")       # the invite opens the main site, not the admin
    assert any(i["email"] == "new@example.com" and i["source"] == "xiaoyuzhou" for i in r.json()["invites"])


# ------------------------------------------------------------------ main-site pieces
def test_more_hours_request_is_approved_in_the_admin_and_mailed(tmp_path):
    app, main, mailer = setup(tmp_path)
    sam = join(app, main)
    assert sam.post("/api/plan/hours", json={"hours": 2, "reason": "两集长访谈", "would_pay": True}).status_code == 200
    assert sam.post("/api/plan/hours", json={"hours": 1}).status_code == 409          # one waiting at a time
    assert any(m["to"] == OWNER for m in mailer.outbox)
    c = sign_in(app)
    h = c.get("/api/admin/hours").json()
    rid = h["requests"][0]["id"]
    assert h["willing"][0]["email"] == MEMBER
    r = c.post(f"/api/admin/hours/{rid}", json={"action": "approve", "hours": 2}, headers=WRITE)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "stepup"
    step_up(app, c)
    mailer.outbox.clear()
    assert c.post(f"/api/admin/hours/{rid}", json={"action": "approve", "hours": 2}, headers=WRITE).status_code == 200
    assert [m["to"] for m in mailer.outbox] == [MEMBER]
    assert sam.get("/api/plan/hours").json()["requests"][0]["status"] == "approved"


def test_maintenance_pauses_new_uploads_only(tmp_path):
    app, main, _ = setup(tmp_path)
    c = sign_in(app)
    step_up(app, c)
    assert c.put("/api/admin/settings/maintenance", json={"on": True}, headers=WRITE).status_code == 200
    r = main.post("/api/imports", json={})
    assert r.status_code == 503 and r.json()["maintenance"] is True
    assert main.get("/api/site/notice").json()["maintenance"] is True
    assert main.get("/api/spaces").status_code == 200                     # everything else keeps working
    c.put("/api/admin/settings/maintenance", json={"on": False}, headers=WRITE)
    assert main.post("/api/imports", json={}).status_code != 503


def test_daily_digest_at_eight_vancouver_and_alerts_once_a_day(tmp_path):
    app, main, mailer = setup(tmp_path)
    auth = app.state.auth
    digest = app.state.admin_digest
    data = app.state.ctx.provide("admin_data")
    real = auth.now
    # 2026-10-24 07:30 in Vancouver (PDT, UTC-7) = 14:30 UTC; then 08:05
    early, late = 1792852200.0, 1792854300.0
    data.alerts = lambda *_: [{"kind": "disk", "pct": 0.83, "used": 41.5e9, "total": 50e9}]
    try:
        auth.now = lambda: early
        mailer.outbox.clear()
        assert digest.tick() == ["disk:2026-10-24"]
        auth.now = lambda: late
        assert digest.tick() == ["digest:2026-10-24"]          # the disk alert is not sent twice in a day
        assert digest.tick() == []
        subjects = [m["subject"] for m in mailer.outbox]
        assert len(subjects) == 2 and all(m["to"] == OWNER for m in mailer.outbox)
        assert "83%" in mailer.outbox[0]["text"]
    finally:
        auth.now = real


def test_admin_access_check_in_the_cloud(tmp_path):
    """In the cloud the admin address needs a token from its own Access application; the main site's
    token (another audience) does not open it."""

    class FakeVerifier:
        def verify(self, token):
            return {"email": OWNER} if token == "admin-token" else None

    app, _, _ = setup(tmp_path, admin_access_verifier=FakeVerifier(), admin_cloud=True)
    c = admin_client(app)
    assert c.get("/").status_code == 403
    assert c.get("/", headers={"cf-access-jwt-assertion": "main-site-token"}).status_code == 403
    ok = c.get("/", headers={"cf-access-jwt-assertion": "admin-token"})
    assert ok.status_code == 200 and ok.headers["x-frame-options"] == "DENY"


def test_the_ai_budget_warning_defaults_to_500_for_the_quality_first_models(tmp_path):
    app, _, _ = setup(tmp_path)
    c = sign_in(app)
    assert c.get("/api/admin/ai").json()["budget"] == 500
    assert c.get("/api/admin/system").json()["budget"] == 500
