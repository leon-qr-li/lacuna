"""HTTP API of the media library and episode music, and export with music (phase 6a)."""
import json
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_core.master import measure

from .synth import EPISODE, SR, make_workspace, write_music
from .fake_claude import FakeCreditAnthropic as FakeAnthropic

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
EP = f"/api/episodes/{EPISODE}"


@pytest.fixture
def ws(tmp_path):
    return make_workspace(tmp_path / "ws")


@pytest.fixture
def fake():
    return FakeAnthropic({"title": "Main Title", "artist": None, "composer": "Hans Zimmer", "album": "Dune OST",
                          "film": "沙丘", "year": 2021, "confidence": 0.9, "note": "官方原声第一首"})


@pytest.fixture
def client(ws, fake):
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent"), credit_client=fake))


def test_library_flow(client, tmp_path, fake):
    src = write_music(tmp_path / "in" / "dune.wav", 6.0)
    r = client.post("/api/library/files", json={"path": str(src), "kind": "music", "note": "沙丘的主题曲"})
    assert r.status_code == 200, r.text
    aid = r.json()["asset"]["id"]
    lib = client.get("/api/library").json()
    assert lib["assets"][0]["credit_line"] == "dune" and lib["assets"][0]["kind_label"] == "配乐"
    out = client.post(f"/api/library/assets/{aid}/lookup").json()
    assert out["asset"]["credit"]["status"] == "suggested" and out["message"] == "官方原声第一首"
    assert out["asset"]["credit_line"] == "《沙丘》原声 · Hans Zimmer — “Main Title”"
    r = client.patch(f"/api/library/assets/{aid}", json={"confirm": True})
    assert r.json()["asset"]["credit"]["status"] == "confirmed"
    audio = client.get(f"/api/library/assets/{aid}/audio")
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"
    assert client.post("/api/library/files", json={"path": str(tmp_path / "nope.mp3")}).status_code == 422
    assert client.delete(f"/api/library/assets/{aid}").json() == {"ok": True}
    assert client.get("/api/library").json()["assets"] == []
    assert client.post("/api/library/assets/a_000/lookup").status_code == 404


def test_episode_music_and_mix_stream(client, tmp_path):
    jingle = client.post("/api/library/files", json={"path": str(write_music(tmp_path / "in" / "j.wav", 6.0)),
                                                      "kind": "jingle"}).json()["asset"]["id"]
    base = client.get(EP).json()["duration"]
    m = client.get(f"{EP}/music").json()
    assert m["placements"] == [] and m["duration"] == pytest.approx(base, abs=0.01) and m["credits"] == []
    m = client.post(f"{EP}/music", json={"asset_id": jingle, "role": "intro", "overlap_s": 2}).json()
    assert m["duration"] == pytest.approx(base + 4.0, abs=0.01)
    # interlude at 20 s *of the final mix* = 16 s of the voice cut (intro adds 4 s)
    m = client.post(f"{EP}/music", json={"asset_id": jingle, "role": "interlude", "at_s": 20.0, "overlap_s": 1}).json()
    mid = next(p for p in m["placements"] if p["role"] == "interlude")
    assert mid["voice_at_s"] == pytest.approx(16.0, abs=0.01) and mid["start_s"] == pytest.approx(19.0, abs=0.01)
    assert [c["role"] for c in m["credits"]] == ["intro", "interlude"]
    m = client.patch(f"{EP}/music/{mid['id']}", json={"gain_db": -3}).json()
    assert next(p for p in m["placements"] if p["id"] == mid["id"])["gain_db"] == -3
    assert client.post(f"{EP}/music", json={"asset_id": jingle, "role": "bed"}).status_code == 409
    pv = client.get(f"{EP}/music/{mid['id']}/preview")
    assert pv.status_code == 200 and pv.content[:4] == b"RIFF"
    r = client.get(m["mix_url"], headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    full = client.get(m["mix_url"])
    x, sr = sf.read(__import__("io").BytesIO(full.content))
    assert len(x) / sr == pytest.approx(m["duration"], abs=0.01)
    # series rule: save, then a fresh episode state is offered it
    m = client.post(f"{EP}/music/series/save", json={"name": "洛城二三事"}).json()
    assert m["series"] == "洛城二三事"
    for p in m["placements"]:
        m = client.delete(f"{EP}/music/{p['id']}").json()
    assert m["series_suggestion"]["name"] == "洛城二三事"
    m = client.post(f"{EP}/music/series/apply", json={"name": "洛城二三事"}).json()
    assert [p["role"] for p in m["placements"]] == ["intro"] and m["series_suggestion"] is None
    assert client.delete(f"{EP}/music/mu_nope").status_code == 404


def test_export_includes_music_and_credits(client, ws, tmp_path):
    song = client.post("/api/library/files", json={"path": str(write_music(tmp_path / "in" / "s.wav", 8.0)),
                                                    "kind": "music"}).json()["asset"]["id"]
    client.post(f"{EP}/music", json={"asset_id": song, "role": "intro", "overlap_s": 2})
    final = client.get(f"{EP}/music").json()["duration"]
    r = client.post(f"{EP}/export", json={"formats": ["wav"], "channels": 2})
    assert r.status_code == 200, r.text
    t = time.time()
    while (job := client.get(f"{EP}/export").json()["job"])["state"] == "running":
        assert time.time() - t < 120
        time.sleep(0.05)
    assert job["state"] == "done", job
    folder = Path(job["result"]["folder"])
    wav = folder / job["result"]["files"]["wav"]
    x, sr = sf.read(str(wav))
    assert x.shape[1] == 2 and len(x) / sr == pytest.approx(final, abs=0.05)
    # the head is the music alone: the two channels carry different notes (stereo kept)
    head = x[int(0.5 * sr):int(1.5 * sr)]
    spec_l = np.abs(np.fft.rfft(head[:, 0])); spec_r = np.abs(np.fft.rfft(head[:, 1]))
    f = np.fft.rfftfreq(len(head), 1 / sr)
    assert f[spec_l.argmax()] == pytest.approx(440, abs=3) and f[spec_r.argmax()] == pytest.approx(660, abs=3)
    lufs, tp = measure([x], sr, 2)
    assert abs(lufs + 16) < 0.6 and tp <= -0.9
    rec = json.loads((folder / job["result"]["files"]["json"]).read_text("utf-8")) if "json" in job["result"]["files"] \
        else json.loads(next(folder.glob("*.json")).read_text("utf-8"))
    assert [c["role"] for c in rec["music"]] == ["intro"]
