"""Manual editing (decision `manual-editing`): cut / silence a selection, waveform tiles, transcript."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import Episode, Workspace, create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.learning import ADDED, decisions, learn

from .synth import EPISODE, SR, make_workspace

EP = f"/api/episodes/{EPISODE}"
# first cut on the synthetic episode: e001 cuts base 4.2-5.3 s, so base = timeline + 1.1 after 5.3


@pytest.fixture
def ws(tmp_path):
    return make_workspace(tmp_path / "ws")


@pytest.fixture
def client(ws):
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))


def summary(client):
    return client.get(EP).json()


def manual_edits(s):
    return [e for e in s["edits"] if e["source"] == "manual"]


def test_cut_both_tracks_is_an_undoable_manual_edit(client):
    s0 = summary(client)
    # timeline 17.0-18.0 = base 18.1-19.1: Leon is speaking
    s = client.post(f"{EP}/manual/cut", json={"start": 17.0, "end": 18.0, "playhead": 20.0}).json()
    assert s["duration"] == pytest.approx(s0["duration"] - 1.0, abs=0.13)     # boundaries snap <= 60 ms
    (e,) = manual_edits(s)
    assert e["id"] == s["edit_id"] and e["category"] == "manual" and e["status"] == "applied" and e["approved"]
    assert not e["consequential"] and e["tracks"] is None
    assert e["title"].startswith("手动删除") and "「" in e["title"]            # quotes the words it removes
    assert e["speech_s"] > 0.5
    assert s["playhead"] == pytest.approx(20.0 - (s0["duration"] - s["duration"]), abs=1e-3)
    assert s["can_undo"] and s["undo_label"].startswith("手动剪辑：")
    s = client.post(f"{EP}/undo", json={}).json()
    assert s["duration"] == pytest.approx(s0["duration"], abs=1e-3)
    s = client.post(f"{EP}/redo", json={}).json()
    assert len(manual_edits(s)) == 1
    # it can be restored like any other edit (the nearby-edits list offers 恢复)
    s = client.post(f"{EP}/edits/{e['id']}/review", json={"action": "restore"}).json()
    assert s["duration"] == pytest.approx(s0["duration"], abs=1e-3)


def test_one_track_silence_keeps_the_timeline(client, ws):
    s0 = summary(client)
    s = client.post(f"{EP}/manual/cut", json={"start": 5.0, "end": 6.0, "track": "Pei"}).json()
    assert s["duration"] == pytest.approx(s0["duration"], abs=1e-3)
    (e,) = manual_edits(s)
    assert e["tracks"] == ["Pei"] and e["room_tone"] and e["title"].startswith("Pei 单轨静音")
    ep = Episode(Workspace(ws), EPISODE)
    (op,) = ep.edits[e["id"]].ops
    assert op["op"] == "erase" and op["track"] == "Pei"
    assert op["start"] == pytest.approx(6.1 * SR, abs=0.07 * SR)


def test_selection_across_an_existing_cut_cuts_around_it(client, ws):
    # timeline 3.5-5.0 spans e001's cut point (base 4.2-5.3 is already gone)
    s = client.post(f"{EP}/manual/cut", json={"start": 3.5, "end": 5.0}).json()
    (e,) = manual_edits(s)
    ops = Episode(Workspace(ws), EPISODE).edits[e["id"]].ops
    assert [o["op"] for o in ops] == ["cut", "cut"]
    assert ops[0]["end"] == int(4.2 * SR) and ops[1]["start"] == int(5.3 * SR)
    # restoring the AI cut underneath still works: the manual pieces never overlap it
    s = client.post(f"{EP}/edits/e001/review", json={"action": "restore"}).json()
    assert next(x for x in s["edits"] if x["id"] == "e001")["status"] == "restored"


def test_silence_skips_what_that_host_already_lost(client, ws):
    # e002 lifts Pei base 11.0-11.4 (timeline 9.9-10.3)
    s = client.post(f"{EP}/manual/cut", json={"start": 9.5, "end": 10.8, "track": "Pei"}).json()
    ops = Episode(Workspace(ws), EPISODE).edits[s["edit_id"]].ops
    assert len(ops) == 2 and ops[0]["end"] <= int(11.0 * SR) and ops[1]["start"] >= int(11.4 * SR)


def test_refusals(client):
    s0 = summary(client)
    assert client.post(f"{EP}/manual/cut", json={"start": 5.0, "end": 5.02}).status_code == 409
    assert client.post(f"{EP}/manual/cut", json={"start": 5.0, "end": 4.0}).status_code == 422
    assert client.post(f"{EP}/manual/cut", json={"start": 5.0, "end": 6.0, "track": "Nobody"}).status_code == 409
    assert client.post("/api/episodes/nope/manual/cut", json={"start": 5.0, "end": 6.0}).status_code == 404
    s = summary(client)
    assert s["duration"] == s0["duration"] and not manual_edits(s) and not s["can_undo"]


def test_wave_tiles(client):
    s = summary(client)
    w = client.get(f"{EP}/manual/wave", params={"tile": 0, "v": s["version"]}).json()
    assert w["start"] == 0 and w["per_s"] == 100
    leon, pei = w["tracks"]
    assert leon["name"] == "Leon" and len(leon["peaks"]) == 1000 and len(pei["peaks"]) == 1000
    # Leon speaks 0.5-4.0 s, Pei is quiet until 5.5 s (base = timeline before the first cut)
    assert max(leon["peaks"][100:350]) > 30 and max(pei["peaks"][100:350]) < 10
    last = int(s["duration"] // 10)
    tail = client.get(f"{EP}/manual/wave", params={"tile": last, "v": s["version"]}).json()
    assert len(tail["tracks"][0]["peaks"]) == pytest.approx((s["duration"] - last * 10) * 100, abs=1)
    assert client.get(f"{EP}/manual/wave", params={"tile": last + 5}).json()["tracks"][0]["peaks"] == []
    assert client.get(f"{EP}/manual/wave", params={"tile": 0, "v": "nope"}).status_code == 404


def test_transcript_marks_cut_words_with_their_edit(client):
    s = summary(client)
    lines = client.get(f"{EP}/manual/transcript", params={"t0": 0, "t1": 12, "v": s["version"]}).json()["lines"]
    assert [ln["speaker"] for ln in lines][:2] == ["Leon", "Pei"]
    w0 = lines[0]["words"][0]
    assert w0[1] == pytest.approx(0.5) and isinstance(w0[0], str) and w0[3] is None
    # e002 lifted Pei's 11.0-11.4 (base): those words are there, marked, at their timeline place
    lifted = [w for ln in lines for w in ln["words"] if w[3] == "e002"]
    assert lifted and all(9.8 <= w[1] <= 10.4 for w in lifted)
    # a manual cut: its words stay listed, struck, at the cut point; the rest moves up
    s = client.post(f"{EP}/manual/cut", json={"start": 0.4, "end": 2.0}).json()
    lines = client.get(f"{EP}/manual/transcript", params={"t0": 0, "t1": 12, "v": s["version"]}).json()["lines"]
    cut = [w for w in lines[0]["words"] if w[3] == s["edit_id"]]
    assert len(cut) >= 4 and len({w[1] for w in cut}) == 1
    kept = [w for w in lines[0]["words"] if w[3] is None]
    assert kept[0][1] < 0.6
    assert client.get(f"{EP}/manual/transcript", params={"t0": 5, "t1": 1}).status_code == 422


def test_manual_cuts_are_learning_evidence_as_added_by_hand(client, ws):
    for a in (17.0, 19.0, 21.0):
        client.post(f"{EP}/manual/cut", json={"start": a, "end": a + 0.8})
    ep = Episode(Workspace(ws), EPISODE)
    ds = [d for d in decisions(ep) if d.source == "manual"]
    assert len(ds) == 3 and all(d.verdict == ADDED and d.kind == "manual" for d in ds)
    rules = [r for r in learn(ds) if r.kind == "missed"]
    assert rules and "手动" in rules[0].detail and "聊天" not in rules[0].detail and "manual" not in rules[0].title
