"""Leon's stutter rules, added directly once in the cloud (Leon 2026-10-20): in force on 学到的规则,
in the next first cut's prompt, older rules untouched, never on the desktop app, runs once."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import lacuna_app.routes.stutter_rule_once as route
from lacuna_app import i18n, stutter_rule_once
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.learning import prompt_rules
from lacuna_app.server import create_app
from lacuna_app.store import Workspace

from .synth import make_workspace

OLD = {"id": "0fe50f00e0", "title": "Leon 连着重复的字或词（口吃，比如「我我」「这个这个」）剪成一个。",
       "instruction": "Leon's stutters must be cut down to one; about 5% may stay.", "source": "remember",
       "quotes": [{"said": "记住：口吃剪成一个", "at": 12.0}], "at": "2026-10-17T22:00:00+00:00"}


def client(root: Path) -> TestClient:
    return TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent")))


@pytest.fixture
def ws(tmp_path) -> Path:
    root = make_workspace(tmp_path / "ws")
    # an older stutter rule Leon adopted
    (root / "learning" / "asks").mkdir(parents=True)
    (root / "learning" / "asks" / "PULSE-013.json").write_text(json.dumps(
        {"schema": 1, "episode": "PULSE-013", "summarized": 0, "asks": [OLD]}, ensure_ascii=False), encoding="utf-8")
    (root / "learning" / "rules.json").write_text(json.dumps(
        {"schema": 1, "rules": {"ask:0fe50f00e0": {"state": "approved", "at": "x", "approved": {
            "at": "x", "digest": "old", "rule": {"id": "ask:0fe50f00e0", "kind": "ask", "title": OLD["title"],
                                                 "detail": "", "prompt": "Leon's standing request: " + OLD["instruction"],
                                                 "key": {"ask": "0fe50f00e0"}, "evidence": {}, "examples": [],
                                                 "policy": None}}}}}, ensure_ascii=False), encoding="utf-8")
    return root


def test_rules_in_force_once_and_old_ones_kept(ws, monkeypatch):
    monkeypatch.setattr(route, "cloud", SimpleNamespace(enabled=lambda: True))
    c = client(ws)
    rules = {r["id"]: r for r in c.get("/api/learning").json()["rules"]}
    for rid in ("ask:stutter-char-20261020", "ask:stutter-clean-cut-20261020"):
        assert rules[rid]["state"] == "approved", rid
        assert "你直接让 LACUNA 加的" in rules[rid]["detail"]
    assert "游游戏" in rules["ask:stutter-char-20261020"]["title"]
    assert rules["ask:0fe50f00e0"]["state"] == "approved"            # word repeats: the older rule stays

    block = prompt_rules(Workspace(ws))
    assert "ALWAYS cut the extra character" in block
    assert "CLEAN CUTS ONLY" in block and "about 5% may stay" in block
    assert stutter_rule_once.done(Workspace(ws))

    # runs once: if Leon later withdraws it on 学到的规则, a restart does not bring it back
    assert c.post("/api/learning/rules", json={"id": "ask:stutter-char-20261020", "action": "reject"}).status_code == 200
    rules = {r["id"]: r for r in client(ws).get("/api/learning").json()["rules"]}
    assert rules["ask:stutter-char-20261020"]["state"] == "rejected"


def test_desktop_app_never_adds(ws, monkeypatch):
    monkeypatch.setattr(route, "cloud", SimpleNamespace(enabled=lambda: False))
    rules = {r["id"] for r in client(ws).get("/api/learning").json()["rules"]}
    assert "ask:stutter-char-20261020" not in rules
    assert not stutter_rule_once.done(Workspace(ws))


@pytest.fixture
def chinese_afterwards():
    yield
    tok = i18n.set_request_lang("zh")      # the English request left "en" as the jobs' language
    i18n.reset_request_lang(tok)


def test_english_detail(ws, monkeypatch, chinese_afterwards):
    monkeypatch.setattr(route, "cloud", SimpleNamespace(enabled=lambda: True))
    c = client(ws)
    c.cookies.set("lacuna_lang", "en")
    r = c.get("/api/learning").json()["rules"]
    detail = next(x["detail"] for x in r if x["id"] == "ask:stutter-char-20261020")
    assert detail.startswith("You had LACUNA add it directly (20")
