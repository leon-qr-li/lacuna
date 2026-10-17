"""Phase 9 publish pack: transcript on the final cut, Claude's draft (fake client), Markdown in the
approved format, local re-timing after edits, names, music from the library, API."""
import json
import sys
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import Episode, Workspace, create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.publish import (TOOL, ClaudePublisher, Publisher, RulePublisher, clean, final_time, load_names,
                                make_publisher, mmss, retime_markdown, segments)

from .fake_claude import FakePublishAnthropic
from .synth import EPISODE, make_workspace

EP = f"/api/episodes/{EPISODE}"


@pytest.fixture
def ws(tmp_path):
    return Workspace(make_workspace(tmp_path / "ws"))


@pytest.fixture
def ep(ws):
    e = Episode(ws, EPISODE)
    yield e
    e.close()


@pytest.fixture
def fake():
    return FakePublishAnthropic()


@pytest.fixture
def pub(ws, fake):
    return Publisher(ws, lambda: ClaudePublisher(client=fake))


def timeline_lines(md: str) -> list[str]:
    part = md.split("## ⏱ 时间轴")[1].split("\n---")[0]
    return [ln for ln in part.splitlines() if ln.startswith("- **")]


# ---------------------------------------------------------------------------- transcript

def test_segments_follow_the_current_cut(ep):
    segs = segments(ep)
    assert [s.id for s in segs][:3] == ["s0001", "s0002", "s0003"]
    # Pei's turn at raw 5.5 s plays at 4.4 s after the 1.1 s pause cut; its anchor stays in raw time
    pei = next(s for s in segs if s.base_s == 5.5)
    assert pei.speaker == "Pei" and pei.start == pytest.approx(4.4, abs=0.01)
    # the lifted interjection (Pei, raw 11.0-11.4) and the cut tangent (26.3-30.7) are not there
    assert not any(10.9 < s.base_s < 11.5 for s in segs)
    assert not any(26.3 <= s.base_s < 30.7 for s in segs)
    assert all(len(s.text) >= 3 for s in segs)


def test_tool_is_strict_and_closed():
    def walk(schema):
        if schema.get("type") == "object":
            assert schema["additionalProperties"] is False
            assert set(schema["required"]) == set(schema["properties"])
            for v in schema["properties"].values():
                walk(v)
        if schema.get("type") == "array":
            walk(schema["items"])
    assert TOOL["strict"] is True
    walk(TOOL["input_schema"])


# ---------------------------------------------------------------------------- generation

def test_generate_writes_the_approved_format(ws, ep, pub, fake):
    usage = []
    pub.on_usage = lambda eid, u: usage.append((eid, u))
    job = pub.start(ep, wait=True)
    assert job["state"] == "done", job
    req = fake.requests[0]
    sent = req["messages"][0]["content"]
    # only text goes out: transcript lines with final-cut times, nothing else from the workspace
    assert "s0002 00:04 Pei：很好看对吧然后那" in sent
    assert "APPROVED EXAMPLE" in req["system"] and "夏天的四部电影" in req["system"]
    assert req["tools"][0]["name"] == "submit_publish_pack"
    assert usage and usage[0][0] == EPISODE and usage[0][1]["cost_usd"] > 0

    v = pub.view(ep)["pack"]
    md = v["markdown"]
    lines = md.splitlines()
    assert lines[0] == "# 合成的一期：两部电影"
    assert "> 《洛城二三事》EP_TEST_合成 · Leon & Pei" in md
    assert "## ⏱ 时间轴" in md and "### 暖场" in md and "### 正题：那个结尾" in md
    assert md.index("### 暖场") < md.index("### 正题：那个结尾")
    tl = timeline_lines(md)
    assert tl[0] == "- **00:00** Leon 聊到「我们今天聊一」"
    assert len(tl) == 6                       # the made-up segment s9999 was dropped ...
    assert any("不存在的段落" in n for n in v["notes"])     # ... and said so
    assert "| 片名 | 导演 / 备注 |" in md and "| 《一部电影》 | 结尾 |" in md
    assert "## 😏 内部梗小词典" in md and "- **网大**：夸人用的，真的。" in md
    assert "## 🎵 本期 BGM" in md and "素材库还没接上" in md       # BGM section is always there
    assert md.rstrip().endswith("分享给一个也爱看电影的朋友吧。*")
    assert v["chapters"] == [{"t": 0.5, "time": "00:00", "heading": "暖场"},
                             {"t": pytest.approx(25.5, abs=0.01), "time": "00:25", "heading": "正题：那个结尾"}]
    assert v["stale"] is False and v["adapter"] == "claude" and v["library"] is False
    assert v["names"] == [{"heard": "结尾", "suggested": "结局", "why": "上下文是在说电影的结局", "state": "open"}]
    # saved through the store, and as a file next to the exports
    saved = json.loads((ep.dir / "publish.json").read_text(encoding="utf-8"))
    assert saved["schema"] == 1 and saved["draft"]["title"] == "合成的一期：两部电影"
    notes = ws.root / "exports" / EPISODE / "publish" / "notes.md"
    assert notes.read_text(encoding="utf-8") == md


def test_timeline_entries_are_sorted_and_need_a_real_segment(ep):
    segs = segments(ep)
    data = {"title": "t", "sections": [
        {"heading": "后", "entries": [{"segment": segs[5].id, "text": "b"}, {"segment": segs[4].id, "text": "a"}]},
        {"heading": "前", "entries": [{"segment": segs[0].id, "text": "x"}]},
        {"heading": "空", "entries": [{"segment": "s0000", "text": "y"}, {"segment": segs[1].id, "text": ""}]}]}
    draft, notes = clean(data, segs)
    assert [s["heading"] for s in draft["sections"]] == ["前", "后"]
    assert [e["text"] for e in draft["sections"][1]["entries"]] == ["a", "b"]
    assert notes == ["有 2 条时间轴引用了不存在的段落，已丢掉。"]


def test_without_claude_a_rule_draft_still_works(ws, ep, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert isinstance(make_publisher(), RulePublisher)
    p = Publisher(ws, lambda: RulePublisher())
    assert p.start(ep, wait=True)["state"] == "done"
    v = p.view(ep)["pack"]
    assert v["adapter"] == "rules" and "没有 Claude" in v["markdown"]
    assert timeline_lines(v["markdown"])[0].startswith("- **00:00** ")


def test_api_failure_is_a_chinese_error(ws, ep):
    class Broken:
        beta = types.SimpleNamespace(messages=types.SimpleNamespace(stream=lambda **kw: (_ for _ in ()).throw(RuntimeError("x"))))
    p = Publisher(ws, lambda: ClaudePublisher(client=Broken()))
    job = p.start(ep, wait=True)
    assert job["state"] == "error" and "调用 Claude 失败" in job["error"]
    assert p.view(ep)["pack"] is None


# ---------------------------------------------------------------------------- after more edits

def test_retime_after_restoring_an_edit(ep, pub):
    pub.start(ep, wait=True)
    before = timeline_lines(pub.view(ep)["pack"]["markdown"])
    ep.review("e003", "restore")           # 4.4 s tangent comes back: everything after it moves
    assert pub.view(ep)["pack"]["stale"] is True
    pub.retime(ep)
    v = pub.view(ep)["pack"]
    after = timeline_lines(v["markdown"])
    assert v["stale"] is False
    assert after[:3] == before[:3]                       # before the tangent: unchanged
    assert after[3] == "- **00:29** Pei 聊到「电影真的很好」"   # 25.5 s + 4.4 s
    assert before[3] == "- **00:25** Pei 聊到「电影真的很好」"
    assert v["chapters"][1]["time"] == "00:29"


def test_retime_keeps_leons_wording(ep, pub):
    pub.start(ep, wait=True)
    md = pub.view(ep)["pack"]["markdown"]
    mine = md.replace("Pei 聊到「电影真的很好」", "Pei：这部真的好看").replace("## 🎨", "我自己加的 **9:99** 一行\n\n## 🎨")
    pub.edit(ep, markdown=mine)
    ep.review("e003", "restore")
    pub.retime(ep)
    v = pub.view(ep)["pack"]
    assert v["edited"] is True
    assert "- **00:29** Pei：这部真的好看" in v["markdown"]
    assert "我自己加的 **9:99** 一行" in v["markdown"]
    # back to the generated text
    pub.edit(ep, markdown=None)
    v = pub.view(ep)["pack"]
    assert v["edited"] is False and "- **00:29** Pei 聊到「电影真的很好」" in v["markdown"]


def test_entry_whose_audio_was_cut_later_is_flagged(ep, pub):
    pub.start(ep, wait=True)
    seg = next(s for s in segments(ep) if s.base_s == 40.3)      # an entry of the fake writer
    ep.apply_op({"op": "cut", "start": int(40.2 * ep.sr), "end": int(43.9 * ep.sr), "tracks": None}, "删掉")
    pub.retime(ep)
    gone = pub.view(ep)["pack"]["gone"]
    assert len(gone) == 1 and seg.text[:6] in gone[0]


def test_retime_markdown_only_swaps_known_times():
    md = "- **00:10** a\n- **00:20** b\n- **00:10** c\nfoo **05:00** bar"
    out = retime_markdown(md, ["00:10", "00:20", "00:10"], ["00:11", "00:25", "00:12"])
    assert out == "- **00:11** a\n- **00:25** b\n- **00:12** c\nfoo **05:00** bar"


def test_mmss_past_an_hour():
    assert mmss(41.9) == "00:41" and mmss(3616) == "1:00:16" and mmss(-3) == "00:00"


# ---------------------------------------------------------------------------- title and names

def test_switch_title_to_an_alternative(ep, pub):
    pub.start(ep, wait=True)
    pub.edit(ep, title="两部电影一个结尾")
    v = pub.view(ep)["pack"]
    assert v["title"] == "两部电影一个结尾" and v["markdown"].startswith("# 两部电影一个结尾\n")
    assert v["alt_titles"][0] == "合成的一期：两部电影" and "两部电影一个结尾" not in v["alt_titles"]
    # with hand-edited Markdown only the heading changes
    pub.edit(ep, markdown=v["markdown"] + "\n加一句")
    pub.edit(ep, title="合成的一期：两部电影")
    v = pub.view(ep)["pack"]
    assert v["markdown"].startswith("# 合成的一期：两部电影\n") and v["markdown"].endswith("加一句")


def test_fixing_a_name_everywhere_and_remembering_it(ws, ep, pub, fake):
    pub.start(ep, wait=True)
    assert "结尾" in pub.view(ep)["pack"]["markdown"]
    pub.name(ep, "结尾", "apply")
    v = pub.view(ep)["pack"]
    assert "结尾" not in v["markdown"] and "结局" in v["markdown"]
    assert v["chapters"][1]["heading"] == "正题：那个结局"
    assert v["names"][0]["state"] == "applied"
    assert load_names(ws)[0]["wrong"] == "结尾" and load_names(ws)[0]["right"] == "结局"
    # the next generation sends the corrected transcript and the list of known names
    pub.start(ep, wait=True)
    sent = fake.requests[-1]["messages"][0]["content"]
    assert "- 结尾 → 结局" in sent
    assert "结尾" not in sent.split("成品转写")[1].split("请按说明")[0]
    with pytest.raises(KeyError):
        pub.name(ep, "不存在", "ignore")


# ---------------------------------------------------------------------------- music from the library (6a)

def test_music_from_the_library_moves_times_and_fills_bgm(ws, ep, pub, monkeypatch):
    cues = [{"role": "intro", "at_s": 0.0, "length_s": 30.0, "inserted": True, "title": "Main Theme",
             "artist": "Michael Giacchino", "film": "Spider-Man"},
            {"role": "interlude", "at_s": 25.0, "length_s": 10.0, "inserted": True, "title": "", "artist": "", "film": ""},
            {"role": "outro", "at_s": 51.0, "length_s": 20.0, "inserted": True, "title": "End", "artist": "", "film": "X"}]
    lib = types.ModuleType("lacuna_app.library")
    lib.episode_music = lambda w, eid: [dict(c) for c in cues] if eid == EPISODE else []
    monkeypatch.setitem(sys.modules, "lacuna_app.library", lib)
    monkeypatch.setattr(sys.modules["lacuna_app"], "library", lib, raising=False)

    pub.start(ep, wait=True)
    v = pub.view(ep)["pack"]
    tl = timeline_lines(v["markdown"])
    assert tl[0] == "- **00:00** 片头"
    assert tl[1] == "- **00:30** Leon 聊到「我们今天聊一」"          # 0.5 s + 30 s intro
    assert "- **00:55** 🎵 间奏" in tl                                # 25 s + 30 s intro
    assert "- **01:05** Pei 聊到「电影真的很好」" in tl                 # 25.5 + 30 + 10
    assert tl[-1] == "- **01:31** 片尾"                              # 51 + 30 + 10
    assert "- **片头**：Main Theme — Michael Giacchino（Spider-Man）" in v["markdown"]
    assert "- **00:55 间奏**：（曲名待补" in v["markdown"]
    assert "- **片尾**：End（X）" in v["markdown"]
    assert v["library"] is True and v["stale"] is False
    # Leon names the interlude in the library -> stale -> re-timing refreshes the BGM lines only
    cues[1]["title"] = "Interlude"
    pub.edit(ep, markdown=v["markdown"].replace("片头", "开场", 1))
    assert pub.view(ep)["pack"]["stale"] is True
    pub.retime(ep)
    md = pub.view(ep)["pack"]["markdown"]
    assert "- **00:55 间奏**：Interlude" in md and "- **00:00** 开场" in md


def test_final_time_adds_inserted_music_only():
    cues = [{"at_s": 0.0, "length_s": 30.0, "inserted": True}, {"at_s": 10.0, "length_s": 99.0, "inserted": False}]
    assert final_time(5.0, cues) == 35.0 and final_time(5.0, None) == 5.0


# ---------------------------------------------------------------------------- API

def test_publish_api(ws, fake):
    pub = Publisher(ws, lambda: ClaudePublisher(client=FakePublishAnthropic(delay=0.3)))
    client = TestClient(create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent"), publisher=pub))
    r = client.get(f"{EP}/publish")
    assert r.status_code == 200 and r.json()["pack"] is None
    assert client.post(f"{EP}/publish/retime").status_code == 404
    r = client.post(f"{EP}/publish/generate")
    assert r.status_code == 200 and r.json()["job"]["state"] == "running"
    assert client.post(f"{EP}/publish/generate").status_code == 409
    for _ in range(100):
        d = client.get(f"{EP}/publish").json()
        if d["job"]["state"] != "running":
            break
        time.sleep(0.05)
    assert d["job"]["state"] == "done" and d["pack"]["title"] == "合成的一期：两部电影"
    assert d["notes_path"].endswith("notes.md")
    r = client.put(f"{EP}/publish", json={"title": "那个结尾到底好不好"})
    assert r.json()["pack"]["title"] == "那个结尾到底好不好"
    r = client.post(f"{EP}/publish/names", json={"heard": "结尾", "action": "ignore"})
    assert r.json()["pack"]["names"][0]["state"] == "ignored"
    assert client.post(f"{EP}/publish/names", json={"heard": "x", "action": "nope"}).status_code == 422
    client.post(f"{EP}/edits/e003/review", json={"action": "restore"})
    assert client.get(f"{EP}/publish").json()["pack"]["stale"] is True
    assert client.post(f"{EP}/publish/retime").json()["pack"]["stale"] is False
    usage = (ws.root / "ai_usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(usage[-1])["kind"] == "publish"
