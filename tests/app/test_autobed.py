"""自动铺底 (docs/decisions/2026-10-30-auto-bed.md): ticked songs fill the talk no other music covers, as a suggestion."""
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter

from .synth import EPISODE, make_workspace, write_music
from .fake_claude import FakeCreditAnthropic as FakeAnthropic
from .test_gaps import mix, rms, upload

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
EP = f"/api/episodes/{EPISODE}"


@pytest.fixture
def client(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent"), credit_client=FakeAnthropic({})))


def test_autobed_fills_the_free_talk_and_is_only_a_suggestion(client, tmp_path):
    intro = upload(client, write_music(tmp_path / "in" / "intro.wav", 6.0), "intro")
    a = upload(client, write_music(tmp_path / "in" / "bed_a.wav", 12.0), "bed")
    b = upload(client, write_music(tmp_path / "in" / "bed_b.wav", 9.0), "bed")
    client.post(f"{EP}/music", json={"asset_id": intro, "role": "intro"})
    v = client.get(f"{EP}/music/autobed").json()
    songs = {s["id"]: s for s in v["songs"]}
    assert songs[intro]["used_as"] == "片头" and songs[a]["used_as"] is None and songs[a]["kind"] == "bed"
    voice = client.get(EP).json()["duration"]
    assert v["stretches"] >= 1 and 0 < v["free_s"] < voice + 6.0
    assert "先勾" in client.post(f"{EP}/music/autobed", json={"asset_ids": []}).json()["message"]

    r = client.post(f"{EP}/music/autobed", json={"asset_ids": [a, b], "seed": 1}).json()
    d = r["draft"]
    assert d and d["source"] == "auto" and "铺满" in r["message"]
    assert client.get(f"{EP}/music").json()["placements"][0]["role"] == "intro"       # nothing applied yet
    beds = [p for p in d["placements"] if p["role"] == "bed"]
    assert len(beds) >= 2 and {p["asset_id"] for p in beds} == {a, b}
    beds.sort(key=lambda p: p["start_s"])
    intro_end = next(p for p in d["placements"] if p["role"] == "intro")["end_s"]
    assert beds[0]["start_s"] >= intro_end - 0.05                                   # not under the intro
    for x, y in zip(beds, beds[1:]):
        assert y["start_s"] == pytest.approx(x["end_s"] - 2.0, abs=0.05)            # 2 s crossfade
    assert beds[-1]["end_s"] <= d["duration"] + 0.01
    assert d["duration"] == pytest.approx(client.get(f"{EP}/music").json()["duration"], abs=0.01)   # same length

    # asking again replaces the earlier fill; accepting applies it and the bed is heard, low
    m = client.post(f"{EP}/music/draft/{d['id']}/accept").json()
    n = len([p for p in m["placements"] if p["role"] == "bed"])
    assert n == len(beds)
    r2 = client.post(f"{EP}/music/autobed", json={"asset_ids": [b], "seed": 2}).json()["draft"]
    assert {p["asset_id"] for p in r2["placements"] if p["role"] == "bed"} == {b}
    assert client.get(f"{EP}/music/autobed").json()["songs"][0]["in_bed"] in (True, False)
    x, sr = mix(client, m)
    assert len(x) / sr == pytest.approx(m["duration"], abs=0.01)


def test_autobed_leaves_gaps_and_interludes_alone(client, tmp_path):
    a = upload(client, write_music(tmp_path / "in" / "bed_a.wav", 30.0), "bed")
    client.post(f"{EP}/gaps", json={"voice_s": 16.0, "snap": False, "len_s": 8})
    d = client.post(f"{EP}/music/autobed", json={"asset_ids": [a], "seed": 3}).json()["draft"]
    gs = client.get(f"{EP}/music").json()["gaps"][0]
    g0, g1 = gs["final_s"], gs["final_s"] + 8.0
    for p in d["placements"]:
        assert p["end_s"] <= g0 + 0.05 or p["start_s"] >= g1 - 0.05                 # the empty gap stays silent
