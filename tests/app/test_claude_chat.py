"""Phase 3: the chat talks to Claude. No network and no key here: a fake client stands in for
`anthropic.Anthropic`, answering with the tool call a real model would make."""
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from lacuna_app import Episode, Workspace, create_app
from lacuna_app import editor as editor_mod
from lacuna_app.analysis import Span
from lacuna_app.editor import (ChatContext, ClaudeEditorAdapter, MockEditorAdapter, Utterance, Word, editor_status,
                               find_api_key, resolve, scene)
from lacuna_app.server import USAGE_LOG

from .synth import AI_EPISODE, make_ai_workspace

EP = f"/api/episodes/{AI_EPISODE}"
REAL_REGISTRY_LOOKUP = editor_mod._windows_registry_key     # conftest stubs it in every test


# ---------------------------------------------------------------- fakes

def tool_response(inp: dict, model="claude-opus-5-5", stop="tool_use"):
    return SimpleNamespace(
        stop_reason=stop, model=model, _request_id="req_test",
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="tool_use", name="propose_edit", input=inp)],
        usage=SimpleNamespace(input_tokens=3000, output_tokens=400, cache_creation_input_tokens=0,
                              cache_read_input_tokens=0))


class FakeClient:
    """Records requests; `answer(scene_dict)` returns the response (or raises)."""

    def __init__(self, answer):
        self.answer = answer
        self.requests: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.requests.append(kw)
        return self.answer(json.loads(kw["messages"][0]["content"]))

    @property
    def last_scene(self) -> dict:
        return json.loads(self.requests[-1]["messages"][0]["content"])


def act(type_, **kw):
    a = {"type": type_, "from_utterance": None, "to_utterance": None, "start_text": None, "end_text": None,
         "pause": None, "target_s": None, "edit": None}
    return a | kw


def answer(actions, message="好的", category="content", title="按指令修改"):
    return {"message": message, "title": title, "reason": "按你的指令", "confidence": 0.8,
            "category": category, "actions": actions}


def api_error(cls, status, msg="error"):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(msg, response=httpx2.Response(status, request=req), body=None)


@pytest.fixture
def ws(tmp_path):
    return make_ai_workspace(tmp_path / "ws")


def app_with(ws, fake):
    return TestClient(create_app(ws, ClaudeEditorAdapter(client=fake), web_dist=Path("/nonexistent")))


def utt(ctx_scene, uid):
    return next(u for u in ctx_scene["utterances"] if u["id"] == uid)


# ---------------------------------------------------------------- what Claude sees

def test_scene_is_text_and_numbers_of_the_current_cut(ws):
    ep = Episode(Workspace(ws), AI_EPISODE)
    ctx, _ = ep.chat_context("删掉这句", 20.0)
    sc = scene(ctx)
    blob = json.dumps(sc, ensure_ascii=False)          # serialisable: no audio, no bytes
    assert sc["instruction"] == "删掉这句" and sc["playhead_mmss"] == "0:20"
    ids = [u["id"] for u in sc["utterances"]]
    assert ids == [f"u{i + 1}" for i in range(len(ids))] and len(ids) >= 8
    starts = [u["start"] for u in sc["utterances"]]
    assert starts == sorted(starts)
    assert {u["speaker"] for u in sc["utterances"]} == {"Leon", "Pei"}
    assert sc["playhead_utterance"] in ids
    # what the first cut removed is not offered as current speech, but is listed as an edit
    content = next(e for e in sc["nearby_edits"] if e["id"] == "a0005")
    assert content["status"] == "applied" and content["removed_text"] == "那个结尾我们今天聊一部"
    assert all(u["end"] <= ctx.duration + 0.6 for u in sc["utterances"])
    assert all(p["length"] > 0 for p in sc["pauses"])
    assert "wav" not in blob and "raw" not in sc


def test_scene_times_follow_the_timeline(ws):
    """Utterance times are timeline seconds: after restoring the content cut, later speech moves
    later by the restored length and the restored words are offered again."""
    ep = Episode(Workspace(ws), AI_EPISODE)
    before = scene(ep.chat_context("x", 30.0)[0])
    ep.review("a0005", "restore")
    after = scene(ep.chat_context("x", 30.0)[0])
    leon_at = lambda sc: [u for u in sc["utterances"] if u["speaker"] == "Leon" and 21.5 <= u["start"] <= 25.5]  # noqa: E731
    assert leon_at(before) == []
    assert [u["text"][:11] for u in leon_at(after)] == ["那个结尾我们今天聊一部"]
    last_b, last_a = before["utterances"][-1], after["utterances"][-1]
    assert last_a["text"] == last_b["text"] or last_a["start"] >= last_b["start"]


# ---------------------------------------------------------------- resolving ids

def _ctx():
    W = lambda t, s: Word(t, s, s + 0.25)  # noqa: E731
    u1 = Utterance("u1", "Leon", [W(c, 10.0 + 0.3 * i) for i, c in enumerate("我觉得这个电影吧就是")])
    u2 = Utterance("u2", "Pei", [W(c, 14.0 + 0.3 * i) for i, c in enumerate("对对对")])
    u3 = Utterance("u3", "Leon", [W(c, 15.0 + 0.3 * i) for i, c in enumerate("节奏有点问题")])
    pauses = [Span(12.95, 14.0), Span(14.85, 15.0)]
    edits = [{"id": "a1", "t": 9.0, "status": "applied", "title": "删除", "category": "content"},
             {"id": "a2", "t": 9.5, "status": "restored", "title": "旧建议", "category": "content"}]
    return ChatContext("x", 11.0, 60.0, pauses, None, edits, "", [u1, u2, u3])


def test_resolve_whole_and_partial_utterance():
    ctx = _ctx()
    p = resolve(answer([act("cut", from_utterance="u1")]), ctx)
    assert len(p.cuts) == 1 and p.cuts[0]["track"] is None
    assert p.cuts[0]["start"] == pytest.approx(10.0)
    # the 1.05 s gap after u1 is kept down to 0.5 s where the sides join
    assert p.cuts[0]["end"] == pytest.approx(12.95 + 1.05 - 0.5, abs=1e-3)
    p = resolve(answer([act("cut", from_utterance="u1", start_text="吧就是")]), ctx)
    c = p.cuts[0]
    assert c["start"] == pytest.approx(10.0 + 0.3 * 7, abs=0.01)     # "吧" (8th char) starts it
    # verbatim quotes may differ in punctuation / spaces
    p = resolve(answer([act("cut", from_utterance="u1", start_text="这个", end_text="电影，")]), ctx)
    assert p.cuts[0]["start"] == pytest.approx(10.9) and not p.notes
    assert p.cuts[0]["end"] == pytest.approx(12.1)    # mid-sentence: joins tight onto "吧"


def test_resolve_across_speakers_warns_about_the_other_host():
    p = resolve(answer([act("cut", from_utterance="u1", to_utterance="u3", end_text="节奏")]), _ctx())
    assert len(p.cuts) == 1
    assert any("Pei" in n and "对对对" in n for n in p.notes)


def test_resolve_one_track_pause_restore():
    ctx = _ctx()
    p = resolve(answer([act("cut_one_track", from_utterance="u2"), act("shorten_pause", pause="p1"),
                        act("restore", edit="a1")]), ctx)
    assert p.cuts[0]["track"] == "Pei" and p.cuts[0]["start"] == pytest.approx(13.97)
    assert p.cuts[1] == {"start": pytest.approx(13.15), "end": pytest.approx(13.8), "track": None}
    assert p.restores == ["a1"] and not p.notes


@pytest.mark.parametrize("bad, words", [
    (act("cut", from_utterance="u99"), "u99"),
    (act("cut", from_utterance="u1", start_text="不存在的话"), "找不到"),
    (act("cut_one_track", from_utterance="u1", to_utterance="u2"), "同一个人"),
    (act("shorten_pause", pause="p2"), "够短"),
    (act("shorten_pause", pause="p7"), "p7"),
    (act("restore", edit="a2"), "原话"),
    (act("restore", edit="zz"), "zz"),
    (act("teleport"), "teleport"),
])
def test_resolve_rejects_what_it_was_not_shown(bad, words):
    p = resolve(answer([bad]), _ctx())
    assert not p.cuts and not p.restores
    assert any(words in n for n in p.notes) and any("没有改动" in n for n in p.notes)


def test_resolve_caps_actions_and_clamps_fields():
    p = resolve({"message": "", "actions": [act("shorten_pause", pause="p1")] * 12, "confidence": 7,
                 "category": "weird"}, _ctx())
    assert len(p.cuts) == 8 and p.confidence == 1.0 and p.category == "chat" and p.message


# ---------------------------------------------------------------- request shape

def test_request_shape():
    fake = FakeClient(lambda sc: tool_response(answer([])))
    ad = ClaudeEditorAdapter(client=fake)
    ad.propose(_ctx())
    req = fake.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["fallbacks"] == "default"
    assert req["betas"] == ["server-side-fallback-2026-07-01"]
    assert req["tool_choice"] == {"type": "auto"} and "thinking" not in req
    tool = req["tools"][0]
    assert tool["name"] == "propose_edit" and tool["strict"] is True
    items = tool["input_schema"]["properties"]["actions"]["items"]
    assert set(items["required"]) == set(items["properties"])      # strict mode: every field required
    assert req["output_config"]["effort"] in ("low", "medium", "high")
    sc = fake.last_scene
    assert [u["id"] for u in sc["utterances"]] == ["u1", "u2", "u3"] and sc["pauses"][0]["id"] == "p1"
    assert "never add" in req["system"].lower() or "can never add" in req["system"].lower()


# ---------------------------------------------------------------- through the API

def test_chat_cut_preview_approve_and_history(ws):
    def ans(sc):
        u = utt(sc, sc["playhead_utterance"])
        return tool_response(answer([act("cut", from_utterance=u["id"])], message=f"删掉 {u['text']}"))
    fake = FakeClient(ans)
    client = app_with(ws, fake)
    assert client.get("/api/health").json()["editor"] == "claude"
    d0 = client.get(EP).json()["duration"]
    r = client.post(f"{EP}/chat", json={"text": "这句删掉", "playhead": 33.0}).json()
    assert r["adapter"] == "claude" and r["proposal"] and r["reply"].startswith("删掉")
    assert r["usage"]["input_tokens"] == 3000 and r["usage"]["cost_usd"] == pytest.approx(0.02)
    said = utt(fake.last_scene, fake.last_scene["playhead_utterance"])
    pid = r["proposal"]["id"]
    ab = client.get(f"{EP}/proposals/{pid}/ab").json()
    assert ab["after"]["duration"] < ab["before"]["duration"]
    s = client.post(f"{EP}/proposals/{pid}/approve", json={"playhead": 33.0}).json()
    removed = d0 - s["duration"]
    assert said["end"] - said["start"] <= removed + 0.1 and removed < said["end"] - said["start"] + 1.6
    chat_edit = next(e for e in s["edits"] if e["source"] == "chat")
    assert chat_edit["status"] == "applied" and chat_edit["category"] == "content"
    assert s["can_undo"]
    # the next turn carries the conversation so far
    client.post(f"{EP}/chat", json={"text": "再多删一点", "playhead": 33.0})
    turns = fake.last_scene["recent_turns"]
    assert turns[-1]["said"] == "这句删掉" and turns[-1]["outcome"] == "proposed and approved"
    # the removed words are gone from what Claude sees now
    assert said["text"] not in [u["text"] for u in fake.last_scene["utterances"]]
    log = (Path(ws) / USAGE_LOG).read_text(encoding="utf-8").strip().splitlines()
    assert len(log) == 2 and json.loads(log[0])["episode"] == AI_EPISODE
    assert "sk-" not in "".join(log)


def test_chat_restore_and_one_track(ws):
    fake = FakeClient(lambda sc: tool_response(answer([act("restore", edit="a0005")], category="chat")))
    client = app_with(ws, fake)
    r = client.post(f"{EP}/chat", json={"text": "刚才删掉的那段恢复", "playhead": 23.0}).json()
    assert r["proposal"]["changes"] == [{"id": "a0005", "field": "status", "new": "restored"}]
    s = client.post(f"{EP}/proposals/{r['proposal']['id']}/approve", json={}).json()
    assert next(e for e in s["edits"] if e["id"] == "a0005")["status"] == "restored"

    def pei_only(sc):
        u = next(u for u in sc["utterances"] if u["speaker"] == "Pei" and u["start"] > 30)
        return tool_response(answer([act("cut_one_track", from_utterance=u["id"], end_text=u["text"][:2])],
                                    category="interjection"))
    fake.answer = pei_only
    d0 = s["duration"]
    r = client.post(f"{EP}/chat", json={"text": "Pei 这个插话去掉", "playhead": 36.0}).json()
    s = client.post(f"{EP}/proposals/{r['proposal']['id']}/approve", json={}).json()
    e = next(e for e in s["edits"] if e["source"] == "chat" and e["category"] == "interjection")
    assert e["tracks"] == ["Pei"] and s["duration"] == pytest.approx(d0)     # nothing moved


def test_chat_no_change_and_plain_text_answers(ws):
    fake = FakeClient(lambda sc: tool_response(answer([], message="你是说哪一句？前面 Leon 那句还是 Pei 这句？")))
    client = app_with(ws, fake)
    n0 = len(client.get(EP).json()["edits"])
    r = client.post(f"{EP}/chat", json={"text": "删掉", "playhead": 20.0}).json()
    assert r["proposal"] is None and "哪一句" in r["reply"]
    fake.answer = lambda sc: SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5",
                                             content=[SimpleNamespace(type="text", text="这里不用改。")], usage=None)
    r = client.post(f"{EP}/chat", json={"text": "这里还行吗", "playhead": 20.0}).json()
    assert r["proposal"] is None and r["reply"] == "这里不用改。"
    fake.answer = lambda sc: tool_response(answer([act("cut", from_utterance="u404")]))
    r = client.post(f"{EP}/chat", json={"text": "删掉", "playhead": 20.0}).json()
    assert r["proposal"] is None and any("u404" in n for n in r["notes"])
    assert len(client.get(EP).json()["edits"]) == n0


@pytest.mark.parametrize("exc, words", [
    (api_error(anthropic.AuthenticationError, 401), "401"),
    (api_error(anthropic.RateLimitError, 429), "429"),
    (api_error(anthropic.BadRequestError, 400, "Your credit balance is too low"), "额度"),
    (api_error(anthropic.InternalServerError, 529), "繁忙"),
    (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")), "网络"),
    (RuntimeError("boom"), "RuntimeError"),
])
def test_api_failures_change_nothing(ws, exc, words):
    def boom(sc):
        raise exc
    client = app_with(ws, FakeClient(boom))
    s0 = client.get(EP).json()
    r = client.post(f"{EP}/chat", json={"text": "删掉这句", "playhead": 20.0})
    assert r.status_code == 200
    r = r.json()
    assert r["proposal"] is None and words in r["reply"] and "没有改动" in r["reply"]
    s = client.get(EP).json()
    assert s["version"] == s0["version"] and len(s["edits"]) == len(s0["edits"])


def test_refusal(ws):
    client = app_with(ws, FakeClient(lambda sc: tool_response(answer([]), stop="refusal")))
    r = client.post(f"{EP}/chat", json={"text": "删掉", "playhead": 20.0}).json()
    assert r["proposal"] is None and "没有处理" in r["reply"]


def test_timeline_change_during_the_call_voids_the_answer(ws):
    """The API call runs outside the episode lock; if the cut changed meanwhile, the answer's
    times are stale and must not become a proposal."""
    ep_holder = {}

    def ans(sc):
        ep_holder["app"].state.episodes[AI_EPISODE].review("a0005", "restore")   # Leon clicks meanwhile
        return tool_response(answer([act("cut", from_utterance=sc["playhead_utterance"])]))
    fake = FakeClient(ans)
    app = create_app(ws, ClaudeEditorAdapter(client=fake), web_dist=Path("/nonexistent"))
    ep_holder["app"] = app
    client = TestClient(app)
    client.get(EP)
    r = client.post(f"{EP}/chat", json={"text": "删掉这句", "playhead": 33.0}).json()
    assert r["proposal"] is None and any("作废" in n for n in r["notes"])


def test_new_proposal_supersedes_and_conflict_is_reported(ws):
    fake = FakeClient(lambda sc: tool_response(answer([act("shorten_pause", pause="p1")], category="pause")))
    client = app_with(ws, fake)
    p1 = client.post(f"{EP}/chat", json={"text": "停顿短一点", "playhead": 6.0}).json()["proposal"]
    p2 = client.post(f"{EP}/chat", json={"text": "停顿短一点", "playhead": 6.0}).json()["proposal"]
    assert p1 and p2 and p1["id"] != p2["id"]
    assert [p["id"] for p in client.get(EP).json()["proposals"]] == [p2["id"]]
    assert fake.last_scene["recent_turns"][-1]["outcome"] in ("proposed, not decided yet", "proposed and rejected")


# ---------------------------------------------------------------- key and engine selection

def test_find_api_key_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", '  "sk-ant-test"  ')
    assert find_api_key() == ("sk-ant-test", "env")


def test_find_api_key_windows_registry(monkeypatch):
    """A server started before `setx` ran has no key in its environment: read the registry."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake = types.ModuleType("winreg")
    fake.HKEY_CURRENT_USER, fake.HKEY_LOCAL_MACHINE = "HKCU", "HKLM"

    class Key:
        def __init__(self, root):
            self.root = root

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def open_key(root, path):
        if root == "HKLM":
            raise OSError("no")
        return Key(root)
    fake.OpenKey = open_key
    fake.QueryValueEx = lambda k, name: ("sk-ant-from-registry", 1)
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(editor_mod, "_windows_registry_key", REAL_REGISTRY_LOOKUP)
    monkeypatch.setattr(editor_mod.sys, "platform", "win32")
    assert find_api_key() == ("sk-ant-from-registry", "registry-user")
    monkeypatch.setattr(editor_mod.sys, "platform", "linux")
    assert find_api_key() == (None, "missing")


def test_editor_status(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert editor_status(MockEditorAdapter())["editor_note"].startswith("没找到")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert ClaudeEditorAdapter().available            # SDK is installed in the test env
    monkeypatch.setattr(editor_mod, "sdk_installed", lambda: False)
    assert not ClaudeEditorAdapter().available
    assert "anthropic" in editor_status(MockEditorAdapter())["editor_note"]
    assert editor_status(ClaudeEditorAdapter(client=object())) == {"editor": "claude", "editor_note": ""}
