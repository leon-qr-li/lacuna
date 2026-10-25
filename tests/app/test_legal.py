"""用户条款和隐私政策 (lacuna_app/legal.py, routes/legal.py, decision 2026-10-25-terms-and-privacy): agreeing at
sign-up, the 「条款已更新」 agree call, and the documents themselves (web/src/features/legal/docs)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app, legal
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.legal import VERSION
from tests.app.e2e.auth import FakeMailer

PW = "correct horse battery"
DOCS = Path(__file__).resolve().parents[2] / "web" / "src" / "features" / "legal" / "docs"
TBD = re.compile(r"【待定：[^】]*】|\[TBD:[^\]]*\]")


def make(tmp_path, cloud=False):
    return TestClient(create_app(tmp_path / "ws", MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer(),
                                 auth_cloud=cloud), base_url="https://testserver" if cloud else "http://testserver")


def stored(c, email):
    return c.app.state.ctx.provide("auth").users[email]


def test_in_the_cloud_an_account_needs_the_box_ticked(tmp_path):
    c = make(tmp_path, cloud=True)
    setup = (tmp_path / "ws" / "auth" / "setup-code.txt").read_text().strip()
    body = {"email": "leon@example.com", "password": PW, "setup_code": setup}
    r = c.post("/api/auth/register", json=body)
    assert r.status_code == 400 and "条款" in r.json()["detail"]
    assert c.post("/api/auth/register", json=body | {"agree": "2020-01-01"}).status_code == 400   # an old version
    assert c.app.state.ctx.provide("auth").users == {}
    assert c.post("/api/auth/register", json=body | {"agree": VERSION}).json()["step"] == "enroll"
    terms = stored(c, "leon@example.com")["terms"]
    assert terms["v"] == VERSION and terms["at"] > 0


def test_status_says_which_version_is_current_and_which_was_agreed(tmp_path):
    c = make(tmp_path)
    assert c.get("/api/auth/status").json()["legal"] == {"version": VERSION, "agreed": None}   # signed out
    c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW, "agree": VERSION})
    assert c.get("/api/auth/status").json()["legal"] == {"version": VERSION, "agreed": VERSION}


def test_an_invite_sign_up_records_the_agreement(tmp_path):
    c = make(tmp_path)
    c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})     # on a checkout: optional
    assert "terms" not in stored(c, "leon@example.com")
    link = c.post("/api/auth/invites", json={"email": "pei@example.com"}).json()["link"]
    pei = TestClient(c.app)
    assert pei.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW,
                                                "agree": VERSION}).status_code == 200
    assert legal.agreed(stored(c, "pei@example.com")) == VERSION


def test_agreeing_later_to_the_current_version(tmp_path):
    c = make(tmp_path)
    assert c.post("/api/auth/agree", json={"version": VERSION}).status_code == 401
    c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    assert c.get("/api/auth/status").json()["legal"]["agreed"] is None       # the screen shows (in the cloud)
    r = c.post("/api/auth/agree", json={"version": "2020-01-01"})
    assert r.status_code == 409                                              # the page was older than the server
    assert c.post("/api/auth/agree", json={"version": VERSION}).json() == {"ok": True, "agreed": VERSION}
    assert c.get("/api/auth/status").json()["legal"]["agreed"] == VERSION
    # kept across a restart (the site database)
    again = TestClient(create_app(tmp_path / "ws", MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer()))
    assert legal.agreed(again.app.state.ctx.provide("auth").users["leon@example.com"]) == VERSION


@pytest.mark.parametrize("doc", ["terms", "privacy"])
def test_both_languages_carry_the_current_version_and_the_same_sections(doc):
    zh, en = ((DOCS / f"{doc}.{lang}.md").read_text(encoding="utf-8") for lang in ("zh", "en"))
    for text in (zh, en):
        assert f"{VERSION}" in text.splitlines()[2], "the version line names lacuna_app/legal.py VERSION"
        assert not re.search(r"claude|anthropic", text, re.I), "users never see the AI vendor"
    heads = [len(re.findall(r"^## ", t, re.M)) for t in (zh, en)]
    assert heads[0] == heads[1] > 5
    assert len(TBD.findall(zh)) == len(TBD.findall(en)) > 0, "every placeholder is in both languages"


def test_what_the_documents_must_say():
    terms_zh, terms_en = (DOCS / "terms.zh.md").read_text(encoding="utf-8"), (DOCS / "terms.en.md").read_text(encoding="utf-8")
    privacy_zh, privacy_en = (DOCS / "privacy.zh.md").read_text(encoding="utf-8"), (DOCS / "privacy.en.md").read_text(encoding="utf-8")
    assert "请只上传你有权使用的音乐" in terms_zh and "only upload music you have the right to use" in terms_en
    assert "DMCA" in terms_zh and "DMCA" in terms_en and "designated agent" in terms_en
    for text in (privacy_zh, privacy_en):
        assert "60" in text and "13" in text      # deleted shows/accounts erased in 60 days; usage records 13 months
    assert "从不发给任何 AI 服务" in privacy_zh and "never sent to any AI service" in privacy_en
    assert "美国" in privacy_zh and "United States" in privacy_en
