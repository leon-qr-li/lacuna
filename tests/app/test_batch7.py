"""Batch 7 (visual walkthrough + copy sweep): the server-side pieces.

B10 the learning page names a source by its title; T3 the episode list says which episodes were exported;
B17 the version people see is the build's date; S1 the owner's server ↔ cloud storage speed test."""
from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app.appinfo import release_date
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.r2 import R2Error, file_sha256
from lacuna_app.server import create_app
from lacuna_app.speedtest import PREFIX, SpeedTest

from .synth import AI_EPISODE, EPISODE, make_ai_workspace, make_workspace


def app(ws):
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))


# ---------------------------------------------------------------- B10 / T3 / B17

def test_learning_page_gets_episode_titles(tmp_path):
    ws = make_ai_workspace(tmp_path / "ws")
    c = app(ws)
    title = c.get(f"/api/episodes/{AI_EPISODE}").json()["title"]
    ov = c.get("/api/learning").json()
    assert ov["titles"][AI_EPISODE] == title and title != AI_EPISODE


def test_episode_list_says_which_were_exported(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    c = app(ws)
    assert c.get("/api/episodes").json()["episodes"][0]["exported"] is False
    out = ws / "exports" / EPISODE
    out.mkdir(parents=True)
    (out / f"{EPISODE}_x.json").write_text("{}", encoding="utf-8")
    assert c.get("/api/episodes").json()["episodes"][0]["exported"] is True


def test_release_date_is_the_build_day(tmp_path):
    assert release_date(tmp_path) is None                     # a development checkout: no VERSION
    v = tmp_path / "VERSION"
    v.write_text("abc1234\n", encoding="utf-8")
    at = datetime(2026, 10, 25, 18, 0, tzinfo=timezone.utc).timestamp()
    os.utime(v, (at, at))
    assert release_date(tmp_path) == "2026.10.25"
    r = app(make_workspace(tmp_path / "ws")).get("/api/app").json()
    assert "release" in r


# ---------------------------------------------------------------- S1 speed test

class FakeBucket:
    def __init__(self, fail_put=False, fail_delete=False):
        self.objects: dict[str, Path] = {}
        self.store = None
        self.fail_put, self.fail_delete = fail_put, fail_delete
        self.deleted: list[str] = []

    def put_file(self, key, path, sha256, progress=None):
        if self.fail_put:
            raise R2Error("PUT -> 500")
        assert file_sha256(path) == sha256
        dest = self.store / key.replace("/", "_")
        shutil.copyfile(path, dest)
        self.objects[key] = dest

    def get_file(self, key, dest, sha256, size, progress=None):
        shutil.copyfile(self.objects[key], dest)
        assert file_sha256(dest) == sha256 and Path(dest).stat().st_size == size

    def delete(self, key):
        if self.fail_delete:
            raise R2Error("DELETE -> 500")
        self.deleted.append(key)
        self.objects.pop(key, None)

    def keys(self, prefix=""):
        return [{"key": k, "size": 0, "modified": 0} for k in self.objects if k.startswith(prefix)]


def bucket_at(tmp_path, **kw):
    b = FakeBucket(**kw)
    b.store = tmp_path / "bucket"
    b.store.mkdir()
    return b


def test_speed_test_round_trip_cleans_up(tmp_path):
    b = bucket_at(tmp_path)
    ticks = iter([0.0, 4.0, 10.0, 13.0])
    st = SpeedTest(lambda: b, tmp_path / "work", size=3 * 1024 * 1024 + 7, clock=lambda: next(ticks))
    out = st.start(background=False)
    assert out["state"] == "done" and out["upload_s"] == 4.0 and out["download_s"] == 3.0
    assert out["upload_mbps"] > 0 and out["download_mbps"] > out["upload_mbps"]
    assert b.objects == {} and len(b.deleted) == 1 and b.deleted[0].startswith(PREFIX)
    assert list((tmp_path / "work").iterdir()) == []          # no local test files left


def test_speed_test_failure_is_plain_and_leaves_nothing(tmp_path):
    b = bucket_at(tmp_path, fail_put=True)
    st = SpeedTest(lambda: b, tmp_path / "work", size=1024)
    out = st.start(background=False)
    assert out["state"] == "error" and "R2" not in out["error"] and "500" not in out["error"]
    assert list((tmp_path / "work").iterdir()) == [] and b.objects == {}


def test_speed_test_removes_a_leftover_object_first(tmp_path):
    b = bucket_at(tmp_path)
    left = b.store / "old"
    left.write_bytes(b"x")
    b.objects[f"{PREFIX}1.bin"] = left
    SpeedTest(lambda: b, tmp_path / "work", size=1024).start(background=False)
    assert f"{PREFIX}1.bin" in b.deleted and b.objects == {}


def test_speed_test_refuses_without_bucket_or_while_running(tmp_path):
    with pytest.raises(ValueError):
        SpeedTest(lambda: None, tmp_path / "work").start(background=False)
    b = bucket_at(tmp_path)
    st = SpeedTest(lambda: b, tmp_path / "work", size=1024)
    st.last = {"state": "running"}
    with pytest.raises(ValueError):
        st.start(background=False)


def test_speed_test_runs_in_the_background(tmp_path):
    b = bucket_at(tmp_path)
    st = SpeedTest(lambda: b, tmp_path / "work", size=1024)
    assert st.start()["state"] in ("running", "done")
    for _ in range(100):
        if st.view()["state"] == "done":
            break
        time.sleep(0.02)
    assert st.view()["state"] == "done"


def test_speed_test_in_the_admin_is_owner_only(tmp_path):
    from tests.app.test_admin import WRITE, join, setup, sign_in, turn_on_2fa
    app, main, _ = setup(tmp_path)
    owner = sign_in(app)
    assert owner.get("/api/admin/storage/speed").json() == {"state": "idle"}
    r = owner.post("/api/admin/storage/speed", headers=WRITE)      # this server has no cloud storage keys
    assert r.status_code == 409 and "R2" not in r.text
    join(app, main)
    turn_on_2fa(app, "sam@example.com")
    app.state.auth.update_user("leon@example.com", "sam@example.com", role="admin")
    sam = sign_in(app, "sam@example.com")
    assert sam.get("/api/admin/storage/speed").status_code == 403
    assert sam.post("/api/admin/storage/speed", headers=WRITE).status_code == 403
