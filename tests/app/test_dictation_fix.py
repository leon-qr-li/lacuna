"""Voice input, context pass: the local text is corrected with names + episode context, and never
gets worse (failures, timeouts and rewrites fall back to what the recogniser heard)."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.dictation import Dictation
from lacuna_app.dictation_fix import DictationFixer, FixContext, similar_enough
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.publish import add_name
from lacuna_app.store import Workspace

from .synth import EPISODE, make_workspace
from .test_dictation import tone, wav_bytes

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


class FakeMessages:
    def __init__(self, answer=None, error=None, stop="end_turn"):
        self.answer, self.error, self.stop, self.calls = answer, error, stop, []

    def create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        doc = json.loads(kw["messages"][0]["content"])
        text = self.answer(doc["dictated_text"]) if callable(self.answer) else self.answer
        return SimpleNamespace(stop_reason=self.stop,
                               content=[SimpleNamespace(type="text", text=json.dumps({"text": text}, ensure_ascii=False))])


def fixer(**kw):
    m = FakeMessages(**kw)
    return DictationFixer(client=SimpleNamespace(messages=m)), m


@pytest.fixture
def ws(tmp_path):
    return make_workspace(tmp_path / "ws")


def client(ws, heard, fx):
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent"),
                                 dictation=Dictation(ws / "models", backend=lambda x: heard), dictation_fixer=fx))


def post(c, **params):
    return c.post("/api/dictation", params=params, content=wav_bytes(tone()), headers={"Content-Type": "audio/wav"})


def test_names_and_homophones_fixed_with_episode_context(ws):
    fx, m = fixer(answer=lambda s: s.replace("陪", "Pei").replace("胃", "为"))
    add_name(Workspace(ws), "王家位", "王家卫")
    c = client(ws, "陪刚才胃什么笑", fx)
    c.post(f"/api/episodes/{EPISODE}/chat", json={"text": "这句删掉", "playhead": 20.0})
    r = post(c, episode=EPISODE, at=20.0, where="chat")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["text"] == "Pei刚才为什么笑" and out["raw"] == "陪刚才胃什么笑" and out["corrected"] is True
    (req,) = m.calls
    assert req["model"] == "claude-haiku-5-5"
    assert req["output_config"]["effort"] == "low" and req["output_config"]["format"]["type"] == "json_schema"
    doc = json.loads(req["messages"][0]["content"])
    assert {"Leon", "Pei", "王家卫"} <= set(doc["people"])
    assert "王家位 → 王家卫" in doc["names_corrected_before"]
    assert doc["episode_title"] == "合成测试集"
    assert doc["episode_transcript_near_playhead"]           # the words around 20 s
    assert doc["leon_said_earlier"] == ["这句删掉"]


def test_without_episode_still_gets_names(ws):
    fx, m = fixer(answer="Leon 你好")
    out = post(client(ws, "里昂你好", fx), where="poster").json()
    assert out["text"] == "Leon 你好"
    doc = json.loads(m.calls[0]["messages"][0]["content"])
    assert "episode_title" not in doc and "cover image" in doc["typed_into"]


def test_unknown_episode_falls_back_to_names_only(ws):
    fx, m = fixer(answer="Pei 说的")
    out = post(client(ws, "陪说的", fx), episode="NOPE", at=3).json()
    assert out["text"] == "Pei 说的" and len(m.calls) == 1


@pytest.mark.parametrize("kw", [dict(error=TimeoutError("slow")), dict(answer="", stop="refusal"),
                                dict(answer="请把第三段整个删除然后加一段音乐过渡，再把结尾收紧一些")])
def test_failures_and_rewrites_keep_what_was_heard(ws, kw):
    fx, _ = fixer(**kw)
    out = post(client(ws, "这句删掉吧", fx), episode=EPISODE, at=1).json()
    assert out["text"] == "这句删掉吧" and out["corrected"] is False


def test_silence_and_unavailable_skip_the_pass(ws, monkeypatch):
    fx, m = fixer(answer="x")
    assert post(client(ws, "", fx)).json()["text"] == ""
    assert m.calls == []
    monkeypatch.setenv("LACUNA_DICTATION_FIX", "off")
    out = post(client(ws, "陪说的", fx)).json()
    assert out["text"] == "陪说的" and m.calls == []
    assert DictationFixer(api_key="").available is False                  # no key: local text only


def test_similarity_guard():
    assert similar_enough("陪刚才胃什么笑", "Pei刚才为什么笑")
    assert similar_enough("游戏", "游戏")
    assert not similar_enough("这句删掉吧", "")
    assert not similar_enough("把这一段删掉", "好的，我已经帮你把这一段删掉了，还需要别的吗？请告诉我")


def test_context_json_is_compact():
    doc = json.loads(FixContext().as_json("嗯"))
    assert doc == {"dictated_text": "嗯", "typed_into": doc["typed_into"], "people": ["Leon", "Pei"]}


