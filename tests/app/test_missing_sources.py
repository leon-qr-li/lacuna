"""An episode whose recordings are not on the server (moved from the desktop with C:\\ paths): clear
errors instead of 500s, and uploading the original files brings the sound back (lacuna_app/sources.py)."""
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import Episode, Workspace, create_app
from lacuna_app.editor import MockEditorAdapter

from .synth import EPISODE, make_workspace, write_music

EP = f"/api/episodes/{EPISODE}"
OCTET = {"Content-Type": "application/octet-stream"}


def client_for(root):
    return TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent")))


@pytest.fixture
def moved(tmp_path):
    """The real case: state.json points at the desktop's Downloads, the files stayed on the PC."""
    root = make_workspace(tmp_path / "ws")
    good = client_for(root)
    song = write_music(tmp_path / "in" / "jingle.wav", 4.0)
    aid = good.post("/api/library/upload", params={"name": "jingle.wav", "kind": "interlude"},
                    content=song.read_bytes(), headers=OCTET).json()["asset"]["id"]
    assert good.post(f"{EP}/music", json={"asset_id": aid, "role": "interlude", "at_s": 20.0}).status_code == 200
    v = good.get(EP).json()["version"]
    expected = good.get(f"{EP}/audio/{v}.wav").content
    pc = tmp_path / "pc"
    st_path = root / "episodes" / EPISODE / "state.json"
    st = json.loads(st_path.read_text(encoding="utf-8"))
    originals = {}
    for m in st["project"]["media"]:
        name = Path(m["path"]).name
        originals[name] = pc / name
        pc.mkdir(exist_ok=True)
        shutil.move(m["path"], pc / name)
        m["path"] = f"C:\\Users\\liqin\\Downloads\\{name}"
    st_path.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return root, originals, expected


def test_missing_recordings_are_listed_and_fail_clearly(moved):
    root, originals, _ = moved
    c = client_for(root)
    s = c.get(EP).json()             # the episode still opens
    miss = s["missing_sources"]
    assert sorted(m["file"] for m in miss) == sorted(originals)
    assert {m["track"] for m in miss} == {"Leon", "Pei"}
    for url in (f"{EP}/audio/{s['version']}.wav", f"{EP}/edits/e003/ab", f"{EP}/music"):
        r = c.get(url)
        assert r.status_code == 409, url
        assert "原始音轨" in r.json()["detail"]


def test_upload_brings_the_sound_back(moved):
    root, originals, expected = moved
    c = client_for(root)
    wrong = c.post(f"{EP}/sources", params={"name": "other.wav"}, content=b"RIFF not this one", headers=OCTET)
    assert wrong.status_code == 422
    names = sorted(originals)
    first = c.post(f"{EP}/sources", params={"name": names[0]}, content=originals[names[0]].read_bytes(), headers=OCTET)
    assert first.status_code == 200, first.text
    assert len(first.json()["episode"]["missing_sources"]) == 1
    # the second one in pieces, as the browser sends a big file
    data = originals[names[1]].read_bytes()
    pid = "ab" * 16
    half = len(data) // 2
    assert c.post("/api/uploads/parts", params={"id": pid, "offset": 0}, content=data[:half], headers=OCTET).status_code == 200
    assert c.post("/api/uploads/parts", params={"id": pid, "offset": half}, content=data[half:], headers=OCTET).status_code == 200
    second = c.post(f"{EP}/sources", params={"name": names[1], "part": pid}, content=b"", headers=OCTET)
    assert second.status_code == 200, second.text
    s = second.json()["episode"]
    assert s["missing_sources"] == []
    assert c.get(f"{EP}/audio/{s['version']}.wav").content == expected
    assert c.get(f"{EP}/edits/e003/ab").status_code == 200
    assert c.get(f"{EP}/music").status_code == 200
    # saved: a fresh load finds the files inside the episode folder
    ep = Episode(Workspace(root), EPISODE)
    assert ep.missing_sources() == []
    assert all(Path(m.path).parent == root / "episodes" / EPISODE / "media" for m in ep.media.values())
    assert c.post(f"{EP}/sources", params={"name": names[0]}, content=b"x", headers=OCTET).status_code == 409
