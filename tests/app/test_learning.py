"""Phase 5 (D27): Leon's review decisions -> candidate rules -> (once approved) first-cut prompt + review policy."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import learning
from lacuna_app.ai_cut import TrackTokens, convert_ops
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.episode import Episode
from lacuna_app.learning import Decision, Learning, decisions, learn, prompt_rules, review_policy
from lacuna_app.review import ReviewPolicy, needs_review
from lacuna_app.server import create_app
from lacuna_app.store import Workspace
from tests.app.synth import AI_EPISODE, make_ai_workspace


def dec(verdict, kind="disfluency", host="Pei", how="single", conf=0.6, text="嗯就是", cons=False, i=[0], **kw):
    i[0] += 1
    return Decision(episode=kw.pop("episode", "EP"), edit_id=f"a{i[0]:04d}", source=kw.pop("source", "first_cut"),
                    kind=kind, category=kw.pop("category", "filler"), host=host, verdict=verdict, how=how,
                    confidence=conf, length_s=0.5, speech_s=0.4, text=text, reason="AI 理由",
                    raw=[100.0 + i[0], 100.5 + i[0]], consequential=cons)


def by_id(rules):
    return {r.id: r for r in rules}


# ---------------------------------------------------------------- learn(): pure rules from decisions

def test_no_decisions_no_rules():
    assert learn([]) == []


def test_restored_routine_kind_becomes_protect_rule_with_review_policy():
    ds = [dec("restored", text=f"呃就是{k}") for k in range(4)] + [dec("untouched", how="none") for _ in range(4)]
    r = by_id(learn(ds))["protect:disfluency:Pei"]
    assert r.kind == "protect" and "Pei的口误" in r.title
    assert r.evidence["restored"] == 4 and r.evidence["ai_cut"] == 8
    # 4 restores vs 4 untouched at weight 0.25 -> 0.8
    assert r.evidence["restore_rate"] == pytest.approx(0.8)
    assert r.policy == {"review": True}             # routine kind: also stop auto-applying it
    assert "Pei" in r.prompt and "呃就是0" in r.prompt and len(r.examples) == 4


def test_few_restores_are_not_a_rule():
    ds = [dec("restored"), dec("restored")] + [dec("kept") for _ in range(2)]
    assert not learn(ds)


def test_low_restore_rate_on_routine_kind_is_review_rule_not_protect():
    ds = [dec("restored") for _ in range(3)] + [dec("kept") for _ in range(12)]     # 3 / 15 = 0.2
    rules = by_id(learn(ds))
    assert "protect:disfluency:Pei" not in rules
    r = rules["review:disfluency:Pei"]
    assert r.policy == {"review": True} and r.prompt == ""      # review effort only, editor unchanged


def test_consequential_kind_all_kept_one_by_one_is_trusted():
    ds = [dec("kept", kind="content", host="Leon", cons=True, category="content") for _ in range(8)]
    r = by_id(learn(ds))["trust:content:Leon"]
    assert r.policy == {"review": False}
    # batch sign-offs are not considered decisions
    ds = [dec("kept", kind="content", host="Leon", cons=True, how="batch", category="content") for _ in range(20)]
    assert "trust:content:Leon" not in by_id(learn(ds))


def test_accepted_suggestions_make_timid_rule():
    ds = [dec("accepted", kind="content", host="Leon", category="content", cons=True) for _ in range(3)]
    ds.append(dec("declined", kind="content", host="Leon", category="content", cons=True))
    r = by_id(learn(ds))["timid:content:Leon"]
    assert r.evidence == {"suggested": 4, "accepted": 3}


def test_chat_additions_make_missed_rule():
    ds = [dec("added", kind="content", host="Leon", source="chat", text=t) for t in ("那个任天堂", "元宇宙吧")]
    r = by_id(learn(ds))["missed:content:Leon"]
    assert "任天堂" in r.detail and "元宇宙吧" in r.prompt


def test_content_taste_needs_both_kept_and_cut_examples():
    cut = [dec("kept", kind="content", host="Leon", category="content", cons=True, text=f"跑题{k}") for k in range(2)]
    kept = [dec("restored", kind="content", host="Leon", category="content", cons=True, text="这段很好笑")]
    r = by_id(learn(cut + kept))["taste:content:Leon"]
    assert "跑题0" in r.prompt and "这段很好笑" in r.prompt and "KEPT" in r.prompt
    assert not any(x.startswith("taste:") for x in by_id(learn(cut)))


def test_confidence_threshold_rule_only_with_signal():
    low = [dec("restored", conf=0.45) for _ in range(3)] + [dec("kept", conf=0.45) for _ in range(3)]
    high = [dec("kept", kind="repetition", conf=0.8) for _ in range(20)]
    r = by_id(learn(low + high))["threshold:confidence"]
    assert r.policy == {"confidence": 0.5}
    flat = [dec("restored", conf=c) for c in (0.45, 0.55, 0.65)] + [dec("kept", conf=0.45) for _ in range(30)]
    assert "threshold:confidence" not in by_id(learn(flat))


def test_learn_is_deterministic_and_digest_ignores_counts():
    ds = [dec("restored") for _ in range(4)]
    a, b = learn(ds), learn(list(ds))
    assert [r.id for r in a] == [r.id for r in b] and a[0].digest() == b[0].digest()


# ---------------------------------------------------------------- review policy

def test_needs_review_defaults_unchanged_and_policy_overrides():
    assert needs_review("filler", 0.6, 0.3) is False
    assert needs_review("content", 0.9, 0.0) is True
    pol = ReviewPolicy(by_kind={("disfluency", "Pei"): True, ("content", "Leon"): False}, confidence=0.5)
    assert needs_review("filler", 0.9, 0.3, kind="disfluency", host="Pei", policy=pol) is True
    assert needs_review("filler", 0.9, 0.3, kind="disfluency", host="Leon", policy=pol) is False
    assert needs_review("filler", 0.45, 0.3, kind="repetition", host="Leon", policy=pol) is True     # threshold
    assert needs_review("content", 0.5, 3.0, kind="content", host="Leon", policy=pol) is False        # trusted
    assert needs_review("content", 0.5, 6.0, kind="content", host="Leon", policy=pol) is True         # but long


def test_converter_applies_policy_per_host():
    L = [{"id": f"L{i:06d}", "t": "呃", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(4)]
    P = [{"id": "P000000", "t": "嗯", "start": 10.0, "end": 10.4}]
    toks = {"L": TrackTokens(L), "P": TrackTokens(P)}
    doc = {"ops": [{"id": "o1", "op": "cut", "track": "L", "from": "L000001", "to": "L000001",
                    "category": "disfluency", "reason": "", "confidence": 0.8},
                   {"id": "o2", "op": "cut", "track": "P", "from": "P000000", "to": "P000000",
                    "category": "disfluency", "reason": "", "confidence": 0.8}]}
    plain, _ = convert_ops(doc, toks, 1000)
    assert [e.consequential for e in plain] == [False, False]
    pol = ReviewPolicy(by_kind={("disfluency", "Pei"): True})
    edits, _ = convert_ops(doc, toks, 1000, policy=pol)
    assert {e.op_id: e.consequential for e in edits} == {"o1": False, "o2": True}


# ---------------------------------------------------------------- decisions() from a real episode

@pytest.fixture
def ai_ws(tmp_path):
    return make_ai_workspace(tmp_path / "ws")


def test_decisions_reflect_review_history(ai_ws):
    ws = Workspace(ai_ws)
    ep = Episode(ws, AI_EPISODE)
    first = [e for e in ep.edits.values() if e.source == "first_cut"]
    content = [e for e in first if e.category == "content" and e.status == "applied"][0]
    suggestion = [e for e in first if e.title.startswith("AI 建议")][0]
    filler = [e for e in first if e.ai_category == "disfluency"][0]
    ep.review(content.id, "restore")                    # Leon keeps the words the AI cut
    ep.review(filler.id, "keep")                        # one considered keep
    ep.review(suggestion.id, "apply")                   # applies the AI's suggestion himself
    ep.review_all("approve")                            # signs off everything else
    ds = {d.edit_id: d for d in decisions(ep)}
    assert ds[content.id].verdict == "restored" and ds[content.id].how == "single"
    assert ds[filler.id].verdict == "kept" and ds[filler.id].how == "single" and ds[filler.id].host == "Leon"
    assert ds[suggestion.id].verdict == "accepted"
    others = [d for d in ds.values() if d.edit_id not in (content.id, filler.id, suggestion.id)]
    assert {d.how for d in others if d.consequential} <= {"batch"}
    assert {d.verdict for d in others if not d.consequential} == {"untouched"}
    pause = next(d for d in ds.values() if d.kind == "pause")
    assert pause.host == "none" and pause.text == ""
    assert ds[content.id].text            # the removed words travel with the decision
    # undone actions leave no trace
    ep.undo(); ep.undo(); ep.undo(); ep.undo()
    assert {d.verdict for d in decisions(ep)} <= {"untouched", "declined"}
    ep.close()


def test_decisions_do_not_write_the_episode(ai_ws):
    ws = Workspace(ai_ws)
    state = ws.episode_dir(AI_EPISODE) / "state.json"
    before = state.read_bytes(), state.stat().st_mtime_ns
    ep = Episode(ws, AI_EPISODE)
    Learning(ws).overview([ep])
    assert (state.read_bytes(), state.stat().st_mtime_ns) == before
    ep.close()


# ---------------------------------------------------------------- store + approval + consumers

def fake_rules(monkeypatch, rules):
    monkeypatch.setattr(learning, "learn", lambda ds: [learning.Rule(**r) for r in rules])


RULE = dict(id="protect:disfluency:Pei", kind="protect", title="Pei的口误：AI 删多了，以后少删", detail="…",
            prompt="Cut Pei's disfluencies much less often.", key={"category": "disfluency", "host": "Pei"},
            evidence={"restored": 4}, examples=[], policy={"review": True})


def test_rules_need_approval_and_approved_snapshot_is_what_counts(tmp_path, monkeypatch):
    ws = Workspace(tmp_path).ensure()
    fake_rules(monkeypatch, [RULE])
    lr = Learning(ws)
    ov = lr.overview()
    assert ov["pending"] == 1 and ov["rules"][0]["state"] == "candidate"
    assert prompt_rules(ws) == "" and review_policy(ws) is None          # nothing applies before approval
    ov = lr.decide(RULE["id"], "approve")
    assert ov["pending"] == 0 and ov["rules"][0]["state"] == "approved"
    assert "Cut Pei's disfluencies much less often." in prompt_rules(ws)
    assert review_policy(ws).by_kind == {("disfluency", "Pei"): True}
    # more evidence, same wording: still approved, no update
    fake_rules(monkeypatch, [RULE | {"evidence": {"restored": 9}}])
    assert lr.overview()["rules"][0]["updated"] is False
    # new wording: shown as an update, but the approved version stays in force
    fake_rules(monkeypatch, [RULE | {"prompt": "Never cut Pei."}])
    ov = lr.overview()
    assert ov["rules"][0]["updated"] is True and ov["pending"] == 1
    assert "much less often" in prompt_rules(ws) and "Never cut Pei" not in prompt_rules(ws)
    # evidence gone: an approved rule stays (marked stale) until Leon drops it
    fake_rules(monkeypatch, [])
    ov = lr.overview()
    assert ov["rules"][0]["state"] == "approved" and ov["rules"][0]["stale"] is True
    lr.decide(RULE["id"], "reject")
    assert prompt_rules(ws) == "" and review_policy(ws) is None
    assert json.loads((ws.root / "learning" / "rules.json").read_text(encoding="utf-8"))["rules"][RULE["id"]]["state"] == "rejected"


def test_decide_unknown_rule_and_action(tmp_path, monkeypatch):
    ws = Workspace(tmp_path).ensure()
    fake_rules(monkeypatch, [RULE])
    with pytest.raises(KeyError):
        Learning(ws).decide("nope", "approve")
    with pytest.raises(ValueError):
        Learning(ws).decide(RULE["id"], "maybe")


def test_decision_snapshots_survive_episode_removal(ai_ws):
    ws = Workspace(ai_ws)
    ep = Episode(ws, AI_EPISODE)
    ep.review(next(e.id for e in ep.edits.values() if e.category == "content" and e.status == "applied"), "restore")
    Learning(ws).overview([ep])
    ep.close()
    snap = ws.root / "learning" / "decisions" / f"{AI_EPISODE}.json"
    assert snap.is_file()
    stats = Learning(ws).overview()["stats"]          # no episodes passed: read from snapshots
    assert stats["restored"] == 1 and stats["episodes"] == [AI_EPISODE]


# ---------------------------------------------------------------- API

def test_learning_api_round_trip(ai_ws, monkeypatch):
    c = TestClient(create_app(ai_ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    EP = f"/api/episodes/{AI_EPISODE}"
    s = c.get(EP).json()
    content = next(e["id"] for e in s["edits"] if e["category"] == "content" and e["status"] == "applied")
    c.post(f"{EP}/edits/{content}/review", json={"action": "restore"})
    ov = c.get("/api/learning").json()
    assert ov["stats"]["restored"] == 1 and ov["stats"]["episodes"] == [AI_EPISODE]
    fake_rules(monkeypatch, [RULE])
    ov = c.get("/api/learning").json()
    assert ov["pending"] == 1
    ov = c.post("/api/learning/rules", json={"id": RULE["id"], "action": "approve"}).json()
    assert ov["rules"][0]["state"] == "approved"
    assert c.post("/api/learning/rules", json={"id": "x", "action": "approve"}).status_code == 404
    assert c.post("/api/learning/rules", json={"id": RULE["id"], "action": "drop"}).status_code == 422


# ---------------------------------------------------------------- second source: Leon's own hand edit

def test_hand_edit_labels_ai_edits_and_finds_what_ai_missed(ai_ws):
    ws = Workspace(ai_ws)
    ep = Episode(ws, AI_EPISODE)
    by_op = {e.op_id: e for e in ep.edits.values()}
    removed = {"Leon": [(18.0, 20.3),      # he also cut the AI's repetition (op3)
                        (36.4, 37.8),      # and the passage the AI only suggested (op6)
                        (46.0, 50.0)],     # and a whole stretch the AI left in (only op8's stumble inside)
               "Pei": []}                  # he kept Pei's interjection (op2) and the content trim (op5) words
    ds = {d.edit_id: d for d in learning.hand_edit_decisions(ep, removed)}
    assert ds[by_op["op0003"].id].verdict == "kept" and ds[by_op["op0003"].id].how == "hand_edit"
    assert ds[by_op["op0006"].id].verdict == "accepted"
    assert ds[by_op["op0005"].id].verdict == "restored" and ds[by_op["op0005"].id].host == "Leon"
    assert ds[by_op["op0002"].id].verdict == "restored" and ds[by_op["op0002"].id].host == "Pei"
    assert ds[by_op["op0008"].id].verdict == "kept"
    assert not any(by_op[o].id in ds for o in ("op0001", "op0007"))          # pauses are not labelled per edit
    missed = [d for d in ds.values() if d.verdict == "added"]
    assert len(missed) == 1 and missed[0].host == "Leon" and missed[0].raw == [46.0, 50.0]
    assert all(d.episode == f"{AI_EPISODE}.hand_edit" for d in ds.values())
    # an alignment that cannot tell is skipped, not guessed
    unsure = learning.hand_edit_decisions(ep, removed, {"Leon": [(25.0, 31.0)]})
    assert by_op["op0005"].id not in {d.edit_id for d in unsure}
    ep.close()


def test_review_decision_beats_hand_edit_and_explicit_rule_beats_hand_edit():
    hand = [dec("restored", kind="content", host="Leon", how="hand_edit", episode="EP.hand_edit") for _ in range(1)]
    hand[0].edit_id = "a0001"
    review = dec("kept", kind="content", host="Leon", episode="EP")
    review.edit_id = "a0001"
    assert learning._merge(hand + [review]) == [review]
    # Pei's stumbles: his old edit kept them, but R002 says cut them more -> no "cut less" rule
    old = [dec("restored", host="Pei", how="hand_edit", episode="EP.hand_edit") for _ in range(10)]
    assert not [r for r in learn(old) if r.kind == "protect"]
    leon = [dec("restored", host="Leon", how="hand_edit", episode="EP.hand_edit") for _ in range(10)]
    assert [r.id for r in learn(leon) if r.kind == "protect"] == ["protect:disfluency:Leon"]


def test_hand_edit_script_writes_snapshot_and_page_uses_it(ai_ws, tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import learn_from_hand_edit as H
    align = tmp_path / "align.json"
    align.write_text(json.dumps({"removed_raw": {"Leon": [[18.0, 20.3]], "Pei": [], "both_tracks": []},
                                 "muted_track_spans": [{"track": "Leon", "raw": [26.5, 29.0],
                                                        "same_offset_heard_both_sides": False}]}), encoding="utf-8")
    ws = Workspace(ai_ws)
    state = ws.episode_dir(AI_EPISODE) / "state.json"
    before = state.read_bytes()
    ds = H.run(ws, AI_EPISODE, align)
    assert state.read_bytes() == before
    assert (ws.root / "learning" / "decisions" / f"{AI_EPISODE}.hand_edit.json").is_file()
    assert any(d.verdict == "kept" for d in ds)
    eps = Learning(ws).overview()["stats"]["episodes"]
    assert eps == [f"{AI_EPISODE}.hand_edit"]
    assert H.run(ws, AI_EPISODE, align, write=False) == ds
