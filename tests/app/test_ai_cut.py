"""AI first-cut ops -> app edits (lacuna_app.ai_cut), review ranking, and the AI episode end to end."""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from lacuna_app.ai_cut import TrackTokens, convert_ops, transcript_for
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.episode import APPLIED, RESTORED, Cuts, Episode, to_tl
from lacuna_app.review import needs_review, review_sort_key
from lacuna_app.server import create_app
from lacuna_app.store import Workspace
from tests.app.synth import AI_EPISODE, AI_TITLE, AI_WINDOW, make_ai_workspace

SR = 1000   # 1 sample per ms keeps expected values readable


def toks(tag, spans):
    """[(start, end, text)] -> token dicts with ids tag000000.."""
    return [{"id": f"{tag}{i:06d}", "t": w, "start": a, "end": b} for i, (a, b, w) in enumerate(spans)]


@pytest.fixture
def tokens():
    # Leon talks 0-2 s and 6-10 s; Pei talks 3-5 s, plus one word at 7.0-7.3 s under Leon
    L = toks("L", [(0.0, 0.5, "我"), (0.5, 1.0, "觉"), (1.0, 1.5, "得"), (1.5, 2.0, "吧"),
                   (6.0, 7.0, "然"), (7.0, 8.0, "后"), (8.0, 9.0, "那"), (9.0, 10.0, "个")])
    P = toks("P", [(3.0, 4.0, "对"), (4.0, 5.0, "啊"), (7.0, 7.3, "嗯")])
    return {"L": TrackTokens(L), "P": TrackTokens(P)}


def op(**kw):
    base = {"id": "op0001", "category": "disfluency", "reason": "口误重启，保留第二次", "confidence": 0.8}
    if "frm" in kw:
        kw["from"] = kw.pop("frm")
    return base | kw


def conv(tokens, *ops, **kw):
    return convert_ops({"episode": "T", "ops": list(ops)}, tokens, SR, **kw)


# ---------------------------------------------------------------- op conversion

def test_cut_both_maps_token_range_to_samples(tokens):
    edits, rep = conv(tokens, op(op="cut", track="both", frm="L000001", to="L000002", category="content",
                                 confidence=0.7))
    (e,) = edits
    assert e.ops == [{"op": "cut", "start": 500, "end": 1500, "tracks": None}]
    assert e.category == "content" and e.ai_category == "content" and e.op_id == "op0001"
    assert e.reason == "口误重启，保留第二次" and e.confidence == 0.7 and e.status == APPLIED
    assert e.source == "first_cut" and e.consequential          # content always goes to review
    assert e.speech_s == pytest.approx(1.0) and "觉得" in e.title
    assert "演示" not in e.title + e.reason
    assert rep.edits_out == 1 and not rep.skipped


def test_window_offsets_and_outside_ops(tokens):
    edits, rep = conv(tokens,
                      op(op="cut", track="both", frm="L000005", to="L000005"),      # 7.0-8.0 raw
                      op(id="op0002", op="cut", track="both", frm=0.2, to=0.4),    # before the window
                      w0=5.0, w1=9.5)
    assert [e.ops[0]["start"] for e in edits] == [2000] and edits[0].ops[0]["end"] == 3000
    assert rep.skipped == {"不在所选时间窗内": 1}


def test_single_track_cut_under_other_host_is_an_erase(tokens):
    # Pei's 嗯 at 7.0-7.3 sits under Leon's speech -> erase it on Pei's track only (room tone is
    # picked from the audio when the episode is created)
    edits, rep = conv(tokens, op(op="cut", track="P", frm="P000002", to="P000002", category="crosstalk"))
    assert edits[0].ops == [{"op": "erase", "track": "Pei", "start": 7000, "end": 7300}]
    assert edits[0].tracks == ["Pei"] and edits[0].category == "crosstalk"


def test_single_track_cut_with_other_track_silent_ripples(tokens):
    edits, rep = conv(tokens, op(op="cut", track="L", frm="L000002", to="L000003", category="repetition"))
    assert edits[0].ops == [{"op": "cut", "start": 1000, "end": 2000, "tracks": None}]
    assert edits[0].category == "filler" and edits[0].ai_category == "repetition"
    # noise on one track always stays on that track (never moves anything)
    edits, _ = conv(tokens, op(op="cut", track="L", frm=2.2, to=2.6, category="single_track_noise"))
    assert edits[0].ops[0]["op"] == "erase" and edits[0].category == "single_track"


def test_tighten_pause_cuts_excess_from_the_middle(tokens):
    # floor gap 5.0-6.0 (Pei ends 5.0, Leon resumes 6.0) -> keep 0.4 s, cut 0.6 s centred
    edits, _ = conv(tokens, op(op="tighten_pause", track="both", at="P000001", target_s=0.4,
                               category="pause", confidence=0.9))
    assert edits[0].ops == [{"op": "cut", "start": 5200, "end": 5800, "tracks": None}]
    assert edits[0].category == "pause" and not edits[0].consequential and edits[0].speech_s == 0
    assert "1.0s → 0.4s" in edits[0].title
    # raw-time 'at' works the same
    edits, _ = conv(tokens, op(op="tighten_pause", track="both", at=5.5, target_s=0.4, category="pause"))
    assert edits[0].ops[0]["start"] == 5200


def test_tighten_pause_skips(tokens):
    _, rep = conv(tokens,
                  op(id="a", op="tighten_pause", track="both", at=3.5, target_s=0.3, category="pause"),  # in a word
                  op(id="b", op="tighten_pause", track="both", at=5.5, target_s=2.0, category="pause"),  # short already
                  # Pei's pause 4.99-7.0 while Leon talks 6-7: needs per-track re-timing -> skipped, counted
                  op(id="c", op="tighten_pause", track="P", at="P000001", target_s=0.2, category="pause"))
    assert sum(rep.skipped.values()) == 3 and len(rep.warnings) == 3
    assert any("单轨停顿" in w for w in rep.warnings)


def test_slip_becomes_engine_slip(tokens):
    edits, _ = conv(tokens, op(op="slip", track="P", frm="P000002", to="P000002", delta_s=1.0,
                               category="interjection_move", confidence=0.4))
    assert edits[0].ops == [{"op": "slip", "track": "Pei", "start": 7000, "end": 7300, "delta": 1000}]
    assert edits[0].category == "interjection" and edits[0].consequential and edits[0].tracks == ["Pei"]


def test_keep_flag_is_a_suggestion_not_applied(tokens):
    edits, _ = conv(tokens, op(op="keep_flag", track="both", frm="L000004", to="L000005", suggested="cut",
                               category="content", confidence=0.5))
    assert edits[0].status == RESTORED and edits[0].consequential and edits[0].title.startswith("AI 建议")


def test_bad_ops_are_skipped_and_counted(tokens):
    edits, rep = conv(tokens,
                      op(id="x1", op="cut", track="both", frm="L999999", to="L000001"),
                      op(id="x2", op="cut", track="both", frm=3.0, to=2.0),
                      op(id="x3", op="explode", track="both"),
                      op(id="x4", op="cut", track="Q", frm=1.0, to=2.0),
                      op(id="x5", op="cut", track="both", frm=1.0, to=2.0, category="nonsense"),
                      op(id="ok", op="cut", track="both", frm=8.0, to=9.0))
    assert [e.op_id for e in edits] == ["ok"]
    assert rep.skipped["无法解析"] == 5 and rep.ops_in == 6 and rep.edits_out == 1


def test_overlapping_cuts_are_trimmed_or_dropped(tokens):
    edits, rep = conv(tokens,
                      op(id="a", op="cut", track="both", frm=6.0, to=8.0),
                      op(id="b", op="cut", track="both", frm=7.5, to=9.0),     # trimmed to 8.0-9.0
                      op(id="c", op="cut", track="both", frm=6.5, to=7.5))     # inside a -> dropped
    cuts = sorted(c for e in edits for c in e.cuts)
    assert cuts == [(6000, 8000), (8000, 9000)]
    assert rep.skipped["与其他删除重叠"] == 1
    assert [e.id for e in edits] == ["a0001", "a0002"]


def test_cut_points_snap_to_quiet_samples(tokens):
    """With audio available, token edges move to the nearby low-energy valley."""
    n = 12 * SR
    rng = np.random.default_rng(0)
    sig = {"Leon": 0.3 * rng.standard_normal(n), "Pei": 0.3 * rng.standard_normal(n)}
    for x in sig.values():
        x[1430:1470] = 1e-4 * rng.standard_normal(40)    # a quiet gap 70 ms before the token edge
        x[2030:2060] = 1e-4 * rng.standard_normal(30)

    def read(name, a, b):
        out = np.zeros(b - a)
        lo, hi = max(a, 0), min(b, n)
        out[lo - a:hi - a] = sig[name][lo:hi]
        return out
    edits, _ = conv(tokens, op(op="cut", track="both", frm="L000003", to="L000003"), read=read)
    a, b = edits[0].cuts[0]
    assert 1430 <= a < 1470 and 2030 <= b < 2060


def test_transcript_window():
    tt = {"L": TrackTokens(toks("L", [(1.0, 1.2, "a"), (5.0, 5.2, "b")]))}
    assert transcript_for(tt, 2.0, 9.0) == {"tracks": {"Leon": [[3.0, 3.2, "b"]]}}


# ---------------------------------------------------------------- review ranking

def test_needs_review_rule():
    assert needs_review("content", 0.95, 0.0)
    assert needs_review("filler", 0.39, 0.2)
    assert not needs_review("filler", 0.59, 0.2)
    assert needs_review("interjection", 0.9, 0.0)
    assert not needs_review("pause", 0.3, 0.0)
    assert needs_review("filler", 0.9, 1.6)
    assert not needs_review("filler", 0.9, 0.4)
    assert not needs_review("pause", 0.6, 0.0)


def test_review_order_is_timeline_order():
    ds = [{"id": "f", "category": "filler", "len": 9.0, "t": 1},
          {"id": "c1", "category": "content", "len": 2.0, "t": 5},
          {"id": "p", "category": "pause", "len": 3.0, "t": 2},
          {"id": "c3", "category": "content", "len": 1.0, "t": 0.5},
          {"id": "c2", "category": "content", "len": 6.0, "t": 9},
          {"id": "b", "category": "filler", "len": 1.0, "t": 5}]
    assert [d["id"] for d in sorted(ds, key=review_sort_key)] == ["c3", "f", "p", "b", "c1", "c2"]


def test_cuts_index_matches_linear_mapping():
    rnd = random.Random(3)
    pts = sorted(rnd.sample(range(100000), 400))
    cuts = [(pts[i], pts[i + 1]) for i in range(0, 400, 2)]
    fast = Cuts(cuts)
    for x in rnd.sample(range(100000), 500) + [c[0] for c in cuts] + [c[1] for c in cuts]:
        assert to_tl(x, fast) == to_tl(x, cuts)


# ---------------------------------------------------------------- AI episode end to end (synthetic audio)

@pytest.fixture
def ai_ws(tmp_path):
    return make_ai_workspace(tmp_path / "ws")


def test_ai_episode_summary_and_review(ai_ws):
    c = TestClient(create_app(ai_ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    s = c.get(f"/api/episodes/{AI_EPISODE}").json()
    assert s["title"] == AI_TITLE and s["demo"] is False and s["raw_offset_s"] == AI_WINDOW[0]
    by_id = {e["id"]: e for e in s["edits"]}
    review = [by_id[i] for i in s["review"]]
    ts = [e["t"] for e in review]
    assert ts == sorted(ts)                      # timeline order, from the first second
    assert sum(e["category"] == "content" for e in review) >= 2
    assert all(e["consequential"] for e in review)
    assert {r["category"] for r in s["routine"]} >= {"pause", "crosstalk", "filler"}
    assert all("演示" not in e["title"] + e["reason"] for e in s["edits"])
    assert all(e["op_id"] for e in s["edits"])
    # the out-of-window op was dropped; the slip edit is listed with its track
    slip = next(e for e in s["edits"] if e["category"] == "interjection")
    assert slip["tracks"] == ["Pei"] and slip["len"] == 0
    # restore the top content trim: duration grows by its length; undo brings it back
    top = max((e for e in review if e["category"] == "content"), key=lambda e: e["len"])
    r = c.post(f"/api/episodes/{AI_EPISODE}/edits/{top['id']}/review", json={"action": "restore"}).json()
    assert r["duration"] == pytest.approx(s["duration"] + top["len"], abs=1e-3)
    assert c.post(f"/api/episodes/{AI_EPISODE}/undo", json={}).json()["duration"] == pytest.approx(s["duration"])
    # the keep_flag suggestion can be applied
    flag = next(e for e in s["edits"] if e["status"] == "restored")
    r = c.post(f"/api/episodes/{AI_EPISODE}/edits/{flag['id']}/review", json={"action": "apply"}).json()
    assert r["duration"] == pytest.approx(s["duration"] - flag["len"], abs=1e-3)
    ab = c.get(f"/api/episodes/{AI_EPISODE}/edits/{slip['id']}/ab").json()
    assert c.get(ab["after"]["url"]).status_code == 200


def test_ai_episode_saved_recipe_replays_identically(ai_ws):
    """state.json's op log (applied sequentially by lacuna_core.Project) gives the same timeline
    as the episode's batch derivation."""
    import json
    from lacuna_core import Project
    ep = Episode(Workspace(ai_ws), AI_EPISODE)
    st = json.loads((ep.dir / "state.json").read_text(encoding="utf-8"))
    seq = Project.from_json(json.dumps(st["project"])).timeline
    fast = ep.timeline_for(ep.enabled)
    strip = lambda tl: [[(c.media_id, c.src_in, c.src_out, c.start) for c in t.clips] for t in tl.tracks]  # noqa: E731
    assert strip(seq) == strip(fast)
    assert any(o["op"]["op"] == "slip" for o in st["project"]["log"])


def test_make_ai_episode_cli_on_synthetic_audio(tmp_path):
    """The script finds Leon.wav / Pei.wav, writes a non-demo episode and never touches raw audio."""
    import hashlib
    import json
    from tests.app.synth import ai_ops_doc, tokens_doc, write_raw
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import make_ai_episode
    raw = tmp_path / "raw"
    write_raw(raw)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.glob("*.wav")}
    (tmp_path / "ops.json").write_text(json.dumps(ai_ops_doc(), ensure_ascii=False), encoding="utf-8")
    (tmp_path / "tokens.json").write_text(json.dumps(tokens_doc(), ensure_ascii=False), encoding="utf-8")
    make_ai_episode.main(["--workspace", str(tmp_path / "ws"), "--raw-dir", str(raw), "--episode", "EPX",
                          "--ops", str(tmp_path / "ops.json"), "--tokens", str(tmp_path / "tokens.json")])
    meta = json.loads((tmp_path / "ws/episodes/EPX/episode.json").read_text(encoding="utf-8"))
    assert meta["title"] == "EP001 · AI 第一刀" and meta["demo"] is False
    assert meta["ai_report"]["edits_out"] == 9      # full recording: the 'window' op is inside now
    ep = Episode(Workspace(tmp_path / "ws"), "EPX")
    assert ep.summary()["raw_duration"] == pytest.approx(60.0)
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.glob("*.wav")} == before
    with pytest.raises(SystemExit):
        make_ai_episode.main(["--workspace", str(tmp_path / "ws"), "--raw-dir", str(tmp_path)])


def test_batch_review_approve_all_is_one_undo_step(ai_ws, tmp_path):
    """「剩下的全部通过」signs off every pending edit as it stands (cuts stay cut, the unapplied AI suggestion
    stays unapplied), is one undo step, and persists across a restart."""
    c = TestClient(create_app(ai_ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    EP = f"/api/episodes/{AI_EPISODE}"
    s = c.get(EP).json()
    assert s["pending_review"] == len(s["review"]) == 4
    # Leon handles one by hand first; the batch only touches the rest
    first = s["review"][0]
    c.post(f"{EP}/edits/{first}/review", json={"action": "restore"})
    r = c.post(f"{EP}/review", json={"action": "approve", "playhead": 5.0}).json()
    assert r["changed"] == 3 and r["pending_review"] == 0
    assert r["undo_label"] == "全部通过（3 处）"
    by_id = {e["id"]: e for e in r["edits"]}
    before = {e["id"]: e for e in s["edits"]}
    assert by_id[first]["status"] == "restored"
    for i in s["review"][1:]:
        assert by_id[i]["approved"] and by_id[i]["status"] == before[i]["status"]
    assert r["duration"] == pytest.approx(s["duration"] + before[first]["len"], abs=1e-3)
    assert r["playhead"] == pytest.approx(5.0, abs=0.5)
    # nothing left: a second batch is a no-op and adds no undo step
    again = c.post(f"{EP}/review", json={"action": "approve"}).json()
    assert again["changed"] == 0 and again["undo_label"] == r["undo_label"]
    # survives a restart
    c2 = TestClient(create_app(ai_ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    assert c2.get(EP).json()["pending_review"] == 0
    # one undo brings back exactly the three
    u = c2.post(f"{EP}/undo", json={}).json()
    assert u["pending_review"] == 3 and u["undo_label"].startswith("恢复")


def test_batch_review_keep_restore_ids_and_errors(ai_ws):
    c = TestClient(create_app(ai_ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    EP = f"/api/episodes/{AI_EPISODE}"
    s = c.get(EP).json()
    content = [i for i in s["review"] if next(e for e in s["edits"] if e["id"] == i)["category"] == "content"]
    lens = {e["id"]: e["len"] for e in s["edits"]}
    applied = [i for i in content if next(e for e in s["edits"] if e["id"] == i)["status"] == "applied"]
    r = c.post(f"{EP}/review", json={"action": "restore", "ids": content}).json()
    assert r["undo_label"].startswith("全部恢复原话")
    assert all(e["status"] == "restored" and e["approved"] for e in r["edits"] if e["id"] in content)
    assert r["duration"] == pytest.approx(s["duration"] + sum(lens[i] for i in applied), abs=1e-3)
    r = c.post(f"{EP}/review", json={"action": "keep", "ids": content}).json()
    assert all(e["status"] == "applied" for e in r["edits"] if e["id"] in content)
    assert r["duration"] == pytest.approx(s["duration"] - sum(lens[i] for i in content if i not in applied), abs=1e-3)
    # bad action / unknown id are refused without changing anything
    assert c.post(f"{EP}/review", json={"action": "bogus"}).status_code == 422
    n_undo = c.get(EP).json()["undo_label"]
    assert c.post(f"{EP}/review", json={"action": "approve", "ids": ["nope"]}).status_code == 404
    assert c.get(EP).json()["undo_label"] == n_undo
