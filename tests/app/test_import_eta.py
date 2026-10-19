"""首检 #5: the import's 「预计还要」 comes from each step's real speed and this machine's past imports."""
import json
import shutil
import time

import pytest

from lacuna_app import import_eta
from lacuna_app.importer import STEPS
from lacuna_app.store import Workspace

NOW = 1_800_000_000.0


def job(step, step_progress, step_elapsed, minutes=40.5, done=(), **kw):
    before = sum(w for s, w in STEPS[:[s for s, _ in STEPS].index(step)])
    w = dict(STEPS)[step]
    return {"state": "running", "step": step, "progress": before + w * step_progress, "step_at": NOW - step_elapsed,
            "steps": {s: {"done": "x"} for s in done}, "tracks": {"L": {"duration": minutes * 60}, "P": {"duration": minutes * 60}},
            **kw}


ALL_BEFORE_CUT = ("models", "asr_L", "asr_P", "features")


def test_first_cut_quarter_done_is_not_two_minutes():
    """Leon's screenshot: 40:31 episode, AI first cut 1/4 windows done after the first window took ~5 min.
    The old whole-bar estimate said ~2 minutes; the rest really runs 3 windows in parallel ≈ one more window."""
    j = job("first_cut", 0.25, 300, done=ALL_BEFORE_CUT, step_first=[300.0, 0.25])
    left = import_eta.estimate(j, {}, now=NOW)
    assert 300 <= left <= 360          # one more window (~300 s) + building the review
    old = 611 * (1 - j["progress"]) / j["progress"]
    assert old < 150                   # what it used to say


def test_first_cut_before_any_window_uses_history():
    j = job("first_cut", 0.0, 60, done=ALL_BEFORE_CUT)
    assert import_eta.estimate(j, {"first_cut": 6.0, "episode": 0.5}, now=NOW) == round(6.0 * 40.5 - 60 + 0.5 * 40.5)


def test_steps_to_come_count_at_their_own_speed():
    # Leon's track half recognised in 100 s; Pei, features, first cut and review still to come
    j = job("asr_L", 0.5, 100, done=("models",))
    hist = {"asr": 3.0, "features": 0.4, "first_cut": 7.0, "episode": 0.5}
    left = import_eta.estimate(j, hist, now=NOW)
    rest = (3.0 + 0.4 + 7.0 + 0.5) * 40.5
    assert left == pytest.approx(100 + rest, abs=2)     # this step's own speed: 100 s more


def test_early_in_a_step_history_counts_more():
    j = job("asr_P", 0.04, 6, done=("models", "asr_L"))
    hist = {"asr": 3.0}
    left = import_eta.estimate(j, hist, now=NOW)
    by_rate, by_hist = 6 * 0.96 / 0.04, 3.0 * 40.5 - 6
    k = 0.04 / import_eta.TRUST_RATE_AT
    expected_rest = sum(import_eta.DEFAULT_RATE[s] * 40.5 for s in ("features", "first_cut", "episode"))
    assert left == pytest.approx(k * by_rate + (1 - k) * by_hist + expected_rest, abs=2)


def test_not_running_has_no_estimate():
    assert import_eta.estimate({"state": "done"}) is None


def test_history_from_past_imports(tmp_path):
    root = tmp_path / "imports"
    for i, (asr, cut) in enumerate([(200, 420), (300, 600), (250, 480)]):
        d = root / f"EP00{i}"
        d.mkdir(parents=True)
        steps = {"models": {"done": "2026-10-17T10:00:00+00:00"},
                 "asr_L": {"done": "2026-10-17T10:05:00+00:00", "seconds": asr},
                 "asr_P": {"done": "2026-10-17T10:10:00+00:00", "seconds": asr},
                 "features": {"done": "2026-10-17T10:11:00+00:00"},
                 # older imports only kept ASR times: the first cut is the gap since features
                 "first_cut": {"done": f"2026-10-17T10:{11 + cut // 60:02d}:00+00:00", "engine": "claude"}}
        (d / "job.json").write_text(json.dumps({"state": "done", "steps": steps,
                                                "tracks": {"L": {"duration": 3000}, "P": {"duration": 3000}}}))
    rules = root / "EP_rules"
    rules.mkdir()
    (rules / "job.json").write_text(json.dumps({"state": "done", "tracks": {"L": {"duration": 3000}},
                                                "steps": {"first_cut": {"done": "x", "engine": "rules", "seconds": 1}}}))
    h = import_eta.history(root)
    assert h["asr"] == pytest.approx(250 / 50)            # every track's ASR step together
    assert h["first_cut"] == pytest.approx(480 / 50)       # the no-AI fallback isn't a sample
    assert "episode" not in h
    assert import_eta.history(tmp_path / "missing") == {}


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_running_import_reports_time_left_and_step_times(tmp_path):
    from .fake_claude import FakeFirstCutAnthropic
    from .synth import write_recordings
    from .test_import import importer
    ws = Workspace(tmp_path / "ws").ensure()
    rec = write_recordings(tmp_path / "rec")
    imp = importer(ws, FakeFirstCutAnthropic(delay=1.0))
    imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])])
    seen = None
    for _ in range(300):
        j = imp.status("EP002")
        if j["state"] == "running" and j.get("step") == "first_cut":
            seen = j
            break
        time.sleep(0.05)
    assert seen is not None and isinstance(seen["eta_s"], int) and seen["eta_s"] >= 0
    for _ in range(300):
        if imp.status("EP002")["state"] == "done":
            break
        time.sleep(0.1)
    j = imp.status("EP002")
    assert j["state"] == "done" and "eta_s" not in j
    for s in ("asr_L", "asr_P", "features", "first_cut", "episode"):
        assert j["steps"][s]["seconds"] >= 0, s
    saved = json.loads((ws.root / "imports" / "EP002" / "job.json").read_text(encoding="utf-8"))
    assert saved["steps"]["first_cut"]["seconds"] >= 1.0
    assert import_eta.history(ws.root / "imports")["first_cut"] > 0      # the next import learns from this one
