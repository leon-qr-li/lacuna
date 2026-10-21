"""Phase 4: import a new episode from two raw tracks.

ASR is replaced by `synth.fake_asr` (the real sherpa-onnx path is covered by
tests/test_asr_real.py when the models are on disk) and Claude by `FakeFirstCutAnthropic`;
everything else - decoding with ffmpeg, features, op conversion, cut-point refinement, episode
creation, the HTTP API - is the real code.
"""
import json
import shutil
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app, show
from lacuna_app.episode import Episode
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.first_cut import (TOOL, ClaudeFirstCut, RuleFirstCut, system_prompt, to_s5_ops, windows)
from lacuna_app.importer import ImportError_, Importer, check_track
from lacuna_app.server import next_episode_id
from lacuna_app.store import Workspace

from .fake_claude import FakeFirstCutAnthropic
from .synth import fake_asr, write_recordings

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture
def rec(tmp_path):
    return write_recordings(tmp_path / "Riverside 下载")


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path / "ws").ensure()


def importer(ws, client=None, **kw):
    client = client or FakeFirstCutAnthropic()
    return Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=client), asr_backend=fake_asr, **kw)


def test_full_import_creates_reviewable_episode(ws, rec):
    fake = FakeFirstCutAnthropic()
    imp = importer(ws, fake)
    job = imp.start("EP002", "EP002 · 测试", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    job = imp.status("EP002")
    assert job["state"] == "done", job["error"]
    assert job["progress"] == 1.0
    assert set(job["steps"]) == {"models", "asr_L", "asr_P", "features", "first_cut", "episode"}
    assert "EP002" in ws.episode_ids()
    res = job["result"]
    # 4 valid ops (the unknown token is dropped) -> 4 edits; the content cut and the 1.8 s repeat need Leon
    assert res["edits"] == 4 and res["to_review"] == 2 and res["engine"] == "claude"

    meta = json.loads((ws.episode_dir("EP002") / "episode.json").read_text(encoding="utf-8"))
    assert meta["title"] == "EP002 · 测试" and meta["source"] == "import" and not meta["demo"]
    assert meta["raw_tracks"]["Leon"] == str(rec["Leon"].resolve())
    assert "合成对话" in meta["ai_notes"]
    # the import cache holds every step's output; only text and numbers went to "Claude"
    d = ws.root / "imports" / "EP002"
    for f in ("asr_L.json", "asr_P.json", "tokens.json", "features.json", "editor_input.md", "ops.json"):
        assert (d / f).is_file(), f
    req = fake.requests[0]
    assert req["model"] == "claude-sonnet-5-5" and req["tools"] == [TOOL]
    doc = req["system"][1]
    assert doc["cache_control"] == {"type": "ephemeral"} and "@0" in doc["text"]
    assert "{我|我嗯}" in doc["text"] or "{|嗯}" in doc["text"]      # SenseVoice disagreement shown
    usage = [json.loads(x) for x in (ws.root / "ai_usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert usage[-1]["kind"] == "first_cut" and usage[-1]["episode"] == "EP002" and usage[-1]["cost_usd"] > 0


def test_import_over_http_then_review(tmp_path, ws, rec):
    imp = importer(ws, FakeFirstCutAnthropic())
    c = TestClient(create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent"), importer=imp))
    assert c.get("/api/imports").json() == {"jobs": [], "next_id": "EP001"}
    r = c.post("/api/imports", json={"id": "EP002", "title": "第二集", "tracks": [str(rec["Leon"]), str(rec["Pei"])]})
    assert r.status_code == 200, r.text
    t = time.time()
    while (job := c.get("/api/imports/EP002").json()["job"])["state"] in ("queued", "running"):
        assert time.time() - t < 60
        time.sleep(0.05)
    assert job["state"] == "done", job["error"]
    lst = c.get("/api/imports").json()
    assert lst["next_id"] == "EP003" and lst["jobs"][0]["id"] == "EP002"
    ep = c.get("/api/episodes/EP002").json()
    assert ep["title"] == "第二集" and ep["pending_review"] == 2 and ep["duration"] < ep["raw_duration"] - 4
    assert ep["has_transcript"]
    # the imported episode behaves like any other: review, undo
    eid = ep["review"][0]
    after = c.post(f"/api/episodes/EP002/edits/{eid}/review", json={"action": "restore"}).json()
    assert after["duration"] > ep["duration"]
    assert c.post("/api/episodes/EP002/undo", json={}).json()["duration"] == ep["duration"]
    # same id again -> refused
    r = c.post("/api/imports", json={"id": "EP002", "tracks": [str(rec["Leon"]), str(rec["Pei"])]})
    assert r.status_code == 422 and "EP002" in r.json()["detail"]


def test_bad_requests(ws, rec, tmp_path):
    imp = importer(ws)
    c = TestClient(create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent"), importer=imp))
    post = lambda *t, **kw: c.post("/api/imports", json={"id": "EP009", "tracks": list(t)} | kw)  # noqa: E731
    leon, pei = str(rec["Leon"]), str(rec["Pei"])
    assert "找不到" in post(str(tmp_path / "nope.wav"), pei).json()["detail"]
    assert "Leon 和 Pei 选了同一个文件" in post(leon, leon).json()["detail"]
    (tmp_path / "notes.txt").write_text("x")
    assert "不是音频" in post(leon, str(tmp_path / "notes.txt")).json()["detail"]
    assert "要 2 条分轨" in post(leon).json()["detail"]
    assert post(leon, pei, id="../x").status_code == 422
    assert c.post("/api/imports/EP404/resume").status_code == 404


def test_api_failure_resumes_from_cache(ws, rec):
    fake = FakeFirstCutAnthropic(fail_windows={0})
    imp = importer(ws, fake)
    imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    job = imp.status("EP002")
    assert job["state"] == "error" and "AI 第一刀没做完" in job["error"] and "继续" in job["error"]
    assert "asr_P" in job["steps"] and "first_cut" not in job["steps"]
    assert "EP002" not in ws.episode_ids()

    def boom(*a):
        raise AssertionError("ASR must not run again")
    imp.asr_backend = boom
    fake.fail_windows.clear()
    imp.resume("EP002", wait=True)
    job = imp.status("EP002")
    assert job["state"] == "done", job["error"]
    assert "EP002" in ws.episode_ids()


def test_refusal_names_the_category_and_is_billed(ws, rec):
    fake = FakeFirstCutAnthropic(refuse_windows={0})          # every model refuses window 1
    imp = importer(ws, fake)
    imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    job = imp.status("EP002")
    assert job["state"] == "error" and "拒绝" in job["error"] and "reasoning_extraction" in job["error"]
    usage = [json.loads(x) for x in (ws.root / "ai_usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(usage) == 1 and usage[0]["refusal"] == "reasoning_extraction" and usage[0]["cost_usd"] > 0


def test_opus_refusal_falls_back_to_sonnet(ws, rec):
    fake = FakeFirstCutAnthropic(refuse_windows={0}, refuse_models={"claude-opus-5-5"})
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=fake, model="claude-opus-5-5"),
                   asr_backend=fake_asr)
    imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    job = imp.status("EP002")
    assert job["state"] == "done", job["error"]
    assert [r["model"] for r in fake.requests] == ["claude-opus-5-5", "claude-sonnet-5-5"]
    assert "betas" in fake.requests[0] and "betas" not in fake.requests[1]   # server fallback is Opus-only
    usage = [json.loads(x) for x in (ws.root / "ai_usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [u.get("refusal") for u in usage] == ["reasoning_extraction", None]
    ops = json.loads((ws.root / "imports" / "EP002" / "ops.json").read_text(encoding="utf-8"))
    assert "claude-sonnet-5-5" in ops["model"]


def test_first_cut_defaults_to_sonnet(monkeypatch):
    monkeypatch.delenv("LACUNA_FIRST_CUT_MODEL", raising=False)
    assert ClaudeFirstCut(client=object()).model == "claude-sonnet-5-5"
    monkeypatch.setenv("LACUNA_FIRST_CUT_MODEL", "claude-opus-5-5")
    assert ClaudeFirstCut(client=object()).model == "claude-opus-5-5"


def test_restart_marks_running_job_interrupted(ws, rec):
    imp = importer(ws)
    imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    job_file = ws.root / "imports" / "EP002" / "job.json"
    j = json.loads(job_file.read_text(encoding="utf-8"))
    j.update(state="running")
    job_file.write_text(json.dumps(j), encoding="utf-8")
    again = importer(ws)
    assert again.status("EP002")["state"] == "interrupted"
    again.forget("EP002")
    assert importer(ws).status() == []


def test_cancel_and_one_job_at_a_time(ws, rec):
    gate = threading.Event()

    def slow_asr(tag, x, progress):
        gate.wait(10)
        progress(0.5, "…")          # raises Cancelled once cancel was requested
        return fake_asr(tag, x, progress)
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()), asr_backend=slow_asr)
    imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])])
    with pytest.raises(Exception, match="正在导入"):
        imp.start("EP003", "", [str(rec["Leon"]), str(rec["Pei"])])
    imp.cancel("EP002")
    gate.set()
    t = time.time()
    while imp.status("EP002")["state"] in ("queued", "running"):
        assert time.time() - t < 30
        time.sleep(0.05)
    assert imp.status("EP002")["state"] == "cancelled"
    assert "EP002" not in ws.episode_ids()


def test_rules_fallback_without_claude(ws, rec):
    imp = Importer(ws, first_cut_factory=RuleFirstCut, asr_backend=fake_asr)
    imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    job = imp.status("EP002")
    assert job["state"] == "done", job["error"]
    assert job["result"]["engine"] == "rules" and job["result"]["edits"] > 0 and job["result"]["to_review"] == 0


def test_learned_rules_reach_the_prompt(ws, rec, monkeypatch):
    from lacuna_app import learning
    seen = []
    monkeypatch.setattr(learning, "prompt_rules", lambda w: "- Leon 恢复了所有关于猫的题外话：别剪猫。")
    monkeypatch.setattr(learning, "review_policy", lambda w: seen.append(w) or None)
    fake = FakeFirstCutAnthropic()
    importer(ws, fake).start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    assert "别剪猫" in fake.requests[0]["system"][0]["text"]
    assert seen                                      # review thresholds come from approved rules too


# ---------------------------------------------------------------- units

def test_windows_cover_the_episode():
    assert windows(300) == [(0.0, 300)]
    w = windows(4412)
    assert w[0] == (0.0, 600.0) and w[-1] == (4200.0, 4412) and len(w) == 8
    assert all(a2 == b1 for (_, b1), (a2, _) in zip(w, w[1:]))
    assert windows(4300)[-1] == (3600.0, 4300)        # a < 3 min tail joins the window before


def test_to_s5_ops_filters_to_window():
    from lacuna_app.ai_cut import TrackTokens
    toks = {"L": TrackTokens([{"id": "L000000", "t": "我", "start": 650.0, "end": 650.2}])}
    base = {"from": None, "to": None, "at": None, "target_s": None, "delta_s": None, "reason": "r", "confidence": 0.5,
            "category": "pause", "track": "both"}
    ops = [base | {"op": "tighten_pause", "at": "100.5", "target_s": 0.4},
           base | {"op": "tighten_pause", "at": "599.6", "target_s": 0.4},          # start just before b: kept
           base | {"op": "cut", "from": "L000000", "to": "L000000", "category": "disfluency"},
           base | {"op": "cut", "from": "L000999", "to": "L000999"},                 # unknown token: dropped
           base | {"op": "tighten_pause", "at": None, "target_s": 0.4}]             # malformed: dropped
    out = to_s5_ops(ops, toks, 0.0, 600.0, last=False)
    assert [o.get("at") for o in out] == [100.5, 599.6]
    out = to_s5_ops(ops, toks, 600.0, 1200.0, last=True)
    assert out == [{"op": "cut", "track": "both", "category": "disfluency", "reason": "r", "confidence": 0.5,
                    "from": "L000000", "to": "L000000"}]


def test_system_prompt_carries_the_rules():
    s = system_prompt()
    assert "Preserve the conversation" in s and "R2. HOST ASYMMETRY" in s and "submit_ops" in s
    assert "LEARNED FROM LEON'S LATER REVIEWS" not in s


def test_rule_first_cut_targets():
    t = RuleFirstCut.target
    assert t("L", "P", 0.5) == 0.2 and t("L", "P", 0.3) is None
    assert t("P", "L", 1.0) == 0.5 and t("P", "L", 0.7) is None
    assert t("L", "L", 0.8) is None and t("L", "L", 1.5) == 0.8 and t("P", "P", 3.0) == 1.0


def test_next_episode_id():
    assert next_episode_id(["EP001_AI", "EP001_demo"]) == "EP002"
    assert next_episode_id(["EP009", "EP_TEST_合成"]) == "EP010"
    assert next_episode_id([]) == "EP001"


def test_check_track(rec):
    info = check_track(rec["Leon"])
    assert info["duration"] == 60.0 and info["sample_rate"] == 16000

def _show(ws, *names):
    show.write_new(ws.root)
    return show.save(ws.root, {"show_name": "周末电影院", "hosts": [{"name": n} for n in names]})


@pytest.mark.parametrize("names", [("Ana", "Bo", "Cy"), ("Solo",)])
def test_import_with_the_shows_own_hosts(ws, rec, tmp_path, names):
    """Any number of hosts: one track each, named and tagged by the workspace's show."""
    prof = _show(ws, *names)
    tags = [h["tag"] for h in prof["hosts"]]
    words = {tags[0]: "L", **({tags[1]: "P"} if len(tags) > 1 else {})}
    paths = [rec["Leon"], rec["Pei"]][:len(tags)]
    if len(tags) == 3:
        third = tmp_path / "Cy.wav"
        shutil.copy(rec["Pei"], third)
        paths.append(third)

    def asr(tag, x, progress=lambda f, s: None):
        if tag in words:
            return fake_asr(words[tag], x, progress)
        return {"audio_s": round(len(x) / 16000, 3), "segments": []}       # a host who never speaks

    fake = FakeFirstCutAnthropic()
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=fake), asr_backend=asr)
    imp.start("EP002", "", [str(p) for p in paths], wait=True)
    job = imp.status("EP002")
    assert job["state"] == "done", job["error"]
    assert job["hosts"] == [[t, n] for t, n in zip(tags, names)]
    assert set(job["steps"]) == {"models", *(f"asr_{t}" for t in tags), "features", "first_cut", "episode"}
    ep = Episode(ws, "EP002")
    assert [t.name for t in ep.base.tracks] == list(names)
    assert set(ep.meta["raw_tracks"]) == set(names)
    # the editor document and the tool speak of these hosts, not Leon and Pei
    req = fake.requests[0]
    doc = req["system"][1]["text"]
    assert all(f"{t} 轨只有 {n} 的麦" in doc for t, n in zip(tags, names))
    assert "Leon" not in doc and "Pei" not in doc and "洛城" not in doc
    assert req["tools"][0]["input_schema"]["properties"]["ops"]["items"]["properties"]["track"]["enum"] == tags + ["both"]
    ep.close()


def test_wrong_number_of_tracks(ws, rec):
    _show(ws, "Ana", "Bo", "Cy")
    imp = importer(ws)
    with pytest.raises(ImportError_, match="要 3 条分轨"):
        imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])])


def test_at_most_four_tracks(ws, rec):
    _show(ws, "Ana", "Bo")
    imp = importer(ws)
    with pytest.raises(ImportError_, match="每个节目最多 4 位主持人，一集最多导入 4 条分轨，收到 5 条"):
        imp.start("EP002", "", [str(rec["Leon"])] * 5)
