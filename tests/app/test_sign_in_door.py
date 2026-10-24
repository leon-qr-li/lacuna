"""The app's own front door (decision 2026-10-21-app-sign-in): Turnstile, new-device emails, 申请试用,
and running without Cloudflare Access in front (LACUNA_ACCESS=off)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.notice_mail import country_name, device_label
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import make_workspace

PW = "correct horse battery"
MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0"


class FakeTurnstile:
    def __init__(self):
        self.seen = []

    def ok(self, token, ip=None):
        self.seen.append(token)
        return token == "good"


def make(tmp_path, **kw):
    mailer = FakeMailer()
    app = create_app(make_workspace(tmp_path / "ws"), MockEditorAdapter(), web_dist=tmp_path / "none",
                     mailer=mailer, mail_inline=True, **kw)
    c = TestClient(app, headers={"user-agent": MAC})
    c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    return c, mailer


def test_turnstile_guards_sign_in_when_on(tmp_path):
    human = FakeTurnstile()
    c, _ = make(tmp_path, turnstile=human, turnstile_site_key="0x4AAA-site")
    assert c.get("/api/auth/status").json()["turnstile"] == "0x4AAA-site"
    c.post("/api/auth/logout")
    r = c.post("/api/auth/login", json={"email": "leon@example.com", "password": PW})
    assert r.status_code == 400 and "人机验证" in r.json()["detail"]
    r = c.post("/api/auth/login", json={"email": "leon@example.com", "password": PW, "turnstile": "bad"})
    assert r.status_code == 400
    assert c.post("/api/auth/login", json={"email": "leon@example.com", "password": PW,
                                           "turnstile": "good"}).status_code == 200


def test_turnstile_off_by_default(tmp_path):
    c, _ = make(tmp_path)
    assert c.get("/api/auth/status").json()["turnstile"] is None
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"email": "leon@example.com", "password": PW}).status_code == 200


def test_a_new_device_gets_an_email_a_known_one_does_not(tmp_path):
    c, mailer = make(tmp_path)
    assert mailer.outbox == []                       # the first sign-in ever: nothing to compare with
    other = TestClient(c.app, headers={"user-agent": WIN, "cf-ipcountry": "US"})
    other.post("/api/auth/login", json={"email": "leon@example.com", "password": PW})
    [m] = mailer.outbox
    assert m["to"] == "leon@example.com" and "新设备" in m["subject"]
    assert "Firefox · Windows" in m["text"] and "美国" in m["text"] and "#/settings/account" in m["text"]
    other.post("/api/auth/login", json={"email": "leon@example.com", "password": PW})
    c.post("/api/auth/login", json={"email": "leon@example.com", "password": PW})
    assert len(mailer.outbox) == 1


def test_device_and_country_names():
    assert device_label(MAC) == "Chrome · macOS" and device_label("") == "未知设备"
    assert country_name("CA") == "加拿大" and country_name("XX") is None and country_name("BR") == "BR"


def test_access_request_reaches_the_owner_once(tmp_path):
    c, mailer = make(tmp_path)
    anon = TestClient(c.app)
    body = {"email": "Host@Example.com", "show": "深夜电影院", "note": "两个人的对谈节目"}
    assert anon.post("/api/access-requests", json=body).json() == {"ok": True}
    assert anon.post("/api/access-requests", json=body).json() == {"ok": True}    # same day: nothing new
    m, got = mailer.outbox                     # the owner's notice and the 「已收到申请」 mail, once each
    assert m["to"] == "leon@example.com" and "host@example.com" in m["subject"] and "深夜电影院" in m["text"]
    assert got["to"] == "host@example.com" and got["subject"] == "我们收到了你的 LACUNA 试用申请"
    assert "审核通过后发送邀请" in got["text"] and "深夜电影院" in got["text"] and "UTC" in got["text"]
    assert "/invite/" not in got["text"] and "两个人的对谈节目" not in got["text"]
    reqs = c.get("/api/access-requests").json()["requests"]
    assert [(r["email"], r["show"]) for r in reqs] == [("host@example.com", "深夜电影院")]
    assert anon.get("/api/access-requests").status_code == 401
    out = c.post(f"/api/access-requests/{reqs[0]['id']}", json={"action": "invite"}).json()
    assert out["requests"] == [] and "/invite/" in out["link"]
    assert mailer.outbox[-1]["to"] == "host@example.com"
    assert [i["email"] for i in c.get("/api/auth/users").json()["invites"]] == ["host@example.com"]


def test_access_requests_are_checked_and_limited(tmp_path):
    human = FakeTurnstile()
    c, mailer = make(tmp_path, turnstile=human, turnstile_site_key="k")
    anon = TestClient(c.app)
    assert anon.post("/api/access-requests", json={"email": "a@example.com"}).status_code == 400
    assert anon.post("/api/access-requests", json={"email": "nope", "turnstile": "good"}).status_code == 400
    codes = [anon.post("/api/access-requests", json={"email": f"p{i}@example.com", "turnstile": "good"}).status_code
             for i in range(6)]
    assert codes == [200] * 5 + [429]
    # dismissing removes it from the list
    rid = c.get("/api/access-requests").json()["requests"][0]["id"]
    assert len(c.post(f"/api/access-requests/{rid}", json={"action": "dismiss"}).json()["requests"]) == 4
    # someone who already has an account: the same answer, no mail to the owner or to them
    n = len(mailer.outbox)
    TestClient(c.app, headers={"cf-connecting-ip": "1.2.3.4"}).post(
        "/api/access-requests", json={"email": "leon@example.com", "turnstile": "good"})
    assert len(mailer.outbox) == n


def test_without_access_in_front_the_app_sign_in_is_the_door(tmp_path, monkeypatch):
    monkeypatch.setenv("LACUNA_CLOUD", "1")
    monkeypatch.setenv("LACUNA_ACCESS", "off")
    ws = make_workspace(tmp_path / "ws")
    app = create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer())
    c = TestClient(app, base_url="https://testserver")
    assert c.get("/api/auth/status").status_code == 200           # no Access token needed
    assert c.get("/api/episodes").status_code == 401              # but the app's sign-in is
    assert c.post("/api/app/api-key", json={"key": "x"}).status_code == 404   # cloud rules still hold
    # the admin host is split off first (its own Access audience, decision admin-site), then the main door
    assert [m.cls.__name__ for m in app.user_middleware[:2]] == ["AdminHost", "CloudGate"]


def test_request_received_mail_speaks_the_language_it_was_asked_in(tmp_path):
    c, mailer = make(tmp_path)
    TestClient(c.app).post("/api/access-requests", json={"email": "ava@example.com", "lang": "en"})
    got = mailer.outbox[-1]
    assert got["to"] == "ava@example.com" and got["subject"] == "We received your LACUNA access request"
    assert "An invite once it's approved" in got["text"] and "节目" not in got["text"]
    assert "ignore this email" in got["html"] and "cid:" in got["html"]       # same 夜航信笺 look, no button
