"""Proper-noun check at import (name_check.py, Leon 2026-10-31): films, people and other names the recogniser
mis-heard are fixed before 审阅 (on by default); only whole words that sound alike, times kept; each fix can be
put back as heard, and is then left alone by later imports and the show notes."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app, show
from lacuna_app import name_check as nc
from lacuna_app import transcript_fix as tf
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.first_cut import ClaudeFirstCut
from lacuna_app.importer import Importer
from lacuna_app.store import Workspace

from .fake_claude import FakeFirstCutAnthropic
from .synth import write_recordings
from .test_transcript_fix import misheard_asr, words

ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


class FakeMessages:
    def __init__(self, answer=lambda doc: [], error=None):
        self.answer, self.error, self.calls = answer, error, []

    def create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        fixes = self.answer(json.loads(kw["messages"][0]["content"]))
        return SimpleNamespace(stop_reason="end_turn", model=nc.MODEL,
                               usage=SimpleNamespace(input_tokens=2000, output_tokens=80),
                               content=[SimpleNamespace(type="text", text=json.dumps({"fixes": fixes}, ensure_ascii=False))])


def checker(**kw):
    m = FakeMessages(**kw)
    return nc.NameChecker(client=SimpleNamespace(messages=m)), m


def line(*texts):
    return tf.Line("L0001", "Leon", words(*texts))


def test_only_whole_words_that_sound_like_the_name_survive():
    lines = [line("我", "觉", "得", "落", "兰", "拍", "得", "好")]
    out = nc.check([
        {"line": "L0001", "wrong": "落兰", "right": "《诺兰》", "why": "导演克里斯托弗·诺兰"},   # marks stripped
        {"line": "L0001", "wrong": "我觉得", "right": "库布里克", "why": "x"},                   # does not sound alike
        {"line": "L0001", "wrong": "不在", "right": "不再", "why": "x"},                         # not in the line
        {"line": "L0009", "wrong": "落兰", "right": "诺兰", "why": "x"},                         # no such line
        {"line": "L0001", "wrong": "落兰", "right": "诺兰", "why": "again"},                     # the same twice
    ], lines)
    assert out == [{"line": "L0001", "wrong": "落兰", "right": "诺兰", "why": "导演克里斯托弗·诺兰"}]
    assert nc.check([{"line": "L0001", "wrong": "落兰", "right": "诺兰", "why": ""}], lines,
                    [{"wrong": "落兰", "right": "诺兰"}]) == []          # put back before: left as heard


def test_the_model_gets_text_only_and_any_failure_changes_nothing(tmp_path):
    ws = Workspace(tmp_path / "ws").ensure()
    lines = [line("我", "觉", "得", "落", "兰", "拍", "得", "好")]
    ch, m = checker(answer=lambda doc: [{"line": "L0001", "wrong": "落兰", "right": "诺兰", "why": "导演"}])
    assert ch.propose(lines, ws.root, "EP003 奥本海默") == [{"line": "L0001", "wrong": "落兰", "right": "诺兰", "why": "导演"}]
    sent = m.calls[0]
    assert sent["model"] == nc.MODEL == "claude-opus-5-5"
    doc = json.loads(sent["messages"][0]["content"])
    assert doc["lines"] == ["L0001 Leon：我觉得落兰拍得好"] and doc["episode_title"] == "EP003 奥本海默"
    bad, _ = checker(error=RuntimeError("down"))
    assert bad.propose(lines, ws.root) == []
    assert nc.NameChecker(api_key="").propose(lines, ws.root) == []


def test_on_by_default_and_off_in_the_project_settings(tmp_path, monkeypatch):
    ws = Workspace(tmp_path / "ws").ensure()
    assert nc.enabled(ws.root)
    p = show.load(ws.root)
    p["name_check"] = False
    show.save(ws.root, p)
    assert not nc.enabled(ws.root) and show.load(ws.root)["name_check"] is False
    p.pop("name_check")                       # a form that doesn't send it keeps the stored one
    show.save(ws.root, p)
    assert not nc.enabled(ws.root)
    p["name_check"] = True
    show.save(ws.root, p)
    assert nc.enabled(ws.root)
    monkeypatch.setenv("LACUNA_NAME_CHECK", "off")
    assert not nc.enabled(ws.root)


def _import(tmp_path, ch):
    ws = Workspace(tmp_path / "ws").ensure()
    rec = write_recordings(tmp_path / "in")
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()), asr_backend=misheard_asr)
    imp.term_fixer = tf.TranscriptFixer(api_key="")       # the show's own names: not this test
    imp.name_checker = ch
    job = imp.start("EP002", "EP002 · 测试", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    assert job["state"] == "done", job["error"]
    return ws, imp


def leon_first(ws) -> str:
    t = json.loads((ws.episode_dir("EP002") / "transcript.json").read_text(encoding="utf-8"))
    return sorted(t["tracks"]["Leon"])[0][2]


@ffmpeg
def test_import_fixes_names_before_review_and_one_can_be_put_back(tmp_path):
    def answer(doc):
        first = next(ln for ln in doc["lines"] if "利奥" in ln)
        return [{"line": first.split(" ", 1)[0], "wrong": "利奥", "right": "Leon", "why": "主持人"}]
    ch, m = checker(answer=answer)
    ws, imp = _import(tmp_path, ch)
    assert m.calls
    assert imp.status("EP002")["steps"]["names"]["fixes"] == [{"wrong": "利奥", "right": "Leon", "count": 1}]
    assert leon_first(ws) == "Leon"
    assert "利奥" not in (ws.root / "imports" / "EP002" / "editor_input.md").read_text(encoding="utf-8")
    usage = [json.loads(x) for x in (ws.root / "ai_usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(u["kind"] == "name_check" and u["episode"] == "EP002" for u in usage)

    c = TestClient(create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    got = c.get("/api/episodes/EP002/names").json()
    assert got["on"] is True
    [row] = got["rows"]
    assert (row["wrong"], row["right"], row["why"], row["count"], row["state"]) == ("利奥", "Leon", "主持人", 1, "applied")
    before = c.get("/api/episodes/EP002").json()
    r = c.post("/api/episodes/EP002/names/keep", json={"wrong": "利奥", "right": "Leon", "playhead": 1.0})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["changed"] == 1 and out["names"][0]["state"] == "kept"
    assert out["version"] == before["version"] and len(out["edits"]) == len(before["edits"])     # audio untouched
    assert out["transcript_rev"] != before["transcript_rev"]
    assert leon_first(ws) == "利奥"
    assert nc.kept(ws.root) == [{"wrong": "利奥", "right": "Leon"}]
    assert c.post("/api/episodes/EP002/names/keep", json={"wrong": "x", "right": "y"}).status_code == 404


@ffmpeg
def test_import_with_the_check_off_keeps_the_text_as_heard(tmp_path):
    ch, m = checker(answer=lambda doc: [{"line": "L0001", "wrong": "利奥", "right": "Leon", "why": ""}])
    root = tmp_path / "ws"
    Workspace(root).ensure()
    p = show.load(root)
    p["name_check"] = False
    show.save(root, p)
    ws, imp = _import(tmp_path, ch)
    assert not m.calls and "names" not in imp.status("EP002")["steps"]
    assert leon_first(ws) == "利"
    assert not (ws.episode_dir("EP002") / nc.EPISODE_FILE).exists()


@ffmpeg
def test_show_notes_leave_a_name_put_back_alone(tmp_path):
    from lacuna_app.episode import Episode
    from lacuna_app.publish import ClaudePublisher, Publisher

    from .fake_claude import FakePublishAnthropic
    from .synth import EPISODE, make_workspace
    ws = Workspace(make_workspace(tmp_path / "ws"))
    ep = Episode(ws, EPISODE)
    try:
        pub = Publisher(ws, lambda: ClaudePublisher(client=FakePublishAnthropic()))
        pub.start(ep, wait=True)
        assert [n["heard"] for n in pub.view(ep)["pack"]["names"]] == ["结尾"]   # the fake writer flags 结尾 → 结局
        nc.keep(ws.root, "结尾", "结局")
        pub.start(ep, wait=True)
        assert pub.view(ep)["pack"]["names"] == []
    finally:
        ep.close()
