"""自定义快捷键 (routes/shortcuts.py): kept per person, follows them to another browser, bad entries dropped."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import make_workspace

PW = "correct horse battery"


def setup(tmp_path, accounts=True):
    ws = make_workspace(tmp_path / "ws")
    c = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer(), mail_inline=True))
    if accounts:
        c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW, "name": "Leon"})
    return c


def test_defaults_are_empty_and_changes_are_kept(tmp_path):
    c = setup(tmp_path)
    assert c.get("/api/shortcuts").json() == {"keys": {}}
    got = c.put("/api/shortcuts", json={"keys": {"gap": ["Shift+G"], "cut": ["Mod+X", "Delete"], "speed": []}}).json()
    assert got["keys"] == {"gap": ["Shift+G"], "cut": ["Mod+X", "Delete"], "speed": []}
    other = TestClient(c.app)  # another browser, same person
    other.post("/api/auth/login", json={"email": "leon@example.com", "password": PW})
    assert other.get("/api/shortcuts").json()["keys"]["gap"] == ["Shift+G"]


def test_each_person_has_their_own(tmp_path):
    leon = setup(tmp_path)
    leon.put("/api/shortcuts", json={"keys": {"gap": ["H"]}})
    link = leon.post("/api/auth/invites", json={"email": "pei@example.com", "plan": "basic"}).json()["link"]
    pei = TestClient(leon.app)
    pei.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW, "name": "Pei"})
    assert pei.get("/api/shortcuts").json() == {"keys": {}}
    assert TestClient(leon.app).get("/api/shortcuts").status_code == 401  # not signed in


def test_bad_entries_are_dropped(tmp_path):
    c = setup(tmp_path)
    got = c.put("/api/shortcuts", json={"keys": {
        "keep": ["K", "K", "Y", "R"],            # repeats dropped, at most 2
        "Bad Name": ["G"],                       # not an action id
        "prev": ["<script>", "Ctrl+Mod+X", "ArrowLeft"],  # not keys
        "help": ["?"],
    }}).json()["keys"]
    assert got == {"keep": ["K", "Y"], "prev": ["ArrowLeft"], "help": ["?"]}


def test_without_accounts_they_live_in_the_workspace(tmp_path):
    c = setup(tmp_path, accounts=False)
    c.put("/api/shortcuts", json={"keys": {"gap": ["Shift+G"]}})
    assert c.get("/api/shortcuts").json()["keys"] == {"gap": ["Shift+G"]}
    assert (tmp_path / "ws" / "shortcuts.json").is_file()
