"""The server answers in the interface language: lacuna_lang=en cookie → English errors, labels,
history and AI instructions; no cookie → Chinese as before. Stored data stays as it was written."""
import re
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app, i18n
from lacuna_app.dictation import Dictation
from lacuna_app.editor import ChatContext, ClaudeEditorAdapter, MockEditorAdapter
from lacuna_app.episode import history_label
from lacuna_app.first_cut import window_request

from .synth import EPISODE, make_workspace

HAN = re.compile(r"[\u3400-\u9fff]")
EP = f"/api/episodes/{EPISODE}"


@pytest.fixture(autouse=True)
def chinese_afterwards():
    yield
    tok = i18n.set_request_lang("zh")      # the requests above left "en" as the jobs' language
    i18n.reset_request_lang(tok)


@contextmanager
def speaking(value):
    tok = i18n.set_request_lang(value)
    try:
        yield
    finally:
        i18n.reset_request_lang(tok)


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(make_workspace(tmp_path / "ws"), MockEditorAdapter(), web_dist=Path("/nonexistent")))


def test_english_cookie_gives_english_text(client):
    client.cookies.set("lacuna_lang", "en")
    r = client.post(f"{EP}/undo", json={})
    assert r.status_code == 409 and r.json()["detail"] == "Nothing to undo"
    s = client.get(EP).json()
    labels = {e["category_label"] for e in s["edits"]}
    assert labels and not any(HAN.search(x) for x in labels), labels
    s = client.post(f"{EP}/edits/e003/review", json={"action": "restore", "playhead": 30.0}).json()
    assert s["undo_label"].startswith("Restore: ")
    reply = client.post(f"{EP}/chat", json={"text": "hello", "playhead": 10.0}).json()["reply"]
    assert reply.startswith("I'm the demo rule engine")


def test_chinese_by_default_and_history_is_stored_in_chinese(client):
    assert client.post(f"{EP}/undo", json={}).json()["detail"] == "没有可以撤销的操作"
    client.cookies.set("lacuna_lang", "en")
    client.post(f"{EP}/edits/e003/review", json={"action": "restore", "playhead": 30.0})
    client.cookies.set("lacuna_lang", "zh")
    s = client.get(EP).json()
    assert s["undo_label"].startswith("恢复：")          # learning.py reads the stored labels


def test_history_labels_shown_in_the_interface_language():
    with speaking("en"):
        assert history_label("全部通过（3 处）") == "Approve all (3 edits)"
        assert history_label("全部通过（1 处）") == "Approve all (1 edit)"
        assert history_label("恢复：停顿 1.5s → 0.4s") == "Restore: 停顿 1.5s → 0.4s"
        assert history_label("手动收紧") == "手动收紧"
    with speaking("zh"):
        assert history_label("全部通过（3 处）") == "全部通过（3 处）"


def test_ai_writes_meta_text_in_the_interface_language():
    ctx = ChatContext(instruction="x", playhead=0.0, duration=600.0, pauses=[], sentence=None)
    with speaking("en"):
        req = ClaudeEditorAdapter(client=object()).build_request(ctx)
        assert "Reply in English." in req["system"][0]["text"] and "Simplified Chinese" not in str(req["tools"])
        assert "in English" in window_request(0, 600, 0, 3)
        assert Dictation.language() == "auto"
    with speaking("zh"):
        req = ClaudeEditorAdapter(client=object()).build_request(ctx)
        assert "Reply in Simplified Chinese." in req["system"][0]["text"]
        assert "English" not in window_request(0, 600, 0, 3)
        assert Dictation.language() == "zh"
