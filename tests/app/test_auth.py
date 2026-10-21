"""Sign-in: accounts, sessions, email codes, the /api gate (lacuna_app/auth.py, routes/auth.py)."""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.auth import Auth, AuthError, MailError, ResendMailer, hash_password, verify_password
from lacuna_app.editor import MockEditorAdapter
from tests.app import site_db
from tests.app.e2e.auth import FakeMailer

PW = "correct horse battery"


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def mailer():
    return FakeMailer()


@pytest.fixture
def client(tmp_path, mailer):
    app = create_app(tmp_path / "ws", MockEditorAdapter(), web_dist=tmp_path / "none", mailer=mailer)
    return TestClient(app)


def last_code(mailer) -> str:
    return re.search(r"\b(\d{6})\b", mailer.outbox[-1]["text"]).group(1)


def test_password_hash_roundtrip_and_salted():
    h = hash_password(PW)
    assert verify_password(PW, h) and not verify_password(PW + "x", h)
    assert hash_password(PW) != h          # random salt
    assert PW not in h
    assert not verify_password(PW, "garbage")


def test_api_open_until_first_account_then_gated(client):
    assert client.get("/api/episodes").status_code == 200
    st = client.get("/api/auth/status").json()
    assert st["accounts"] is False and st["setup"] is True and st["first"] is True
    # the first account needs no email code and signs in at once
    r = client.post("/api/auth/register", json={"email": "Leon@Example.com", "password": PW})
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    assert client.get("/api/auth/status").json()["email"] == "leon@example.com"
    assert client.get("/api/episodes").status_code == 200
    # another browser (no cookie) is locked out of the API but the launcher's checks still answer
    other = TestClient(client.app)
    assert other.get("/api/episodes").status_code == 401
    assert other.post("/api/episodes/x/undo").status_code == 401
    assert other.get("/api/health").status_code == 200
    assert other.get("/api/app").status_code == 200
    assert other.get("/api/auth/status").json() == {**st, "accounts": True, "setup": False, "first": False}
    assert st["mail"] is None and st["require_2fa"] is False         # nothing about email until signed in


def test_login_logout_remember(client):
    client.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    client.post("/api/auth/logout")
    assert client.get("/api/episodes").status_code == 401
    assert client.post("/api/auth/login", json={"email": "leon@example.com", "password": "wrong password"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": " LEON@example.com ", "password": PW, "remember": True})
    assert r.status_code == 200 and "max-age=2592000" in r.headers["set-cookie"].lower()
    assert client.get("/api/episodes").status_code == 200
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"email": "leon@example.com", "password": PW, "remember": False})
    assert "max-age" not in r.headers["set-cookie"].lower()      # browser-session cookie


def test_sessions_survive_restart_and_store_no_secrets(tmp_path, mailer):
    ws = tmp_path / "ws"
    c1 = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=mailer))
    c1.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    token = c1.cookies.get("lacuna_session")
    c2 = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=mailer))
    c2.cookies.set("lacuna_session", token)
    assert c2.get("/api/episodes").status_code == 200
    stored = site_db.stored(ws)
    assert PW not in stored and token not in stored


def test_session_expiry(tmp_path, mailer):
    clock = Clock()
    a = Auth(tmp_path, mailer, clock=clock)
    tok, _ = a.register_first("leon@example.com", PW, None, remember=False)["session"]
    assert a.who(tok) == "leon@example.com"
    clock.t += 12 * 3600 + 1
    assert a.who(tok) is None
    tok, _ = a.login("leon@example.com", PW, remember=True)["session"]
    clock.t += 29 * 86400
    assert a.who(tok) == "leon@example.com"


def test_login_lockout(tmp_path, mailer):
    clock = Clock()
    a = Auth(tmp_path, mailer, clock=clock)
    a.register_first("leon@example.com", PW, None, remember=True)
    for _ in range(5):
        with pytest.raises(AuthError):
            a.login("leon@example.com", "nope nope nope", True)
    with pytest.raises(AuthError) as e:
        a.login("leon@example.com", PW, True)      # right password, still locked
    assert e.value.status == 429 and "15 分钟" in str(e.value)
    clock.t += 14 * 60
    with pytest.raises(AuthError):
        a.login("leon@example.com", PW, True)
    clock.t += 61
    assert a.login("leon@example.com", PW, True)["step"] == "done"


def test_validation(client):
    assert client.post("/api/auth/register", json={"email": "not-an-email", "password": PW}).status_code == 400
    assert client.post("/api/auth/register", json={"email": "a@b.co", "password": "short"}).status_code == 400
    assert client.get("/api/auth/status").json()["accounts"] is False


def test_code_cooldown_and_tries(tmp_path, mailer):
    clock = Clock()
    a = Auth(tmp_path, mailer, clock=clock)
    a.register_first("leon@example.com", PW, None, True)
    a.send_code("leon@example.com", "reset")
    with pytest.raises(AuthError) as e:
        a.send_code("leon@example.com", "reset")
    assert e.value.status == 429
    for _ in range(4):
        with pytest.raises(AuthError):
            a.reset("leon@example.com", "999999" if last_code(mailer) != "999999" else "888888", "new password 123")
    with pytest.raises(AuthError, match="太多次"):
        a.reset("leon@example.com", "999999" if last_code(mailer) != "999999" else "888888", "new password 123")
    with pytest.raises(AuthError, match="过期"):        # the code is gone after 5 tries
        a.reset("leon@example.com", last_code(mailer), "new password 123")
    clock.t += 61
    a.send_code("leon@example.com", "reset")
    clock.t += 601
    with pytest.raises(AuthError, match="过期"):
        a.reset("leon@example.com", last_code(mailer), "new password 123")


def test_forgot_password_flow(client, mailer):
    client.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    old_cookie = client.cookies.get("lacuna_session")
    other = TestClient(client.app)
    # unknown email: same answer, nothing sent
    assert other.post("/api/auth/code", json={"email": "who@example.com", "purpose": "reset"}).json() == {"sent": True}
    assert not mailer.outbox
    assert other.post("/api/auth/code", json={"email": "leon@example.com", "purpose": "reset"}).status_code == 200
    r = other.post("/api/auth/reset", json={"email": "leon@example.com", "code": last_code(mailer),
                                            "password": "a brand new password"})
    assert r.status_code == 200 and other.get("/api/episodes").status_code == 200
    # the old session ended, the old password no longer works, the new one does
    stale = TestClient(client.app)
    stale.cookies.set("lacuna_session", old_cookie)
    assert stale.get("/api/episodes").status_code == 401
    assert stale.post("/api/auth/login", json={"email": "leon@example.com", "password": PW}).status_code == 401
    assert stale.post("/api/auth/login", json={"email": "leon@example.com", "password": "a brand new password"}).status_code == 200


def test_mail_failure_is_reported(tmp_path):
    class Down(FakeMailer):
        def send(self, *a, **k):
            raise MailError("连不上 Resend")  # i18n-ignore
    a = Auth(tmp_path, Down())
    a.register_first("leon@example.com", PW, None, True)
    with pytest.raises(AuthError) as e:
        a.send_code("leon@example.com", "reset")
    assert e.value.status == 502 and "Resend" in str(e.value)
    # a failed send leaves no code behind and no cooldown
    assert not a.codes


def test_settings_endpoints(client, mailer, monkeypatch):
    client.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    assert client.post("/api/auth/test-mail").json() == {"sent": True, "to": "leon@example.com"}
    assert mailer.outbox[-1]["to"] == "leon@example.com"
    assert client.post("/api/auth/config", json={"sender": "no address"}).status_code == 400
    st = client.post("/api/auth/config", json={"sender": "LACUNA <hi@lacuna.fm>"}).json()
    assert st["mail"]["sender"] == "LACUNA <hi@lacuna.fm>"
    assert client.post("/api/auth/resend-key", json={"key": "sk-ant-wrong"}).status_code == 400
    saved = {}
    monkeypatch.setattr("lacuna_app.auth.save_secret", lambda n, v: saved.setdefault(n, v) and "file")
    r = client.post("/api/auth/resend-key", json={"key": "re_" + "x" * 30})
    assert r.status_code == 200 and saved == {"RESEND_API_KEY": "re_" + "x" * 30}
    assert "re_xxx" not in json.dumps(r.json())


def test_resend_mailer_request_and_errors(monkeypatch):
    import io
    import urllib.error
    sent = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def ok(req, timeout):
        sent.update(url=req.full_url, auth=req.get_header("Authorization"), ua=req.get_header("User-agent"),
                    body=json.loads(req.data))
        return Resp(b'{"id":"1"}')

    monkeypatch.setattr("urllib.request.urlopen", ok)
    m = ResendMailer(key=lambda: "re_test_key_1234567890")
    m.send("LACUNA <onboarding@resend.dev>", "leon@example.com", "subj", "body")
    assert sent["url"] == "https://api.resend.com/emails" and sent["auth"] == "Bearer re_test_key_1234567890"
    assert sent["ua"] == "LACUNA-Studio"
    assert sent["body"] == {"from": "LACUNA <onboarding@resend.dev>", "to": ["leon@example.com"], "subject": "subj",
                            "text": "body"}

    def testing_only(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(
            b'{"message":"You can only send testing emails to your own email address (leon@example.com)."}'))
    monkeypatch.setattr("urllib.request.urlopen", testing_only)
    with pytest.raises(MailError, match="验证自己的域名"):
        m.send("x <a@b.c>", "pei@example.com", "s", "t")
    with pytest.raises(MailError, match="Resend API key"):
        ResendMailer(key=lambda: None).send("x <a@b.c>", "a@b.c", "s", "t")
