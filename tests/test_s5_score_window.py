"""S5 scorer: --min-raw/--max-raw window restricts AI + GT to the window; default unchanged."""
import importlib.util
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCORE = os.path.join(HERE, "..", "spikes", "s5_first_cut", "score.py")


@pytest.fixture(scope="module")
def S():
    spec = importlib.util.spec_from_file_location("s5_score", SCORE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _toks(tag, spans):
    out = []
    for i, (a, b) in enumerate(spans):
        nxt = spans[i + 1][0] - b if i + 1 < len(spans) else None
        out.append({"id": f"{tag}{i:06d}", "start": a, "end": b, "t": "字", "pause_after": nxt})
    return out


@pytest.fixture()
def files(tmp_path):
    # L speaks 0-4 and 10-14, P speaks 5-9 and 15-19; floor gaps between turns.
    tok = {"tracks": {"L": _toks("L", [(0, 1), (1, 2), (2, 3), (3, 4), (10, 11), (11, 12), (12, 13), (13, 14)]),
                      "P": _toks("P", [(5, 6), (6, 7), (7, 8), (8, 9), (15, 16), (16, 17), (17, 18), (18, 19)])}}
    gt = {"removed_raw": {"Leon": [[1.0, 2.0], [11.0, 12.0]], "Pei": [[11.0, 12.0]]},
          "muted_track_spans": [],
          "segments": [{"type": "raw", "leon_src": [0.0, 1.0], "pei_src": [0.0, 1.0], "final_start": 0.0, "final_end": 1.0},
                       {"type": "raw", "leon_src": [2.0, 11.0], "pei_src": [2.0, 11.0], "final_start": 1.0, "final_end": 10.0},
                       {"type": "raw", "leon_src": [12.0, 20.0], "pei_src": [12.0, 20.0], "final_start": 10.0, "final_end": 18.0}],
          "stats": {"raw_duration_s": 20.0, "raw_removed_s": {"Leon": 2.0, "Pei": 1.0},
                    "final_from_raw_s": 18.0, "final_duration_s": 18.0}}
    ops = {"episode": "T", "ops": [
        {"id": "a", "op": "cut", "track": "L", "from": "L000001", "to": "L000001", "category": "disfluency", "reason": "x", "confidence": 0.5},
        {"id": "b", "op": "cut", "track": "both", "from": 11.0, "to": 12.0, "category": "content", "reason": "x", "confidence": 0.5}]}
    p = {}
    for k, v in (("tok", tok), ("gt", gt), ("ops", ops)):
        p[k] = tmp_path / f"{k}.json"
        p[k].write_text(json.dumps(v))
    return p, ops


def test_default_scores_whole_episode(S, files):
    p, ops = files
    R = S.score(ops, str(p["gt"]), str(p["tok"]))
    assert "window_raw_s" not in R
    assert R["tracks"]["L"]["ai_removed_s"] == pytest.approx(2.0)
    assert R["tracks"]["L"]["gt_removed_s"] == pytest.approx(2.0)
    assert R["tracks"]["L"]["precision_s"] == pytest.approx(1.0)
    assert R["duration"]["raw_s"] == 20.0


def test_window_clips_ai_and_gt(S, files):
    p, ops = files
    R = S.score(ops, str(p["gt"]), str(p["tok"]), min_raw=10.0)
    assert R["window_raw_s"][0] == 10.0
    L = R["tracks"]["L"]
    # the 1-2 s removal (both AI and GT) is outside the window and must not count
    assert L["ai_removed_s"] == pytest.approx(1.0)
    assert L["gt_removed_s"] == pytest.approx(1.0)
    assert L["precision_s"] == pytest.approx(1.0) and L["recall_s"] == pytest.approx(1.0)
    d = R["duration"]
    assert d["raw_s"] == pytest.approx(10.0, abs=0.05)
    assert d["leon_est_by_formula_s"] == pytest.approx(9.0, abs=0.05)
    assert d["ai_est_s"] == pytest.approx(9.0, abs=0.05)


def test_window_excludes_out_of_window_misses(S, files):
    p, _ = files
    only_late = {"episode": "T", "ops": [
        {"id": "b", "op": "cut", "track": "both", "from": 11.0, "to": 12.0, "category": "content", "reason": "x", "confidence": 0.5}]}
    full = S.score(only_late, str(p["gt"]), str(p["tok"]))
    win = S.score(only_late, str(p["gt"]), str(p["tok"]), min_raw=10.0, max_raw=20.0)
    assert full["tracks"]["L"]["recall_s"] < 1.0          # misses GT 1-2 s
    assert win["tracks"]["L"]["recall_s"] == pytest.approx(1.0)
