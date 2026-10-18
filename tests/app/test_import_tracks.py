"""首检 #4: raw tracks dragged into the import form are copied into the workspace and imported from there."""
import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app, import_tracks
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.store import Workspace

from .test_import import importer
from .synth import write_recordings

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
OCTET = {"Content-Type": "application/octet-stream"}


@pytest.fixture
def setup(tmp_path):
    ws = Workspace(tmp_path / "ws").ensure()
    rec = write_recordings(tmp_path / "Downloads")
    imp = importer(ws)
    c = TestClient(create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent"), importer=imp))
    return ws, rec, imp, c


def upload(c, path: Path, name: str | None = None):
    return c.post("/api/imports/tracks", params={"name": name or path.name}, content=path.read_bytes(), headers=OCTET)


def test_dropped_tracks_import_and_go_with_the_episode(setup):
    ws, rec, imp, c = setup
    tracks = {}
    for who in ("Leon", "Pei"):
        r = upload(c, rec[who], f"{who} 原始音轨.wav")
        assert r.status_code == 200, r.text
        t = r.json()["track"]
        assert t["name"] == f"{who} 原始音轨.wav" and t["duration"] > 10 and t["size"] == rec[who].stat().st_size
        assert Path(t["path"]).parent.parent == (ws.root / "imported_tracks").resolve()
        tracks[who] = t["path"]
    r = c.post("/api/imports", json={"id": "EP002", "title": "", "leon": tracks["Leon"], "pei": tracks["Pei"]})
    assert r.status_code == 200, r.text
    for _ in range(300):
        if c.get("/api/imports/EP002").json()["job"]["state"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert c.get("/api/imports/EP002").json()["job"]["state"] == "done"
    # in use: never removed by the form, never pruned
    assert c.post("/api/imports/tracks/remove", json={"path": tracks["Leon"]}).json() == {"removed": False}
    assert import_tracks.prune(ws, imp.track_paths(), now=time.time() + 10 * 86400) == []
    # deleting the episode for good removes the app's copies; the originals stay
    c.post("/api/episodes/EP002/archive")
    r = c.delete("/api/episodes/EP002")
    assert r.status_code == 200 and len(r.json()["tracks"]) == 2
    assert not any(Path(p).exists() for p in tracks.values())
    assert rec["Leon"].is_file() and rec["Pei"].is_file()


def test_upload_checks(setup):
    ws, rec, _, c = setup
    assert c.post("/api/imports/tracks", params={"name": "a.wav"}, content=b"x").status_code == 415   # no preflight-free posts
    assert c.post("/api/imports/tracks", params={"name": "notes.txt"}, content=b"x", headers=OCTET).status_code == 422
    assert c.post("/api/imports/tracks", params={"name": "a.wav"}, content=b"", headers=OCTET).status_code == 422
    assert c.post("/api/imports/tracks", params={"name": "../../evil.wav"}, content=rec["Leon"].read_bytes(),
                  headers=OCTET).json()["track"]["name"] == "evil.wav"
    # failed uploads leave nothing behind; only the good one is there
    assert len(list((ws.root / "imported_tracks").iterdir())) == 1


def test_form_lets_go_of_a_copy(setup):
    ws, rec, _, c = setup
    p = upload(c, rec["Pei"]).json()["track"]["path"]
    assert c.post("/api/imports/tracks/remove", json={"path": p}).json() == {"removed": True}
    assert not Path(p).exists() and not Path(p).parent.exists()
    # anything outside imported_tracks/ is never removed
    assert c.post("/api/imports/tracks/remove", json={"path": str(rec["Leon"])}).json() == {"removed": False}
    assert rec["Leon"].is_file()


def test_abandoned_copies_pruned_after_a_day(setup):
    ws, rec, _, c = setup
    p = Path(upload(c, rec["Pei"]).json()["track"]["path"])
    assert import_tracks.prune(ws, []) == []                       # fresh: kept
    old = time.time() - 2 * 86400
    os.utime(p, (old, old))
    os.utime(p.parent, (old, old))
    assert import_tracks.prune(ws, []) == [p.parent.name]
    assert not p.exists()
