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


def beds(m):
    return sorted((p for p in m["placements"] if p["role"] == "bed"), key=lambda p: p["start_s"])


def test_autobed_puts_each_song_in_once_at_random_and_applies_it(client, tmp_path):
    intro = upload(client, write_music(tmp_path / "in" / "intro.wav", 6.0), "intro")
    a = upload(client, write_music(tmp_path / "in" / "bed_a.wav", 8.0), "bed")
    b = upload(client, write_music(tmp_path / "in" / "bed_b.wav", 6.0), "bed")
    client.post(f"{EP}/music", json={"asset_id": intro, "role": "intro"})
    v = client.get(f"{EP}/music/autobed").json()
    songs = {s["id"]: s for s in v["songs"]}
    assert songs[intro]["used_as"] == "片头" and songs[a]["used_as"] is None and songs[a]["kind"] == "bed"
    assert v["stretches"] >= 1 and v["free_s"] > 14 and v["beds"] == 0
    assert "先勾" in client.post(f"{EP}/music/autobed", json={"asset_ids": []}).json()["message"]

    before = client.get(f"{EP}/music").json()
    r = client.post(f"{EP}/music/autobed", json={"asset_ids": [a, b], "seed": 1}).json()
    assert r["placed"] == 2 and "铺好了 2 首" in r["message"] and r["draft"] is None       # straight in, no 采用
    bs = beds(r)
    assert sorted(p["asset_id"] for p in bs) == sorted([a, b])                            # each song once
    intro_end = next(p for p in r["placements"] if p["role"] == "intro")["end_s"]
    assert bs[0]["start_s"] >= intro_end - 0.05                                         # not under the intro
    assert bs[0]["end_s"] <= bs[1]["start_s"] + 2.05                                    # no pile-up
    assert bs[-1]["end_s"] <= r["duration"] + 0.01 and r["duration"] == pytest.approx(before["duration"], abs=0.01)
    x, sr = mix(client, r)
    assert len(x) / sr == pytest.approx(r["duration"], abs=0.01)

    # again: a new spread replaces the old one; songs longer than the room: the extra ones stay out
    long = [upload(client, write_music(tmp_path / "in" / f"long{i}.wav", 40.0 + i), "bed") for i in range(3)]
    r = client.post(f"{EP}/music/autobed", json={"asset_ids": long, "seed": 2}).json()
    assert {p["asset_id"] for p in beds(r)} <= set(long) and 1 <= r["placed"] < 3 and "放不下" in r["message"]
    assert client.get(f"{EP}/music/autobed").json()["beds"] == r["placed"]

    # 取消所有铺底: every bed goes, the intro stays
    r = client.delete(f"{EP}/music/autobed").json()
    assert r["removed"] >= 1 and beds(r) == [] and [p["role"] for p in r["placements"]] == ["intro"]


def test_autobed_leaves_gaps_alone(client, tmp_path):
    a = upload(client, write_music(tmp_path / "in" / "bed_a.wav", 30.0), "bed")
    client.post(f"{EP}/gaps", json={"voice_s": 25.0, "snap": False, "len_s": 8})
    r = client.post(f"{EP}/music/autobed", json={"asset_ids": [a], "seed": 3}).json()
    g0 = r["gaps"][0]["final_s"]
    g1 = g0 + 8.0
    assert r["placed"] == 1
    for p in beds(r):
        assert p["end_s"] <= g0 + 0.05 or p["start_s"] >= g1 - 0.05                    # the empty gap stays silent


def test_cleanup_once_keeps_intro_and_outro(client, tmp_path, monkeypatch):
    from lacuna_app.routes import gap_bed_cleanup_once as c
    intro = upload(client, write_music(tmp_path / "in" / "intro.wav", 6.0), "intro")
    a = upload(client, write_music(tmp_path / "in" / "bed_a.wav", 8.0), "bed")
    client.post(f"{EP}/music", json={"asset_id": intro, "role": "intro"})
    client.post(f"{EP}/gaps", json={"voice_s": 25.0, "snap": False})
    client.post(f"{EP}/music/autobed", json={"asset_ids": [a], "seed": 1})
    root = Path(client.app.state.ctx.ws.root) if hasattr(client.app.state, "ctx") else None
    if root is None:
        pytest.skip("no ctx on the app")
    assert c.run(root) == [EPISODE]
    m = client.get(f"{EP}/music").json()
    assert [p["role"] for p in m["placements"]] == ["intro"] and m["gaps"] == []
    assert (root / "episodes" / EPISODE / "music.json.before-cleanup-20261030").exists()
    assert c.run(root) == []                                                            # nothing left to clean


def test_beds_placed_at_25_db_go_back_to_22(client, tmp_path):
    from lacuna_app.routes import bed_level_back_once as c
    a = upload(client, write_music(tmp_path / "in" / "bed_a.wav", 8.0), "bed")
    b = upload(client, write_music(tmp_path / "in" / "bed_b.wav", 9.0), "bed")
    client.post(f"{EP}/music", json={"asset_id": a, "role": "bed", "bg_db": 25})
    client.post(f"{EP}/music", json={"asset_id": b, "role": "bed", "bg_db": 18})
    root = Path(client.app.state.ctx.ws.root)
    assert c.run(root) == {EPISODE: 1}
    levels = {p["asset_id"]: p["bg_db"] for p in client.get(f"{EP}/music").json()["placements"]}
    assert levels == {a: 22.0, b: 18.0}                                                  # a hand-set level stays
    client.post(f"{EP}/music", json={"asset_id": a, "role": "bed"})
    assert all(p["bg_db"] in (22.0, 18.0) for p in client.get(f"{EP}/music").json()["placements"])
