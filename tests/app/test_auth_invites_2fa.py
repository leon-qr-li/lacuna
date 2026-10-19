"""Invite-only accounts, roles, two-step sign-in, devices (lacuna_app/auth.py, totp.py, routes/auth.py)."""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app, totp
from lacuna_app.auth import Auth, AuthError
from lacuna_app.editor import MockEditorAdapter
from tests.app.e2e.auth import FakeMailer

PW = "correct horse battery"


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def now_code(secret: str, at: float | None = None) -> str:
    import time
    return totp.code_at(secret, int((at if at is not None else time.time()) // totp.STEP))


@pytest.fixture
def mailer():
    return FakeMailer()


def make(tmp_path, mailer, cloud=False):
    # the cloud cookie is Secure: the test browser must be on https to send it back
    return TestClient(create_app(tmp_path / "ws", MockEditorAdapter(), web_dist=tmp_path / "none", mailer=mailer,
                                 auth_cloud=cloud), base_url="https://testserver" if cloud else "http://testserver")


def invite_token(link: str) -> str:
    return link.rsplit("/", 1)[1]


# ---------------------------------------------------------------------------------------------- totp

def test_totp_matches_rfc6238_vectors():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"      # "12345678901234567890" (RFC 6238 appendix B, SHA-1)
    for t, want in [(59, "94287082"), (1111111109, "07081804"), (1234567890, "89005924"), (2000000000, "69279037")]:
        assert totp.code_at(secret, t // 30) == want[-6:]
    assert totp.match(secret, "287082", 59) == 1
    assert totp.match(secret, "287082", 59 + 30) == 1          # one step of clock drift is fine
    assert totp.match(secret, "287082", 59 + 90) is None
    assert totp.match(secret, "287082", 59, after=1) is None   # already used
    assert totp.match(secret, "abc", 59) is None
    assert "secret=" + secret in totp.uri(secret, "leon@example.com") and totp.uri(secret, "a@b.c").startswith("otpauth://totp/")
    codes = totp.recovery_codes()
    assert len(set(codes)) == 10 and all(re.fullmatch(r"[a-z2-9]{5}-[a-z2-9]{5}", c) for c in codes)
    assert totp.norm_recovery(codes[0].upper().replace("-", " ")) == codes[0]


# ---------------------------------------------------------------------------------------------- invites

def test_invite_only_signup(tmp_path, mailer):
    c = make(tmp_path, mailer)
    c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    pei = TestClient(c.app)
    # no open sign-up any more: without an invite, a second account is refused
    r = pei.post("/api/auth/register", json={"email": "pei@example.com", "password": PW})
    assert r.status_code == 403
    assert pei.post("/api/auth/code", json={"email": "pei@example.com", "purpose": "register"}).status_code == 400
    assert pei.post("/api/auth/invites", json={"email": "pei@example.com"}).status_code == 401
    out = c.post("/api/auth/invites", json={"email": "Pei@Example.com", "role": "member"},
                 headers={"origin": "https://studio.example"}).json()
    assert out["mailed"] is True and out["link"].startswith("https://studio.example/#/invite/")
    assert mailer.outbox[-1]["to"] == "pei@example.com" and out["link"] in mailer.outbox[-1]["text"]
    assert [i["email"] for i in out["invites"]] == ["pei@example.com"]
    tok = invite_token(out["link"])
    assert pei.post("/api/auth/invite", json={"token": tok}).json()["email"] == "pei@example.com"
    assert pei.post("/api/auth/invite", json={"token": "nope"}).status_code == 404
    r = pei.post("/api/auth/register", json={"invite": tok, "password": PW})
    assert r.status_code == 200 and r.json()["step"] == "done"
    assert pei.get("/api/auth/status").json()["email"] == "pei@example.com"
    assert pei.get("/api/auth/status").json()["role"] == "member"
    # used up
    assert TestClient(c.app).post("/api/auth/register", json={"invite": tok, "password": PW}).status_code == 404
    # the token itself is never stored
    assert tok not in (tmp_path / "ws" / "auth" / "users.json").read_text()


def test_invite_expiry_revoke_and_newest_wins(tmp_path, mailer):
    clock = Clock()
    a = Auth(tmp_path, mailer, clock=clock)
    a.register_first("leon@example.com", PW, None, True)
    first = invite_token(a.invite("leon@example.com", "pei@example.com", "member", "http://x")["link"])
    second = invite_token(a.invite("leon@example.com", "pei@example.com", "admin", "http://x")["link"])
    with pytest.raises(AuthError):
        a.invite_info(first)                       # replaced by the newer link
    assert a.invite_info(second)["role"] == "admin"
    a.revoke_invite(a.list_invites()[0]["id"])
    with pytest.raises(AuthError):
        a.invite_info(second)
    third = invite_token(a.invite("leon@example.com", "pei@example.com", "member", "http://x")["link"])
    clock.t += 7 * 86400 + 1
    with pytest.raises(AuthError, match="失效"):
        a.register_invite(third, PW, True)
    with pytest.raises(AuthError):
        a.invite("leon@example.com", "leon@example.com", "member", "http://x")   # already has an account


def test_invite_link_returned_when_mail_fails(tmp_path):
    class Down(FakeMailer):
        def send(self, *a):
            from lacuna_app.auth import MailError
            raise MailError("Resend 403")
    a = Auth(tmp_path, Down())
    a.register_first("leon@example.com", PW, None, True)
    out = a.invite("leon@example.com", "pei@example.com", "member", "http://127.0.0.1:8765")
    assert out["mailed"] is False and "403" in out["mail_error"] and out["link"].startswith("http://127.0.0.1:8765/#/invite/")
    assert a.register_invite(invite_token(out["link"]), PW, True)["step"] == "done"


# ---------------------------------------------------------------------------------------------- roles

def test_roles_and_member_management(tmp_path, mailer):
    clock = Clock()
    a = Auth(tmp_path, mailer, clock=clock)
    a.register_first("leon@example.com", PW, None, True)
    for email, role in [("ann@example.com", "admin"), ("bob@example.com", "member"), ("cy@example.com", "member")]:
        a.register_invite(invite_token(a.invite("leon@example.com", email, role, "http://x")["link"]), PW, True)
    assert [(u["email"], u["role"]) for u in a.list_users()][:2] == [("leon@example.com", "owner"), ("ann@example.com", "admin")]
    # admins invite and manage members, but can't make admins or touch the owner / other admins
    with pytest.raises(AuthError) as e:
        a.invite("ann@example.com", "dee@example.com", "admin", "http://x")
    assert e.value.status == 403
    a.invite("ann@example.com", "dee@example.com", "member", "http://x")
    with pytest.raises(AuthError):
        a.update_user("ann@example.com", "leon@example.com", disabled=True)
    with pytest.raises(AuthError):
        a.update_user("bob@example.com", "cy@example.com", disabled=True)
    with pytest.raises(AuthError):
        a.update_user("leon@example.com", "leon@example.com", role="member")      # not yourself
    with pytest.raises(AuthError):
        a.update_user("leon@example.com", "bob@example.com", role="owner")        # one owner
    # disabling ends their sessions and blocks sign-in
    tok, _ = a.login("bob@example.com", PW, True)["session"]
    a.update_user("ann@example.com", "bob@example.com", disabled=True)
    assert a.who(tok) is None
    with pytest.raises(AuthError):
        a.login("bob@example.com", PW, True)
    a.update_user("ann@example.com", "bob@example.com", disabled=False)
    assert a.login("bob@example.com", PW, True)["step"] == "done"
    a.update_user("leon@example.com", "bob@example.com", role="admin")
    assert a.role("bob@example.com") == "admin"
    a.delete_user("leon@example.com", "cy@example.com")
    assert "cy@example.com" not in a.users


def test_member_cannot_use_owner_settings(tmp_path, mailer):
    c = make(tmp_path, mailer)
    c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    tok = invite_token(c.post("/api/auth/invites", json={"email": "pei@example.com"}).json()["link"])
    pei = TestClient(c.app)
    pei.post("/api/auth/register", json={"invite": tok, "password": PW})
    assert pei.get("/api/episodes").status_code == 200
    assert pei.get("/api/auth/status").json()["mail"] is None
    for path, body in [("/api/auth/config", {"sender": "x <a@b.c>"}), ("/api/auth/resend-key", {"key": "re_" + "x" * 30}),
                       ("/api/auth/test-mail", None), ("/api/app/api-key", {"key": "x"}),
                       ("/api/app/update/apply", None), ("/api/auth/invites", {"email": "z@example.com"})]:
        assert pei.post(path, json=body).status_code == 403, path
    assert pei.get("/api/auth/users").status_code == 403
    assert c.get("/api/auth/users").json()["users"][1]["email"] == "pei@example.com"


def test_old_accounts_get_roles(tmp_path, mailer):
    d = tmp_path / "auth"
    d.mkdir()
    (d / "users.json").write_text(json.dumps({"users": [
        {"email": "leon@example.com", "hash": "x", "created": 1, "owner": True, "verified": False},
        {"email": "pei@example.com", "hash": "x", "created": 2, "owner": False, "verified": True}],
        "config": {"allow_register": True, "sender": "S <s@x.y>"}}))
    a = Auth(tmp_path, mailer)
    assert a.role("leon@example.com") == "owner" and a.role("pei@example.com") == "member"
    assert a.config == {"sender": "S <s@x.y>"}


# ---------------------------------------------------------------------------------------------- 2fa

def test_cloud_requires_two_step_from_the_first_sign_in(tmp_path, mailer):
    c = make(tmp_path, mailer, cloud=True)
    # a fresh server: the owner needs the setup code from the server's disk
    st = c.get("/api/auth/status").json()
    assert st["require_2fa"] is True and st["setup_code"] is True
    code_file = tmp_path / "ws" / "auth" / "setup-code.txt"
    setup = code_file.read_text().strip()
    assert c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW,
                                              "setup_code": "wrong"}).status_code == 403
    r = c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW, "setup_code": setup})
    out = r.json()
    assert out["step"] == "enroll" and "set-cookie" not in r.headers           # no session before the code
    assert c.get("/api/episodes").status_code == 401
    assert not code_file.exists()
    assert c.post("/api/auth/2fa/enroll", json={"ticket": out["ticket"], "code": "000000"}).status_code == 401
    used = now_code(out["secret"])
    r = c.post("/api/auth/2fa/enroll", json={"ticket": out["ticket"], "code": used})
    assert r.status_code == 200 and "secure" in r.headers["set-cookie"].lower()
    recovery = r.json()["recovery"]
    assert len(recovery) == 10 and c.get("/api/auth/status").json()["twofa"] is True
    stored = (tmp_path / "ws" / "auth" / "users.json").read_text()
    assert not any(x in stored for x in recovery)

    # signing in again: password, then the authenticator (the same code can't be used twice)
    other = TestClient(c.app, base_url="https://testserver")
    out = other.post("/api/auth/login", json={"email": "leon@example.com", "password": PW}).json()
    assert out["step"] == "2fa" and other.get("/api/episodes").status_code == 401
    assert other.post("/api/auth/2fa", json={"ticket": out["ticket"], "code": used}).status_code == 401
    # a recovery code works once
    assert other.post("/api/auth/2fa", json={"ticket": out["ticket"], "code": recovery[0].upper()}).status_code == 200
    assert other.get("/api/episodes").status_code == 200
    third = TestClient(c.app, base_url="https://testserver")
    t = third.post("/api/auth/login", json={"email": "leon@example.com", "password": PW}).json()["ticket"]
    assert third.post("/api/auth/2fa", json={"ticket": t, "code": recovery[0]}).status_code == 401
    # in the cloud nobody can switch it off
    assert c.post("/api/auth/2fa/off", json={"code": recovery[1]}).status_code == 403


def test_two_step_with_clock(tmp_path, mailer):
    clock = Clock()
    a = Auth(tmp_path, mailer, clock=clock, cloud=True)
    a.setup_code = None
    out = a.register_first("leon@example.com", PW, None, True)
    a.enroll(out["ticket"], now_code(out["secret"], clock.t))
    secret = a.users["leon@example.com"]["totp"]["secret"]
    t = a.login("leon@example.com", PW, True)["ticket"]
    with pytest.raises(AuthError):
        a.second_step(t, now_code(secret, clock.t))          # the enrolment code, already used
    clock.t += 30
    assert a.second_step(t, now_code(secret, clock.t))["step"] == "done"
    # a ticket lasts 5 minutes
    t = a.login("leon@example.com", PW, True)["ticket"]
    clock.t += 301
    with pytest.raises(AuthError, match="重新登录"):
        a.second_step(t, now_code(secret, clock.t))
    # wrong codes count toward the lockout
    t = a.login("leon@example.com", PW, True)["ticket"]
    for _ in range(5):
        with pytest.raises(AuthError):
            a.second_step(t, "000000" if now_code(secret, clock.t) != "000000" else "111111")
    with pytest.raises(AuthError) as e:
        a.login("leon@example.com", PW, True)
    assert e.value.status == 429


def test_desktop_two_step_is_optional(tmp_path, mailer):
    c = make(tmp_path, mailer)
    c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    assert c.get("/api/auth/status").json()["twofa"] is False
    s = c.post("/api/auth/2fa/setup").json()
    assert c.post("/api/auth/2fa/confirm", json={"code": "000000" if now_code(s["secret"]) != "000000" else "111111"}).status_code == 400
    rec = c.post("/api/auth/2fa/confirm", json={"code": now_code(s["secret"])}).json()["recovery"]
    assert len(rec) == 10
    out = TestClient(c.app).post("/api/auth/login", json={"email": "leon@example.com", "password": PW}).json()
    assert out["step"] == "2fa"
    new = c.post("/api/auth/2fa/recovery", json={"code": rec[0]}).json()["recovery"]
    assert set(new).isdisjoint(rec)
    assert c.post("/api/auth/2fa/off", json={"code": rec[1]}).status_code == 400   # old codes are gone
    assert c.post("/api/auth/2fa/off", json={"code": new[0]}).json()["twofa"] is False


def test_reset_password_needs_second_step(tmp_path, mailer):
    clock = Clock()
    a = Auth(tmp_path, mailer, clock=clock, cloud=True)
    a.setup_code = None
    out = a.register_first("leon@example.com", PW, None, True)
    rec = a.enroll(out["ticket"], now_code(out["secret"], clock.t))["recovery"]
    old_tok, _ = a.second_step(a.login("leon@example.com", PW, True)["ticket"], rec[0])["session"]
    a.send_code("leon@example.com", "reset")
    code = re.search(r"\b(\d{6})\b", mailer.outbox[-1]["text"]).group(1)
    out = a.reset("leon@example.com", code, "a brand new password")
    assert out["step"] == "2fa"
    assert verify_old(a, PW)                         # nothing changed yet
    a.second_step(out["ticket"], rec[1])
    assert verify_old(a, "a brand new password") and a.who(old_tok) is None


def verify_old(a, pw):
    from lacuna_app.auth import verify_password
    return verify_password(pw, a.users["leon@example.com"]["hash"])


def test_owner_resets_a_lost_authenticator(tmp_path, mailer):
    clock = Clock()
    a = Auth(tmp_path, mailer, clock=clock, cloud=True)
    a.setup_code = None
    o = a.register_first("leon@example.com", PW, None, True)
    a.enroll(o["ticket"], now_code(o["secret"], clock.t))
    p = a.register_invite(invite_token(a.invite("leon@example.com", "pei@example.com", "member", "http://x")["link"]), PW, True)
    a.enroll(p["ticket"], now_code(p["secret"], clock.t))
    assert a.login("pei@example.com", PW, True)["step"] == "2fa"
    a.update_user("leon@example.com", "pei@example.com", reset_2fa=True)
    assert a.login("pei@example.com", PW, True)["step"] == "enroll"


# ---------------------------------------------------------------------------------------------- devices

def test_devices_list_and_sign_out(tmp_path, mailer):
    c = make(tmp_path, mailer)
    c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW}, headers={"user-agent": "Laptop"})
    phone = TestClient(c.app)
    phone.post("/api/auth/login", json={"email": "leon@example.com", "password": PW}, headers={"user-agent": "Phone"})
    rows = c.get("/api/auth/sessions").json()["sessions"]
    assert [r["agent"] for r in rows] == ["Laptop", "Phone"] and rows[0]["current"] is True
    out = c.post("/api/auth/sessions/end", json={}).json()
    assert out["ended"] == 1 and len(out["sessions"]) == 1
    assert phone.get("/api/episodes").status_code == 401 and c.get("/api/episodes").status_code == 200


def test_change_password_signs_out_other_devices(tmp_path, mailer):
    c = make(tmp_path, mailer)
    c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    other = TestClient(c.app)
    other.post("/api/auth/login", json={"email": "leon@example.com", "password": PW})
    assert c.post("/api/auth/password", json={"old": "wrong one!!", "new": "another password"}).status_code == 400
    assert c.post("/api/auth/password", json={"old": PW, "new": "another password"}).status_code == 200
    assert c.get("/api/episodes").status_code == 200 and other.get("/api/episodes").status_code == 401


def test_cloud_locks_a_noisy_address(tmp_path, mailer):
    clock = Clock()
    a = Auth(tmp_path, mailer, clock=clock)
    a.register_first("leon@example.com", PW, None, True)
    for i in range(30):
        with pytest.raises(AuthError):
            a.login(f"x{i}@example.com", "nope nope nope", True, ip="1.2.3.4")
    with pytest.raises(AuthError) as e:
        a.login("leon@example.com", PW, True, ip="1.2.3.4")
    assert e.value.status == 429
    assert a.login("leon@example.com", PW, True, ip="5.6.7.8")["step"] == "done"
