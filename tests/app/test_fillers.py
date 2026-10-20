"""English um / uh (decision `english-fillers`): detected fillers become transcript words, the episode lists
every filler, and 去掉 um / uh cuts the ones still heard as one undoable step."""
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import Episode, Workspace, create_app, fillers, show
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.first_cut import ClaudeFirstCut
from lacuna_app.importer import Importer

from .fake_claude import FakeFirstCutAnthropic
from .synth import EPISODE, SR, write_recordings
from .synth_en import EN_EPISODE, make_en_workspace
from .test_english import english_asr

EP = f"/api/episodes/{EN_EPISODE}"


@pytest.fixture
def ws(tmp_path):
    return make_en_workspace(tmp_path / "ws")


@pytest.fixture
def client(ws):
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))


def test_merge_adds_detected_fillers_as_words_in_time_order():
    t = fillers.merge({"tracks": {"Ana": [[0.0, 0.2, "so"], [1.0, 1.2, "yes"]], "Bo": []}},
                      [{"track": "A", "start": 0.5, "end": 0.7, "heard": "Uh.", "filler": True},
                       {"track": "A", "start": 2.0, "end": 2.2, "heard": "Yeah.", "filler": False},
                       {"track": "X", "start": 2.0, "end": 2.2, "heard": "Um", "filler": True}],
                      {"A": "Ana", "B": "Bo"})
    assert t["tracks"]["Ana"] == [[0.0, 0.2, "so"], [0.5, 0.7, "uh"], [1.0, 1.2, "yes"]]
    assert t["detected_fillers"] == 1


def test_listing_counts_every_filler_and_what_is_already_cut(client):
    r = client.get(f"{EP}/fillers").json()
    assert r["language"] == "en"
    assert [(i["track"], i["text"]) for i in r["items"]] == [
        ("Leon", "Um,"), ("Leon", "um"), ("Leon", "uh"), ("Pei", "uh"), ("Pei", "uh")]
    gone = [i for i in r["items"] if i["gone"]]
    assert [i["gone"] for i in gone] == ["e004"]          # the Pei "uh" inside the AI's pause cut
    assert r["left"] == 4 and r["cut"] == 1
    assert r["hosts"] == [{"name": "Leon", "left": 3, "cut": 0}, {"name": "Pei", "left": 1, "cut": 1}]
    # timeline seconds: after e001 (base 4.2-5.3 cut) everything moves 1.1 s earlier
    assert next(i for i in r["items"] if i["text"] == "uh" and i["track"] == "Leon")["t"] == pytest.approx(16.4 - 1.1, abs=1e-3)


def test_chinese_episode_has_no_fillers(tmp_path):
    from .synth import make_workspace
    c = TestClient(create_app(make_workspace(tmp_path / "zh"), MockEditorAdapter(), web_dist=Path("/nonexistent")))
    r = c.get(f"/api/episodes/{EPISODE}/fillers").json()
    assert r["items"] == [] and r["left"] == 0 and r["language"] == "zh"


def test_cut_all_is_one_undoable_step(client, ws):
    s0 = client.get(EP).json()
    s = client.post(f"{EP}/fillers/cut", json={"playhead": 20.0}).json()
    assert s["cut"] == 4
    assert s["undo_label"] == "去掉 um / uh（4 处）"
    new = [e for e in s["edits"] if e["category"] == "filler" and e["source"] == "manual"]
    assert len(new) == 4 and all(e["status"] == "applied" and e["approved"] for e in new)
    assert {e["title"] for e in new} >= {"去掉口头禅「Um,」· Leon", "去掉口头禅「uh」· Pei"}
    # three are cut from both tracks (the timeline closes up), the one under Pei's turn only silences Leon
    ep = Episode(Workspace(ws), EN_EPISODE)
    kinds = sorted((ep.edits[e["id"]].ops[0]["op"], ep.edits[e["id"]].ops[0].get("track")) for e in new)
    assert kinds == [("cut", None), ("cut", None), ("cut", None), ("erase", "Leon")]
    erase = next(ep.edits[e["id"]].ops[0] for e in new if ep.edits[e["id"]].ops[0]["op"] == "erase")
    assert 6.1 * SR <= erase["start"] <= 6.25 * SR and 6.45 * SR <= erase["end"] <= 6.6 * SR
    ep.close()
    assert s["duration"] < s0["duration"] - 0.5
    r = client.get(f"{EP}/fillers").json()
    assert r["left"] == 0 and r["cut"] == 5
    # nothing left: a second press changes nothing
    s2 = client.post(f"{EP}/fillers/cut", json={}).json()
    assert s2["cut"] == 0 and s2["undo_label"] == s["undo_label"]
    # one undo brings every one of them back
    s = client.post(f"{EP}/undo", json={}).json()
    assert s["duration"] == pytest.approx(s0["duration"], abs=1e-3)
    assert client.get(f"{EP}/fillers").json()["left"] == 4


def test_cut_one_host_and_restore_one_filler(client):
    s = client.post(f"{EP}/fillers/cut", json={"tracks": ["Pei"]}).json()
    assert s["cut"] == 1
    r = client.get(f"{EP}/fillers").json()
    assert r["hosts"][0] == {"name": "Leon", "left": 3, "cut": 0}
    # each filler is its own edit: restoring one (a click on the struck word) brings back only it
    s = client.post(f"{EP}/fillers/cut", json={"tracks": ["Leon"]}).json()
    eid = next(i["gone"] for i in client.get(f"{EP}/fillers").json()["items"] if i["text"] == "Um,")
    client.post(f"{EP}/edits/{eid}/review", json={"action": "restore"})
    r = client.get(f"{EP}/fillers").json()
    assert r["left"] == 1 and next(i for i in r["items"] if i["text"] == "Um,")["gone"] is None
    assert client.post(f"{EP}/fillers/cut", json={"tracks": ["Nobody"]}).status_code == 409


def test_cut_fillers_show_struck_in_the_transcript(client):
    client.post(f"{EP}/fillers/cut", json={})
    v = client.get(EP).json()["version"]
    lines = client.get(f"{EP}/manual/transcript", params={"t0": 0, "t1": 30, "v": v}).json()["lines"]
    words = [w for ln in lines for w in ln["words"] if w[0] in ("Um,", "uh", "um")]
    assert words and all(w[3] for w in words)


def test_history_label_in_english():
    from lacuna_app.episode import history_label
    from lacuna_app.i18n import reset_request_lang, set_request_lang
    tok = set_request_lang("en")
    try:
        assert history_label("去掉 um / uh（3 处）") == "Remove um / uh (3 fillers)"
    finally:
        reset_request_lang(tok)
        reset_request_lang(set_request_lang("zh"))      # the module-wide fallback is back to Chinese too


def test_backfill_merges_an_older_english_import(tmp_path):
    root = make_en_workspace(tmp_path / "ws")
    d = root / "episodes" / EN_EPISODE
    t = json.loads((d / "transcript.json").read_text(encoding="utf-8"))
    t["tracks"]["Leon"] = [w for w in t["tracks"]["Leon"] if w[2] not in ("uh", "um")]
    del t["detected_fillers"]
    (d / "transcript.json").write_text(json.dumps(t), encoding="utf-8")
    job = root / "imports" / EN_EPISODE
    job.mkdir(parents=True)
    (job / "job.json").write_text(json.dumps({"id": EN_EPISODE, "hosts": [["L", "Leon"], ["P", "Pei"]]}), encoding="utf-8")
    (job / "features.json").write_text(json.dumps({"sounds": [
        {"track": "L", "start": 16.4, "end": 16.75, "heard": "Uh", "filler": True}]}), encoding="utf-8")
    c = TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    r = c.get(f"{EP}/fillers").json()
    assert [i["text"] for i in r["items"] if i["track"] == "Leon"] == ["Um,", "uh"]
    assert json.loads((d / "transcript.json").read_text(encoding="utf-8"))["detected_fillers"] == 1
    assert c.get(f"{EP}/fillers").json()["left"] == r["left"]          # only once


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_english_import_writes_detected_fillers_into_the_transcript(tmp_path):
    ws = Workspace(tmp_path / "ws").ensure()
    rec = write_recordings(tmp_path / "rec")
    show.write_new(ws.root)
    show.save(ws.root, {"show_name": "Talk", "language": "en", "hosts": [{"name": "Ana"}, {"name": "Bo"}]})
    tags = [h["tag"] for h in show.load(ws.root)["hosts"]]
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()),
                   asr_backend=lambda tag, x, p=lambda f, s: None: english_asr({tags[0]: "L", tags[1]: "P"}[tag], x, p))
    imp.hear_backend = lambda audio: (lambda clips: ["Uh."] * len(clips))
    imp.start("EP003", "", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    assert imp.status("EP003")["state"] == "done"
    feats = json.loads((ws.root / "imports" / "EP003" / "features.json").read_text(encoding="utf-8"))
    n = sum(1 for s in feats["sounds"] if s.get("filler"))
    ep = Episode(ws, "EP003")
    assert ep.transcript["detected_fillers"] == n
    assert sum(1 for w in ep.transcript["tracks"]["Ana"] + ep.transcript["tracks"]["Bo"] if w[2] == "uh") == n
    ep.close()
