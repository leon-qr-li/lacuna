"""Long-term asks from the chat: saved chat log, the 「记住：」 prefix, the store of confirmed asks.
How asks get confirmed (drafts, 本集学到的规则) is tested in test_lessons.py."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app.chat_learning import ChatAsks, remember_text
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.episode import Episode
from lacuna_app.learning import Learning
from lacuna_app.server import create_app
from lacuna_app.store import CHAT_FILE, Workspace

from .synth import AI_EPISODE, EPISODE, make_ai_workspace, make_workspace

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture
def ai_ws(tmp_path):
    return make_ai_workspace(tmp_path / "ws")


def client_for(root, **services):
    return TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"), **services))


# ---------------------------------------------------------------- "记住：……"

@pytest.mark.parametrize("text,ask", [
    ("记住：Pei 的嗯都别删", "Pei 的嗯都别删"),
    ("记住 以后片头别剪", "以后片头别剪"),
    ("帮我记住，我跑题的地方剪狠点", "我跑题的地方剪狠点"),
    ("Remember: keep Pei's laughs", "keep Pei's laughs"),
    ("删掉这句", None),
    ("记住：", None),
    ("你记住了吗", None),
])
def test_remember_text(text, ask):
    assert remember_text(text) == ask


# ---------------------------------------------------------------- the chat log is kept with the episode

def test_chat_log_survives_restart_with_outcome(tmp_path):
    root = make_workspace(tmp_path / "ws")
    c = client_for(root)
    EP = f"/api/episodes/{EPISODE}"
    p = c.post(f"{EP}/chat", json={"text": "这里停顿短一点", "playhead": 15.5}).json()["proposal"]
    c.post(f"{EP}/proposals/{p['id']}/approve", json={})
    c.post(f"{EP}/chat", json={"text": "这段加点音乐", "playhead": 10})
    doc = json.loads((root / "episodes" / EPISODE / CHAT_FILE).read_text(encoding="utf-8"))
    assert [t["said"] for t in doc["turns"]] == ["这里停顿短一点", "这段加点音乐"]
    assert doc["turns"][0]["state"] == "approved" and doc["turns"][0]["time"]
    again = Episode(Workspace(root), EPISODE)               # a restart reads it back
    assert [t["said"] for t in again.chat_log()] == ["这里停顿短一点", "这段加点音乐"]
    assert again.chat_history()[0]["outcome"] == "proposed and approved"


def test_broken_chat_log_does_not_stop_the_episode(tmp_path):
    root = make_workspace(tmp_path / "ws")
    (root / "episodes" / EPISODE / CHAT_FILE).write_text("{not json", encoding="utf-8")
    assert Episode(Workspace(root), EPISODE).chat_log() == []


# ---------------------------------------------------------------- confirmed asks are stored here

def test_put_replaces_wording_and_quotes_add_up(ai_ws):
    ws = Workspace(ai_ws)
    asks = ChatAsks(ws)
    asks.put(AI_EPISODE, {"id": "a1", "title": "Pei 的嗯别删", "instruction": "Keep Pei's 嗯.", "source": "remember",
                          "quotes": [{"said": "记住：Pei 的嗯都别删", "at": 12.0}]})
    asks.put("EP002", {"id": "a1", "title": "Pei 的「嗯」保留", "instruction": "Keep Pei's 嗯 (again).",
                       "source": "lesson", "quotes": [{"said": "嗯还是别删", "at": 70.0}]})
    rule = next(r for r in Learning(ws).overview()["rules"] if r["kind"] == "ask")
    assert rule["id"] == "ask:a1" and rule["title"] == "Pei 的「嗯」保留"      # the latest wording wins
    assert rule["evidence"]["said"] == 2 and rule["examples"][1]["reason"] == "1:10"
    assert "记住" in rule["detail"] or "remember" in rule["detail"]


def test_old_summary_asks_still_show(ai_ws):
    d = ai_ws / "learning" / "asks"
    d.mkdir(parents=True)
    (d / f"{AI_EPISODE}.json").write_text(json.dumps({"episode": AI_EPISODE, "asks": [
        {"id": "s1", "title": "开头别剪", "instruction": "Keep intros.", "source": "summary", "at": "2026-10-17",
         "quotes": [{"said": "开头别剪", "at": 3.0}]}]}, ensure_ascii=False), encoding="utf-8")
    rule = next(r for r in Learning(Workspace(ai_ws)).overview()["rules"] if r["kind"] == "ask")
    assert rule["title"] == "开头别剪" and rule["state"] == "candidate"


# ---------------------------------------------------------------- export no longer learns silently

@needs_ffmpeg
def test_export_does_not_summarise_the_chat(tmp_path):
    root = make_workspace(tmp_path / "ws")
    from tests.app.fake_lessons import FakeRuleWriter
    writer = FakeRuleWriter()
    c = client_for(root, rule_writer=writer)
    EP = f"/api/episodes/{EPISODE}"
    c.post(f"{EP}/chat", json={"text": "以后 Pei 的嗯都别删", "playhead": 3})
    c.post(f"{EP}/export", json={"formats": ["wav"]})
    t = time.time()
    while c.get(f"{EP}/export").json()["job"]["state"] == "running" and time.time() - t < 60:
        time.sleep(0.05)
    assert c.get(f"{EP}/export").json()["job"]["state"] == "done"
    time.sleep(0.3)
    assert writer.calls == [] and not (root / "learning" / "asks").exists()


def test_failing_after_export_hook_does_not_fail_export(tmp_path):
    from lacuna_app.exporter import Exporter
    root = make_workspace(tmp_path / "ws")
    ex = Exporter(Workspace(root))
    ex.on_done.append(lambda ep: 1 / 0)
    job = ex.start(Episode(Workspace(root), EPISODE), ["wav"], wait=True)
    assert ex.status(EPISODE)["state"] == "done" and job["id"]
