"""Big files in pieces (lacuna_app/upload_parts.py): under Cloudflare's 100 MB body limit."""
import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app, upload_parts
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.store import Workspace

from .synth import write_recordings

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
OCTET = {"Content-Type": "application/octet-stream"}
ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def setup(tmp_path):
    ws = Workspace(tmp_path / "ws").ensure()
    rec = write_recordings(tmp_path / "Downloads")
    c = TestClient(create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    return ws, rec, c


def piece(c, data: bytes, offset: int, pid: str = ID):
    return c.post("/api/uploads/parts", params={"id": pid, "offset": offset}, content=data, headers=OCTET)


def send_in_pieces(c, data: bytes, size: int, pid: str = ID):
    for off in range(0, len(data), size):
        r = piece(c, data[off:off + size], off, pid)
        assert r.status_code == 200 and r.json()["size"] == off + len(data[off:off + size]), r.text


def test_track_sent_in_pieces_is_the_same_file(setup):
    ws, rec, c = setup
    data = rec["Leon"].read_bytes()
    size = len(data) // 3 + 1
    send_in_pieces(c, data[:size], size)
    # the connection dropped during the second piece: it is sent again from its offset
    assert piece(c, data[size:size + 100], size).status_code == 200
    for off in range(size, len(data), size):
        assert piece(c, data[off:off + size], off).status_code == 200
    r = c.post("/api/imports/tracks", params={"name": "Leon.wav", "part": ID}, headers=OCTET)
    assert r.status_code == 200, r.text
    t = r.json()["track"]
    assert Path(t["path"]).read_bytes() == data and t["duration"] > 10
    assert not upload_parts.part_path(ws, ID).exists()      # the pieces are gone once used


def test_library_asset_sent_in_pieces(setup):
    ws, rec, c = setup
    data = rec["Pei"].read_bytes()
    send_in_pieces(c, data, len(data) // 2 + 1)
    r = c.post("/api/library/upload", params={"name": "song.wav", "kind": "other", "part": ID}, headers=OCTET)
    assert r.status_code == 200, r.text
    assert not upload_parts.part_path(ws, ID).exists()


def test_bad_pieces_are_refused(setup, monkeypatch):
    ws, rec, c = setup
    assert piece(c, b"x", 0, pid="../../etc").status_code == 422
    assert piece(c, b"x", 5).status_code == 422                       # nothing started yet
    assert piece(c, b"abc", 0).status_code == 200
    assert piece(c, b"x", 10).status_code == 422                      # a piece is missing
    assert c.post("/api/uploads/parts", params={"id": ID}, content=b"x",
                  headers={"Content-Type": "text/plain"}).status_code == 415
    monkeypatch.setattr(upload_parts, "MAX_PIECE", 4)
    assert piece(c, b"12345", 0).status_code == 422
    r = c.post("/api/imports/tracks", params={"name": "x.wav", "part": "f" * 32}, headers=OCTET)
    assert r.status_code == 422 and not list((ws.root / "imported_tracks").glob("*/*"))


def test_unfinished_pieces_are_pruned_after_a_day(setup):
    ws, rec, c = setup
    assert piece(c, b"abc", 0).status_code == 200
    p = upload_parts.part_path(ws, ID)
    old = time.time() - upload_parts.STALE_S - 10
    os.utime(p, (old, old))
    upload_parts.prune(ws)
    assert not p.exists()
