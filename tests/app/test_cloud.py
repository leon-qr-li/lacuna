"""Cloud mode (lacuna_app/cloud.py): Cloudflare Access token check, desktop-only actions, invite list."""
from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lacuna_app import cloud, create_app, totp
from lacuna_app.cloud import AccessVerifier, CloudConfigError
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.legal import VERSION
from tests.app.e2e.auth import FakeMailer

TEAM, AUD = "lacunastudio.cloudflareaccess.com", "aud-tag-123"
PW = "correct horse battery"


@pytest.fixture(scope="module")
def keys():
    good, bad = (rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(good.public_key()))
    return good, bad, {"keys": [jwk | {"kid": "k1", "alg": "RS256"}]}


def token(key, kid="k1", aud=AUD, iss=f"https://{TEAM}", exp=300, email="leon@example.com"):
    now = int(time.time())
    return jwt.encode({"aud": [aud], "iss": iss, "iat": now, "exp": now + exp, "email": email}, key,
                      algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def verifier(keys):
    return AccessVerifier(TEAM, AUD, fetch_keys=lambda url: keys[2])


@pytest.fixture
def client(tmp_path, monkeypatch, verifier):
    monkeypatch.setenv("LACUNA_CLOUD", "1")
    app = create_app(tmp_path / "ws", MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer(),
                     access_verifier=verifier)
    return TestClient(app, base_url="https://testserver")     # the cloud session cookie is Secure


def hdr(t):
    return {"Cf-Access-Jwt-Assertion": t}


def test_verifier_accepts_only_our_tokens(keys, verifier):
    good, bad, _ = keys
    assert verifier.verify(token(good))["email"] == "leon@example.com"
    assert verifier.verify(token(bad)) is None                       # someone else's key
    assert verifier.verify(token(good, aud="other-app")) is None     # another Access application
    assert verifier.verify(token(good, iss="https://evil.cloudflareaccess.com")) is None
    assert verifier.verify(token(good, exp=-120)) is None            # expired
    assert verifier.verify(token(good, kid="nope")) is None
    assert verifier.verify("not-a-jwt") is None
    unsigned = jwt.encode({"aud": AUD, "iss": f"https://{TEAM}", "iat": 1, "exp": 2**31}, None, algorithm="none")
    assert verifier.verify(unsigned) is None


def test_cloud_mode_fails_closed_without_access_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LACUNA_CLOUD", "1")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    with pytest.raises(CloudConfigError):
        create_app(tmp_path / "ws", MockEditorAdapter(), web_dist=tmp_path / "none")


def test_every_request_needs_an_access_token(client, keys):
    good, bad, _ = keys
    for path in ("/", "/api/health", "/api/app", "/api/episodes", "/api/auth/status"):
        assert client.get(path).status_code == 403, path
        assert client.get(path, headers=hdr(token(bad))).status_code == 403, path
    assert client.get("/api/auth/status", headers=hdr(token(good))).status_code == 200


def test_before_sign_in_app_info_is_version_only(client, keys):
    h = hdr(token(keys[0]))
    # the first account in the cloud: setup code from the server, then two-step (docs/decisions/2026-10-19-invites-roles-2fa.md)
    setup = (client.app.state.workspace.root / "auth" / "setup-code.txt").read_text().strip()
    r = client.post("/api/auth/register", json={"email": "leon@example.com", "password": PW, "agree": VERSION, "setup_code": setup},
                    headers=h)
    assert r.status_code == 200 and r.json()["step"] == "enroll"
    code = totp.code_at(r.json()["secret"], int(time.time() // totp.STEP))
    assert client.post("/api/auth/2fa/enroll", json={"ticket": r.json()["ticket"], "code": code}, headers=h).status_code == 200
    signed_in = client.get("/api/app", headers=h).json()
    assert "workspace" in signed_in and "busy" in signed_in and signed_in["cloud"] is True
    stranger = TestClient(client.app, base_url="https://testserver")
    for path in ("/api/app", "/api/health"):
        info = stranger.get(path, headers=h).json()
        assert set(info) == {"ok", "version", "cloud"}, path


def test_no_path_is_open_without_a_token_any_more(client, keys):
    """the public /api/version of 2026-10-20 is withdrawn (decision 2026-10-25-withdraw-public-version): the deploy
    check reads /api/health through Access with a service token, and gets the version only"""
    for method, path in (("GET", "/api/version"), ("GET", "/api/health"), ("GET", "/api/app")):
        assert client.request(method, path).status_code == 403, (method, path)
    info = client.get("/api/health", headers=hdr(token(keys[0]))).json()
    assert set(info) == {"ok", "version", "cloud"}


def owner_signed_in(client, keys, monkeypatch) -> dict:
    """The owner's account, signed in (a cloud server answers nothing but the sign-up screen before)."""
    monkeypatch.setenv("LACUNA_OWNER_EMAIL", "leon@example.com")
    h = hdr(token(keys[0]))
    out = client.post("/api/auth/register", json={"email": "leon@example.com", "password": PW, "agree": VERSION}, headers=h).json()
    code = totp.code_at(out["secret"], int(time.time() // totp.STEP))
    assert client.post("/api/auth/2fa/enroll", json={"ticket": out["ticket"], "code": code}, headers=h).status_code == 200
    return h


def test_a_fresh_cloud_server_answers_only_the_sign_up_screen(client, keys):
    h = hdr(token(keys[0]))
    assert client.get("/api/auth/status", headers=h).status_code == 200
    assert client.get("/api/episodes", headers=h).status_code == 401


def test_desktop_only_actions_are_gone(client, keys, monkeypatch):
    h = owner_signed_in(client, keys, monkeypatch)
    for path in ("/api/app/update/check", "/api/app/update/prepare", "/api/app/update/apply", "/api/app/api-key",
                 "/api/auth/resend-key", "/api/episodes/EP001/exports/open", "/api/library/open"):
        assert client.post(path, json={"key": "sk-x"}, headers=h).status_code == 404, path


def test_import_reads_only_uploaded_tracks(client, keys, tmp_path, monkeypatch):
    h = owner_signed_in(client, keys, monkeypatch)
    outside = tmp_path / "secret.wav"
    outside.write_bytes(b"RIFF")
    r = client.post("/api/imports", json={"id": "EP009", "tracks": [str(outside), str(outside)]}, headers=h)
    assert r.status_code == 422


def test_desktop_mode_is_untouched(tmp_path, monkeypatch):
    monkeypatch.delenv("LACUNA_CLOUD", raising=False)
    c = TestClient(create_app(tmp_path / "ws", MockEditorAdapter(), web_dist=tmp_path / "none"))
    assert c.get("/api/health").status_code == 200
    info = c.get("/api/app").json()
    assert "workspace" in info and info["cloud"] is False


class FakeCF:
    def __init__(self, emails):
        self.group = {"name": "LACUNA invited", "include": [{"email": {"email": e}} for e in emails]}
        self.calls = []

    def __call__(self, method, path, token, body=None):
        self.calls.append((method, path))
        if method == "PUT":
            self.group = body
        return self.group

    def emails(self):
        return [r["email"]["email"] for r in self.group["include"]]


def test_access_invite_list(monkeypatch):
    fake = FakeCF(["leon@example.com"])
    assert cloud._edit_group("pei@example.com", True, cf=fake) is False        # not in the cloud: no-op
    assert fake.calls == []
    monkeypatch.setenv("LACUNA_CLOUD", "1")
    for k, v in {"CF_ACCESS_API_TOKEN": "t", "CF_ACCOUNT_ID": "a", "CF_ACCESS_GROUP_ID": "g"}.items():
        monkeypatch.setenv(k, v)
    assert cloud._edit_group("Pei@Example.com", True, cf=fake)
    assert cloud._edit_group("pei@example.com", True, cf=fake)                 # no duplicate
    assert fake.emails() == ["leon@example.com", "pei@example.com"]
    assert cloud._edit_group("pei@example.com", False, cf=fake)
    assert fake.emails() == ["leon@example.com"]
    assert cloud._edit_group("leon@example.com", False, cf=fake) is False      # never empty the list
    assert fake.emails() == ["leon@example.com"]


def test_host_flag_needs_cloud_mode(monkeypatch, tmp_path):
    from lacuna_app.__main__ import main
    monkeypatch.delenv("LACUNA_CLOUD", raising=False)
    with pytest.raises(SystemExit):
        main(["--workspace", str(tmp_path), "--host", "0.0.0.0", "--no-browser"])


def test_access_email_reaches_the_app(verifier, keys, monkeypatch):
    monkeypatch.setenv("LACUNA_CLOUD", "1")
    app = FastAPI()

    @app.get("/probe")
    def probe(request: Request):
        return {"email": cloud.access_email(request)}

    cloud.install(app, signed_in=lambda c: False, version=lambda: "v", verifier=verifier)
    r = TestClient(app).get("/probe", headers=hdr(token(keys[0], email="Leon@Example.com")))
    assert r.json() == {"email": "leon@example.com"}
    monkeypatch.setenv("LACUNA_OWNER_EMAIL", " Leon@example.com ")
    assert cloud.owner_email() == "leon@example.com"
    monkeypatch.delenv("LACUNA_CLOUD")
    assert cloud.owner_email() is None


def test_owner_signs_up_first_without_setup_code(client, keys, monkeypatch):
    """No shell on the server to read setup-code.txt: Access proved the owner's email (LACUNA_OWNER_EMAIL)."""
    monkeypatch.setenv("LACUNA_OWNER_EMAIL", "leon@example.com")
    leon, other = hdr(token(keys[0])), hdr(token(keys[0], email="pei@example.com"))
    st = client.get("/api/auth/status", headers=leon).json()
    assert st["setup_code"] is False and st["owner_email"] == "leon@example.com"
    assert client.get("/api/auth/status", headers=other).json()["setup_code"] is True
    # someone else through Access, or the owner's Access email with another account email: code still needed
    for h, email in ((other, "pei@example.com"), (other, "leon@example.com"), (leon, "pei@example.com")):
        r = client.post("/api/auth/register", json={"email": email, "password": PW, "agree": VERSION}, headers=h)
        assert r.status_code == 403, (h, email)
    r = client.post("/api/auth/register", json={"email": "Leon@example.com", "password": PW, "agree": VERSION}, headers=leon)
    assert r.status_code == 200 and r.json()["step"] == "enroll"           # two-step sign-in still required
    assert client.get("/api/auth/status", headers=leon).json()["email"] is None
    assert not (client.app.state.workspace.root / "auth" / "setup-code.txt").exists()
