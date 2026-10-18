"""Confirmed learning (首次检测 #9, #12): 「记住」 shows LACUNA's reading first and stores a rule only after
Leon confirms; 本集学到的规则 proposes this episode's habits with evidence, each adopted, edited or skipped."""
from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lacuna_app.chat_learning import ChatAsks
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.episode import Episode
from lacuna_app.learning import Learning, prompt_rules
from lacuna_app.lessons import ClaudeRuleWriter
from lacuna_app.server import create_app
from lacuna_app.store import Workspace

from .fake_lessons import FakeRuleWriter
from .synth import AI_EPISODE, EPISODE, make_ai_workspace, make_workspace, seed_learning

EP = f"/api/episodes/{AI_EPISODE}"


class NoAI(MockEditorAdapter):
    def propose(self, ctx):
        raise AssertionError("「记住」 must not go to the editing producer")


@pytest.fixture
def ai_ws(tmp_path):
    return make_ai_workspace(tmp_path / "ws")


def client(root, writer=None, adapter=None):
    return TestClient(create_app(root, adapter or NoAI(), web_dist=Path("/nonexistent"),
                                 rule_writer=writer or FakeRuleWriter()))


def asks(c):
    return [r for r in c.get("/api/learning").json()["rules"] if r["kind"] == "ask"]


# ================================================================ #9 「记住」 asks before it stores

@pytest.mark.parametrize("how", ["prefix", "button"])
def test_remember_is_a_draft_until_confirmed(ai_ws, how):
    c = client(ai_ws)
    if how == "prefix":
        r = c.post(f"{EP}/chat", json={"text": "记住：Pei 的嗯都别删", "playhead": 12.0}).json()
    else:
        r = c.post(f"{EP}/remember", json={"text": "Pei 的嗯都别删", "playhead": 12.0}).json()
    d = r["remember"]
    assert r["proposal"] is None and d["state"] == "pending"
    assert d["title"] == "每一期都照做：Pei 的嗯都别删" and d["title"] != "Pei 的嗯都别删"   # never his raw words
    assert d["understood"].startswith("我理解的是") and not d["fallback"]
    assert asks(c) == [] and prompt_rules(ai_ws) == ""           # nothing stored before he confirms
    turn = Episode(Workspace(ai_ws), AI_EPISODE).chat_log()[-1]
    assert turn["said"] == "记住：Pei 的嗯都别删" and turn["remember"] and turn["reply"] == d["understood"]

    out = c.post(f"{EP}/remember/{d['id']}", json={"action": "confirm"}).json()
    assert out["state"] == "confirmed" and out["rule"].startswith("ask:")
    [rule] = asks(c)
    assert rule["title"] == d["title"] and rule["state"] == "approved"   # he just confirmed it: in force
    assert rule["examples"][0]["text"] == "记住：Pei 的嗯都别删"       # his words stay as the evidence
    assert "In every episode: Pei 的嗯都别删" in prompt_rules(ai_ws)
    # deciding twice changes nothing
    assert c.post(f"{EP}/remember/{d['id']}", json={"action": "drop"}).json()["state"] == "confirmed"


def test_change_it_then_confirm_or_drop(ai_ws):
    w = FakeRuleWriter()
    c = client(ai_ws, w)
    d = c.post(f"{EP}/remember", json={"text": "我跑题的地方剪狠点", "playhead": 5.0}).json()["remember"]
    d2 = c.post(f"{EP}/remember/{d['id']}/revise", json={"text": "只针对 Leon"}).json()
    assert d2["id"] == d["id"] and d2["title"] == f"{d['title']}（只针对 Leon）"
    assert d2["understood"] == "我按你说的改了：只针对 Leon。" and d2["history"][0]["feedback"] == "只针对 Leon"
    sent = w.calls[-1][1]
    assert sent["current"]["title"] == d["title"] and sent["feedback"] == "只针对 Leon"
    assert asks(c) == []
    c.post(f"{EP}/remember/{d['id']}", json={"action": "confirm"})
    assert [r["title"] for r in asks(c)] == [d2["title"]]
    # 不用: nothing stored, the draft stays on file (habits are never deleted, only not adopted)
    e = c.post(f"{EP}/remember", json={"text": "开头别剪", "playhead": 1.0}).json()["remember"]
    assert c.post(f"{EP}/remember/{e['id']}", json={"action": "drop"}).json()["state"] == "dropped"
    assert len(asks(c)) == 1
    doc = json.loads((ai_ws / "learning" / "lessons" / f"{AI_EPISODE}.json").read_text(encoding="utf-8"))
    assert [x["state"] for x in doc["drafts"]] == ["confirmed", "dropped"]
    assert c.post(f"{EP}/remember/{e['id']}/revise", json={"text": "x"}).status_code == 409
    assert c.post(f"{EP}/remember/nope", json={"action": "confirm"}).status_code == 404


def test_same_rule_again_updates_the_existing_one(ai_ws):
    c = client(ai_ws)
    d = c.post(f"{EP}/remember", json={"text": "Pei 的嗯都别删", "playhead": 1.0}).json()["remember"]
    c.post(f"{EP}/remember/{d['id']}", json={"action": "confirm"})
    again = c.post(f"{EP}/remember", json={"text": "每一期都照做：Pei 的嗯", "playhead": 9.0}).json()["remember"]
    assert again["same_as"] and again["same_as_title"] == d["title"]
    c.post(f"{EP}/remember/{again['id']}", json={"action": "confirm"})
    [rule] = asks(c)
    assert rule["evidence"]["said"] == 2 and rule["state"] == "approved" and not rule["updated"]


def test_without_ai_his_words_are_shown_for_confirmation(ai_ws):
    c = client(ai_ws, SimpleNamespace(available=False))
    d = c.post(f"{EP}/remember", json={"text": "Pei 的笑声留着", "playhead": 1.0}).json()["remember"]
    assert d["fallback"] and d["title"] == "Pei 的笑声留着" and asks(c) == []
    d2 = c.post(f"{EP}/remember/{d['id']}/revise", json={"text": "Pei 的笑声都保留"}).json()
    assert d2["title"] == "Pei 的笑声都保留"                      # his correction is the new wording
    c.post(f"{EP}/remember/{d['id']}", json={"action": "confirm"})
    assert [r["title"] for r in asks(c)] == ["Pei 的笑声都保留"]
    # a failing writer falls back the same way, never breaks the chat
    c2 = client(ai_ws, FakeRuleWriter(boom=True))
    assert c2.post(f"{EP}/remember", json={"text": "开头别剪", "playhead": 1.0}).json()["remember"]["fallback"]


def test_rule_writer_request_and_answer():
    seen = []

    def create(**kw):
        seen.append(kw)
        name = kw["tools"][0]["name"]
        out = ({"title": "t", "understood": "u", "instruction": "i", "same_as": ""} if name == "submit_rule"
               else {"lessons": [{"title": "l", "instruction": "i", "why": "w", "relation": "new", "related": "",
                                  "turns": [1], "edits": []}]})
        return SimpleNamespace(model=kw["model"], content=[SimpleNamespace(type="tool_use", name=name, input=out)],
                               usage=SimpleNamespace(input_tokens=900, output_tokens=80))

    w = ClaudeRuleWriter(client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert w.available
    out, usage = w.rewrite({"said": "Pei 的嗯别删", "recent_chat": [], "existing_rules": []})
    assert out["title"] == "t" and usage["cost_usd"] < 0.02
    lessons, _ = w.summarize({"chat": [], "review": [], "existing_rules": []})
    assert lessons[0]["title"] == "l"
    assert [k["tools"][0]["name"] for k in seen] == ["submit_rule", "submit_lessons"]
    # forced tool_choice is refused (400) by the current models: auto + the prompt names the tool (V6)
    assert all(k["tool_choice"] == {"type": "auto"} for k in seen)
    assert "calling the submit_rule tool" in seen[0]["system"]
    assert all("sonnet" in k["model"] and k["tools"][0]["strict"] for k in seen)
    assert "Never store his words as they are" in seen[0]["system"]
    assert json.loads(seen[0]["messages"][0]["content"])["said"] == "Pei 的嗯别删"


# ================================================================ #12 本集学到的规则

def chat(c, *texts):
    for i, t in enumerate(texts):
        c.post(f"{EP}/chat", json={"text": t, "playhead": 5.0 + 10 * i})


def review_something(c):
    eds = c.get(EP).json()["edits"]
    e = next(e for e in eds if e["status"] == "applied")
    c.post(f"{EP}/edits/{e['id']}/review", json={"action": "restore"})
    return e["id"]


def run(c):
    c.post(f"{EP}/lessons/run")
    t = time.time()
    while (v := c.get(f"{EP}/lessons").json())["state"] == "running" and time.time() - t < 10:
        time.sleep(0.02)
    return v


def test_lessons_summarise_the_episode_with_evidence(ai_ws):
    seed_learning(ai_ws)                                  # one learned (non-chat) rule exists already
    w = FakeRuleWriter()
    c = client(ai_ws, w, MockEditorAdapter())
    assert c.get(f"{EP}/lessons").json()["state"] == "none"
    chat(c, "这段跑题了删掉")
    eid = review_something(c)
    v = run(c)
    assert v["state"] == "done" and not v["stale"] and v["pending"] == 3
    sent = w.calls[-1][1]
    assert sent["chat"][0]["leon_said"] == "这段跑题了删掉"
    assert any(r["edit"] == eid and r["verdict"] == "restored" for r in sent["review"])
    assert sent["existing_rules"] and sent["existing_rules"][0]["state"] == "candidate"
    new, edits, reinforce = v["lessons"]
    assert new["relation"] == "new" and new["turns"][0]["said"] == "这段跑题了删掉" and new["why"]
    assert edits["edits"][0]["edit"] == eid
    assert edits["edits"][0]["verdict"] == "restored"             # his single decisions come first
    assert reinforce["relation"] == "reinforce" and reinforce["related_title"]
    assert asks(c) == []                                  # nothing is a rule until adopted
    # more chat afterwards makes it stale; running again keeps decided lessons, replaces open ones
    c.post(f"{EP}/lessons/{new['id']}", json={"action": "skip"})
    chat(c, "停顿再短一点")
    assert c.get(f"{EP}/lessons").json()["stale"]
    v2 = run(c)
    assert not v2["stale"] and [x["state"] for x in v2["lessons"]].count("skipped") == 1
    assert w.calls[-1][1]["already_reviewed"] == [{"title": new["title"], "decision": "skipped"}]
    assert [x["title"] for x in v2["lessons"]].count(new["title"]) == 1    # a decided lesson is not proposed again


def test_adopt_edit_and_chat_about_a_lesson(ai_ws):
    seed_learning(ai_ws)
    c = client(ai_ws, FakeRuleWriter(), MockEditorAdapter())
    chat(c, "这段跑题了删掉")
    review_something(c)
    new, edits, reinforce = run(c)["lessons"]

    # adopt as proposed -> an ask in force, his sentences as examples
    out = c.post(f"{EP}/lessons/{new['id']}", json={"action": "adopt"}).json()
    assert out["state"] == "adopted"
    rule = next(r for r in asks(c) if r["id"] == out["rule"])
    assert rule["title"] == new["title"] and rule["state"] == "approved"
    assert rule["examples"][0]["text"] == "这段跑题了删掉"
    assert "Cut Leon's digressions harder." in prompt_rules(ai_ws)
    assert c.post(f"{EP}/lessons/{new['id']}/edit", json={"text": "x"}).status_code == 409

    # edit by hand, then by talking to LACUNA, then adopt
    e1 = c.post(f"{EP}/lessons/{edits['id']}/edit", json={"text": "停顿收到 0.5 秒"}).json()
    assert e1["title"] == "停顿收到 0.5 秒" and e1["edited"] and "停顿收到 0.5 秒" in e1["instruction"]
    e2 = c.post(f"{EP}/lessons/{edits['id']}/revise", json={"text": "只对 Leon"}).json()
    assert e2["title"] == "停顿收到 0.5 秒（只对 Leon）" and e2["reply"] == "我按你说的改了：只对 Leon。"
    assert len(e2["history"]) == 2
    out = c.post(f"{EP}/lessons/{edits['id']}", json={"action": "adopt"}).json()
    assert next(r for r in asks(c) if r["id"] == out["rule"])["title"] == e2["title"]

    # reinforcing a learned rule as is = approving that rule (no duplicate)
    out = c.post(f"{EP}/lessons/{reinforce['id']}", json={"action": "adopt"}).json()
    assert out["rule"] == reinforce["related"]
    states = {r["id"]: r["state"] for r in c.get("/api/learning").json()["rules"]}
    assert states[reinforce["related"]] == "approved" and len(asks(c)) == 2
    v = c.get(f"{EP}/lessons").json()
    assert v["pending"] == 0 and all(x["rule_state"] == "approved" for x in v["lessons"])


def test_reinforce_and_conflict_with_an_ask_iterate_it(ai_ws):
    ws = Workspace(ai_ws)
    ChatAsks(ws).put("EP_旧", {"id": "a1", "title": "Pei 的嗯别删", "instruction": "Keep Pei's 嗯.",
                               "source": "remember", "quotes": [{"said": "记住：Pei 的嗯别删", "at": 1.0}]})
    Learning(ws).decide("ask:a1", "approve")
    lessons = [
        {"title": "Pei 的嗯保留", "instruction": "x", "why": "w", "relation": "reinforce", "related": "ask:a1",
         "turns": [1], "edits": []},
        {"title": "Pei 句首的嗯可以删", "instruction": "Cut Pei's 嗯 at sentence starts.", "why": "w",
         "relation": "conflict", "related": "ask:a1", "turns": [1], "edits": []},
        {"title": "无出处", "instruction": "x", "why": "w", "relation": "new", "related": "", "turns": [99],
         "edits": ["nope"]},
        {"title": "相关不存在", "instruction": "x", "why": "w", "relation": "conflict", "related": "ask:zzz",
         "turns": [1], "edits": []},
    ]
    c = client(ai_ws, FakeRuleWriter(lessons=lessons), MockEditorAdapter())
    chat(c, "Pei 的嗯还是留着吧")
    rein, conf, unknown = run(c)["lessons"]                       # a lesson citing nothing real is dropped
    assert unknown["relation"] == "new" and unknown["related"] == ""
    c.post(f"{EP}/lessons/{rein['id']}", json={"action": "adopt"})
    [r] = asks(c)
    assert r["title"] == "Pei 的嗯别删" and r["evidence"]["said"] == 2 and not r["updated"]
    c.post(f"{EP}/lessons/{conf['id']}", json={"action": "adopt"})
    [r] = asks(c)                                                 # same rule, newer wording, still in force
    assert r["id"] == "ask:a1" and r["title"] == "Pei 句首的嗯可以删" and r["state"] == "approved"
    assert "Cut Pei's 嗯 at sentence starts." in prompt_rules(ai_ws)


def test_lessons_without_key_errors_and_demo(ai_ws, tmp_path):
    c = client(ai_ws, SimpleNamespace(available=False), MockEditorAdapter())
    assert run(c)["state"] == "no_key"
    c = client(ai_ws, FakeRuleWriter(boom=True), MockEditorAdapter())
    v = run(c)
    assert v["state"] == "error" and v["error"] == "AI 服务出了点问题"    # never the raw error
    w = FakeRuleWriter()
    c = client(ai_ws, w, MockEditorAdapter())
    v = run(c)                                                     # nothing happened yet: an empty answer
    assert v["state"] == "done" and v["lessons"] == []
    demo = make_workspace(tmp_path / "demo")
    cd = client(demo, w, MockEditorAdapter())
    cd.post(f"/api/episodes/{EPISODE}/lessons/run")
    assert cd.get(f"/api/episodes/{EPISODE}/lessons").json()["state"] == "demo"
    assert c.post(f"{EP}/lessons/nope", json={"action": "adopt"}).status_code == 404
    assert c.post(f"{EP}/lessons/nope", json={"action": "bogus"}).status_code == 422


def test_lessons_outlive_the_episode_folder(ai_ws):
    """Learning evidence is never deleted with an episode (Leon 2026-10-17)."""
    c = client(ai_ws, FakeRuleWriter(), MockEditorAdapter())
    d = c.post(f"{EP}/remember", json={"text": "开头别剪", "playhead": 1.0}).json()["remember"]
    c.post(f"{EP}/remember/{d['id']}", json={"action": "confirm"})
    assert (ai_ws / "learning" / "lessons" / f"{AI_EPISODE}.json").is_file()
    assert not list((ai_ws / "episodes" / AI_EPISODE).glob("lessons*"))


# ================================================================ V6: no forced tool, readable errors

def _api_error(status: int, message: str):
    import anthropic
    import httpx
    resp = httpx.Response(status, request=httpx.Request("POST", "https://api.example/v1/messages"))
    return anthropic.APIStatusError(message, response=resp, body=None) if status != 400 else \
        anthropic.BadRequestError(message, response=resp, body=None)


def test_rule_writer_asks_again_when_the_answer_is_plain_text():
    calls = []

    def create(**kw):
        calls.append(kw)
        if len(calls) == 1:
            content = [SimpleNamespace(type="text", text="好的，我来想想")]
        else:
            content = [SimpleNamespace(type="tool_use", name="submit_rule",
                                       input={"title": "t", "understood": "u", "instruction": "i", "same_as": ""})]
        return SimpleNamespace(model=kw["model"], content=content, stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=900, output_tokens=80))

    w = ClaudeRuleWriter(client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    out, _ = w.rewrite({"said": "x", "recent_chat": [], "existing_rules": []})
    assert out["title"] == "t" and len(calls) == 2


def test_failed_rewrite_and_summary_explain_in_words(ai_ws):
    def create(**kw):
        raise _api_error(400, "tool_choice: forced tool use is not supported with this model")

    writer = ClaudeRuleWriter(client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    c = client(ai_ws, writer, MockEditorAdapter())
    d = c.post(f"{EP}/remember", json={"text": "开头别剪", "playhead": 1.0}).json()["remember"]
    assert d["fallback"] and d["title"] == "开头别剪"
    assert d["error"] == "AI 服务返回错误（400）" and "tool_choice" not in json.dumps(d)
    v = run(c)
    assert v["state"] == "error" and v["error"] == "AI 服务返回错误（400）"
    # in English too, and never naming the AI vendor
    c.cookies.set("lacuna_lang", "en")
    d = c.post(f"{EP}/remember", json={"text": "keep the intro", "playhead": 1.0}).json()["remember"]
    assert d["error"].startswith("The AI service") and "Claude" not in d["error"]
    c.cookies.set("lacuna_lang", "zh")
    c.get(f"{EP}/lessons")

    # no key at all -> his words without an error
    c2 = client(ai_ws, SimpleNamespace(available=False))
    assert c2.post(f"{EP}/remember", json={"text": "片尾别剪", "playhead": 1.0}).json()["remember"]["error"] == ""


def test_an_old_raw_summary_error_is_not_shown(ai_ws):
    p = ai_ws / "learning" / "lessons" / f"{AI_EPISODE}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema": 1, "episode": AI_EPISODE, "drafts": [], "lessons": [],
                             "summary": {"state": "error", "error": "Error code: 400 - {'type': 'error'}"}}))
    v = client(ai_ws).get(f"{EP}/lessons").json()
    assert v["state"] == "none" and v["error"] is None     # the old version's failure: just offer 总结


def test_a_dropped_remember_never_comes_back_as_a_lesson(ai_ws):
    """Leon 2026-10-18: he said 不用 to a 「记住」 card, then 总结 proposed that very rule again."""
    lessons = [{"title": "开头别剪", "instruction": "x", "why": "你说过。", "relation": "new", "related": "",
                "turns": [2], "edits": []},
               {"title": "片头保留完整", "instruction": "x", "why": "你说过。", "relation": "new", "related": "",
                "turns": [2], "edits": []},
               {"title": "Leon 跑题的段落剪狠一点", "instruction": "x", "why": "第 1 句。", "relation": "new",
                "related": "", "turns": [1], "edits": []}]
    w = FakeRuleWriter(lessons=lessons)
    c = client(ai_ws, w, MockEditorAdapter())
    chat(c, "这段跑题了删掉")                                                     # turn 1
    d = c.post(f"{EP}/remember", json={"text": "开头别剪", "playhead": 1.0}).json()["remember"]   # turn 2
    c.post(f"{EP}/remember/{d['id']}", json={"action": "drop"})
    v = run(c)
    sent = w.calls[-1][1]
    assert [t["turn"] for t in sent["chat"]] == [1]                     # 「记住」 turns are not shown at all
    assert {"title": d["title"], "decision": "skipped"} in sent["already_reviewed"]
    assert [x["title"] for x in v["lessons"]] == ["Leon 跑题的段落剪狠一点"]
    assert v["lessons"][0]["turns"][0]["said"] == "这段跑题了删掉"


def test_nothing_runs_until_he_clicks_summarize(ai_ws):
    w = FakeRuleWriter()
    c = client(ai_ws, w, MockEditorAdapter())
    chat(c, "这段跑题了删掉")
    for _ in range(3):
        assert c.get(f"{EP}/lessons").json()["state"] == "none"
    assert not [k for k, _ in w.calls if k == "summarize"]
    assert run(c)["state"] == "done"


def test_no_module_forces_a_tool():
    """Forced tool_choice ({"type": "tool"} / "any") makes the current models answer 400 (V6)."""
    import re
    root = Path(__file__).resolve().parents[2] / "lacuna_app"
    bad = [f"{p.name}:{i}" for p in root.rglob("*.py") for i, line in enumerate(p.read_text("utf-8").splitlines(), 1)
           if re.search(r"tool_choice\s*[=:]\s*\{\s*[\"']type[\"']\s*:\s*[\"'](tool|any)[\"']", line)]
    assert bad == []
