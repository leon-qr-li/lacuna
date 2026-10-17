"""Long-term asks from the chat: saved chat log, "记住：……", after-export summary -> candidate rules."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lacuna_app.chat_learning import ChatAsks, ChatLearner, ClaudeAskSummarizer, remember_text
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.episode import Episode
from lacuna_app.learning import Learning, prompt_rules
from lacuna_app.server import create_app
from lacuna_app.store import CHAT_FILE, Workspace

from .synth import AI_EPISODE, EPISODE, make_ai_workspace, make_workspace

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture
def ai_ws(tmp_path):
    return make_ai_workspace(tmp_path / "ws")


def client_for(root, **services):
    return TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"), **services))


class FakeSummarizer:
    available = True

    def __init__(self, answer=None, boom=False):
        self.answer, self.boom, self.calls = answer or [], boom, []

    def summarize(self, turns, existing):
        self.calls.append(([t["said"] for t in turns], [a["id"] for a in existing]))
        if self.boom:
            raise RuntimeError("network down")
        return self.answer, {"model": "fake", "cost_usd": 0.01}


def episode(root, eid=AI_EPISODE):
    return Episode(Workspace(root), eid)


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


def test_remember_in_chat_makes_candidate_rule_without_ai(ai_ws):
    class NoAI(MockEditorAdapter):
        def propose(self, ctx):
            raise AssertionError("记住 must not call the AI")

    c = TestClient(create_app(ai_ws, NoAI(), web_dist=Path("/nonexistent")))
    r = c.post(f"/api/episodes/{AI_EPISODE}/chat", json={"text": "记住：Pei 的嗯都别删", "playhead": 12.0}).json()
    assert r["proposal"] is None and "Pei 的嗯都别删" in r["reply"] and "学到的规则" in r["reply"]
    ov = c.get("/api/learning").json()
    rule = next(x for x in ov["rules"] if x["kind"] == "ask")
    assert rule["title"] == "Pei 的嗯都别删" and rule["state"] == "candidate" and ov["pending"] >= 1
    assert rule["examples"][0]["text"] == "记住：Pei 的嗯都别删" and rule["examples"][0]["episode"] == AI_EPISODE
    assert prompt_rules(ai_ws) == ""                         # nothing changes before Leon adopts it
    c.post("/api/learning/rules", json={"id": rule["id"], "action": "approve"})
    assert "Pei 的嗯都别删" in prompt_rules(ai_ws)          # ... then the next first cut is told
    # the same ask said twice is one rule
    c.post(f"/api/episodes/{AI_EPISODE}/chat", json={"text": "记住： Pei 的嗯都别删。", "playhead": 30.0})
    assert sum(x["kind"] == "ask" for x in c.get("/api/learning").json()["rules"]) == 1


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


# ---------------------------------------------------------------- after export: summary -> rules

def say(ep, *texts):
    for i, t in enumerate(texts):
        ep.log_turn(t, 10.0 * i, "好的")


def test_summary_becomes_rules_with_his_words(ai_ws):
    ep = episode(ai_ws)
    say(ep, "删掉这句", "Pei 的嗯别删", "这里的嗯也留着，Pei 的嗯以后都别删")
    fake = FakeSummarizer([{"title": "Pei 的语气词「嗯」不要删", "instruction": "Keep Pei's 嗯 fillers.",
                            "turns": [2, 3], "same_as": ""},
                           {"title": "无出处", "instruction": "x", "turns": [99], "same_as": ""}])
    learner = ChatLearner(Workspace(ai_ws), lambda: fake)
    new = learner.summarize(ep)
    assert len(new) == 1 and learner.last[AI_EPISODE] == {"state": "done", "new": 1}
    rules = [r for r in Learning(Workspace(ai_ws)).overview()["rules"] if r["kind"] == "ask"]
    assert len(rules) == 1                                    # an ask that cites no turn is dropped
    r = rules[0]
    assert r["title"] == "Pei 的语气词「嗯」不要删" and "Keep Pei's" in r["prompt"]
    assert [x["text"] for x in r["examples"]] == ["Pei 的嗯别删", "这里的嗯也留着，Pei 的嗯以后都别删"]
    assert r["examples"][0]["reason"] == "0:10"               # where in the episode he said it
    # a later export only sends what was said since
    say(ep, "开头那段太长")
    learner.summarize(ep)
    assert fake.calls[-1][0] == ["开头那段太长"]
    learner.summarize(ep)                                     # nothing new -> no call
    assert len(fake.calls) == 2 and learner.last[AI_EPISODE]["state"] == "nothing"


def test_same_ask_in_a_later_episode_adds_up(ai_ws):
    ws = Workspace(ai_ws)
    ep = episode(ai_ws)
    say(ep, "Pei 的嗯别删")
    ChatLearner(ws, lambda: FakeSummarizer([{"title": "Pei 的嗯别删", "instruction": "Keep Pei's 嗯.",
                                             "turns": [1], "same_as": ""}])).summarize(ep)
    aid = ChatAsks(ws).all()[0]["id"]
    other = ai_ws / "episodes" / "EP002"
    shutil.copytree(ai_ws / "episodes" / AI_EPISODE, other)
    (other / CHAT_FILE).unlink()
    ep2 = episode(ai_ws, "EP002")
    say(ep2, "嗯还是别删")
    fake = FakeSummarizer([{"title": "Pei 的「嗯」保留", "instruction": "Keep Pei's 嗯 (again).",
                            "turns": [1], "same_as": aid}])
    ChatLearner(ws, lambda: fake).summarize(ep2)
    assert fake.calls[0][1] == [aid]                          # it was shown what is already known
    rules = [r for r in Learning(ws).overview()["rules"] if r["kind"] == "ask"]
    assert len(rules) == 1 and rules[0]["evidence"]["said"] == 2
    assert sorted(rules[0]["evidence"]["episodes"]) == sorted([AI_EPISODE, "EP002"]) and rules[0]["title"] == "Pei 的「嗯」保留"


def test_summary_is_skipped_safely(ai_ws, tmp_path):
    ws = Workspace(ai_ws)
    ep = episode(ai_ws)
    say(ep, "Pei 的嗯别删")
    off = SimpleNamespace(available=False)
    learner = ChatLearner(ws, lambda: off)
    assert learner.summarize(ep) == [] and learner.last[AI_EPISODE]["state"] == "no_key"
    boom = ChatLearner(ws, lambda: FakeSummarizer(boom=True))
    assert boom.summarize(ep) == [] and boom.last[AI_EPISODE]["state"] == "error"
    fake = FakeSummarizer([])
    ChatLearner(ws, lambda: fake).summarize(ep)               # turns were still pending after both
    assert fake.calls[0][0] == ["Pei 的嗯别删"]
    # remember turns are already rules; demo episodes are not Leon's taste
    ep.log_turn("记住：x", 1.0, "记下了", remember=True)
    calls = len(fake.calls)
    ChatLearner(ws, lambda: fake).summarize(ep)
    assert len(fake.calls) == calls
    demo_root = make_workspace(tmp_path / "demo")
    demo = Episode(Workspace(demo_root), EPISODE)
    say(demo, "Pei 的嗯别删")
    ChatLearner(Workspace(demo_root), lambda: fake).summarize(demo)
    assert len(fake.calls) == calls


def test_claude_summarizer_request_and_answer():
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(model=kw["model"], stop_reason="tool_use", content=[SimpleNamespace(
            type="tool_use", name="submit_long_term_asks",
            input={"asks": [{"title": "t", "instruction": "i", "turns": [1], "same_as": ""}]})],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=100))

    s = ClaudeAskSummarizer(client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    found, usage = s.summarize([{"said": "Pei 的嗯别删", "reply": "好", "proposal": "p1", "state": "approved"}],
                               [{"id": "abc", "title": "旧的"}])
    assert found[0]["title"] == "t" and usage["cost_usd"] < 0.05
    body = json.loads(seen["messages"][0]["content"])
    assert body["chat"][0] == {"turn": 1, "leon_said": "Pei 的嗯别删", "producer_replied": "好",
                               "outcome": "change approved"}
    assert body["existing_preferences"] == [{"id": "abc", "title": "旧的"}]
    assert seen["tool_choice"]["name"] == "submit_long_term_asks" and "sonnet" in seen["model"]


@needs_ffmpeg
def test_export_runs_chat_learning_after_it_finishes(tmp_path):
    root = make_workspace(tmp_path / "ws")
    done = []
    learner = SimpleNamespace(after_export=lambda ep: done.append(ep.id), asks=ChatAsks(Workspace(root)))
    c = client_for(root, chat_learner=learner)
    EP = f"/api/episodes/{EPISODE}"
    c.post(f"{EP}/export", json={"formats": ["wav"]})
    t = time.time()
    while c.get(f"{EP}/export").json()["job"]["state"] == "running" and time.time() - t < 60:
        time.sleep(0.05)
    assert c.get(f"{EP}/export").json()["job"]["state"] == "done" and done == [EPISODE]


def test_failing_after_export_hook_does_not_fail_export(tmp_path):
    from lacuna_app.exporter import Exporter
    root = make_workspace(tmp_path / "ws")
    ex = Exporter(Workspace(root))
    ex.on_done.append(lambda ep: 1 / 0)
    job = ex.start(Episode(Workspace(root), EPISODE), ["wav"], wait=True)
    assert ex.status(EPISODE)["state"] == "done" and job["id"]
