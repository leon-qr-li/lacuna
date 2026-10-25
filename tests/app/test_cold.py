"""Audio of episodes not used for 14 days moves to cloud storage and comes back when opened (lacuna_app/cold.py,
decision 2026-10-25-audio-cold-storage)."""
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import Workspace, create_app
from lacuna_app.cold import (COLD_AFTER_S, STORE_FILE, ColdStore, cold_paths, is_cold, last_used, referenced)
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.r2 import R2Error

from .synth import EPISODE, make_workspace

EP = f"/api/episodes/{EPISODE}"
DAY = 86400


class FakeBucket:
    """R2 in memory: key -> (bytes, sha256, modified)."""

    def __init__(self):
        self.objects: dict[str, tuple[bytes, str, float]] = {}
        self.puts = 0
        self.fail_put = False

    def exists(self, key, size, sha):
        o = self.objects.get(key)
        return o is not None and len(o[0]) == size and o[1] == sha

    def head(self, key):
        o = self.objects.get(key)
        return {"size": len(o[0]), "sha256": o[1]} if o else None

    def put_file(self, key, path, sha, progress=None):
        if self.fail_put:
            raise R2Error("down")
        data = Path(path).read_bytes()
        assert hashlib.sha256(data).hexdigest() == sha
        self.objects[key] = (data, sha, time.time())
        self.puts += 1

    def get_file(self, key, dest, sha, size, progress=None):
        data = self.objects[key][0]
        assert hashlib.sha256(data).hexdigest() == sha and len(data) == size
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(data)
        if progress:
            progress(size)

    def delete(self, key):
        self.objects.pop(key, None)

    def keys(self, prefix=""):
        return [{"key": k, "size": len(v[0]), "modified": v[2]} for k, v in self.objects.items() if k.startswith(prefix)]


class Clock:
    def __init__(self):
        self.t = time.time()

    def __call__(self):
        return self.t


def opened_once(root):
    """Open the episode once (the clipping-repair cache is made), then let 15 days pass."""
    c = TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    v = c.get(EP).json()["version"]
    return c.get(f"{EP}/audio/{v}.wav").content


@pytest.fixture
def setup(tmp_path):
    root = make_workspace(tmp_path / "ws")
    sound = opened_once(root)
    clock = Clock()
    clock.t = last_used(Workspace(root).episode_dir(EPISODE)) + COLD_AFTER_S + DAY
    bucket = FakeBucket()
    store = ColdStore(bucket, clock=clock)
    return root, store, bucket, clock, sound


def test_an_old_episode_moves_out_and_comes_back_on_open(setup):
    root, store, bucket, clock, sound = setup
    ws = Workspace(root)
    files = referenced(ws, EPISODE)
    assert files and all(f.startswith(f"episodes/{EPISODE}/raw/") for f in files)
    sizes = sum((root / f).stat().st_size for f in files)

    out = store.sweep([(ws, lambda _e: False)])
    assert out == {"moved": 1, "freed": sizes, "failed": 0}
    d = ws.episode_dir(EPISODE)
    assert is_cold(d) and not any((root / f).exists() for f in files)
    assert len(bucket.objects) == len(files)
    assert cold_paths(d) == {str((root / f).resolve()) for f in files}

    c = TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"), cold=store))
    # the list (and search, learning) still works without the audio, and nothing is "missing"
    assert any(e["id"] == EPISODE for e in c.get("/api/episodes").json()["episodes"])
    r = c.get(EP)
    for _ in range(100):
        if r.status_code != 423:
            break
        assert r.json()["restoring"]["failed"] is False and "取回" in r.json()["detail"]
        time.sleep(0.05)
        r = c.get(EP)
    assert r.status_code == 200 and r.json()["missing_sources"] == []
    assert not is_cold(d) and all((root / f).is_file() for f in files)
    assert c.get(f"{EP}/audio/{r.json()['version']}.wav").content == sound


def test_a_recent_or_busy_episode_stays(setup):
    root, store, bucket, clock, _ = setup
    ws = Workspace(root)
    assert store.sweep([(ws, lambda _e: True)])["moved"] == 0          # open in memory / a job runs
    clock.t -= 2 * DAY                                                    # used 13 days ago
    assert store.sweep([(ws, lambda _e: False)])["moved"] == 0
    assert not bucket.objects and not is_cold(ws.episode_dir(EPISODE))


def test_opened_while_uploading_stays_and_the_upload_is_reused(setup):
    root, store, bucket, clock, _ = setup
    ws = Workspace(root)
    calls = []

    def busy(_eid):
        calls.append(1)
        return len(calls) > 1           # free when the sweep looks, opened by the time it would delete

    assert store.sweep([(ws, busy)])["moved"] == 0
    assert not is_cold(ws.episode_dir(EPISODE)) and all((root / f).is_file() for f in referenced(ws, EPISODE))
    n = bucket.puts
    assert store.sweep([(ws, lambda _e: False)])["moved"] == 1
    assert bucket.puts == n            # already there: not sent again


def test_a_failed_upload_deletes_nothing(setup):
    root, store, bucket, clock, _ = setup
    ws = Workspace(root)
    bucket.fail_put = True
    assert store.sweep([(ws, lambda _e: False)]) == {"moved": 0, "freed": 0, "failed": 1}
    assert all((root / f).is_file() for f in referenced(ws, EPISODE))
    assert not (ws.episode_dir(EPISODE) / STORE_FILE).exists()


def test_never_opened_since_the_repair_cache_existed_stays(setup):
    root, store, bucket, clock, _ = setup
    ws = Workspace(root)
    shutil.rmtree(ws.episode_dir(EPISODE) / "declip")
    assert store.sweep([(ws, lambda _e: False)])["moved"] == 0


def test_staging_never_moves_audio_out(setup):
    root, _, bucket, clock, _ = setup
    reader = ColdStore(bucket, clock=clock, freezing=False)
    assert reader.sweep([(Workspace(root), lambda _e: False)])["moved"] == 0
    assert reader.gc([root]) == 0


def test_files_another_episode_plays_stay(setup):
    root, store, bucket, clock, _ = setup
    ws = Workspace(root)
    files = referenced(ws, EPISODE)
    assert store.freeze(ws, EPISODE, keep=files) == 0


def test_moved_out_again_after_a_restore_costs_no_upload(setup):
    root, store, bucket, clock, _ = setup
    ws = Workspace(root)
    store.sweep([(ws, lambda _e: False)])
    n = bucket.puts
    store.thaw(ws, EPISODE)
    d = ws.episode_dir(EPISODE)
    assert not is_cold(d)
    clock.t += COLD_AFTER_S + DAY
    assert store.sweep([(ws, lambda _e: False)])["moved"] == 1
    assert bucket.puts == n and is_cold(d)


def test_gc_deletes_only_what_nothing_refers_to(setup):
    root, store, bucket, clock, _ = setup
    ws = Workspace(root)
    store.sweep([(ws, lambda _e: False)])
    keep = set(bucket.objects)
    bucket.objects["audio/" + "0" * 64] = (b"x", "0" * 64, time.time() - 8 * DAY)   # an emptied show's file
    bucket.objects["audio/" + "1" * 64] = (b"y", "1" * 64, time.time())             # just uploaded
    clock.t = time.time()
    assert store.gc([root]) == 1
    assert set(bucket.objects) == keep | {"audio/" + "1" * 64}


def test_restore_failure_says_so_and_tries_again(setup):
    root, store, bucket, clock, _ = setup
    ws = Workspace(root)
    store.sweep([(ws, lambda _e: False)])
    saved = dict(bucket.objects)
    bucket.objects.clear()
    c = TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"), cold=store))
    r = c.get(EP)
    for _ in range(100):
        if r.json().get("restoring", {}).get("failed"):
            break
        time.sleep(0.05)
        r = c.get(EP)
    assert r.status_code == 423 and r.json()["restoring"]["failed"] is True
    bucket.objects.update(saved)
    clock.t += 60                       # asked again a while later: tried again
    for _ in range(100):
        r = c.get(EP)
        if r.status_code == 200:
            break
        time.sleep(0.05)
    assert r.status_code == 200


def test_busy_list_waits_for_audio_on_its_way(setup):
    root, store, bucket, clock, _ = setup
    store._moving.add("x")
    c = TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"), cold=store))
    assert any("音频" in b for b in c.get("/api/app").json()["busy"])
