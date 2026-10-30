"""间隙 (docs/decisions/2026-10-30-edit-gaps.md): a silent stretch opened while editing; the voice edit stays as it was."""
import hashlib
import io
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.music import layout

from .synth import EPISODE, make_workspace, write_music
from .fake_claude import FakeCreditAnthropic as FakeAnthropic

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
EP = f"/api/episodes/{EPISODE}"


@pytest.fixture
def ws(tmp_path):
    return make_workspace(tmp_path / "ws")


@pytest.fixture
def client(ws):
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent"), credit_client=FakeAnthropic({})))


def upload(client, path, kind="interlude"):
    r = client.post("/api/library/upload", params={"name": Path(path).name, "kind": kind, "note": ""},
                    content=Path(path).read_bytes(), headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    return r.json()["asset"]["id"]


def episode_files(ws) -> dict[str, str]:
    """Everything of the episode but the gaps file: the voice edit must never change."""
    d = Path(ws) / "episodes" / EPISODE
    return {str(p.relative_to(d)): hashlib.sha1(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*"))
            if p.is_file() and not p.name.startswith("gaps.json")}


def mix(client, m):
    x, sr = sf.read(io.BytesIO(client.get(m["mix_url"]).content))
    return x, sr


def rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def test_gap_opens_silence_and_leaves_the_edit_alone(client, ws):
    before = client.get(f"{EP}/music").json()
    v, _ = mix(client, before)
    files = episode_files(ws)
    voice = client.get(EP).json()["duration"]
    r = client.post(f"{EP}/gaps", json={"voice_s": 16.0, "snap": False})
    assert r.status_code == 200, r.text
    g = r.json()["gaps"]
    assert len(g) == 1 and g[0]["len_s"] == 15.0 and g[0]["voice_s"] == pytest.approx(16.0, abs=0.01)
    assert g[0]["filled_by"] is None and r.json()["inserts"] == [[pytest.approx(16.0, abs=0.01), 15.0]]
    assert episode_files(ws) == files                       # edits, cuts, music.json: untouched
    assert client.get(EP).json()["duration"] == voice       # the voice cut is the same length
    m = client.get(f"{EP}/music").json()
    assert m["duration"] == pytest.approx(voice + 15.0, abs=0.01)
    assert m["gaps"][0]["final_s"] == pytest.approx(16.0, abs=0.01) and m["mix_version"] != before["mix_version"]
    x, sr = mix(client, m)
    assert len(x) / sr == pytest.approx(m["duration"], abs=0.01)
    assert rms(x[int(16.1 * sr):int(30.9 * sr)]) < 1e-4    # nobody talks in the gap
    # the talk after the gap is the talk that came after 16 s before, 15 s later
    assert np.allclose(x[int(32 * sr):int(36 * sr)], v[int(17 * sr):int(21 * sr)], atol=2e-4)
    # one gap per point; length change; out-of-range length refused
    assert client.post(f"{EP}/gaps", json={"voice_s": 16.0, "snap": False}).status_code == 409
    gid = g[0]["id"]
    assert client.patch(f"{EP}/gaps/{gid}", json={"len_s": 5}).json()["gaps"][0]["len_s"] == 5.0
    assert client.patch(f"{EP}/gaps/{gid}", json={"len_s": 0}).status_code == 422
    assert client.get(f"{EP}/music").json()["duration"] == pytest.approx(voice + 5.0, abs=0.01)
    # removing it gives back exactly the episode as it was
    assert client.delete(f"{EP}/gaps/{gid}").json()["gaps"] == []
    after = client.get(f"{EP}/music").json()
    assert after["mix_version"] == before["mix_version"] and after["export_key"] == before["export_key"]
    assert after["duration"] == before["duration"] and episode_files(ws) == files
    assert client.delete(f"{EP}/gaps/{gid}").status_code == 404


def test_gap_snaps_to_a_pause_and_follows_later_edits(client):
    g = client.post(f"{EP}/gaps", json={"voice_s": 16.0}).json()["gaps"][0]
    # snapped onto the middle of a pause between sentences (or left where it was when none is near)
    assert abs(g["voice_s"] - 16.0) <= 4.0
    # a cut before the gap moves it earlier on the voice cut, by the length of the cut
    ep = client.get(EP).json()
    r = client.post(f"{EP}/manual/cut", json={"start": 1.0, "end": 2.0, "track": None, "playhead": 0})
    assert r.status_code == 200, r.text
    g2 = client.get(f"{EP}/gaps").json()["gaps"][0]
    assert g2["voice_s"] == pytest.approx(g["voice_s"] - 1.0, abs=0.02)
    assert client.get(EP).json()["duration"] == pytest.approx(ep["duration"] - 1.0, abs=0.02)


def test_fill_gaps_with_interludes_keeps_the_gap_length(client, tmp_path):
    r = client.post(f"{EP}/music/gaps/auto").json()
    assert "还没有间隙" in r["message"] and r["draft"] is None
    client.post(f"{EP}/gaps", json={"voice_s": 16.0, "snap": False, "len_s": 8})
    r = client.post(f"{EP}/music/gaps/auto").json()
    assert "休息间隙" in r["message"] and r["draft"] is None              # no interlude music in the library
    song = upload(client, write_music(tmp_path / "in" / "long.wav", 20.0))
    upload(client, write_music(tmp_path / "in" / "intro.wav", 6.0), "intro")
    voice = client.get(EP).json()["duration"]
    r = client.post(f"{EP}/music/gaps/auto").json()
    d = r["draft"]
    assert d and len(d["changes"]) == 1 and "long" in d["changes"][0]["text"]
    assert d["duration"] == pytest.approx(voice + 8.0, abs=0.01)          # the gap keeps its length
    pv = client.get(f"{EP}/music/draft/{d['changes'][0]['pid']}/preview")
    assert pv.status_code == 200 and pv.content[:4] == b"RIFF"
    m = client.post(f"{EP}/music/draft/{d['id']}/accept").json()
    p = m["placements"][0]
    assert p["asset_id"] == song and p["in_gap"] and p["gap_id"] == m["gaps"][0]["id"]
    assert m["gaps"][0]["filled_by"] == p["id"] and m["gaps"][0]["music_name"]
    assert p["start_s"] == pytest.approx(16.0, abs=0.01) and p["end_s"] == pytest.approx(24.0, abs=0.01)
    assert m["duration"] == pytest.approx(voice + 8.0, abs=0.01) and m["inserts"] == [[pytest.approx(16.0, abs=0.01), 8.0]]
    x, sr = mix(client, m)
    assert rms(x[int(18 * sr):int(22 * sr)]) > 1e-3                      # music in the gap ...
    assert rms(x[int(23.9 * sr):int(24.0 * sr)]) < rms(x[int(19 * sr):int(21 * sr)]) / 4   # ... faded out at its end
    # nothing left to fill
    assert "已经有音乐" in client.post(f"{EP}/music/gaps/auto").json()["message"]
    # the music goes with its gap
    r = client.delete(f"{EP}/gaps/{m['gaps'][0]['id']}").json()
    assert r["removed_music"] == 1 and client.get(f"{EP}/music").json()["placements"] == []


def test_export_holds_the_gaps_it_started_with(client, ws):
    m0 = client.get(f"{EP}/music").json()
    client.post(f"{EP}/gaps", json={"voice_s": 16.0, "snap": False, "len_s": 3})
    m = client.get(f"{EP}/music").json()
    assert m["export_key"] != m0["export_key"]           # an export made before the gap is out of date
    job = client.post(f"{EP}/export", json={"formats": ["wav"], "channels": 1, "wait": True})
    assert job.status_code == 200, job.text


def test_layout_without_gaps_is_unchanged():
    a = {"id": "a1", "duration_s": 10.0}
    p = {"id": "p", "asset_id": "a1", "role": "interlude", "at_base": 1000, "status": "applied", "solo_s": 1.0, "ramp_s": 0.5}
    one = layout([p], {"a1": a}, 100, 5000, lambda b: b)
    two = layout([p], {"a1": a}, 100, 5000, lambda b: b, [])
    assert one.inserts == two.inserts == [(1000, 0, 200)] and one.gaps == []
    # a gap at the same point as an interlude: both open time, the interlude first
    three = layout([p], {"a1": a}, 100, 5000, lambda b: b, [{"id": "g", "at_base": 1000, "len_s": 3.0}])
    assert three.inserts == [(1000, 0, 200), (1000, 1, 300)] and three.gaps[0]["start"] == 1200
