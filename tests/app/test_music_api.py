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


def upload(client, path, kind="interlude", note="", name=None, ctype="application/octet-stream"):
    return client.post("/api/library/upload", params={"name": name or Path(path).name, "kind": kind, "note": note},
                       content=Path(path).read_bytes(), headers={"Content-Type": ctype})


def test_library_flow(client, tmp_path, fake):
    src = write_music(tmp_path / "in" / "dune.wav", 6.0)
    r = upload(client, src, note="沙丘的主题曲")
    assert r.status_code == 200, r.text
    aid = r.json()["asset"]["id"]
    lib = client.get("/api/library").json()
    assert lib["assets"][0]["credit_line"] == "dune" and lib["assets"][0]["kind_label"] == "休息间隙"
    out = client.post(f"/api/library/assets/{aid}/lookup").json()
    assert out["asset"]["credit"]["status"] == "suggested" and out["message"] == "官方原声第一首"
    assert out["asset"]["credit_line"] == "《沙丘》原声 · Hans Zimmer — “Main Title”"
    r = client.patch(f"/api/library/assets/{aid}", json={"confirm": True})
    assert r.json()["asset"]["credit"]["status"] == "confirmed"
    audio = client.get(f"/api/library/assets/{aid}/audio")
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"
    assert client.delete(f"/api/library/assets/{aid}").json() == {"ok": True}
    assert client.get("/api/library").json()["assets"] == []
    assert client.post("/api/library/assets/a_000/lookup").status_code == 404


def test_upload_is_safe(client, ws, tmp_path):
    lib = Path(ws) / "library"
    src = write_music(tmp_path / "in" / "theme.wav", 4.0)
    # only the base name counts: a path in the name can't escape the library folder
    r = upload(client, src, name="../../evil/主题曲.wav")
    assert r.status_code == 200, r.text
    a = r.json()["asset"]
    assert a["file"] == "music/主题曲.wav" and (lib / "music" / "主题曲.wav").is_file()
    assert not (Path(ws).parent / "evil").exists()
    # same music again under another name: one asset, no second copy on disk
    r = upload(client, src, name="copy.wav", note="再来一次")
    assert r.json()["duplicate"] is True and r.json()["asset"]["id"] == a["id"]
    assert not (lib / "music" / "copy.wav").exists()
    # same name, different music: kept side by side
    r = upload(client, write_music(tmp_path / "in" / "x.wav", 3.0), name="主题曲.wav", kind="intro")
    assert r.json()["asset"]["file"] == "jingles/主题曲.wav"
    r = upload(client, write_music(tmp_path / "in" / "y.wav", 2.0), name="主题曲.wav", kind="intro")
    assert r.json()["asset"]["file"] == "jingles/主题曲 (1).wav"
    # a form post (what another web page could send without a CORS preflight) is refused
    assert upload(client, src, ctype="text/plain").status_code == 415
    assert upload(client, src, name="notes.txt").status_code == 422
    assert upload(client, src, kind="video").status_code == 422
    bad = tmp_path / "broken.mp3"
    bad.write_bytes(b"not audio at all" * 100)
    assert upload(client, bad).status_code == 422
    assert not list(lib.rglob("broken*")) and not list(lib.rglob("*.part"))
    assert len(client.get("/api/library").json()["assets"]) == 3


def test_episode_music_and_mix_stream(client, tmp_path):
    jingle = upload(client, write_music(tmp_path / "in" / "j.wav", 6.0), "intro").json()["asset"]["id"]
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
    song = upload(client, write_music(tmp_path / "in" / "s.wav", 8.0)).json()["asset"]["id"]
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


def _wait_export(client):
    t = time.time()
    while (job := client.get(f"{EP}/export").json()["job"])["state"] == "running":
        assert time.time() - t < 120
        time.sleep(0.05)
    assert job["state"] == "done", job
    return job


def test_suggestions_chat_nudge_and_stale_export(ws, tmp_path):
    from .fake_music import FakeMusicAnthropic
    fake = FakeMusicAnthropic()
    client = TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent"), music_client=fake))
    for name, kind, secs in (("i.wav", "intro", 6.0), ("m.wav", "interlude", 5.0), ("o.wav", "outro", 7.0)):
        upload(client, write_music(tmp_path / "in" / name, secs), kind)
    # export first, with no music
    client.post(f"{EP}/export", json={"formats": ["wav"]})
    job = _wait_export(client)
    assert job["music_stale"] is False
    # place by use: a suggestion, not yet in the music (nor in the export)
    m = client.post(f"{EP}/music/auto").json()
    d = m["draft"]
    assert m["placements"] == [] and len(d["changes"]) == 3 and "试听" in m["message"]
    mid = next(p for p in d["placements"] if p["role"] == "interlude")
    pv = client.get(f"{EP}/music/draft/{mid['id']}/preview")
    assert pv.status_code == 200 and pv.content[:4] == b"RIFF"
    assert client.get(f"{EP}/music/draft/mu_nope/preview").status_code == 404
    assert client.get(f"{EP}/export").json()["job"]["music_stale"] is False
    assert client.post(f"{EP}/music/draft/move", json={"pid": "mu_nope", "voice_s": 3}).status_code == 404
    assert client.post(f"{EP}/music/draft/dr_nope/accept").status_code == 404
    m = client.post(f"{EP}/music/draft/{d['id']}/accept").json()
    assert sorted(p["role"] for p in m["placements"]) == ["interlude", "intro", "outro"] and m["draft"] is None
    # the export made before is now out of date, here and on the upload page
    assert client.get(f"{EP}/export").json()["job"]["music_stale"] is True
    assert client.get(f"{EP}/upload").json()["audio"]["stale"] is True
    # nudge: 1 s later on the final mix, exactly
    mid = next(p for p in m["placements"] if p["role"] == "interlude")
    m = client.patch(f"{EP}/music/{mid['id']}", json={"at_s": mid["at_s"] + 1}).json()
    moved = next(p for p in m["placements"] if p["id"] == mid["id"])
    assert moved["at_s"] == pytest.approx(mid["at_s"] + 1, abs=0.01)
    # talk: a suggestion that changes the level; then discarded
    m = client.post(f"{EP}/music/chat", json={"text": "间奏小 3 dB"}).json()
    assert m["draft"]["source"] == "chat" and "-3" in m["draft"]["changes"][0]["text"]
    assert next(p for p in m["placements"] if p["id"] == mid["id"])["gain_db"] == 0
    m = client.post(f"{EP}/music/draft/discard").json()
    assert m["draft"] is None
    # talk: "片尾去掉", accepted
    m = client.post(f"{EP}/music/chat", json={"text": "片尾去掉"}).json()
    m = client.post(f"{EP}/music/draft/{m['draft']['id']}/accept").json()
    assert "outro" not in {p["role"] for p in m["placements"]}
    assert client.post(f"{EP}/music/chat", json={"text": ""}).status_code == 422
    from lacuna_app.server import USAGE_LOG
    usage = [json.loads(x) for x in (ws / USAGE_LOG).read_text("utf-8").splitlines()]
    assert [u["kind"] for u in usage] == ["music_chat", "music_chat"] and len(fake.calls) == 2
    # a fresh export carries exactly the accepted music and is current again
    client.post(f"{EP}/export", json={"formats": ["wav"]})
    job = _wait_export(client)
    assert job["music_stale"] is False
    rec = json.loads(next(Path(job["result"]["folder"]).glob(f"{job['basename']}*.json")).read_text("utf-8"))
    assert [c["role"] for c in rec["music"]] == ["intro", "interlude"] and rec["music_version"] == job["music_version"]
