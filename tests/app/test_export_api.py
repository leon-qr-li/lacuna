import io
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

from .synth import EPISODE, SR, make_workspace

EP = f"/api/episodes/{EPISODE}"
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture
def ws(tmp_path):
    return make_workspace(tmp_path / "ws")


@pytest.fixture
def client(ws):
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))


def wait_done(client, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        job = client.get(f"{EP}/export").json()["job"]
        if job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("export did not finish")


def test_no_export_yet(client):
    assert client.get(f"{EP}/export").json() == {"job": None}


def test_export_wav_current_version(client, ws):
    summ = client.get(EP).json()
    r = client.post(f"{EP}/export", json={"formats": ["wav"]})
    assert r.status_code == 200 and r.json()["job"]["state"] == "running"
    job = wait_done(client)
    assert job["state"] == "done", job["error"]
    assert job["version"] == summ["version"] and job["progress"] == 1.0
    res = job["result"]
    assert set(res["files"]) == {"wav"}
    rep = res["report"]
    assert rep["output_lufs"] == pytest.approx(-16.0, abs=0.5)
    assert rep["output_true_peak_db"] <= -1.0
    # downloaded file = the edited version (same length as the timeline), stereo, mastered
    d = client.get(f"{EP}/exports/{res['files']['wav']}")
    assert d.status_code == 200
    y, sr = sf.read(io.BytesIO(d.content), always_2d=True)
    assert sr == SR and y.shape == (round(summ["duration"] * SR), 2)
    assert measure([y], sr, 2)[0] == pytest.approx(rep["output_lufs"], abs=0.05)
    # export record next to the audio, inside the workspace
    folder = Path(res["folder"])
    assert folder == ws / "exports" / EPISODE
    record = json.loads((folder / f"{job['basename']}.json").read_text(encoding="utf-8"))
    applied = sorted(e["id"] for e in summ["edits"] if e["status"] == "applied")
    assert record["applied_edits"] == applied and record["version"] == summ["version"]
    # source media untouched
    assert sorted(p.name for p in (ws / "episodes" / EPISODE / "raw").iterdir()) == ["Leon.wav", "Pei.wav"]


@needs_ffmpeg
def test_export_mp3_mono(client):
    client.post(f"{EP}/export", json={"formats": ["mp3"], "channels": 1, "mp3_kbps": 96})
    job = wait_done(client)
    assert job["state"] == "done", job["error"]
    assert set(job["result"]["files"]) == {"mp3"} and not job["result"]["errors"]
    assert job["result"]["mp3"]["kbps"] == 96
    d = client.get(f"{EP}/exports/{job['result']['files']['mp3']}")
    assert d.status_code == 200 and d.content[:3] in (b"ID3", b"\xff\xfb")


def test_export_rejects_bad_requests(client):
    assert client.post(f"{EP}/export", json={"formats": []}).status_code == 422
    assert client.post(f"{EP}/export", json={"formats": ["flac"]}).status_code == 422
    assert client.post(f"{EP}/export", json={"channels": 6}).status_code == 422
    assert client.post("/api/episodes/nope/export", json={}).status_code == 404


def test_one_export_at_a_time(client):
    client.app.state.exporter._running = "someone"
    assert client.post(f"{EP}/export", json={"formats": ["wav"]}).status_code == 409
    client.app.state.exporter._running = None


def test_export_file_paths_are_confined(client, ws):
    client.post(f"{EP}/export", json={"formats": ["wav"]})
    wait_done(client)
    (ws / "secret.txt").write_text("x")
    for name in ("..%2F..%2Fsecret.txt", "..%5C..%5Csecret.txt", "secret.txt", "x.exe", "nope.wav"):
        assert client.get(f"{EP}/exports/{name}").status_code == 404


def test_export_does_not_block_preview(client):
    client.post(f"{EP}/export", json={"formats": ["wav"]})
    r = client.get(EP)
    a = client.get(r.json()["audio_url"], headers={"Range": "bytes=0-9999"})
    assert a.status_code == 206
    wait_done(client)
